"""Standalone validation — mocks Coinbase API so tests run without network."""

import sys, os, warnings, datetime as dt, traceback
import numpy as np, pandas as pd

warnings.filterwarnings("ignore")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ------------------------------------------------------------------
# Mock streamlit caching so we can import modules without a runtime
# ------------------------------------------------------------------
import streamlit as st
from unittest.mock import MagicMock

# Patch cache decorators to be no-ops
def _noop_cache_data(*a, **k):
    def decorator(f):
        return f
    return decorator
st.cache_data = _noop_cache_data
st.cache_resource = _noop_cache_data

# ------------------------------------------------------------------
# Mock coinbase_api so no network calls happen
# ------------------------------------------------------------------
import coinbase_api as api

api._get = MagicMock(return_value=[
    {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "display_name": "Bitcoin", "status": "online", "limit_only": False},
    {"id": "ETH-USD", "base_currency": "ETH", "quote_currency": "USD", "display_name": "Ethereum", "status": "online", "limit_only": False},
    {"id": "SOL-USD", "base_currency": "SOL", "quote_currency": "USD", "display_name": "Solana", "status": "online", "limit_only": False},
    {"id": "DOGE-USD", "base_currency": "DOGE", "quote_currency": "USD", "display_name": "Dogecoin", "status": "online", "limit_only": False},
    {"id": "RENDER-USD", "base_currency": "RENDER", "quote_currency": "USD", "display_name": "Render", "status": "online", "limit_only": False},
    {"id": "AKT-USD", "base_currency": "AKT", "quote_currency": "USD", "display_name": "Akash Network", "status": "online", "limit_only": False},
])

# ------------------------------------------------------------------
# Mock cache module so we generate synthetic candle data
# ------------------------------------------------------------------
import cache

def _synthetic_candles(product_id: str, granularity: int, days: int = 540) -> pd.DataFrame:
    """Generate realistic-looking OHLCV data."""
    np.random.seed(hash(product_id) % 2**31)
    if granularity == 86400:
        periods = days
        freq = "D"
    else:
        periods = days * 24
        freq = "H"
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=periods, freq=freq)

    # Random walk with slight upward drift
    returns = np.random.normal(0.001, 0.03, periods)
    prices = 100 * np.exp(np.cumsum(returns))

    df = pd.DataFrame({
        "date": dates,
        "open": prices * (1 + np.random.normal(0, 0.005, periods)),
        "high": prices * (1 + np.abs(np.random.normal(0, 0.02, periods))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.02, periods))),
        "close": prices,
        "volume": np.random.uniform(1000, 100000, periods),
    })
    df["low"] = np.minimum(df["low"], df["open"])
    df["low"] = np.minimum(df["low"], df["close"])
    df["high"] = np.maximum(df["high"], df["open"])
    df["high"] = np.maximum(df["high"], df["close"])
    return df

cache.get_cached = lambda pid, gran: _synthetic_candles(pid, gran)
cache.latest_ts = lambda pid, gran: int(pd.Timestamp.now().timestamp())
cache.oldest_ts = lambda pid, gran: int((pd.Timestamp.now() - pd.Timedelta(days=540)).timestamp())
cache.upsert = lambda *a, **k: None
cache.freshness_hours = lambda *a, **k: 0.5

# ------------------------------------------------------------------
# Now import the rest
# ------------------------------------------------------------------
import importlib
import patterns as pat
import analysis as an
import chatbot as cb

importlib.reload(pat)
importlib.reload(an)
importlib.reload(cb)

PASS, FAIL = [], []

def check(name, fn):
    t0 = dt.datetime.now()
    try:
        fn()
        PASS.append((name, (dt.datetime.now() - t0).total_seconds()))
        print(f"  PASS {name}")
    except AssertionError as e:
        FAIL.append((name, str(e)))
        print(f"  FAIL {name}: {e}")
    except Exception:
        FAIL.append((name, traceback.format_exc(limit=3)))
        print(f"  FAIL {name}: exception\n{traceback.format_exc(limit=3)}")

pat.set_local_offset(-5.0)

