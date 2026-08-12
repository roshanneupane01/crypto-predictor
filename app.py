"""
TradeSnapshot - Crypto trading insights with live prices
"""
import datetime as dt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_searchbox import st_searchbox

from coinbase_api import (
    get_all_products, filter_products, get_currency_names,
    get_ticker, get_stats_24h, POPULAR,
)
from analysis import compute_indicators, compute_stats
from chatbot import answer as bot_answer
from patterns import (
    set_local_offset, local_tz_label, get_full_history, find_pivots,
    hourly_table, weekday_table, typical_day_shape,
    trade_plan, detect_runs, forecast_path, signal_verdict, prefetch_popular,
)

st.set_page_config(page_title="TradeSnapshot", page_icon="📈", layout="wide")

# ---------- inject browser local-time offset ----------
_TZ_HTML = """
<script>
(function() {
    var off = -(new Date().getTimezoneOffset() / 60);
    var cur = new URLSearchParams(window.parent.location.search).get('tz_off');
    var stored = window.parent.localStorage.getItem('tz_off');
    var use = cur !== null ? parseFloat(cur) : (stored !== null ? parseFloat(stored) : off);
    window.parent.localStorage.setItem('tz_off', use);
    if (cur === null || Math.abs(parseFloat(cur) - use) > 1e-9) {
        var p = new URLSearchParams(window.parent.location.search);
        p.set('tz_off', use);
        window.parent.location.search = p.toString();
    }
})();
</script>
"""
try:
    st.components.v1.html(_TZ_HTML, height=0, scrolling=False)
except Exception:
    try:
        st.iframe("data:text/html," + _TZ_HTML.replace("\n", "%20"), height=0, scrolling=False)
    except Exception:
        pass

_qp = st.query_params.get("tz_off")
if _qp is not None:
    try:
        set_local_offset(float(_qp))
    except (TypeError, ValueError):
        pass
TZ_LABEL = local_tz_label()

# ---------- page styling ----------
st.markdown("""
<style>
:root { --gain:#16c784; --loss:#ea3943; --ink:#e6e9f0; --sub:#9aa4b2; --card:#1b2130; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; }
.hero { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom: 4px; }
.hero .name { font-size: 1.6rem; font-weight: 700; }
.hero .sym  { color: var(--sub); font-size:.9rem; letter-spacing:.06em; }
.price-big { font-size: 2.1rem; font-weight: 700; letter-spacing:-.01em; }
.chg { font-size: .95rem; font-weight: 600; padding: 2px 10px; border-radius: 999px; }
.chg.up { color: var(--gain); background: rgba(22,199,132,.12); }
.chg.down { color: var(--loss); background: rgba(234,57,67,.12); }
.badge { padding: 6px 14px; border-radius: 999px; font-weight: 600; font-size: .92rem; }
.badge.gain { background: rgba(22,199,132,.14); color: var(--gain); }
.badge.loss { background: rgba(234,57,67,.14); color: var(--loss); }
.badge.gray { background: rgba(154,164,178,.14); color: var(--sub); }
.card { background: var(--card); border: 1px solid rgba(255,255,255,.06); border-radius: 14px; padding: 14px 16px; margin-bottom: 10px; }
.card .lab { color: var(--sub); font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
.card .val { font-size: 1.15rem; font-weight: 700; }
.card .val.green { color: var(--gain); }
.card .val.red { color: var(--loss); }
.card .sub { color: var(--sub); font-size: .8rem; margin-top: 3px; }
.mini-note { color: var(--sub); font-size: .82rem; }
.mini-note b { color: #d8dee9; }
div[data-testid="stMetric"] { background: var(--card); border: 1px solid rgba(255,255,255,.06); border-radius: 14px; padding: 12px 14px; }
hr { border: none; border-top: 1px solid rgba(255,255,255,.06); margin: 1.2rem 0; }
</style>
""", unsafe_allow_html=True)

# ---------------- session ----------------
if "selected" not in st.session_state:
    st.session_state.selected = None


def clear_all():
    st.session_state.selected = None
    st.session_state.pop("search", None)


def fmt(v, dec=4):
    return f"${v:,.{dec}g}"


def fd(ts):
    return ts.strftime("%a %b %d")


def fh(ts):
    return ts.strftime("%I:%M %p").lstrip("0")


def friendly_day(ts):
    if ts is None:
        return "soon"
    today = pd.Timestamp.now().normalize()
    d = pd.Timestamp(ts).normalize()
    delta = (d - today).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta <= 7:
        return f"{d.strftime('%a')} ({d.strftime('%b %d')})"
    return d.strftime("%b %d")


