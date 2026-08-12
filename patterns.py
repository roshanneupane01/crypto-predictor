"""Pattern-mining + robust trade planning.

Local-time convention: all buckets and "today" summaries use the browser's
timezone, injected via ``set_local_offset(hours)`` from the frontend (via a
query param). Server-side Coinbase candles stay in UTC and are shifted by
that offset only when grouping by hour-of-day / weekday.
"""

import datetime as dt
import threading

import numpy as np
import pandas as pd
import streamlit as st

import cache
from coinbase_api import _get

# browser offset from UTC in hours (positive = ahead of UTC)
_local_offset_hours: float = 0.0


def set_local_offset(hours: float):
    global _local_offset_hours
    _local_offset_hours = float(hours)


def local_tz_label() -> str:
    """e.g. 'UTC-5' style short label based on the browser offset."""
    off = _local_offset_hours
    sign = "-" if off < 0 else "+"
    hours = abs(off)
    h = int(hours)
    m = int(round((hours - h) * 60))
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def _offset_td() -> pd.Timedelta:
    return pd.Timedelta(hours=_local_offset_hours)


# ------------------------------------------------------------- data layer
def _fetch_chunk(product_id: str, granularity: int,
                 start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    frames = []
    max_span = dt.timedelta(seconds=granularity * 299)
    cur = start
    while cur < end:
        chunk_end = min(cur + max_span, end)
        try:
            raw = _get(
                f"/products/{product_id}/candles",
                params={"granularity": granularity,
                        "start": cur.isoformat(), "end": chunk_end.isoformat()},
            )
            if raw:
                d = pd.DataFrame(raw, columns=["time", "low", "high", "open", "close", "volume"])
                d["date"] = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_localize(None)
                frames.append(d[["date", "open", "high", "low", "close", "volume"]])
        except Exception:
            pass
        cur = chunk_end
    if not frames:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return (pd.concat(frames, ignore_index=True)
              .drop_duplicates(subset="date").sort_values("date")
              .reset_index(drop=True))


def _refresh_product(product_id: str):
    """Sync local cache with Coinbase (tail-fetch only). Runs in background."""
    now = dt.datetime.now(dt.timezone.utc)
    for gran, horizon_days in ((86400, 9000), (3600, 1460)):
        latest = cache.latest_ts(product_id, gran)
        if latest is None:
            start = now - dt.timedelta(days=horizon_days)
        else:
            start = dt.datetime.fromtimestamp(latest + 1, tz=dt.timezone.utc)
            start -= dt.timedelta(seconds=gran * 2)  # small overlap to heal gaps
        if (now - start).total_seconds() < gran * 10:
            continue
        df = _fetch_chunk(product_id, gran, start, now)
        if df.empty:
            continue
        cache.upsert(product_id, gran, df)
        if latest is None:
            st.cache_data.clear()  # invalidate the cached get_full_history


def _start_refresh(product_id: str):
    if st.session_state.get(f"_refreshing_{product_id}"):
        return
    st.session_state[f"_refreshing_{product_id}"] = True

    def run():
        try:
            _refresh_product(product_id)
        finally:
            st.session_state[f"_refreshing_{product_id}"] = False

    threading.Thread(target=run, daemon=True).start()


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _cached_history(product_id: str, _v: int = 0):
    daily = cache.get_cached(product_id, 86400)
    hourly = cache.get_cached(product_id, 3600)
    return daily, hourly


def get_full_history(product_id: str):
    """
    Returns whatever is cached locally (instant). If the cache is empty for
    this product, blocks once while we fetch, then future loads are instant.
    Triggers a background tail-refresh afterwards.
    """
    daily, hourly = _cached_history(product_id)
    if daily.empty or len(daily) < 40:
        # one-time slow path: user picked a coin we haven't cached yet
        with st.spinner(f"First load for {product_id} — downloading history… (this happens only once)"):
            _refresh_product(product_id)
        daily, hourly = cache.get_cached(product_id, 86400), cache.get_cached(product_id, 3600)
    else:
        _start_refresh(product_id)
    return daily, hourly


def prefetch_popular(products, quote: str = "USD"):
    """Kick off background caching for popular coins so first-click is instant."""
    for sym in ["BTC", "ETH", "SOL", "RENDER", "AKT", "DOGE", "XRP", "ADA"]:
        pid = f"{sym}-{quote}"
        if any(p["id"] == pid for p in products):
            _start_refresh(pid)


# ------------------------------------------------------------------ pivots
def find_pivots(df: pd.DataFrame, order: int = 7, min_separation: int = 4,
                prominence_pct: float = 0.02):
    close = df["close"].to_numpy(dtype=float)
    dates = df["date"].to_numpy()
    n = len(close)
    if n < 2 * order + 5:
        e = pd.DataFrame(columns=["date", "price"])
        return e.copy(), e.copy()

    hi, lo = [], []
    hi_l = hi_r = lo_l = lo_r = 0
    for i in range(order, n - order):
        w = close[i - order: i + order + 1]
        if close[i] == w.max() and close[i] >= close[i - order] * (1 + prominence_pct) \
           and close[i] >= close[i + order] * (1 + prominence_pct):
            hi.append(i)
        if close[i] == w.min() and close[i] <= close[i - order] * (1 - prominence_pct) \
           and close[i] <= close[i + order] * (1 - prominence_pct):
            lo.append(i)

    def separate(idx, mode):
        if not idx:
            return idx
        kept = [idx[0]]
        for j in idx[1:]:
            if j - kept[-1] >= min_separation:
                kept.append(j)
            elif (mode == "max" and close[j] > close[kept[-1]]) or \
                 (mode == "min" and close[j] < close[kept[-1]]):
                kept[-1] = j
        return kept

    hi, lo = separate(hi, "max"), separate(lo, "min")
    ph = pd.DataFrame({"date": pd.to_datetime(dates[hi]), "price": close[hi]})
    pl = pd.DataFrame({"date": pd.to_datetime(dates[lo]), "price": close[lo]})
    return ph, pl


def detect_runs(df: pd.DataFrame, threshold: float = 0.18):
    """Zig-zag bull/bear runs over the full daily history."""
    d = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    prices = d["close"].to_numpy(dtype=float)
    dates = d["date"].to_numpy()
    n = len(prices)
    if n < 30:
        return [], 0.0

    runs = []
    last_piv_i = 0
    last_piv_p = prices[0]
    run_hi_i, run_hi = 0, prices[0]
    run_lo_i, run_lo = 0, prices[0]
    direction = 0

    def _maybe_add(typ, i0, i1):
        p0, p1 = prices[i0], prices[i1]
        ret = (p1 / p0 - 1) * 100
        if abs(ret) >= threshold * 100:
            runs.append({
                "type": typ,
                "start": pd.Timestamp(dates[i0]),
                "end": pd.Timestamp(dates[i1]),
                "start_price": float(p0),
                "end_price": float(p1),
                "days": int((pd.Timestamp(dates[i1]) - pd.Timestamp(dates[i0])).days),
                "return_pct": float(ret),
            })

    for i in range(1, n):
        v = prices[i]
        if direction >= 0 and v > run_hi:
            run_hi_i, run_hi = i, v
        if direction <= 0 and v < run_lo:
            run_lo_i, run_lo = i, v
        if direction >= 0 and v <= run_hi * (1 - threshold):
            _maybe_add("bull", last_piv_i, run_hi_i)
            last_piv_i, last_piv_p = run_hi_i, run_hi
            run_lo_i, run_lo = i, v
            direction = -1
        elif direction <= 0 and v >= run_lo * (1 + threshold):
            _maybe_add("bear", last_piv_i, run_lo_i)
            last_piv_i, last_piv_p = run_lo_i, run_lo
            run_hi_i, run_hi = i, v
            direction = 1

    end_i = n - 1
    if direction == 1:
        _maybe_add("bull", last_piv_i, end_i)
    elif direction == -1:
        _maybe_add("bear", last_piv_i, end_i)
    elif direction == 0:
        # still in first leg
        if prices[end_i] > last_piv_p * (1.05):
            _maybe_add("bull", last_piv_i, end_i)
        elif prices[end_i] < last_piv_p * 0.95:
            _maybe_add("bear", last_piv_i, end_i)

    cur_state = (
        (prices[-1] / run_lo - 1) if direction == 1
        else (prices[-1] / run_hi - 1) if direction == -1
        else 0.0
    )
    return runs, cur_state


# ------------------------------------------------------------- seasonality
def hourly_table(hourly: pd.DataFrame) -> pd.DataFrame:
    if hourly.empty:
        return pd.DataFrame()
    h = hourly.dropna(subset=["open", "high", "low", "close"]).copy()
    h["open"] = h["open"].replace(0, np.nan)
    h = h.dropna(subset=["open"])
    h["ret"] = h["close"].pct_change() * 100
    h["hi_from_open"] = (h["high"] / h["open"] - 1) * 100
    h["lo_from_open"] = (h["low"].replace(0, np.nan) / h["open"] - 1) * 100
    h["hour_local"] = (h["date"] + _offset_td()).dt.hour
    g = h.groupby("hour_local").agg(
        avg_ret=("ret", "mean"),
        avg_hi=("hi_from_open", "mean"),
        avg_lo=("lo_from_open", "mean"),
        samples=("ret", "count"),
    ).reset_index().sort_values("hour_local")
    return g


def weekday_table(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.dropna(subset=["close"]).copy()
    d["ret"] = d["close"].pct_change() * 100
    d = d.dropna(subset=["ret"])
    d["local"] = d["date"] + _offset_td()
    d["weekday"] = d["local"].dt.dayofweek
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    g = d.groupby("weekday")["ret"].agg(["mean", "count"]).reset_index().sort_values("weekday")
    g["day"] = g["weekday"].map(lambda i: names[int(i)])
    return g[["weekday", "day", "mean", "count"]]


def typical_day_shape(hourly: pd.DataFrame) -> pd.DataFrame:
    if hourly.empty:
        return pd.DataFrame()
    h = hourly.dropna(subset=["open", "close"]).copy()
    h["open"] = h["open"].replace(0, np.nan)
    h = h.dropna(subset=["open"])
    h["pct"] = (h["close"] / h["open"] - 1) * 100
    h["hour_local"] = (h["date"] + _offset_td()).dt.hour
    return h.groupby("hour_local")["pct"].mean().reset_index().sort_values("hour_local")


def today_summary(hourly: pd.DataFrame) -> dict:
    if hourly.empty:
        return {}
    h = hourly.copy()
    h["local_dt"] = h["date"] + _offset_td()
    today_local = pd.Timestamp.now().normalize()
    t = h[h["local_dt"].dt.normalize() == today_local]
    if t.empty:
        t = h.tail(24)
    if t.empty:
        return {}
    il, ih = t["low"].idxmin(), t["high"].idxmax()
    return {
        "low_price": float(t.loc[il, "low"]), "low_time": t.loc[il, "local_dt"],
        "high_price": float(t.loc[ih, "high"]), "high_time": t.loc[ih, "local_dt"],
    }


# --------------------------------------------------------- robust planning
def _weekday_avg_map(daily: pd.DataFrame) -> dict:
    wt = weekday_table(daily)
    if wt.empty:
        return {}
    return {int(r.weekday): float(r.mean) for r in wt.itertuples()}


def _best_future_weekday(avg_map: dict, from_dt: pd.Timestamp, sign: str,
                         within_days: int = 45) -> pd.Timestamp:
    """
    sign='+' -> best (most positive) upcoming weekday for SELLING
    sign='-' -> worst (most negative) upcoming weekday for BUYING a dip
    Falls back to from_dt when no data.
    """
    cand = [from_dt + pd.Timedelta(days=i) for i in range(1, within_days + 1)]
    cand = [c for c in cand if c.weekday() in avg_map]
    if not cand:
        return from_dt
    key = (max if sign == "+" else min)
    return key(cand, key=lambda c: avg_map.get(c.weekday(), 0.0))


def _recent_momentum_factor(df: pd.DataFrame) -> float:
    """0.6 (cooling) … 1.4 (hot) based on last-14d vs last-90d-centered RSI."""
    if len(df) < 90:
        return 1.0
    rsi_recent = df["RSI_14"].tail(14).mean()
    if np.isnan(rsi_recent):
        return 1.0
    if rsi_recent > 62:
        return 1.15
    if rsi_recent < 40:
        return 0.85
    return 1.0


def _recent_vol_factor(daily: pd.DataFrame) -> float:
    """Recent-30d daily vol relative to long-run vol -> scales swings a bit."""
    r = daily["close"].pct_change().dropna()
    if len(r) < 60:
        return 1.0
    recent = r.tail(30).std()
    long = r.std()
    if long and not np.isnan(long) and long > 0:
        ratio = recent / long
        return float(np.clip(ratio, 0.75, 1.5))
    return 1.0


def _next_bottom_after(daily: pd.DataFrame, pl: pd.DataFrame) -> dict:
    now = daily["date"].iloc[-1]
    if len(pl) >= 3:
        gaps = pl["date"].diff().dt.days.dropna().tail(12)
        med_gap = float(gaps.median()) if len(gaps) else 30.0
        last_low = pl["date"].iloc[-1]
        since = (now - last_low).days
    else:
        med_gap = 30.0
        since = 0

    momentum = _recent_momentum_factor(daily)
    # If the market is currently heating up, the next bottom comes sooner
    est_days = max(2.0, med_gap * (2 - momentum) / 2)
    est = now + pd.Timedelta(days=max(1.0, est_days - since * 0.4))
    return {"next_bottom": est, "bottom_gap_days": med_gap}


def trade_plan(df: pd.DataFrame, ph: pd.DataFrame, pl: pd.DataFrame,
               price: float | None = None) -> dict:
    """
    Robust next-trade suggestion logic:

    Entry  = nearest cluster of historical swing lows at or below current price,
             giving a zone [support*0.985, min(current*1.004, support*1.02)].
    If no support exists (deep discount vs all history), zone hugs current price.
    Sell   = entry * median(leg returns, vol-scaled), targets timed to the best
             forward weekday.
    Hold   = median swing-low -> next-swing-high duration (in days).
    Stop   = entry zone low * 0.95.
    """
    cur = float(price if price is not None else df["close"].iloc[-1])
    now = df["date"].iloc[-1]
    plan: dict = {"current": cur}
    vol_factor = _recent_vol_factor(df)
    plan["vol_factor"] = vol_factor

    # --- legs: swing low -> following swing high ---
    legs = []
    if len(pl) and len(ph):
        merged = pd.concat([pl.assign(kind="L"), ph.assign(kind="H")]).sort_values("date")
        pdata = merged.to_dict("records")
        for i, p in enumerate(pdata):
            if p["kind"] != "L":
                continue
            nxt = next((q for q in pdata[i + 1:] if q["kind"] == "H"), None)
            if nxt:
                legs.append({
                    "hold_days": max(1, (nxt["date"] - p["date"]).days),
                    "ret_pct": (nxt["price"] / p["price"] - 1) * 100,
                })
    if len(legs) >= 4:
        rets = np.array([l["ret_pct"] for l in legs])
        med_hold = float(np.median([l["hold_days"] for l in legs]))
        med_ret = float(np.median(rets))
        p25 = float(np.percentile(rets, 25))
        p75 = float(np.percentile(rets, 75))
    else:
        med_hold, med_ret, p25, p75 = 14.0, 15.0, 8.0, 25.0

    med_ret = float(np.clip(med_ret * vol_factor, 4.0, 60.0))
    plan["hold_days"] = med_hold
    plan["leg_ret_pct"] = med_ret
    plan["leg_ret_lo"] = float(np.clip(p25 * vol_factor, 3.0, med_ret))
    plan["leg_ret_hi"] = float(np.clip(p75 * vol_factor, med_ret, 90.0))
    plan["n_legs"] = len(legs)

    # --- entry zone from supports near current price ---
    # only historical lows within 20% of current are meaningful as "nearby support"
    lows = pl.copy() if len(pl) else pd.DataFrame(columns=["date", "price"])
    supports = lows[
        (lows["price"] <= cur * 1.001) & (lows["price"] >= cur * 0.80)
    ].sort_values("date")

    if len(supports) >= 1:
        recent_supports = supports.tail(5)["price"].to_numpy()
        # weight by recency so old supports matter less
        w = np.linspace(0.5, 1.0, len(recent_supports))
        support = float(np.average(recent_supports, weights=w))
        support = min(support, cur)  # never above current
        plan["support_ref"] = support

        # zone = ±small band around support, never crossing above current
        lo = support * 0.99
        hi = support * 1.03
        hi = min(hi, cur * 1.02)
        if lo >= hi:  # keep it sane regardless of support/cur relationship
            lo, hi = min(lo, hi) * 0.99, max(lo, hi) * 1.01
        plan["entry_zone"] = (lo, hi)
        plan["entry_price"] = (lo + hi) / 2
        last_sup = supports.iloc[-1]
        plan["last_low_price"] = float(last_sup["price"])
        plan["last_low_date"] = last_sup["date"]
    else:
        # price is below ALL historical swing lows: deep discount vs history
        plan["support_ref"] = cur
        plan["entry_zone"] = (cur * 0.985, cur * 1.01)
        plan["entry_price"] = cur

    # --- timing for the next entry: momentum-adjusted next bottom ---
    nb = _next_bottom_after(df, pl if len(pl) else pd.DataFrame())
    plan["next_bottom"] = nb["next_bottom"]
    plan["bottom_gap_days"] = nb["bottom_gap_days"]

    # --- sell target / stop / RR ---
    e_lo, e_hi = plan["entry_zone"]
    plan["sell_target"] = plan["entry_price"] * (1 + med_ret / 100)
    plan["sell_zone"] = (e_hi * (1 + plan["leg_ret_lo"] / 100),
                         plan["entry_price"] * (1 + plan["leg_ret_hi"] / 100))
    plan["stop_loss"] = e_lo * 0.95
    plan["risk_pct"] = (plan["entry_price"] / plan["stop_loss"] - 1) * 100
    plan["reward_pct"] = med_ret
    plan["risk_reward"] = med_ret / plan["risk_pct"] if plan["risk_pct"] > 0 else float("inf")

    if len(ph):
        plan["resistance_ref"] = float(ph["price"].iloc[-1])

    # --- timing of exit: best forward weekday ---
    wd_avg = _weekday_avg_map(df)
    entry_d = max(now + pd.Timedelta(days=1), plan["next_bottom"])
    plan["entry_day_ideal"] = _best_future_weekday(wd_avg, entry_d, sign="-", within_days=45)
    # exit ≈ entry + hold, snapped only a few days to the best weekday so the
    # shown dates stay consistent with the "hold N days" number
    exit_base = plan["entry_day_ideal"] + pd.Timedelta(days=med_hold)
    plan["exit_day_ideal"] = _best_future_weekday(wd_avg, exit_base, sign="+", within_days=3)
    plan["next_top"] = plan["exit_day_ideal"]
    plan["top_gap_days"] = float(ph["date"].diff().dt.days.dropna().median()) if len(ph) >= 3 else 30.0
    plan["buy_day_avg"] = wd_avg.get(plan["entry_day_ideal"].weekday(), 0.0)
    plan["sell_day_avg"] = wd_avg.get(plan["exit_day_ideal"].weekday(), 0.0)
    plan["hold_until_est"] = plan["exit_day_ideal"]

    if cur <= plan["entry_price"] * 1.02:
        plan["within_zone_now"] = True
    else:
        plan["within_zone_now"] = False
    return plan


def forecast_path(df: pd.DataFrame, plan: dict, days: int | None = None):
    """Build a forward-looking price path for the bull/bear projection chart."""
    now = df["date"].iloc[-1]
    cur = plan["current"]
    if days is None:
        if plan.get("hold_until_est") is not None:
            days = int((plan["hold_until_est"] - now).days) + 14
        else:
            days = plan.get("hold_days", 14) + 14
        days = max(14, min(int(days), 90))
    futures = pd.date_range(now + pd.Timedelta(days=1), periods=days)
    hold_days = max(1, plan.get("hold_days", 14))
    entry = plan.get("entry_price", cur)
    target = plan["sell_target"]
    inc = (target / entry - 1) / min(hold_days, days)
    rets = np.concatenate([
        np.cumsum(np.repeat(inc, min(hold_days, days))),
        np.repeat(target / entry - 1, max(0, days - hold_days)),
    ])[:days]
    path = entry * (1 + rets)
    return pd.DataFrame({"date": futures, "price": path})


def signal_verdict(df: pd.DataFrame, plan: dict) -> dict:
    """Simple 🟢/🔴/⚪ from current price vs the computed plan."""
    cur = plan["current"]
    e_lo, e_hi = plan["entry_zone"]
    rsi = float(df["RSI_14"].iloc[-1]) if "RSI_14" in df and not np.isnan(df["RSI_14"].iloc[-1]) else 50.0

    if cur <= e_hi * 1.03:
        if rsi < 32:
            return {"tone": "green", "emoji": "🟢",
                    "verdict": "Inside/near a historical BUY zone with oversold momentum."}
        return {"tone": "green", "emoji": "🟢",
                "verdict": "Price is inside the suggested buy zone — historically a decent place to accumulate."}
    if plan.get("resistance_ref") and cur >= plan["resistance_ref"] * 0.97:
        return {"tone": "red", "emoji": "🔴",
                "verdict": "Near the recent swing high — historically where tops form."}
    if rsi > 68:
        return {"tone": "red", "emoji": "🔴",
                "verdict": "Momentum is overbought (RSI high) — chasing here has historically been poor."}
    if cur > e_hi * 1.25:
        return {"tone": "gray", "emoji": "⚪",
                "verdict": f"Price has run {plan['leg_ret_pct']:.0f}%-style moves before — mid-range, nothing obvious."}
    return {"tone": "gray", "emoji": "⚪",
            "verdict": "Mid-range relative to recent swings — fair to wait for a better zone."}