# ------------------------------------------------- 1. search typeahead
print("\n== 1. Typeahead search ==")
products = api.get_all_products()
names = api.get_currency_names()

def t_akash():
    m = api.filter_products(products, "ak", quote="USD", limit=8)
    ids = [p["id"] for p in m]
    if not any("AKT" in i for i in ids):
        if not any(p["base_currency"] == "AKT" for p in products):
            return
        raise AssertionError(f"'ak' should surface AKT, got {ids[:5]}")

def t_btc():
    m = api.filter_products(products, "btc", quote="USD", limit=5)
    assert m and m[0]["id"] == "BTC-USD", f"top match for 'btc' should be BTC-USD, got {m[:2]}"

def t_render_by_name():
    m = api.filter_products(products, "render", quote="USD", limit=5)
    assert m and any(p["base_currency"] == "RENDER" for p in m), f"'render' -> {[x['id'] for x in m]}"

def t_partial():
    m = api.filter_products(products, "sol", quote="USD", limit=5)
    assert any(p["id"] == "SOL-USD" for p in m), f"'sol' should include SOL-USD -> {[x['id'] for x in m]}"

def t_letter_a():
    m = api.filter_products(products, "a", quote="USD", limit=8)
    ids = [p["id"] for p in m]
    assert len(m) > 0, "letter 'a' should return something"
    first_letters = [p["base_currency"][0].upper() for p in m[:4]]
    assert "A" in first_letters, f"'a' should surface A-coins, got {ids}"

def t_dropdown_shows_while_typing():
    for q in ("a", "ak", "render", "so"):
        matches = api.filter_products(products, q, quote="USD", limit=8)
        assert len(matches) > 0, f"typing '{q}' should show options"

def t_names_have_aliases():
    assert names.get("BTC") == "Bitcoin"
    assert names.get("AKT") == "Akash Network"

for fn in (t_akash, t_btc, t_render_by_name, t_partial, t_names_have_aliases, t_letter_a, t_dropdown_shows_while_typing):
    check(fn.__name__, fn)

# --------------------------------------------- 1b. Security & config checks
print("\n== 1b. Security & config checks ==")
_APP_SRC = None

def t_badges_make_sense():
    global _APP_SRC
    if _APP_SRC is None:
        app_path = os.path.join(SCRIPT_DIR, "app.py")
        with open(app_path, encoding="utf-8") as f:
            _APP_SRC = f.read()
    buy = _APP_SRC.find("Next buy zone")
    sell = _APP_SRC.find("Sell target")
    assert "buy the dip" in _APP_SRC[buy:buy + 400], "buy-zone badge should say 'buy the dip'"
    assert "sell the bounce" in _APP_SRC[sell:sell + 400], "sell-target badge should say 'sell the bounce'"
    assert 'Sell target rise expected' not in _APP_SRC, "old 'rise expected' badge still on the sell target"
    assert 'Next buy zone dip expected' not in _APP_SRC, "old ambiguous 'dip expected' label still on buy zone"
    assert "just_picked" in _APP_SRC, "just_picked flag missing from app.py"
    assert "_MAX_CHAT_KEYS" in _APP_SRC, "chat key cap missing from app.py"
    config_path = os.path.join(SCRIPT_DIR, ".streamlit", "config.toml")
    with open(config_path, encoding="utf-8") as f:
        cfg = f.read()
    assert "showErrorDetails = false" in cfg, "showErrorDetails should be false in production"
    api_path = os.path.join(SCRIPT_DIR, "coinbase_api.py")
    with open(api_path, encoding="utf-8") as f:
        api_src = f.read()
    assert "tenacity" in api_src, "tenacity retry not found in coinbase_api.py"
    assert "retry" in api_src, "retry decorator not found"

check("badges_and_security", t_badges_make_sense)

# ------------------------------------------------- 2. per-coin end-to-end
print("\n== 2. End-to-end per coin (loop) ==")
TEST_COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "RENDER-USD", "AKT-USD"]
coin_logs = {}

