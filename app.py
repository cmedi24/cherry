from __future__ import annotations

import csv
import html
import io
import mimetypes
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import streamlit as st


BRAND_NAME = "새로운 농원"
APP_NAME = "새로운 농원 체리 주문장부"
UPLOAD_DIR = Path("assets/product_images")

ORDER_STATUSES = ["입금 대기", "입금 완료", "포장중", "배달중", "완료", "취소"]
RECEIVE_TYPES = ["직접배달", "직접수령", "택배"]

PRODUCT_EXTRA_COLUMNS = {
    "short_description": "TEXT NOT NULL DEFAULT ''",
    "detail_description": "TEXT NOT NULL DEFAULT ''",
    "taste_notes": "TEXT NOT NULL DEFAULT ''",
    "size_notes": "TEXT NOT NULL DEFAULT ''",
    "harvest_notice": "TEXT NOT NULL DEFAULT ''",
    "storage_guide": "TEXT NOT NULL DEFAULT ''",
    "delivery_guide": "TEXT NOT NULL DEFAULT ''",
    "refund_guide": "TEXT NOT NULL DEFAULT ''",
    "main_image": "TEXT NOT NULL DEFAULT ''",
    "extra_images": "TEXT NOT NULL DEFAULT ''",
    "badges": "TEXT NOT NULL DEFAULT ''",
}


def setting(name: str, default: str = "") -> str:
    """환경변수와 Streamlit Cloud secrets를 같은 방식으로 읽습니다."""
    if os.getenv(name):
        return os.getenv(name, default)
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


DB_PATH = Path(setting("CHERRY_DB_PATH", "cherry_orders.db"))
ADMIN_PASSWORD = setting("CHERRY_ADMIN_PASSWORD", "1234")
BANK_ACCOUNT = setting("CHERRY_BANK_ACCOUNT", "농협 000-0000-0000-00 홍길동")
TELEGRAM_BOT_TOKEN = setting("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = setting("TELEGRAM_CHAT_ID", "")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def money(value: int | float) -> str:
    return f"{int(value):,}원"


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                variety TEXT NOT NULL DEFAULT '',
                weight TEXT NOT NULL,
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '판매중',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
