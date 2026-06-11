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
                quantity INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                receive_type TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                receive_date TEXT NOT NULL DEFAULT '',
                request_note TEXT NOT NULL DEFAULT '',
                depositor_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '입금 대기',
                paid_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        migrate_products(conn)

        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            insert_sample_products(conn)
        else:
            enrich_existing_sample_products(conn)


def migrate_products(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
    for column, definition in PRODUCT_EXTRA_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE products ADD COLUMN {column} {definition}")


def insert_sample_products(conn: sqlite3.Connection) -> None:
    samples = sample_products()
    conn.executemany(
        """
        INSERT INTO products (
            name, variety, weight, price, stock, description, status, created_at,
            short_description, detail_description, taste_notes, size_notes, harvest_notice,
            storage_guide, delivery_guide, refund_guide, main_image, extra_images, badges
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        samples,
    )


def enrich_existing_sample_products(conn: sqlite3.Connection) -> None:
    legacy_names = {
        "프리미엄 생체리": 0,
        "가정용 실속 체리": 1,
        "소량 맛보기 체리": 2,
    }
    for old_name, sample_index in legacy_names.items():
        row = conn.execute("SELECT id FROM products WHERE name = ?", (old_name,)).fetchone()
        if row:
            apply_sample_product_details(conn, row["id"], sample_products()[sample_index], rename=True)

    for sample in sample_products():
        name = sample[0]
        row = conn.execute("SELECT id, short_description FROM products WHERE name = ?", (name,)).fetchone()
        if not row or row["short_description"]:
            continue
        apply_sample_product_details(conn, row["id"], sample, rename=False)


def apply_sample_product_details(conn: sqlite3.Connection, product_id: int, sample: tuple, rename: bool) -> None:
    name_sql = "name = ?," if rename else ""
    params = []
    if rename:
        params.append(sample[0])
    params.extend(
        [
            sample[1],
            sample[2],
            sample[3],
            sample[5],
            sample[8],
            sample[9],
            sample[10],
            sample[11],
            sample[12],
            sample[13],
            sample[14],
            sample[15],
            sample[16],
            sample[17],
            sample[18],
            product_id,
        ]
    )
    conn.execute(
        f"""
        UPDATE products
        SET {name_sql} variety = ?, weight = ?, price = ?, description = ?, short_description = ?,
            detail_description = ?, taste_notes = ?, size_notes = ?, harvest_notice = ?,
            storage_guide = ?, delivery_guide = ?, refund_guide = ?, main_image = ?,
            extra_images = ?, badges = ?
        WHERE id = ?
        """,
        params,
    )


def sample_products() -> list[tuple]:
    created = now_text()
    image = "assets/product_images/sample-premium.png"
    family_image = "assets/product_images/sample-family.png"
    gift_image = "assets/product_images/sample-gift.png"
    refund = "파손이나 변질 시 수령 당일 사진 확인 후 처리해드립니다."
    return [
        (
            "프리미엄 생체리 1kg",
            "스위트하트",
            "1kg",
            18000,
            25,
            "당도가 높고 과육이 단단한 프리미엄 체리입니다.",
            "판매중",
            created,
            "당도가 높고 과육이 단단한 프리미엄 체리",
            "신선하게 수확한 체리를 선별하여 보내드립니다. 알이 단단하고 색이 고른 상품 위주로 담았습니다.",
            "달콤함이 강하고 산미는 적은 편입니다.",
            "한입에 먹기 좋은 중대과 중심 구성입니다.",
            "주문 당일 또는 전날 수확분을 기준으로 선별합니다.",
            "수령 후 냉장 보관하고 물기는 먹기 직전에 씻어주세요. 빠른 섭취를 권장합니다.",
            "논산 직접배달 가능 / 택배 가능",
            refund,
            image,
            f"{image}\nassets/product_images/cherry-hero.png",
            "당일수확,직접배달,인기",
        ),
        (
            "실속형 생체리 2kg",
            "레이니어",
            "2kg",
            32000,
            18,
            "가족이 함께 즐기기 좋은 실속형 구성입니다.",
            "판매중",
            created,
            "가족이 함께 즐기기 좋은 실속형 구성",
            "크기와 색이 조금씩 다를 수 있지만 맛과 신선도를 우선해 구성한 실속형 체리입니다.",
            "부드러운 단맛과 은은한 산미가 함께 느껴집니다.",
            "가정용으로 먹기 좋은 혼합 크기입니다.",
            "상태가 좋은 체리를 골라 넉넉하게 담아드립니다.",
            "냉장 보관 후 3~5일 안에 드시면 가장 좋습니다.",
            "논산 및 인근 지역 직접배달 가능 / 택배 가능",
            refund,
            family_image,
            f"{family_image}\nassets/product_images/cherry-hero.png",
            "직접배달,한정 수량",
        ),
        (
            "선물용 특대과 체리 2kg",
            "좌등금",
            "2kg",
            39000,
            8,
            "선물하기 좋은 특대과 선별 상품입니다.",
            "판매중",
            created,
            "선물하기 좋은 특대과 선별 상품",
            "크기와 색감을 한 번 더 확인해 담는 선물용 구성입니다. 중요한 선물이나 감사 인사용으로 추천합니다.",
            "진한 단맛과 풍부한 과즙감이 좋습니다.",
            "큼직한 특대과 위주로 선별합니다.",
            "수확 후 무른 과를 제외하고 포장 전 한 번 더 확인합니다.",
            "수령 즉시 냉장 보관하고 선물 전까지 차갑게 유지해주세요.",
            "직접배달 우선 / 택배 가능 여부는 주문 전 확인 권장",
            refund,
            gift_image,
            f"{gift_image}\nassets/product_images/cherry-hero.png",
            "인기,품절임박,직접배달",
        ),
    ]


def rows(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(query, params).fetchone()


def make_order_no(order_id: int) -> str:
    return f"CH{datetime.now().strftime('%Y%m%d')}-{order_id:04d}"


def send_telegram_new_order(order: sqlite3.Row) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    message = f"""[{BRAND_NAME} 체리 주문] 새 주문이 들어왔습니다.
주문자: {order['customer_name']}
상품: {order['product_name']}
수량: {order['quantity']}
총금액: {money(order['total_price'])}
수령 방식: {order['receive_type']}
주소: {order['address']}
입금자명: {order['depositor_name']}"""
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": message}).encode()
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        urllib.request.urlopen(url, data=data, timeout=5).read()
    except Exception:
        # 알림 실패가 주문 접수를 막지 않도록 조용히 무시합니다.
        pass


def set_product_auto_status(conn: sqlite3.Connection, product_id: int) -> None:
    product = conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        return
    if product["stock"] <= 0:
        conn.execute("UPDATE products SET status = '품절', stock = 0 WHERE id = ?", (product_id,))


def create_order(form: dict) -> tuple[bool, str, str | None]:
    with get_conn() as conn:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (form["product_id"],)).fetchone()
        if not product:
            return False, "상품을 찾을 수 없습니다.", None
        if product["status"] != "판매중" or product["stock"] < form["quantity"]:
            return False, "재고가 부족하거나 품절된 상품입니다.", None

        total_price = product["price"] * form["quantity"]
        created_at = now_text()
        cur = conn.execute(
            """
            INSERT INTO orders (
                order_no, customer_name, phone, product_id, product_name, quantity, total_price,
                receive_type, address, receive_date, request_note, depositor_name,
                status, created_at, updated_at
            )
            VALUES ('TEMP', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '입금 대기', ?, ?)
            """,
            (
                form["customer_name"],
                form["phone"],
                product["id"],
                product["name"],
                form["quantity"],
                total_price,
                form["receive_type"],
                form["address"],
                form["receive_date"],
                form["request_note"],
                form["depositor_name"],
                created_at,
                created_at,
            ),
        )
        order_id = cur.lastrowid
        order_no = make_order_no(order_id)
        conn.execute("UPDATE orders SET order_no = ? WHERE id = ?", (order_no, order_id))
        conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (form["quantity"], product["id"]))
        set_product_auto_status(conn, product["id"])

    order = one("SELECT * FROM orders WHERE order_no = ?", (order_no,))
    if order:
        send_telegram_new_order(order)
    return True, "주문이 접수되었습니다.", order_no


def update_order_status(order_id: int, new_status: str) -> None:
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order or order["status"] == new_status:
            return

        updates = ["status = ?", "updated_at = ?"]
        params: list = [new_status, now_text()]
        if new_status == "입금 완료" and not order["paid_at"]:
            updates.append("paid_at = ?")
            params.append(now_text())
        if new_status == "완료":
            updates.append("completed_at = ?")
            params.append(now_text())

        params.append(order_id)
        conn.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = ?", params)

        if new_status == "취소" and order["status"] != "취소":
            conn.execute("UPDATE products SET stock = stock + ?, status = '판매중' WHERE id = ?", (order["quantity"], order["product_id"]))


def cancel_order(order_id: int) -> None:
    update_order_status(order_id, "취소")


def create_csv_download(order_filter: str = "all") -> bytes:
    where = ""
    params: tuple = ()
    if order_filter == "waiting":
        where = "WHERE status = ?"
        params = ("입금 대기",)
    elif order_filter == "delivery":
        where = "WHERE status = ?"
        params = ("배달중",)

    order_rows = rows(
        f"""
        SELECT order_no, customer_name, phone, address, product_name, quantity, total_price,
               depositor_name, status, request_note, created_at
        FROM orders
        {where}
        ORDER BY created_at DESC
        """,
        params,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["주문번호", "주문자명", "연락처", "주소", "상품명", "수량", "총금액", "입금자명", "주문상태", "요청사항", "주문일시"])
    for order in order_rows:
        writer.writerow([order[key] for key in order.keys()])
    return output.getvalue().encode("utf-8-sig")


def local_image_to_data_uri(path_text: str) -> str:
    path = Path(path_text)
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    import base64

    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def placeholder_image() -> str:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 620">
      <defs>
        <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
          <stop stop-color="#fff1f2"/><stop offset="1" stop-color="#fee2e2"/>
        </linearGradient>
      </defs>
      <rect width="900" height="620" fill="url(#bg)"/>
      <circle cx="365" cy="345" r="92" fill="#be123c"/>
      <circle cx="492" cy="340" r="104" fill="#9f1239"/>
      <circle cx="443" cy="248" r="78" fill="#e11d48"/>
      <path d="M420 230 C430 130 505 98 592 116" fill="none" stroke="#166534" stroke-width="22" stroke-linecap="round"/>
      <ellipse cx="598" cy="116" rx="72" ry="28" fill="#15803d" transform="rotate(-12 598 116)"/>
      <text x="450" y="535" text-anchor="middle" font-size="46" font-family="Arial" font-weight="700" fill="#881337">Fresh Cherry</text>
    </svg>
    """
    return "data:image/svg+xml;charset=utf-8," + urllib.parse.quote(svg)


def image_src(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return placeholder_image()
    if value.startswith(("http://", "https://", "data:")):
        return value
    return local_image_to_data_uri(value) or placeholder_image()


def split_images(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").replace(",", "\n").splitlines() if line.strip()]


def product_summary(product: sqlite3.Row) -> str:
    return product["short_description"] or product["description"] or "신선하게 선별한 체리 상품입니다."


def product_detail(product: sqlite3.Row, key: str, fallback: str) -> str:
    return product[key] or product["description"] or fallback


def save_uploaded_image(uploaded_file, prefix: str) -> str:
    if not uploaded_file:
        return ""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower() or ".png"
    safe_prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in ("-", "_"))[:32] or "product"
    filename = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{suffix}"
    target = UPLOAD_DIR / filename
    target.write_bytes(uploaded_file.getbuffer())
    return str(target).replace("\\", "/")


def save_uploaded_images(uploaded_files, prefix: str) -> list[str]:
    return [path for file in uploaded_files or [] if (path := save_uploaded_image(file, prefix))]


def apply_style() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="🍒", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(
        """
        <style>
        :root {
            --cherry: #9f1239;
            --cherry-deep: #881337;
            --cherry-soft: #fff1f2;
            --rose-line: #fecdd3;
            --leaf: #166534;
            --leaf-soft: #dcfce7;
            --ink: #27272a;
            --muted: #71717a;
            --paper: #ffffff;
        }
        .stApp { background: #fffafa; color: var(--ink); }
        header[data-testid="stHeader"] { height: 0; background: transparent; }
        div[data-testid="stToolbar"], #MainMenu, footer { display: none; visibility: hidden; }
        h1, h2, h3 { letter-spacing: 0; }
        .block-container {
            padding-top: calc(1.2rem + env(safe-area-inset-top));
            padding-bottom: calc(2rem + env(safe-area-inset-bottom));
        }
        .brand-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 10px 0 14px;
        }
        .brand-name {
            font-size: 24px;
            font-weight: 950;
            color: var(--cherry-deep);
            line-height: 1.1;
        }
        .brand-sub {
            margin-top: 3px;
            color: var(--muted);
            font-size: 14px;
            font-weight: 700;
        }
        .brand-mark {
            min-width: 92px;
            text-align: center;
            padding: 9px 11px;
            border-radius: 8px;
            background: #fff;
            border: 1px solid #f2d2d8;
            color: var(--leaf);
            font-weight: 900;
            box-shadow: 0 6px 18px rgba(22, 101, 52, .07);
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #f1d6dc;
            border-radius: 8px;
            padding: 14px;
        }
        .hero {
            position: relative;
            min-height: 220px;
            border-radius: 8px;
            overflow: hidden;
            background-size: cover;
            background-position: center;
            margin-bottom: 14px;
            border: 1px solid #f5c2cb;
        }
        .hero::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, rgba(68, 16, 28, .82), rgba(68, 16, 28, .34), rgba(68, 16, 28, .08));
        }
        .hero-content {
            position: relative;
            z-index: 1;
            max-width: 620px;
            padding: 28px 22px;
            color: white;
        }
        .hero-title { font-size: clamp(30px, 7vw, 54px); line-height: 1.08; font-weight: 900; margin-bottom: 12px; }
        .hero-copy { font-size: 17px; line-height: 1.55; margin-bottom: 18px; }
        .hero-tags, .badge-row { display: flex; gap: 8px; flex-wrap: wrap; }
        .hero-tag, .badge {
            display: inline-flex;
            align-items: center;
            min-height: 28px;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 800;
        }
        .hero-tag { background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.28); color: white; }
        .badge { background: var(--cherry-soft); color: var(--cherry); border: 1px solid #ffe4e6; }
        .badge.green { background: var(--leaf-soft); color: var(--leaf); border-color: #bbf7d0; }
        .badge.gray { background: #f4f4f5; color: #52525b; border-color: #e4e4e7; }
        .notice-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin: 14px 0 18px;
        }
        .notice-item, .info-card, .product-card, .detail-section {
            background: white;
            border: 1px solid #f2d2d8;
            border-radius: 8px;
            box-shadow: 0 8px 24px rgba(159, 18, 57, 0.06);
        }
        .notice-item { padding: 14px; }
        .notice-label { font-size: 13px; color: var(--muted); margin-bottom: 5px; }
        .notice-value { font-size: 17px; font-weight: 900; color: var(--cherry-deep); }
        .trust-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 12px 0 18px;
        }
        .trust-item {
            background: #ffffff;
            border: 1px solid #f2d2d8;
            border-radius: 8px;
            padding: 13px;
        }
        .trust-title { font-weight: 900; color: var(--cherry-deep); margin-bottom: 5px; }
        .trust-copy { color: var(--muted); font-size: 14px; line-height: 1.45; }
        .easy-order { margin: 12px 0 18px; }
        .easy-card {
            background: #fff;
            border: 1px solid #f2d2d8;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 8px 24px rgba(159, 18, 57, 0.06);
        }
        .easy-card h3 { margin: 0 0 10px; color: var(--cherry-deep); }
        .step-list {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .step {
            background: var(--cherry-soft);
            border-radius: 8px;
            padding: 11px;
            border: 1px solid #ffe4e6;
        }
        .step-num { font-size: 13px; font-weight: 900; color: var(--cherry); }
        .step-title { font-weight: 900; margin: 4px 0; }
        .step-copy { font-size: 13px; color: var(--muted); line-height: 1.38; }
        .product-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
        }
        .product-card { overflow: hidden; }
        .product-image {
            width: 100%;
            aspect-ratio: 4 / 3;
            object-fit: cover;
            display: block;
            background: #fff1f2;
        }
        .product-body { padding: 14px; }
        .product-title { font-size: 20px; font-weight: 900; margin: 8px 0 6px; color: var(--ink); }
        .product-meta { color: var(--muted); margin-bottom: 8px; }
        .product-price { font-size: 23px; font-weight: 900; color: var(--cherry); margin: 8px 0; }
        .product-desc { min-height: 42px; line-height: 1.45; }
        .stock-line { font-size: 14px; color: var(--leaf); font-weight: 800; margin: 8px 0 10px; }
        .detail-hero {
            display: grid;
            grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr);
            gap: 18px;
            align-items: start;
        }
        .detail-main-image {
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: cover;
            border-radius: 8px;
            border: 1px solid #f2d2d8;
        }
        .thumb-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
        .thumb-row img { width: 100%; aspect-ratio: 1 / 1; object-fit: cover; border-radius: 8px; border: 1px solid #f2d2d8; }
        .detail-panel, .detail-section { padding: 16px; }
        .detail-title { font-size: clamp(27px, 6vw, 40px); font-weight: 900; line-height: 1.14; margin: 8px 0; }
        .detail-price { font-size: 31px; font-weight: 900; color: var(--cherry); margin: 8px 0; }
        .detail-section { margin-top: 12px; }
        .detail-section h4 { margin: 0 0 8px; font-size: 17px; color: var(--cherry-deep); }
        .big-total { font-size: 26px; font-weight: 900; color: var(--cherry); }
        .stButton button, .stDownloadButton button {
            min-height: 46px;
            border-radius: 8px;
            font-weight: 900;
        }
        div[data-testid="stTabs"] div[role="tablist"] {
            background: #fffafa;
            border-bottom: 1px solid #f2d2d8;
            padding: 6px 0;
            gap: 4px;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            min-height: 44px;
            color: var(--cherry-deep);
            background: #ffffff;
            border: 1px solid #f2d2d8;
            border-radius: 8px;
            margin-right: 4px;
            opacity: 1;
        }
        div[data-testid="stTabs"] button[role="tab"] p {
            color: var(--cherry-deep) !important;
            font-weight: 900;
            font-size: 15px;
            white-space: nowrap;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: var(--cherry);
            border-color: var(--cherry);
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {
            color: #ffffff !important;
        }
        @media (max-width: 900px) {
            .product-grid, .notice-grid, .detail-hero, .trust-grid, .step-list { grid-template-columns: 1fr; }
            .hero { min-height: 210px; }
            .hero::after { background: linear-gradient(180deg, rgba(68,16,28,.78), rgba(68,16,28,.38)); }
        }
        @media (max-width: 640px) {
            .block-container {
                padding-top: calc(3rem + env(safe-area-inset-top));
                padding-left: 12px;
                padding-right: 12px;
            }
            .brand-bar { padding: 4px 0 8px; align-items: flex-start; }
            .brand-name { font-size: 22px; }
            .brand-sub { font-size: 13px; }
            .brand-mark { min-width: 74px; font-size: 13px; padding: 7px 8px; }
            .hero { min-height: 168px; margin-bottom: 8px; }
            .hero-content { padding: 18px 14px; }
            .hero-title { font-size: 30px; margin-bottom: 8px; }
            .hero-copy { font-size: 14px; line-height: 1.42; margin-bottom: 0; }
            .hero-tags { gap: 5px; margin-bottom: 8px; }
            .hero-tag { min-height: 24px; padding: 3px 8px; font-size: 12px; }
            .notice-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 6px;
                margin: 8px 0 10px;
            }
            .notice-item { padding: 9px 7px; }
            .notice-label { font-size: 11px; margin-bottom: 3px; }
            .notice-value { font-size: 13px; line-height: 1.25; }
            .easy-order { display: none; }
            .easy-card { padding: 11px; }
            .easy-card h3 { font-size: 18px; margin-bottom: 7px; }
            .step-list { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; }
            .step { padding: 8px 6px; }
            .step-num { font-size: 10px; }
            .step-title { font-size: 12px; margin: 3px 0; }
            .step-copy { display: none; }
            .trust-grid { display: none; }
            .notice-item, .product-body, .detail-panel, .detail-section { padding: 12px; }
            .product-image { aspect-ratio: 16 / 9; }
            div[data-testid="stTabs"] div[role="tablist"] {
                position: sticky;
                top: calc(0.4rem + env(safe-area-inset-top));
                z-index: 50;
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                overflow: visible;
                column-gap: 4px;
                box-shadow: 0 6px 18px rgba(159, 18, 57, 0.08);
                border: 1px solid #f2d2d8;
                border-radius: 8px;
                padding: 5px;
            }
            div[data-testid="stTabs"] button[role="tab"] {
                width: 100%;
                min-width: 0;
                min-height: 42px;
                padding-left: 4px;
                padding-right: 4px;
                margin-right: 0;
            }
            div[data-testid="stTabs"] button[role="tab"] p {
                font-size: 14px;
                line-height: 1.1;
            }
            .stButton button, .stDownloadButton button { min-height: 48px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    color = "green" if status in ("판매중", "입금 완료", "완료") else "gray" if status in ("품절", "취소") else ""
    return f"<span class='badge {color}'>{esc(status)}</span>"


def render_badges(product: sqlite3.Row) -> str:
    badge_values = [badge.strip() for badge in (product["badges"] or "").split(",") if badge.strip()]
    if product["stock"] <= 5 and product["status"] == "판매중" and "품절임박" not in badge_values:
        badge_values.append("품절임박")
    if not badge_values:
        badge_values = ["당일수확", "직접배달"]
    return "".join(f"<span class='badge'>{esc(badge)}</span>" for badge in badge_values)


def brand_header() -> None:
    st.markdown(
        f"""
        <div class="brand-bar">
            <div>
                <div class="brand-name">{BRAND_NAME}</div>
                <div class="brand-sub">농원에서 바로 안내하는 제철 체리 주문</div>
            </div>
            <div class="brand-mark">빠른<br>주문확인</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main_banner() -> None:
    hero_image = image_src("assets/product_images/cherry-hero.png")
    st.markdown(
        f"""
        <section class="hero" style="background-image: url('{hero_image}')">
            <div class="hero-content">
                <div class="hero-tags">
                    <span class="hero-tag">오늘 수확한 신선한 체리</span>
                    <span class="hero-tag">직접배달 가능</span>
                    <span class="hero-tag">한정 수량 판매중</span>
                </div>
                <div class="hero-title">{BRAND_NAME} 체리</div>
                <div class="hero-copy">상품을 고르고 수령 방법을 남기면 주문이 접수됩니다. 입금 확인부터 포장·배달 상태까지 한곳에서 확인하세요.</div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def notice_box() -> None:
    st.markdown(
        """
        <div class="notice-grid">
            <div class="notice-item">
                <div class="notice-label">오늘 주문 마감</div>
                <div class="notice-value">오후 5시</div>
            </div>
            <div class="notice-item">
                <div class="notice-label">배달 가능 지역</div>
                <div class="notice-value">논산 및 인근</div>
            </div>
            <div class="notice-item">
                <div class="notice-label">택배 가능 여부</div>
                <div class="notice-value">가능</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def easy_order_guide() -> None:
    st.markdown(
        """
        <div class="easy-order">
            <div class="easy-card">
                <h3>주문은 간단하게 진행됩니다</h3>
                <div class="step-list">
                    <div class="step">
                        <div class="step-num">STEP 1</div>
                        <div class="step-title">상품 선택</div>
                        <div class="step-copy">사진, 중량, 가격, 남은 재고를 보고 고릅니다.</div>
                    </div>
                    <div class="step">
                        <div class="step-num">STEP 2</div>
                        <div class="step-title">수령 정보 입력</div>
                        <div class="step-copy">배달, 직접수령, 택배 중 편한 방법을 선택합니다.</div>
                    </div>
                    <div class="step">
                        <div class="step-num">STEP 3</div>
                        <div class="step-title">주문 상태 확인</div>
                        <div class="step-copy">주문번호와 연락처로 입금·포장·배달 상태를 확인합니다.</div>
                    </div>
                </div>
                <p class="trust-copy" style="margin-top: 12px;">주문 후 안내된 계좌로 입금하면 관리자가 확인하고 상태를 업데이트합니다.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def trust_points() -> None:
    st.markdown(
        f"""
        <div class="trust-grid">
            <div class="trust-item">
                <div class="trust-title">{BRAND_NAME} 직접 판매</div>
                <div class="trust-copy">상품 안내와 주문 관리를 한곳에서 확인합니다.</div>
            </div>
            <div class="trust-item">
                <div class="trust-title">남은 재고 표시</div>
                <div class="trust-copy">한정 수량을 보고 바로 주문할 수 있습니다.</div>
            </div>
            <div class="trust-item">
                <div class="trust-title">상태 조회 가능</div>
                <div class="trust-copy">입금 대기부터 완료까지 주문 상태를 확인합니다.</div>
            </div>
            <div class="trust-item">
                <div class="trust-title">모바일 우선</div>
                <div class="trust-copy">카카오톡을 보듯 휴대폰에서 크게 누르게 만들었습니다.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def product_list_view() -> None:
    st.subheader("상품 목록")
    products = rows("SELECT * FROM products ORDER BY status DESC, id DESC")
    if not products:
        st.info("등록된 상품이 없습니다.")
        return

    st.markdown("<div class='product-grid'>", unsafe_allow_html=True)
    for product in products:
        st.markdown(
            f"""
            <div class="product-card">
                <img class="product-image" src="{image_src(product['main_image'])}" alt="{esc(product['name'])}">
                <div class="product-body">
                    <div class="badge-row">{status_badge(product['status'])}{render_badges(product)}</div>
                    <div class="product-title">{esc(product['name'])}</div>
                    <div class="product-meta">{esc(product['weight'])} · {esc(product['variety'])}</div>
                    <div class="product-price">{money(product['price'])}</div>
                    <div class="product-desc">{esc(product_summary(product))}</div>
                    <div class="stock-line">남은 재고 {int(product['stock'])}개</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_order, col_detail = st.columns(2)
        disabled = product["status"] != "판매중" or product["stock"] <= 0
        if col_order.button("주문하기", key=f"card_order_{product['id']}", type="primary", use_container_width=True, disabled=disabled):
            st.session_state["selected_product_id"] = product["id"]
            st.session_state["buyer_tab_hint"] = "주문"
            st.info("상단의 주문 탭에서 선택한 상품으로 주문을 이어가세요.")
        if col_detail.button("상세보기", key=f"card_detail_{product['id']}", use_container_width=True):
            st.session_state["detail_product_id"] = product["id"]
            st.session_state["buyer_tab_hint"] = "상세"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def product_detail_view() -> None:
    st.subheader("상품 상세")
    products = rows("SELECT * FROM products ORDER BY id DESC")
    if not products:
        st.info("등록된 상품이 없습니다.")
        return

    selected_id = st.session_state.get("detail_product_id") or products[0]["id"]
    product_ids = [p["id"] for p in products]
    if selected_id not in product_ids:
        selected_id = products[0]["id"]
    selected_index = product_ids.index(selected_id)
    labels = [f"{p['name']} · {p['weight']}" for p in products]
    picked_label = st.selectbox("상세 볼 상품", labels, index=selected_index)
    product = products[labels.index(picked_label)]
    st.session_state["detail_product_id"] = product["id"]

    images = [product["main_image"]] + split_images(product["extra_images"])
    images = [img for img in images if img]
    if not images:
        images = [""]
    thumbs = "".join(f'<img src="{image_src(img)}" alt="추가 이미지">' for img in images[:4])

    st.markdown(
        f"""
        <div class="detail-hero">
            <div>
                <img class="detail-main-image" src="{image_src(images[0])}" alt="{esc(product['name'])}">
                <div class="thumb-row">{thumbs}</div>
            </div>
            <div class="detail-panel">
                <div class="badge-row">{status_badge(product['status'])}{render_badges(product)}</div>
                <div class="detail-title">{esc(product['name'])}</div>
                <div class="product-meta">{esc(product['weight'])} · {esc(product['variety'])}</div>
                <div class="detail-price">{money(product['price'])}</div>
                <p>{esc(product_summary(product))}</p>
                <p class="stock-line">남은 재고 {int(product['stock'])}개</p>
            </div>
        </div>
        <div class="detail-section"><h4>상세 설명</h4><p>{esc(product_detail(product, 'detail_description', '신선한 체리를 선별해 보내드립니다.'))}</p></div>
        <div class="detail-section"><h4>맛 특징</h4><p>{esc(product_detail(product, 'taste_notes', '달콤하고 산뜻한 체리 맛을 즐길 수 있습니다.'))}</p></div>
        <div class="detail-section"><h4>크기감</h4><p>{esc(product_detail(product, 'size_notes', '먹기 좋은 크기 위주로 구성합니다.'))}</p></div>
        <div class="detail-section"><h4>수확/선별 안내</h4><p>{esc(product_detail(product, 'harvest_notice', '상태가 좋은 체리를 선별해 포장합니다.'))}</p></div>
        <div class="detail-section"><h4>보관 방법</h4><p>{esc(product_detail(product, 'storage_guide', '수령 후 냉장 보관하고 빠르게 섭취해주세요.'))}</p></div>
        <div class="detail-section"><h4>배송 안내</h4><p>{esc(product_detail(product, 'delivery_guide', '직접배달 또는 택배 가능 여부를 주문 시 확인합니다.'))}</p></div>
        <div class="detail-section"><h4>교환/환불 안내</h4><p>{esc(product_detail(product, 'refund_guide', '파손이나 변질은 수령 당일 사진 확인 후 처리합니다.'))}</p></div>
        """,
        unsafe_allow_html=True,
    )
    disabled = product["status"] != "판매중" or product["stock"] <= 0
    if st.button("이 상품 주문하기", key=f"detail_order_{product['id']}", type="primary", use_container_width=True, disabled=disabled):
        st.session_state["selected_product_id"] = product["id"]
        st.session_state["buyer_tab_hint"] = "주문"
        st.success("주문 탭에서 선택한 상품으로 주문을 이어가세요.")


def buyer_order_view() -> None:
    st.subheader("주문하기")
    products = rows("SELECT * FROM products WHERE status = '판매중' AND stock > 0 ORDER BY id DESC")
    if not products:
        st.info("현재 주문 가능한 상품이 없습니다.")
        return

    labels = {f"{p['name']} {p['weight']} - {money(p['price'])} / 재고 {p['stock']}개": p for p in products}
    product_ids = [p["id"] for p in products]
    selected_product_id = st.session_state.get("selected_product_id")
    selected_index = product_ids.index(selected_product_id) if selected_product_id in product_ids else 0

    with st.form("order_form"):
        customer_name = st.text_input("주문자 이름")
        phone = st.text_input("연락처")
        selected_label = st.selectbox("상품 선택", list(labels.keys()), index=selected_index)
        selected_product = labels[selected_label]
        quantity = st.number_input("수량", min_value=1, max_value=max(1, selected_product["stock"]), step=1)
        receive_type = st.radio("수령 방식", RECEIVE_TYPES, horizontal=True)
        address = st.text_area("주소 또는 수령 장소", placeholder="직접수령이면 수령 장소 메모를 적어주세요.")
        receive_date = st.date_input("희망 수령일")
        request_note = st.text_area("요청사항", placeholder="문 앞에 두기, 오후 배달 희망 등")
        depositor_name = st.text_input("입금자명", value=customer_name)
        st.markdown(f"<div class='big-total'>총 결제금액 {money(selected_product['price'] * quantity)}</div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("주문하기", type="primary", use_container_width=True)

    if submitted:
        required = [customer_name.strip(), phone.strip(), depositor_name.strip()]
        if not all(required):
            st.error("주문자 이름, 연락처, 입금자명을 입력해주세요.")
            return
        ok, message, order_no = create_order(
            {
                "customer_name": customer_name.strip(),
                "phone": phone.strip(),
                "product_id": selected_product["id"],
                "quantity": int(quantity),
                "receive_type": receive_type,
                "address": address.strip(),
                "receive_date": str(receive_date),
                "request_note": request_note.strip(),
                "depositor_name": depositor_name.strip(),
            }
        )
        if ok and order_no:
            st.session_state["last_order_no"] = order_no
            st.success(message)
            st.rerun()
        else:
            st.error(message)


def order_complete_view() -> None:
    st.subheader("주문 완료")
    order_no = st.session_state.get("last_order_no")
    if not order_no:
        st.info("주문을 완료하면 이곳에 주문 정보가 표시됩니다.")
        return
    order = one("SELECT * FROM orders WHERE order_no = ?", (order_no,))
    if not order:
        st.info("주문 정보를 찾을 수 없습니다.")
        return

    st.markdown(
        f"""
        <div class="detail-section">
            {status_badge(order['status'])}
            <h3>주문번호 {esc(order['order_no'])}</h3>
            <p>상품: {esc(order['product_name'])} · {int(order['quantity'])}개</p>
            <p class="big-total">총 결제금액 {money(order['total_price'])}</p>
            <p><b>입금 계좌</b><br>{esc(BANK_ACCOUNT)}</p>
            <p><b>입금자명</b> {esc(order['depositor_name'])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def order_lookup_view() -> None:
    st.subheader("주문 조회")
    with st.form("lookup_form"):
        order_no = st.text_input("주문번호")
        phone = st.text_input("연락처")
        submitted = st.form_submit_button("주문 상태 확인", use_container_width=True)
    if submitted:
        order = one("SELECT * FROM orders WHERE order_no = ? AND phone = ?", (order_no.strip(), phone.strip()))
        if not order:
            st.error("주문번호와 연락처가 일치하는 주문을 찾을 수 없습니다.")
            return
        st.markdown(
            f"""
            <div class="detail-section">
                {status_badge(order['status'])}
                <h3>{esc(order['product_name'])}</h3>
                <p>수량 {int(order['quantity'])}개 · {money(order['total_price'])}</p>
                <p>수령 방식: {esc(order['receive_type'])} / 희망일: {esc(order['receive_date'])}</p>
                <p>요청사항: {esc(order['request_note'] or '-')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def buyer_page() -> None:
    brand_header()
    main_banner()
    notice_box()
    easy_order_guide()
    trust_points()
    tab_products, tab_detail, tab_order, tab_done, tab_lookup = st.tabs(["상품", "상세", "주문", "완료", "조회"])
    if st.session_state.get("buyer_tab_hint"):
        st.caption(f"안내: {st.session_state.pop('buyer_tab_hint')} 탭에서 계속 진행할 수 있습니다.")
    with tab_products:
        product_list_view()
    with tab_detail:
        product_detail_view()
    with tab_order:
        buyer_order_view()
    with tab_done:
        order_complete_view()
    with tab_lookup:
        order_lookup_view()


def admin_login() -> bool:
    if st.session_state.get("admin_logged_in"):
        return True
    st.title("관리자 로그인")
    password = st.text_input("관리자 비밀번호", type="password")
    if st.button("로그인", type="primary", use_container_width=True):
        if password == ADMIN_PASSWORD:
            st.session_state["admin_logged_in"] = True
            st.rerun()
        else:
            st.error("비밀번호가 맞지 않습니다.")
    return False


def dashboard_view() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    today_orders = rows("SELECT * FROM orders WHERE created_at LIKE ?", (f"{today}%",))
    status_counts = {status: 0 for status in ORDER_STATUSES}
    for order in today_orders:
        status_counts[order["status"]] += 1

    cols = st.columns(3)
    cols[0].metric("오늘 총 주문 건수", f"{len(today_orders)}건")
    cols[1].metric("오늘 총 판매 수량", f"{sum(o['quantity'] for o in today_orders if o['status'] != '취소')}개")
    cols[2].metric("오늘 총 매출", money(sum(o["total_price"] for o in today_orders if o["status"] != "취소")))

    cols = st.columns(5)
    for idx, status in enumerate(["입금 대기", "입금 완료", "포장중", "배달중", "완료"]):
        cols[idx].metric(status, f"{status_counts[status]}건")


def product_form_defaults(product: sqlite3.Row | None = None) -> dict:
    return {
        "name": product["name"] if product else "",
        "variety": product["variety"] if product else "",
        "weight": product["weight"] if product else "",
        "price": int(product["price"]) if product else 0,
        "stock": int(product["stock"]) if product else 0,
        "status": product["status"] if product else "판매중",
        "short_description": product["short_description"] if product else "",
        "detail_description": product["detail_description"] if product else "",
        "taste_notes": product["taste_notes"] if product else "",
        "size_notes": product["size_notes"] if product else "",
        "harvest_notice": product["harvest_notice"] if product else "",
        "storage_guide": product["storage_guide"] if product else "",
        "delivery_guide": product["delivery_guide"] if product else "",
        "refund_guide": product["refund_guide"] if product else "",
        "main_image": product["main_image"] if product else "",
        "extra_images": product["extra_images"] if product else "",
        "badges": product["badges"] if product else "",
    }


def render_product_form(form_key: str, product: sqlite3.Row | None = None) -> tuple[bool, bool, dict]:
    defaults = product_form_defaults(product)
    with st.form(form_key):
        st.markdown("##### 기본 정보")
        name = st.text_input("상품명", value=defaults["name"])
        variety = st.text_input("품종", value=defaults["variety"])
        weight = st.text_input("중량", value=defaults["weight"], placeholder="예: 1kg")
        price = st.number_input("가격", min_value=0, step=1000, value=defaults["price"])
        stock = st.number_input("재고", min_value=0, step=1, value=defaults["stock"])
        status = st.radio("판매 상태", ["판매중", "품절"], index=0 if defaults["status"] == "판매중" else 1, horizontal=True)
        badges = st.text_input("배지", value=defaults["badges"], placeholder="예: 당일수확,직접배달,인기,품절임박")

        st.markdown("##### 판매 문구")
        short_description = st.text_input("짧은 설명", value=defaults["short_description"])
        detail_description = st.text_area("상세 설명", value=defaults["detail_description"], height=110)
        taste_notes = st.text_area("맛 특징", value=defaults["taste_notes"])
        size_notes = st.text_area("크기감", value=defaults["size_notes"])
        harvest_notice = st.text_area("수확/선별 안내", value=defaults["harvest_notice"])
        storage_guide = st.text_area("보관 방법", value=defaults["storage_guide"])
        delivery_guide = st.text_area("배송 안내", value=defaults["delivery_guide"])
        refund_guide = st.text_area("교환/환불 안내", value=defaults["refund_guide"])

        st.markdown("##### 이미지")
        main_image_url = st.text_input("대표 이미지 URL 또는 경로", value=defaults["main_image"])
        main_image_upload = st.file_uploader("대표 이미지 업로드", type=["png", "jpg", "jpeg", "webp"], key=f"{form_key}_main")
        extra_images_text = st.text_area("추가 이미지 URL 또는 경로들", value=defaults["extra_images"], help="여러 장은 줄바꿈으로 입력하세요.")
        extra_uploads = st.file_uploader("추가 이미지 업로드", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key=f"{form_key}_extra")

        col_save, col_delete = st.columns(2)
        save = col_save.form_submit_button("저장", type="primary", use_container_width=True)
        delete = col_delete.form_submit_button("삭제", use_container_width=True) if product else False

    if save:
        uploaded_main = save_uploaded_image(main_image_upload, name or "product")
        uploaded_extra = save_uploaded_images(extra_uploads, name or "product")
        main_image = uploaded_main or main_image_url.strip()
        extra_images = "\n".join(split_images(extra_images_text) + uploaded_extra)
        data = {
            "name": name.strip(),
            "variety": variety.strip(),
            "weight": weight.strip(),
            "price": int(price),
            "stock": int(stock),
            "status": "품절" if int(stock) == 0 else status,
            "description": short_description.strip() or detail_description.strip(),
            "short_description": short_description.strip(),
            "detail_description": detail_description.strip(),
            "taste_notes": taste_notes.strip(),
            "size_notes": size_notes.strip(),
            "harvest_notice": harvest_notice.strip(),
            "storage_guide": storage_guide.strip(),
            "delivery_guide": delivery_guide.strip(),
            "refund_guide": refund_guide.strip(),
            "main_image": main_image,
            "extra_images": extra_images,
            "badges": badges.strip(),
        }
        return save, delete, data
    return save, delete, {}


def product_admin_view() -> None:
    st.subheader("상품 관리")
    with st.expander("상품 추가", expanded=False):
        save, _, data = render_product_form("product_add")
        if save:
            if not data["name"] or not data["weight"] or data["price"] <= 0:
                st.error("상품명, 중량, 가격을 입력해주세요.")
            else:
                with get_conn() as conn:
                    conn.execute(
                        """
                        INSERT INTO products (
                            name, variety, weight, price, stock, description, status, created_at,
                            short_description, detail_description, taste_notes, size_notes, harvest_notice,
                            storage_guide, delivery_guide, refund_guide, main_image, extra_images, badges
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            data["name"],
                            data["variety"],
                            data["weight"],
                            data["price"],
                            data["stock"],
                            data["description"],
                            data["status"],
                            now_text(),
                            data["short_description"],
                            data["detail_description"],
                            data["taste_notes"],
                            data["size_notes"],
                            data["harvest_notice"],
                            data["storage_guide"],
                            data["delivery_guide"],
                            data["refund_guide"],
                            data["main_image"],
                            data["extra_images"],
                            data["badges"],
                        ),
                    )
                st.success("상품을 추가했습니다.")
                st.rerun()

    for product in rows("SELECT * FROM products ORDER BY id DESC"):
        with st.expander(f"{product['name']} · 재고 {product['stock']} · {product['status']}"):
            col_img, col_info = st.columns([1, 2])
            col_img.image(image_src(product["main_image"]), use_container_width=True)
            col_info.write(product_summary(product))
            save, delete, data = render_product_form(f"product_edit_{product['id']}", product)
            if save:
                if not data["name"] or not data["weight"] or data["price"] <= 0:
                    st.error("상품명, 중량, 가격을 입력해주세요.")
                else:
                    with get_conn() as conn:
                        conn.execute(
                            """
                            UPDATE products
                            SET name = ?, variety = ?, weight = ?, price = ?, stock = ?, description = ?,
                                status = ?, short_description = ?, detail_description = ?, taste_notes = ?,
                                size_notes = ?, harvest_notice = ?, storage_guide = ?, delivery_guide = ?,
                                refund_guide = ?, main_image = ?, extra_images = ?, badges = ?
                            WHERE id = ?
                            """,
                            (
                                data["name"],
                                data["variety"],
                                data["weight"],
                                data["price"],
                                data["stock"],
                                data["description"],
                                data["status"],
                                data["short_description"],
                                data["detail_description"],
                                data["taste_notes"],
                                data["size_notes"],
                                data["harvest_notice"],
                                data["storage_guide"],
                                data["delivery_guide"],
                                data["refund_guide"],
                                data["main_image"],
                                data["extra_images"],
                                data["badges"],
                                product["id"],
                            ),
                        )
                    st.success("상품을 수정했습니다.")
                    st.rerun()
            if delete:
                with get_conn() as conn:
                    conn.execute("DELETE FROM products WHERE id = ?", (product["id"],))
                st.warning("상품을 삭제했습니다.")
                st.rerun()


def order_card(order: sqlite3.Row, prefix: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{order['order_no']}** · {order['customer_name']} · {order['product_name']} {order['quantity']}개")
        st.write(f"{order['phone']} / {order['receive_type']} / {order['address'] or '-'}")
        st.write(f"금액 {money(order['total_price'])} / 입금자명 {order['depositor_name']} / 주문일 {order['created_at']}")
        st.write(f"요청사항: {order['request_note'] or '-'}")
        col_status, col_apply, col_cancel = st.columns([2, 1, 1])
        new_status = col_status.selectbox("상태 변경", ORDER_STATUSES, index=ORDER_STATUSES.index(order["status"]), key=f"{prefix}_status_{order['id']}")
        if col_apply.button("변경", key=f"{prefix}_apply_{order['id']}", use_container_width=True):
            update_order_status(order["id"], new_status)
            st.rerun()
        if col_cancel.button("취소", key=f"{prefix}_cancel_{order['id']}", use_container_width=True):
            cancel_order(order["id"])
            st.rerun()


def order_admin_view() -> None:
    st.subheader("주문 관리")
    status_filter = st.selectbox("상태 필터", ["전체"] + ORDER_STATUSES)
    query = "SELECT * FROM orders"
    params: tuple = ()
    if status_filter != "전체":
        query += " WHERE status = ?"
        params = (status_filter,)
    query += " ORDER BY created_at DESC"
    for order in rows(query, params):
        order_card(order, "orders")


def payment_admin_view() -> None:
    st.subheader("입금 대기 관리")
    waiting = rows("SELECT * FROM orders WHERE status = '입금 대기' ORDER BY created_at ASC")
    if not waiting:
        st.success("입금 대기 주문이 없습니다.")
    for order in waiting:
        with st.container(border=True):
            st.write(f"**{order['order_no']}** {order['customer_name']} / {order['product_name']} {order['quantity']}개 / {money(order['total_price'])}")
            st.write(f"입금자명: {order['depositor_name']} / 연락처: {order['phone']}")
            if st.button("입금 완료", key=f"paid_{order['id']}", type="primary", use_container_width=True):
                update_order_status(order["id"], "입금 완료")
                st.rerun()


def delivery_admin_view() -> None:
    st.subheader("배달 관리")
    delivery = rows("SELECT * FROM orders WHERE status = '배달중' ORDER BY address ASC, created_at ASC")
    if not delivery:
        st.info("배달중 주문이 없습니다.")
    for order in delivery:
        with st.container(border=True):
            st.write(f"**{order['customer_name']}** · {order['phone']}")
            st.write(f"주소: {order['address'] or '-'}")
            st.write(f"{order['product_name']} {order['quantity']}개 / 요청사항: {order['request_note'] or '-'}")
            if st.button("배달 완료", key=f"done_{order['id']}", type="primary", use_container_width=True):
                update_order_status(order["id"], "완료")
                st.rerun()


def download_view() -> None:
    st.subheader("CSV 다운로드")
    col_all, col_wait, col_delivery = st.columns(3)
    col_all.download_button("전체 주문 목록", create_csv_download("all"), "cherry_all_orders.csv", "text/csv", use_container_width=True)
    col_wait.download_button("입금 대기 목록", create_csv_download("waiting"), "cherry_waiting_payment.csv", "text/csv", use_container_width=True)
    col_delivery.download_button("배달 목록", create_csv_download("delivery"), "cherry_delivery_orders.csv", "text/csv", use_container_width=True)


def admin_page() -> None:
    if not admin_login():
        return
    st.title("판매 관리자")
    st.sidebar.markdown(f"**{BRAND_NAME} 관리자**")
    st.sidebar.caption("구매자에게는 관리자 화면이 보이지 않습니다.")
    if st.sidebar.button("구매자 화면으로 돌아가기", use_container_width=True):
        st.session_state["admin_logged_in"] = False
        st.query_params.clear()
        st.rerun()
    if st.sidebar.button("로그아웃", use_container_width=True):
        st.session_state["admin_logged_in"] = False
        st.rerun()
    tab_dash, tab_products, tab_orders, tab_payments, tab_delivery, tab_csv = st.tabs(
        ["대시보드", "상품 관리", "주문 관리", "입금 관리", "배달 관리", "CSV"]
    )
    with tab_dash:
        dashboard_view()
    with tab_products:
        product_admin_view()
    with tab_orders:
        order_admin_view()
    with tab_payments:
        payment_admin_view()
    with tab_delivery:
        delivery_admin_view()
    with tab_csv:
        download_view()


def main() -> None:
    init_db()
    apply_style()
    is_admin_url = st.query_params.get("admin") == "1"
    if is_admin_url:
        admin_page()
    else:
        buyer_page()


if __name__ == "__main__":
    main()