for pid in TEST_COINS:
    try:
        daily, hourly = pat.get_full_history(pid)
        df = an.compute_indicators(daily)
        ph, pl = pat.find_pivots(df, order=7)
        price = float(df["close"].iloc[-1])
        plan = pat.trade_plan(df, ph, pl, price=price)
        stats = an.compute_stats(df, recent_days=90)
        runs, cur = pat.detect_runs(df)
        sig = pat.signal_verdict(df, plan)
        proj = pat.forecast_path(df, plan)

        assert not daily.empty, "no daily history"
        assert plan["entry_zone"][0] <= plan["entry_zone"][1], "entry zone inverted"

        if plan["entry_zone"][0] > price * 1.05 and not plan.get("deep_discount", False):
            raise AssertionError(
                f"entry zone {plan['entry_zone']} still ABOVE current {price:.4g} "
                "(the old bug — anchoring to a stale swing low)"
            )

        assert plan["sell_target"] > plan["entry_price"] * 1.01, "target not above entry"
        assert plan["stop_loss"] < plan["entry_zone"][0], "stop not below entry zone"
        assert plan["hold_days"] > 0
        assert len(proj) > 0

        sz_lo, sz_hi = plan["entry_zone"]
        if sz_lo > price * 1.05:
            raise AssertionError(f"entry zone {plan['entry_zone']} too far above current {price:.4g}")

        sell_lo, sell_hi = plan["sell_zone"]
        assert sell_lo > sz_hi, f"sell zone {plan['sell_zone']} overlaps entry zone {plan['entry_zone']}"

        assert plan["risk_reward"] <= 10.0, f"risk-reward {plan['risk_reward']} unrealistically high"
        assert plan["risk_pct"] >= 3.0, f"risk_pct {plan['risk_pct']} too low (min 3%)"
        assert plan["risk_reward"] > 0, "negative risk-reward"
        assert plan["entry_price"] <= sz_hi and plan["entry_price"] >= sz_lo * 0.999
        assert plan["exit_day_ideal"] >= plan["entry_day_ideal"]
        gap_days = (plan["exit_day_ideal"] - plan["entry_day_ideal"]).days
        assert abs(gap_days - plan["hold_days"]) <= 6, \
            f"exit {gap_days}d after entry but hold is {plan['hold_days']}d"
        assert abs(float(proj["price"].iloc[-1]) / plan["sell_target"] - 1) < 0.2
        assert plan["sell_target"] > plan["entry_zone"][1] * 1.004, "sell target below entry zone top"

        rets = proj["price"].pct_change().dropna()
        assert rets.std() > 0, "forecast path is perfectly linear (no noise added)"

        coin_logs[pid] = {
            "price": round(price, 4),
            "entry_zone": [round(v, 4) for v in plan["entry_zone"]],
            "sell": round(plan["sell_target"], 4),
            "hold_days": plan["hold_days"],
            "rr": round(plan["risk_reward"], 1),
            "runs": len(runs),
            "sig": sig["emoji"],
        }
        PASS.append((f"e2e::{pid}", 0))
        print(f"  PASS e2e::{pid} price={price:.4g} zone={plan['entry_zone'][0]:.4g}-{plan['entry_zone'][1]:.4g} "
              f"target={plan['sell_target']:.4g} hold={plan['hold_days']:.0f}d rr=1:{plan['risk_reward']:.1f}")
    except AssertionError as e:
        FAIL.append((f"e2e::{pid}", str(e)))
        print(f"  FAIL e2e::{pid}: {e}")
    except Exception:
        FAIL.append((f"e2e::{pid}", traceback.format_exc(limit=3)))
        print(f"  FAIL e2e::{pid}:\n{traceback.format_exc(limit=3)}")

# ------------------------------------------------- 3. local-time bucketing
print("\n== 3. Local timezone bucketing ==")

def t_tz_shift():
    d, h = pat.get_full_history("BTC-USD")
    if h.empty:
        print("  (skipped — hourly cache empty, expected on a fresh app)")
        return
    ht_off = pat.hourly_table(h)
    pat.set_local_offset(2.0)
    ht_on = pat.hourly_table(h)
    pat.set_local_offset(-5.0)
    assert not ht_off.empty and not ht_on.empty, "hourly tables empty"
    dif = (ht_off["avg_ret"] - ht_on["avg_ret"]).abs().sum()
    assert dif > 1e-6, "local-time buckets didn't change when the UTC offset changed"