# ---------------- header + search ----------------
products = get_all_products()
_ALL_NAMES = get_currency_names()
prefetch_popular(products)

st.title("📈 TradeSnapshot")
st.caption(f"Patterns & trade timing for any Coinbase coin · times in your local time ({TZ_LABEL})")


def _search_suggest(q: str) -> list[tuple[str, str]]:
    if not q or not q.strip():
        return []
    ms = filter_products(products, q, quote="USD", limit=8)
    return [
        (_ALL_NAMES.get(m["base_currency"].upper(), m["base_currency"]) + f" ({m['base_currency']})", m["id"])
        for m in ms
    ]


pick_sel = st_searchbox(
    _search_suggest,
    key="coin_search",
    placeholder="Type a coin — suggestions appear as you type…",
    debounce=200,
    edit_after_submit="option",
    clear_on_submit=True,
    rerun_on_update=True,
)
if pick_sel:
    _pid = pick_sel[1] if isinstance(pick_sel, (tuple, list)) else pick_sel
    if isinstance(_pid, str) and any(p["id"] == _pid for p in products) and st.session_state.selected != _pid:
        st.session_state.selected = _pid
        st.rerun()

selected = st.session_state.selected

if not selected:
    st.markdown("#### Popular")
    pop = [p for p in POPULAR if any(x["id"] == f"{p}-USD" for x in products)][:10]
    cols = st.columns(len(pop))
    for c, sym in zip(cols, pop):
        if c.button(sym, key=f"pop_{sym}", use_container_width=True):
            st.session_state.selected = f"{sym}-USD"
            st.rerun()
    st.stop()

# ---------------- resolve product ----------------
prod = next((p for p in products if p["id"] == selected), None)
if prod is None:
    st.warning("That coin isn't tradable on Coinbase right now.")
    st.session_state.selected = None
    st.stop()

BASE = prod["base_currency"]
NAME = get_currency_names().get(BASE.upper()) or prod["display_name"]

# ---------------- load data (instant after first touch) ----------------
daily, hourly = get_full_history(selected)
if daily.empty or len(daily) < 60:
    st.warning(
        f"Coinbase has very little history for **{BASE}** yet "
        f"({len(daily)} daily candles). The app needs at least ~60 days to find patterns. "
        "Try a more established coin from the list."
    )
    st.stop()

df = compute_indicators(daily)
ph, pl = find_pivots(df, order=7)
stats = compute_stats(df, recent_days=90)

ticker = get_ticker(selected)
s24 = get_stats_24h(selected)
price = float(ticker["price"]) if ticker.get("price") else float(df["close"].iloc[-1])
chg = s24["change_pct"] if s24 else 0.0

# ---- the robust plan + verdict ----
plan = trade_plan(df, ph, pl, price=price)
sig = signal_verdict(df, plan)
runs, cur_run_state = detect_runs(df)

# ================= TOP HERO =================
@st.fragment(run_every="30s")
def hero_price(pid, name, base):
    t = get_ticker(pid)
    s = get_stats_24h(pid)
    p = float(t["price"]) if t.get("price") else None
    chg24 = s.get("change_pct") if s else None
    ts = pd.Timestamp.now().strftime("%I:%M:%S %p")
    chg_cls = "up" if (chg24 or 0) >= 0 else "down"
    if p is not None:
        st.markdown(
            f'<div class="hero">'
            f'<span class="name">{name}</span><span class="sym">{base}/USD · Coinbase · 🟢 live</span></div>'
            f'<div class="hero"><span class="price-big">{fmt(p)}</span>'
            f'<span class="chg {chg_cls}">{(chg24 or 0):+.2f}% 24h</span>'
            f'<span class="mini-note" style="margin-left:8px">updated {ts}</span></div>',
            unsafe_allow_html=True,
        )

left, right = st.columns([3, 1])
with left:
    hero_price(selected, NAME, BASE)
with right:
    st.button("← Back to search", on_click=clear_all, use_container_width=True)

if sig["tone"] == "green":
    st.success(f"**{sig['emoji']} {sig['verdict']}**")
elif sig["tone"] == "red":
    st.error(f"**{sig['emoji']} {sig['verdict']}**")
else:
    st.info(f"**{sig['emoji']} {sig['verdict']}**")

