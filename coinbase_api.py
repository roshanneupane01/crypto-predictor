"""Coinbase Exchange public API client (no auth required)."""

import datetime as dt

import pandas as pd
import requests
import streamlit as st

BASE = "https://api.exchange.coinbase.com"
_HEADERS = {"Accept": "application/json", "User-Agent": "crypto-predictor-app/1.0"}
_TIMEOUT = 20


def _get(path: str, params: dict | None = None):
    resp = requests.get(BASE + path, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# Friendly names so users can search by coin name, not just ticker.
_NAME_ALIASES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP",
    "DOGE": "Dogecoin", "ADA": "Cardano", "AVAX": "Avalanche", "LINK": "Chainlink",
    "LTC": "Litecoin", "BCH": "Bitcoin Cash", "DOT": "Polkadot", "MATIC": "Polygon",
    "SHIB": "Shiba Inu", "UNI": "Uniswap", "ATOM": "Cosmos", "XLM": "Stellar",
    "NEAR": "NEAR Protocol", "APT": "Aptos", "ARB": "Arbitrum", "OP": "Optimism",
    "FIL": "Filecoin", "AAVE": "Aave", "PEPE": "Pepe", "SUI": "Sui",
    "INJ": "Injective", "RENDER": "Render", "AKT": "Akash Network", "SEI": "Sei",
    "TAO": "Bittensor", "TRX": "TRON", "ETC": "Ethereum Classic", "HBAR": "Hedera",
    "ALGO": "Algorand", "MKR": "Maker", "CRV": "Curve DAO", "LDO": "Lido DAO",
    "SNX": "Synthetix", "COMP": "Compound", "GRT": "The Graph", "IMX": "Immutable",
    "MANA": "Decentraland", "SAND": "The Sandbox", "AXS": "Axie Infinity",
    "ENJ": "Enjin", "CHZ": "Chiliz", "BAT": "Basic Attention Token", "ZEC": "Zcash",
    "DASH": "Dash", "XTZ": "Tezos", "EOS": "EOS", "ICP": "Internet Computer",
    "STX": "Stacks", "KAVA": "Kava", "FET": "Fetch.ai", "WLD": "Worldcoin",
    "BONK": "Bonk", "WIF": "dogwifhat", "FLOKI": "Floki", "GALA": "Gala",
    "APE": "ApeCoin", "ENS": "Ethereum Name Service", "SKL": "SKALE", "ANKR": "Ankr",
    "AMP": "Amp", "NMR": "Numeraire", "RLC": "iExec RLC", "CELO": "Celo",
    "BAND": "Band Protocol", "UMA": "UMA", "BAL": "Balancer", "YFI": "yearn.finance",
    "ZRX": "0x", "POL": "Polygon Ecosystem Token", "USDC": "USD Coin", "USDT": "Tether",
}

# Popular coins used for the start-page picker + background pre-cache
POPULAR = ["BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "LINK",
           "RENDER", "AKT", "INJ", "NEAR", "APT", "ARB", "OP", "SUI", "PEPE", "SHIB"]


@st.cache_data(ttl=3600, show_spinner="Loading Coinbase product catalogue…")
def get_all_products() -> list[dict]:
    data = _get("/products")
    out = []
    for p in data:
        dn = p.get("display_name")
        if isinstance(dn, dict):
            dn = dn.get("en") or next(iter(dn.values()), None)
        out.append({
            "id": p["id"],
            "base_currency": p["base_currency"],
            "quote_currency": p["quote_currency"],
            "display_name": str(dn) if dn else p["base_currency"],
            "status": p.get("status", "offline"),
            "limit_only": bool(p.get("limit_only", False)),
        })
    out.sort(key=lambda x: (x["base_currency"], x["quote_currency"]))
    return out


@st.cache_data(ttl=86400)
def get_currency_names() -> dict:
    out = {}
    try:
        data = _get("/currencies")
        for c in data:
            if c.get("id") and c.get("name"):
                out[c["id"].upper()] = c["name"]
    except Exception:
        pass
    out.update(_NAME_ALIASES)
    return out


def _is_tradable(p: dict) -> bool:
    return p["status"] == "online" and not p["limit_only"]


def filter_products(products: list[dict], query: str, quote: str = "USD", limit: int = 8) -> list[dict]:
    """Typeahead search over tradable products, ranked by match quality."""
    if not query:
        return []
    q = query.strip().lower()
    if not q:
        return []
    names = get_currency_names()

    matches = [
        p for p in products
        if _is_tradable(p)
        and (quote is None or p["quote_currency"] == quote)
        and (q in p["id"].lower()
             or q in p["base_currency"].lower()
             or q in str(p["display_name"]).lower()
             or q in names.get(p["base_currency"].upper(), "").lower())
    ]

    def rank(p: dict):
        b = p["base_currency"].lower()
        nm = names.get(p["base_currency"].upper(), "").lower()
        if b == q:
            tier = 0
        elif b.startswith(q) or p["id"].lower().startswith(q):
            tier = 1
        elif nm and nm.startswith(q):
            tier = 2
        else:
            tier = 3
        return (tier, len(b), p["id"])

    matches.sort(key=rank)
    return matches[:limit]


@st.cache_data(ttl=300)
def get_product(product_id: str) -> dict:
    return _get(f"/products/{product_id}")


@st.cache_data(ttl=30)
def get_ticker(product_id: str) -> dict:
    return _get(f"/products/{product_id}/ticker")


@st.cache_data(ttl=30)
def get_stats_24h(product_id: str) -> dict | None:
    try:
        s = _get(f"/products/{product_id}/stats")
        o, lp = float(s["open"]), float(s["last"])
        s["change_pct"] = (lp - o) / o * 100 if o else 0.0
        return s
    except Exception:
        return None