check("tz_offset_changes_buckets", t_tz_shift)

# ------------------------------------------------- 4. chatbot answers
print("\n== 4. Chatbot ==")
daily, hourly = pat.get_full_history("RENDER-USD")
df = an.compute_indicators(daily)
ph, pl = pat.find_pivots(df, 7)
price = float(df["close"].iloc[-1])
plan = pat.trade_plan(df, ph, pl, price=price)
stats = an.compute_stats(df, 90)
wt = pat.weekday_table(daily)
hourly_daily = pat.hourly_table(hourly)
ctx = {
    "name": "Render", "base": "RENDER", "plan": plan, "stats": stats,
    "tz": pat.local_tz_label(),
    "best_buy_hour": (dt.time(hour=int(hourly_daily.loc[hourly_daily["avg_lo"].idxmin(), "hour_local"])).strftime("%I %p").lstrip("0")
                      if not hourly_daily.empty else None),
    "best_sell_hour": (dt.time(hour=int(hourly_daily.loc[hourly_daily["avg_hi"].idxmax(), "hour_local"])).strftime("%I %p").lstrip("0")
                       if not hourly_daily.empty else None),
    "best_day": wt.loc[wt["mean"].idxmax(), "day"], "best_day_ret": float(wt["mean"].max()),
    "worst_day": wt.loc[wt["mean"].idxmin(), "day"], "worst_day_ret": float(wt["mean"].min()),
}

QUESTIONS_OK = [
    "when should I buy next at what price entry point?",
    "how long do I hold it and at what price should I sell on what day?",
    "what price should I set to sell and on what day?",
    "what time of day is best to buy?",
    "best day of week to buy?",
    "stop loss?",
    "what is the ath?",
    "give me a full trade plan",
    "hello",
]

def t_bot():
    for q in QUESTIONS_OK:
        a = cb.answer(q, ctx)
        assert isinstance(a, str) and len(a) > 10, f"empty/short answer for '{q}'"
        assert "Traceback" not in a, f"error text leaked for '{q}'"
        assert "<script>" not in a.lower(), f"XSS risk in answer for '{q}'"

check("chatbot_all_questions", t_bot)

def t_bot_zone_coherent():
    a = cb.answer("when should I buy next at what price entry point?", ctx)
    assert ("inside that zone" in a) or ("above" in a and "suggested zone" in a), f"zone context missing:\n{a}"

check("bot_when_buy_coherent", t_bot_zone_coherent)

# ------------------------------------------------- 5. speed
print("\n== 5. Load speed (after warmup) ==")
pat.get_full_history("ETH-USD")

def t_second_load_fast():
    t0 = dt.datetime.now()
    daily, hourly = pat.get_full_history("ETH-USD")
    dt_s = (dt.datetime.now() - t0).total_seconds()
    assert dt_s < 2.0, f"warm load took {dt_s:.2f}s (target < 2s)"

check("warm_load_under_2s", t_second_load_fast)

# ------------------------------------------------- 6. API resilience
print("\n== 6. API resilience ==")

def t_retry_decorator_exists():
    import inspect
    # In mocked env, _get is MagicMock; check the real module source instead
    api_path = os.path.join(SCRIPT_DIR, "coinbase_api.py")
    with open(api_path, encoding="utf-8") as f:
        src = f.read()
    assert "retry" in src or "Retrying" in src, "_get should use tenacity retry"

check("retry_decorator_on_get", t_retry_decorator_exists)

def t_timeout_reduced():
    assert api._TIMEOUT <= 10, f"timeout {api._TIMEOUT}s too high (should be <= 10)"

check("timeout_under_10s", t_timeout_reduced)

# ------------------------------------------------- summary
print("\n" + "=" * 56)
print(f"PASSED {len(PASS)} / {len(PASS) + len(FAIL)}")
if FAIL:
    print("FAILURES:")
    for n, e in FAIL:
        print(f"  - {n}: {e[:200]}")
    sys.exit(1)
else:
    print("ALL TESTS PASS")
    sys.exit(0)