# ---- compute best hours ----
ht = hourly_table(hourly)
wt = weekday_table(daily)
best_buy_hour_txt = best_sell_hour_txt = None
if not ht.empty:
    bh = int(ht.loc[ht["avg_lo"].idxmin(), "hour_local"])
    sh = int(ht.loc[ht["avg_hi"].idxmax(), "hour_local"])
    best_buy_hour_txt = dt.time(hour=bh).strftime("%I %p").lstrip("0")
    best_sell_hour_txt = dt.time(hour=sh).strftime("%I %p").lstrip("0")
if not wt.empty:
    wday = wt.loc[wt["mean"].idxmin(), "day"]
    sday = wt.loc[wt["mean"].idxmax(), "day"]
else:
    wday = sday = None

# ---- hero cards ----
now_str = pd.Timestamp.now().strftime("%I:%M %p").lstrip("0")
c1, c2, c3, c4 = st.columns(4)
e_lo, e_hi = plan["entry_zone"]
in_zone = e_lo * 0.98 <= price <= e_hi * 1.02
zone_note = "✅ current price is in this zone" if in_zone else "set a limit buy here for when it dips"
c1.markdown(
    f'<div class="card"><div class="lab">Next buy zone <span class="badge gain" style="margin-left:6px">buy the dip</span></div>'
    f'<div class="val green">{fmt(e_lo)} – {fmt(e_hi)}</div>'
    f'<div class="sub">expect a dip here · <b>{friendly_day(plan["entry_day_ideal"])}</b>'
    + (f" around <b>{best_buy_hour_txt}</b>" if best_buy_hour_txt else "")
    + f" {TZ_LABEL} · {zone_note}</div></div>',
    unsafe_allow_html=True,
)
s_lo, s_hi = plan.get("sell_zone", (plan["sell_target"] * .95, plan["sell_target"] * 1.05))
c2.markdown(
    f'<div class="card"><div class="lab">Sell target <span class="badge loss" style="margin-left:6px">sell the bounce</span></div>'
    f'<div class="val red">{fmt(s_lo)} – {fmt(s_hi)}</div>'
    f'<div class="sub">expect a bounce to here, then a pullback · take profit ~<b>{friendly_day(plan["exit_day_ideal"])}</b>'
    + (f" around <b>{best_sell_hour_txt}</b>" if best_sell_hour_txt else "")
    + f" {TZ_LABEL} · ~{plan['leg_ret_pct']:+.0f}% from entry</div></div>',
    unsafe_allow_html=True,
)
c3.markdown(
    f'<div class="card"><div class="lab">Typical hold</div>'
    f'<div class="val">{plan["hold_days"]:.0f} days</div>'
    f'<div class="sub">in around '
    f'<b>{friendly_day(plan["entry_day_ideal"])}</b> → out around <b>{friendly_day(plan["exit_day_ideal"])}</b></div></div>',
    unsafe_allow_html=True,
)
c4.markdown(
    f'<div class="card"><div class="lab">Stop / risk</div>'
    f'<div class="val">{fmt(plan["stop_loss"])}</div>'
    f'<div class="sub">risk {plan["risk_pct"]:.0f}% · reward {plan["reward_pct"]:.0f}% · 1:{plan["risk_reward"]:.1f} RR</div></div>',
    unsafe_allow_html=True,
)

# ================= BULL / BEAR TIMELINE CHART =================
st.markdown("---")
st.subheader("🐂 Bull & Bear runs — since listing, plus what's projected next")

lookback = st.slider("Chart window (days)", 90, min(365 * 4, len(df)), min(365 * 2, len(df)),
                     label_visibility="collapsed")
cut = df["date"] >= df["date"].iloc[-1] - pd.Timedelta(days=lookback)
chart_df = df.loc[cut]

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=chart_df["date"], y=chart_df["close"], name="Price",
    line=dict(color="#5b8cff", width=1.8),
    hovertemplate="%{x|%b %d %Y}: $%{y:,.4g}<extra></extra>",
))

run_colors = {"bull": "rgba(22,199,132,.13)", "bear": "rgba(234,57,67,.13)"}
last_pv = chart_df["date"].iloc[-1]
for r in runs:
    if r["end"] < chart_df["date"].iloc[0]:
        continue
    x0 = max(r["start"], chart_df["date"].iloc[0])
    fig.add_vrect(x0=x0, x1=r["end"], fillcolor=run_colors[r["type"]],
                  layer="below", line_width=0)

proj = forecast_path(df, plan)
fig.add_trace(go.Scatter(
    x=proj["date"], y=proj["price"], name="Projected path",
    line=dict(color="#f7b500", width=2.4, dash="dash"),
    hovertemplate="~%{x|%b %d %Y}: $%{y:,.4g}<extra></extra>",
))
fig.add_hrect(y0=e_lo, y1=e_hi, fillcolor="rgba(22,199,132,.10)", line_width=0,
              annotation_text="buy zone", annotation_position="bottom left")
