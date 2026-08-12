"""Rule-based crypto assistant that answers from the coin's computed patterns."""

import datetime as dt
import re

import numpy as np
import pandas as pd

_QA = [
    (r"\bwhen\b.*\b(buy|enter|entry|get in|accumulate)", "when_buy"),
    (r"\bwhen\b.*\b(sell|exit|take profit|dump|offload)", "when_sell"),
    (r"\bhow long\b.*\b(hold|keep|wait)", "hold_time"),
    (r"\bhold\b", "hold_time"),
    (r"\b(entry|buy|entry point|what price.*buy|buy at what|buy price)\b", "entry_price"),
    (r"\b(sell|target|exit|take profit|tp)\b.*\b(price|at)\b", "sell_price"),
    (r"\bsell price\b|\btarget price\b|\bexit price\b", "sell_price"),
    (r"\bstop\b.*\b(loss)?", "stop_loss"),
    (r"\brisk\b", "risk"),
    (r"\b(day|weekday)\b.*best|best.*\b(day|weekday)\b", "best_day"),
    (r"\bwhat (time|hour)\b|\b(time|hour) of (the )?day\b|\bbest (time|hour)\b", "best_time"),
    (r"\bath\b|all.?time high", "ath"),
    (r"\batl\b|all.?time low", "atl"),
    (r"\bbuy\b", "when_buy"),
    (r"\bsell\b", "when_sell"),
    (r"\bplan\b|\btrade\b|\bstrategy\b", "plan"),
]

HELP = (
    "I can answer questions like:\n\n"
    "- *When should I buy next, and at what price?*\n"
    "- *How long should I hold it?*\n"
    "- *What price should I sell at, and on what day?*\n"
    "- *What's the best time of day / day of week to buy or sell?*\n"
    "- *Where's my stop loss / what's my risk?*\n"
    "- *What's the ATH / ATL?*"
)

def fmt(v, dec=4):
    return f"${v:,.{dec}g}"

def fmt_d(ts):
    return ts.strftime("%a %b %d, %Y")

def _h(ts):
    return ts.strftime("%I:%M %p").lstrip("0")

