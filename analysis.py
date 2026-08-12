"""Technical indicators, market-cycle detection, and price forecasting."""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- indicators
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values("date").reset_index(drop=True)

    df["SMA_20"] = df["close"].rolling(20).mean()
    df["SMA_50"] = df["close"].rolling(50).mean()
    df["EMA_12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["EMA_26"] = df["close"].ewm(span=26, adjust=False).mean()

    # RSI(14) — Wilder's smoothing
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # daily returns for volatility
    df["ret"] = df["close"].pct_change()
    return df


# ------------------------------------------------------------------- stats
def compute_stats(df: pd.DataFrame, recent_days: int = 90) -> dict:
    ath_idx = df["high"].idxmax()
    atl_idx = df["low"].idxmin()
    ath, atl = df.loc[ath_idx, "high"], df.loc[atl_idx, "low"]
    ath_dt, atl_dt = df.loc[ath_idx, "date"], df.loc[atl_idx, "date"]
    current = df["close"].iloc[-1]

    window = df.tail(recent_days)
    change_n = (current / window["close"].iloc[0] - 1) * 100 if len(window) > 1 else 0.0
    vol_ann = float(df["ret"].std() * np.sqrt(365) * 100) if df["ret"].notna().sum() > 10 else float("nan")

    rsi_now = float(df["RSI_14"].iloc[-1]) if not np.isnan(df["RSI_14"].iloc[-1]) else 50.0
    sma20 = float(df["SMA_20"].iloc[-1]) if not np.isnan(df["SMA_20"].iloc[-1]) else current
    sma50 = float(df["SMA_50"].iloc[-1]) if not np.isnan(df["SMA_50"].iloc[-1]) else current

    trend = "bullish" if (change_n > 0 and sma20 >= sma50) else "bearish"

    return {
        "current": current,
        "ath": float(ath),
        "ath_dt": ath_dt,
        "ath_date": ath_dt.strftime("%Y-%m-%d"),
        "atl": float(atl),
        "atl_dt": atl_dt,
        "atl_date": atl_dt.strftime("%Y-%m-%d"),
        "pct_from_ath": float((current / ath - 1) * 100) if ath else 0.0,
        "pct_above_atl": float((current / atl - 1) * 100) if atl else 0.0,
        "change_90d": float(change_n),
        "vol_ann_pct": vol_ann,
        "rsi": rsi_now,
        "sma20": sma20,
        "sma50": sma50,
        "trend": trend,
    }


# ----------------------------------------------------- bull/bear run finder
def detect_cycles(df: pd.DataFrame, threshold: float = 0.15, min_move: float = 0.15) -> list[dict]:
    """
    Zig-zag swing detection:
      - direction flips only after price retraces `threshold` from the
        running extreme. A confirmed run of magnitude >= `min_move`
        is labelled bull (up) or bear (down).
    """
    prices = df.set_index("date")["close"].dropna()
    if len(prices) < 20:
        return []

    dates = prices.index.to_list()
    vals = prices.to_numpy()

    cycles: list[dict] = []
    last_pivot_idx = 0
    last_pivot_val = vals[0]
    run_high_idx, run_high = 0, vals[0]
    run_low_idx, run_low = 0, vals[0]
    direction = 0  # +1 bull, -1 bear, 0 undefined

    for i in range(1, len(vals)):
        v = vals[i]
        if direction >= 0 and v > run_high:
            run_high_idx, run_high = i, v
        if direction <= 0 and v < run_low:
            run_low_idx, run_low = i, v

        if direction >= 0 and v <= run_high * (1 - threshold):
            # bull leg ended at run_high
            move = run_high / last_pivot_val - 1
            if abs(move) >= min_move:
                cycles.append(_mk_cycle("bull", dates, last_pivot_idx, run_high_idx, vals))
            last_pivot_idx, last_pivot_val = run_high_idx, run_high
            run_low_idx, run_low = i, v
            direction = -1
        elif direction <= 0 and v >= run_low * (1 + threshold):
            move = run_low / last_pivot_val - 1
            if abs(move) >= min_move:
                cycles.append(_mk_cycle("bear", dates, last_pivot_idx, run_low_idx, vals))
            last_pivot_idx, last_pivot_val = run_low_idx, run_low
            run_high_idx, run_high = i, v
            direction = 1

    # trailing open leg
    end_idx = len(vals) - 1
    if direction == 1:
        move = vals[end_idx] / last_pivot_val - 1
        if abs(move) >= min_move:
            cycles.append(_mk_cycle("bull", dates, last_pivot_idx, end_idx, vals))
    elif direction == -1:
        move = vals[end_idx] / last_pivot_val - 1
        if abs(move) >= min_move:
            cycles.append(_mk_cycle("bear", dates, last_pivot_idx, end_idx, vals))

    return cycles


def _mk_cycle(kind, dates, i0, i1, vals) -> dict:
    p0, p1 = vals[i0], vals[i1]
    return {
        "type": kind,
        "start": dates[i0],
        "end": dates[i1],
        "start_price": float(p0),
        "end_price": float(p1),
        "duration_days": int((dates[i1] - dates[i0]).days),
        "return_pct": float((p1 / p0 - 1) * 100),
    }


# ---------------------------------------------------------------- forecasting
def forecast_prices(df: pd.DataFrame, horizon: int, degree: int = 2):
    """
    Polynomial trend fit on log-prices + light RSI mean-reversion tilt.
    Returns (forecast, upper, lower) numpy arrays of length `horizon`.
    """
    close = df["close"].dropna().to_numpy(dtype=float)
    n = len(close)
    x = np.arange(n, dtype=float)

    log_p = np.log(close)
    coeffs = np.polyfit(x, log_p, deg=degree)
    poly = np.poly1d(coeffs)

    xf = np.arange(n, n + horizon, dtype=float)
    fc = np.exp(poly(xf))

    # RSI tilt: overbought -> dampen, oversold -> lift
    rsi = float(df["RSI_14"].iloc[-1]) if "RSI_14" in df and not np.isnan(df["RSI_14"].iloc[-1]) else 50.0
    tilt = np.clip((50.0 - rsi) / 50.0, -1.0, 1.0) * 0.004  # up to +-0.4%/day
    days = np.arange(1, horizon + 1, dtype=float)
    fc = fc * np.exp(tilt * days)

    # residual-based 95% band, widened by daily volatility
    resid = log_p - poly(x)
    sigma = float(np.std(resid)) if len(resid) > 5 else 0.05
    daily_vol = float(np.nanstd(np.diff(np.log(close[-60:])))) if n > 65 else 0.04
    width = 1.96 * np.sqrt(sigma**2 + (daily_vol * np.sqrt(days)) ** 2)
    upper = fc * np.exp(width)
    lower = fc * np.exp(-width)
    lower = np.maximum(lower, 1e-12)
    return fc, upper, lower