fig.add_hline(y=plan["entry_price"], line_dash="dot", line_color="#16c784", line_width=1)
fig.add_hline(y=plan["sell_target"], line_dash="dot", line_color="#ea3943", line_width=1,
              annotation_text="target", annotation_position="top right")

fig.update_layout(
    height=430, margin=dict(l=8, r=8, t=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    yaxis_title="Price (USD)", hovermode="x unified",
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
)
fig.update_xaxes(showgrid=False)
fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
st.plotly_chart(fig, use_container_width=True)

# ---- run history table ----
r1c, r2c = st.columns([2, 1])
with r1c:
    st.markdown("**Past runs**")
    if runs:
        rows = []
        for r in runs[-14:][::-1]:
            rows.append({
                "Run": "🐂 Bull" if r["type"] == "bull" else "🐻 Bear",
                "Start": r["start"].strftime("%b %d %Y"),
                "End": r["end"].strftime("%b %d %Y"),
                "From": fmt(r["start_price"]), "To": fmt(r["end_price"]),
                "Days": r["days"], "Move": f"{r['return_pct']:+.1f}%",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=260)
    else:
        st.caption("No major swings detected at this sensitivity.")
with r2c:
    st.markdown("**Right now**")
    in_bull = cur_run_state >= 0
    st.markdown(
        f'<div class="card"><div class="lab">Current swing</div>'
        f'<div class="val">{"🐂 Bullish leg" if in_bull else "🐻 Bearish leg"}</div>'
        f'<div class="sub">{"+" if cur_run_state >= 0 else ""}{cur_run_state*100:.1f}% from the last '
        f'{"bottom" if in_bull else "top"}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="card"><div class="lab">Highs & lows</div>'
        f'<div class="val">H {fmt(stats["ath"])}</div>'
        f'<div class="sub">L {fmt(stats["atl"])} · {stats["pct_from_ath"]:+.1f}% from high · {stats["ath_date"]}</div></div>',
        unsafe_allow_html=True,
    )

# ================= TODAY + BEST TIMES =================
st.markdown("---")


@st.fragment(run_every="30s")
def live_today(pid):
    try:
        t = get_ticker(pid)
        s = get_stats_24h(pid)
        lp = float(t["price"]) if t.get("price") else None
        hi = float(s["high"]) if s and s.get("high") else None
        lo = float(s["low"]) if s and s.get("low") else None
        op = float(s["open"]) if s and s.get("open") else None
        chg24 = s.get("change_pct") if s else None
    except Exception:
        lp = hi = lo = op = chg24 = None
    now_str = pd.Timestamp.now().strftime("%I:%M:%S %p")
    st.caption(f"🔴 Live · refreshed {now_str} your time")

    a, b, c = st.columns(3)
    a.markdown(
        f'<div class="card"><div class="lab">Price now</div>'
        f'<div class="val">{fmt(lp) if lp is not None else "—"}</div>'
        f'<div class="sub">{chg24:+.2f}% 24h</div></div>' if lp is not None else '<div class="card">n/a</div>',
        unsafe_allow_html=True,
    )
    b.markdown(
        f'<div class="card"><div class="lab">Day\'s low</div>'
        f'<div class="val" style="color:#ea3943">{fmt(lo) if lo is not None else "—"}</div>'
        + (f'<div class="sub">{"price is at the low" if lp and lo and lp <= lo*1.01 else f"{((lp/lo-1)*100):+.1f}%% above it" if lp and lo else ""}</div>'
           if lo is not None else '<div class="sub">—</div>')
        + '</div>',
        unsafe_allow_html=True,
    )
    c.markdown(
        f'<div class="card"><div class="lab">Day\'s high</div>'
        f'<div class="val" style="color:#16c784">{fmt(hi) if hi is not None else "—"}</div>'
        + (f'<div class="sub">{"price is at the high" if lp and hi and lp >= hi*0.99 else f"{((lp/hi-1)*100):+.1f}%% below it" if lp and hi else ""}</div>'
           if hi is not None else '<div class="sub">—</div>')
        + '</div>',
        unsafe_allow_html=True,
    )

with st.expander("📍 Today at a glance — live prices", expanded=True):
    live_today(selected)

st.subheader("⏰ Historically best times")

t3c1, t3c2 = st.columns(2)
t3c1.markdown(
    f'<div class="card"><div class="lab">Buy time of day</div>'
    f'<div class="val green">{best_buy_hour_txt or "n/a"}</div>'
    f'<div class="sub">intraday lows tend to form here</div></div>',
    unsafe_allow_html=True,
)
t3c1.markdown(
    f'<div class="card"><div class="lab">Buy day of week</div>'
    f'<div class="val green">{wday or "n/a"}</div>'
    f'<div class="sub">historically weakest day (dips)</div></div>',
    unsafe_allow_html=True,
)
t3c2.markdown(
    f'<div class="card"><div class="lab">Sell time of day</div>'
    f'<div class="val red">{best_sell_hour_txt or "n/a"}</div>'
    f'<div class="sub">intraday highs tend to form here</div></div>',
    unsafe_allow_html=True,
)
t3c2.markdown(
    f'<div class="card"><div class="lab">Sell day of week</div>'
    f'<div class="val red">{sday or "n/a"}</div>'
    f'<div class="sub">historically strongest day (gains)</div></div>',
    unsafe_allow_html=True,
)

# ================= small charts =================
st.markdown("---")
hcol1, hcol2 = st.columns(2)
with hcol1:
    st.markdown("**Typical day** — which hours tend to rise or fall")
    shape = typical_day_shape(hourly)
    if not shape.empty:
        shape["label"] = shape["hour_local"].map(lambda h: dt.time(hour=int(h)).strftime("%I %p").lstrip("0"))
        f = px.bar(shape, x="label", y="pct",
                   color=shape["pct"].map(lambda v: "up" if v >= 0 else "down"),
                   color_discrete_map={"up": "#16c784", "down": "#ea3943"},
                   labels={"label": "", "pct": "Avg % / hour"})
        f.update_layout(height=230, margin=dict(l=4, r=4, t=4, b=4),
                        showlegend=False, xaxis_tickangle=-45,
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        f.update_yaxes(gridcolor="rgba(255,255,255,.06)")
        st.plotly_chart(f, use_container_width=True, config={"displayModeBar": False})
    else:
        st.caption("No hourly data.")
with hcol2:
    st.markdown("**By day of week** — avg daily return")
    if not wt.empty:
        f = px.bar(wt, x="day", y="mean",
                   color=wt["mean"].map(lambda v: "up" if v >= 0 else "down"),
                   color_discrete_map={"up": "#16c784", "down": "#ea3943"},
                   labels={"day": "", "mean": "Avg % / day"})
        f.update_layout(height=230, margin=dict(l=4, r=4, t=4, b=4),
                        showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)")
        f.update_yaxes(gridcolor="rgba(255,255,255,.06)")
        st.plotly_chart(f, use_container_width=True, config={"displayModeBar": False})

# ================= CHAT =================
st.markdown("---")
st.subheader(f"🤖 Ask about {BASE}")

if not wt.empty:
    _best_day = wt.loc[wt["mean"].idxmax(), "day"]; _best_day_ret = float(wt["mean"].max())
    _worst_day = wt.loc[wt["mean"].idxmin(), "day"]; _worst_day_ret = float(wt["mean"].min())
else:
    _best_day = _worst_day = None; _best_day_ret = _worst_day_ret = 0.0

_ctx = {
    "name": NAME, "base": BASE, "plan": plan, "stats": stats, "tz": TZ_LABEL,
    "best_buy_hour": best_buy_hour_txt, "best_sell_hour": best_sell_hour_txt,
    "best_day": _best_day, "best_day_ret": _best_day_ret,
    "worst_day": _worst_day, "worst_day_ret": _worst_day_ret,
}

ck = f"chat_{selected}"
st.session_state.setdefault(ck, [])

for m in st.session_state[ck]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

def ask(q):
    st.session_state[ck].append({"role": "user", "content": q})
    st.session_state[ck].append({"role": "assistant", "content": bot_answer(q, _ctx)})

quick = [
    "When should I buy and at what price?",
    "How long should I hold and when do I sell?",
    "What price should I sell at?",
    "Give me the full trade plan",
]
qc = st.columns(len(quick))
for c, q in zip(qc, quick):
    if c.button(q, key=f"q_{selected}_{hash(q) & 0xffffff}", use_container_width=True):
        ask(q)
        st.rerun()

user_q = st.chat_input(f"Ask anything about {BASE}…", key=f"cin_{selected}")
if user_q:
    ask(user_q)
    st.rerun()

st.caption(
    "Built on every Coinbase candle since this coin listed. Patterns are historical tendencies, "
    "not guarantees — size positions you can afford to lose."
)