def _sanitize_html(text: str) -> str:
    """Escape HTML special chars to prevent XSS from API-derived strings."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))

def answer(question: str, ctx: dict) -> str:
    q = question.lower().strip()
    if not q or q in ("hi", "hello", "hey", "help", "?"):
        return f"👋 Ask me anything about **{ctx['name']}**. {HELP}"

    if re.search(r"\b(time|hour)\b", q) and re.search(r"\b(buy|sell|day|best)\b", q):
        return _Handlers.best_time(ctx)

    handler = None
    for pat, h in _QA:
        if re.search(pat, q):
            handler = h
            break
    fn = getattr(_Handlers, handler, None) if handler else None
    if fn is None:
        return "I'm not sure how to answer that yet. " + HELP

    cur_time = dt.datetime.now().strftime("%I:%M %p").lstrip("0")
    suffix = f"\n\n*As of {cur_time} {ctx.get('tz', 'local time')} — price won't stand still, so recheck when you trade.*"
    body = fn(ctx)
    return body + suffix

def _zone(p):
    lo, hi = p["entry_zone"]
    return f"**{fmt(lo)} – {fmt(hi)}**"

class _Handlers:
    @staticmethod
    def when_buy(ctx):
        p = ctx["plan"]
        parts = [f"**Next suggested entry for {ctx['name']}:**"]
        if p.get("next_bottom") is not None:
            when = fmt_d(p["entry_day_ideal"]) if p.get("entry_day_ideal") is not None else fmt_d(p["next_bottom"])
            parts.append(f"- 🗓 Next swing bottom estimated around **{when}** (median gap between bottoms on this coin: ~{p['bottom_gap_days']:.0f} days).")
        lo, hi = p["entry_zone"]
        cur = p["current"]
        ref = ""
        if p.get("last_low_price") is not None and p.get("last_low_date") is not None:
            ref = f" — nearest historical support is around {fmt(p['last_low_price'])} (from {p['last_low_date'].date()})"
        parts.append(f"- 💰 Buy zone {_zone(p)}{ref}.")
        if cur <= hi * 1.02:
            parts.append(f"✅ Price right now (**{fmt(cur)}**) is **inside that zone** — historically a reasonable place to start accumulating.")
        else:
            diff = (lo / cur - 1) * 100
            parts.append(f"💡 Price now is **{fmt(cur)}**, which is **above** the suggested zone (~{abs(diff):.0f}% above). The plan is a *limit* order at the zone, not to chase here.")
        if ctx.get("best_buy_hour"):
            parts.append(f"- ⏰ On your chosen day, dips most often form around **{ctx['best_buy_hour']}** your local time.")
        if ctx.get("worst_day"):
            parts.append(f"- 📅 Historically the weakest weekday (best dip day): **{ctx['worst_day']}** (avg {ctx.get('worst_day_ret', 0):+.2f}%).")
        return "\n".join(parts)

    @staticmethod
    def entry_price(ctx):
        p = ctx["plan"]
        lo, hi = p["entry_zone"]
        cur = p["current"]
        if cur <= hi * 1.02:
            status = f"You're already inside it — current price {fmt(cur)}."
        else:
            status = f"Current price is {fmt(cur)}, so this would be a limit order {(lo / cur - 1) * 100:.0f}%–{(hi / cur - 1) * 100:.0f}% below the current price."
        return f"**Entry price idea:** limit buy in the {_zone(p)} zone. {status}"

    @staticmethod
    def when_sell(ctx):
        p = ctx["plan"]
        parts = ["**When to sell:**"]
        parts.append(f"- 🎯 Target **{fmt(p['sell_target'])}** (~{p['leg_ret_pct']:+.0f}% above the entry zone — the median up-swing on this coin, volatility-adjusted).")
        if p.get("sell_zone") is not None:
            lo, hi = p["sell_zone"]
            parts.append(f"- Realistic scale-out zone: **{fmt(lo)} – {fmt(hi)}**.")
        if p.get("resistance_ref"):
            parts.append(f"- Watch the previous major swing high (possible resistance) at **{fmt(p['resistance_ref'])}**.")
        if p.get("exit_day_ideal") is not None:
            parts.append(f"- 🗓 Historically the strongest upcoming exit day is **{fmt_d(p['exit_day_ideal'])}**.")
        if ctx.get("best_sell_hour"):
            parts.append(f"- ⏰ Intraday highs most often print near **{ctx['best_sell_hour']}** your local time.")
        return "\n".join(parts)

    @staticmethod
    def sell_price(ctx):
        p = ctx["plan"]
        lo, hi = p.get("sell_zone", (p["sell_target"] * 0.93, p["sell_target"] * 1.07))
        return f"**Sell target:** around **{fmt(p['sell_target'])}**, with a sensible scale-out zone of **{fmt(lo)} – {fmt(hi)}**."

    @staticmethod
    def hold_time(ctx):
        p = ctx["plan"]
        extra = ""
        if p.get("next_bottom") is not None and p.get("hold_until_est") is not None:
            extra = f" For example, buy near the next expected bottom ({fmt_d(p['next_bottom'])}) → target selling near **{fmt_d(p['hold_until_est'])}**."
        return f"**Typical hold time:** the median swing low→high run on {ctx['name']} takes about **{p['hold_days']:.0f} days** (from {p['n_legs']} past swings)." + extra

    @staticmethod
    def stop_loss(ctx):
        p = ctx["plan"]
        return f"**Risk:** for an entry near {fmt(p['entry_price'])}, a stop around **{fmt(p['stop_loss'])}** (just below the buy zone) implies risk ≈ {p['risk_pct']:.0f}% vs. expected reward ≈ {p['reward_pct']:.0f}% (risk-reward ~1:{p['risk_reward']:.1f})."

    @staticmethod
    def risk(ctx):
        return _Handlers.stop_loss(ctx)

    @staticmethod
    def best_day(ctx):
        return f"For **{ctx['name']}**, historically: **{ctx['worst_day']}** is the weakest day (avg {ctx.get('worst_day_ret', 0):+.2f}% — good for buying dips) and **{ctx['best_day']}** is the strongest (avg {ctx.get('best_day_ret', 0):+.2f}% — good for selling into strength)."

    @staticmethod
    def best_time(ctx):
        if ctx.get("best_buy_hour") is None:
            return "This coin doesn't have enough intraday data yet for hour-of-day patterns."
        return f"Historically for **{ctx['name']}** (your local time): intraday **lows tend to form near {ctx['best_buy_hour']}** (good time to buy), and intraday **highs tend to form near {ctx['best_sell_hour']}** (good time to sell)."

    @staticmethod
    def ath(ctx):
        s = ctx["stats"]
        return f"**{ctx['name']}** all-time high: **{fmt(s['ath'])}** on {s['ath_date']} (currently {s['pct_from_ath']:+.1f}% away)."

    @staticmethod
    def atl(ctx):
        s = ctx["stats"]
        return f"**{ctx['name']}** all-time low: **{fmt(s['atl'])}** on {s['atl_date']} (currently {s['pct_above_atl']:+.1f}% above it)."

    @staticmethod
    def plan(ctx):
        p = ctx["plan"]
        lo, hi = p["entry_zone"]
        entry_day = fmt_d(p["entry_day_ideal"]) if p.get("entry_day_ideal") is not None else (fmt_d(p["next_bottom"]) if p.get("next_bottom") is not None else "soon")
        exit_day = fmt_d(p["exit_day_ideal"]) if p.get("exit_day_ideal") is not None else "n/a"
        return (
            f"**Suggested plan for {ctx['name']}:**\n\n"
            f"1. **Buy** {_zone(p)} around **{entry_day}**."
            f"\n2. **Hold** ~**{p['hold_days']:.0f} days** (typical up-swing on this coin)."
            f"\n3. **Sell** near **{fmt(p['sell_target'])}** (~{p['leg_ret_pct']:+.0f}%) — historically a good day would be **{exit_day}**."
            f"\n4. **Stop loss** ~**{fmt(p['stop_loss'])}** below the zone (risk {p['risk_pct']:.0f}% : reward {p['reward_pct']:.0f}%)."
        )
