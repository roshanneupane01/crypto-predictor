"""Fast local candle cache (SQLite) so first load feels instant.

Coinbase rate-limits and caps candles at 300/request, so re-downloading the
full hourly history on every Streamlit rerun was the main source of lag.
This module stores each product's daily + hourly candles in a local DB and
only fetches the missing tail from the API.
"""

import datetime as dt
import os
import sqlite3
import threading

import numpy as np
import pandas as pd

import streamlit as st

_DB_LOCK = threading.Lock()
_DEFAULT_DIR = os.path.join(os.path.dirname(__file__), ".cache")
_DB_PATH = os.path.join(_DEFAULT_DIR, "candles.db")

def _conn():
    os.makedirs(_DEFAULT_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS candles ("
        "product TEXT, granularity INT, ts INT, "
        "open REAL, high REAL, low REAL, close REAL, volume REAL, "
        "PRIMARY KEY (product, granularity, ts))"
    )
    return conn

def _table_key(product_id: str, granularity: int) -> tuple[str, int]:
    return product_id.upper(), granularity

@st.cache_resource
def _shared_conn():
    return _conn()

def get_cached(product_id: str, granularity: int) -> pd.DataFrame:
    """All locally cached candles for a product, or empty."""
    conn = _shared_conn()
    product, gran = _table_key(product_id, granularity)
    with _DB_LOCK:
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE product=? AND granularity=? ORDER BY ts",
            (product, gran),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_localize(None)
    return df[["date", "open", "high", "low", "close", "volume"]]

def upsert(product_id: str, granularity: int, df: pd.DataFrame) -> None:
    if df.empty:
        return
    conn = _shared_conn()
    product, gran = _table_key(product_id, granularity)
    d = df.copy()
    d["ts"] = (d["date"].astype("int64") // 10**9).astype(int)
    payload = [
        (product, gran, int(r.ts), float(r.open), float(r.high), float(r.low),
         float(r.close), float(r.volume))
        for r in d.itertuples()
    ]
    with _DB_LOCK:
        conn.executemany(
            "INSERT OR REPLACE INTO candles (product, granularity, ts, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?,?)",
            payload,
        )
        conn.commit()

def latest_ts(product_id: str, granularity: int) -> int | None:
    conn = _shared_conn()
    product, gran = _table_key(product_id, granularity)
    with _DB_LOCK:
        row = conn.execute(
            "SELECT MAX(ts) FROM candles WHERE product=? AND granularity=?",
            (product, gran),
        ).fetchone()
    return row[0] if row and row[0] is not None else None

def oldest_ts(product_id: str, granularity: int) -> int | None:
    conn = _shared_conn()
    product, gran = _table_key(product_id, granularity)
    with _DB_LOCK:
        row = conn.execute(
            "SELECT MIN(ts) FROM candles WHERE product=? AND granularity=?",
            (product, gran),
        ).fetchone()
    return row[0] if row and row[0] is not None else None

def freshness_hours(product_id: str, granularity: int = 86400) -> float | None:
    ts = latest_ts(product_id, granularity)
    if ts is None:
        return None
    age = dt.datetime.now(dt.timezone.utc).timestamp() - ts
    return age / 3600.0
