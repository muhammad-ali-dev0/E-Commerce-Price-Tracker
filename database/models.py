"""
Database Models
===============
SQLite schema and ORM-like helper for the price tracker.

Tables:
  products      – canonical product catalogue
  price_history – one row per scrape per product
  sellers       – seller master list
  alerts        – user-configured price alerts
  alert_log     – triggered alert history
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/price_tracker.db")


class Database:
    """Thin wrapper around sqlite3 with helper query methods."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        logger.info(f"Connected to DB at {self.db_path}")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Schema ────────────────────────────────────────────────────────────────

    def create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id      TEXT,
                name            TEXT NOT NULL,
                category        TEXT,
                source          TEXT NOT NULL,
                url             TEXT,
                image_url       TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(product_id, source)
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_ref     INTEGER NOT NULL REFERENCES products(id),
                price           REAL NOT NULL,
                original_price  REAL,
                discount_pct    REAL,
                rating          REAL,
                review_count    INTEGER DEFAULT 0,
                seller          TEXT,
                stock_status    TEXT DEFAULT 'Unknown',
                stock_count     INTEGER,
                scraped_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sellers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                source      TEXT,
                rating      REAL,
                total_products INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_ref     INTEGER REFERENCES products(id),
                email           TEXT NOT NULL,
                target_price    REAL NOT NULL,
                pct_drop        REAL,
                active          INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now')),
                triggered_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS alert_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_ref   INTEGER REFERENCES alerts(id),
                triggered_at TEXT,
                old_price   REAL,
                new_price   REAL,
                message     TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_ref);
            CREATE INDEX IF NOT EXISTS idx_price_history_scraped ON price_history(scraped_at);
            CREATE INDEX IF NOT EXISTS idx_products_source ON products(source);
        """)
        self.conn.commit()
        logger.info("Tables created / verified")

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_product(self, item: dict) -> int:
        """Insert or ignore product; return its row id."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO products (product_id, name, category, source, url, image_url)
            VALUES (:product_id, :name, :category, :source, :url, :image_url)
            """,
            item,
        )
        self.conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = self.conn.execute(
            "SELECT id FROM products WHERE product_id=? AND source=?",
            (item.get("product_id"), item.get("source")),
        ).fetchone()
        return row["id"] if row else None

    def insert_price_record(self, item: dict):
        product_id = self.upsert_product(item)
        if not product_id:
            logger.warning(f"Could not resolve product id for {item.get('name')}")
            return
        self.conn.execute(
            """
            INSERT INTO price_history
              (product_ref, price, original_price, discount_pct, rating, review_count,
               seller, stock_status, stock_count, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                item.get("price"),
                item.get("original_price"),
                item.get("discount_pct"),
                item.get("rating"),
                item.get("review_count", 0),
                item.get("seller"),
                item.get("stock_status", "Unknown"),
                item.get("stock_count"),
                item.get("scraped_at", datetime.utcnow().isoformat()),
            ),
        )
        self.conn.commit()

    def add_alert(self, product_id: int, email: str, target_price: float, pct_drop: float = None):
        self.conn.execute(
            "INSERT INTO alerts (product_ref, email, target_price, pct_drop) VALUES (?,?,?,?)",
            (product_id, email, target_price, pct_drop),
        )
        self.conn.commit()

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_price_history(self, product_ref: int, days: int = 30):
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            """
            SELECT scraped_at, price, seller, discount_pct
            FROM price_history
            WHERE product_ref = ? AND scraped_at >= ?
            ORDER BY scraped_at ASC
            """,
            (product_ref, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cheapest_sellers(self, product_ref: int):
        rows = self.conn.execute(
            """
            SELECT seller, MIN(price) as min_price, AVG(price) as avg_price,
                   MAX(price) as max_price, COUNT(*) as observations
            FROM price_history
            WHERE product_ref = ? AND price IS NOT NULL
            GROUP BY seller
            ORDER BY min_price ASC
            """,
            (product_ref,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_alerts(self):
        rows = self.conn.execute(
            """
            SELECT a.id, a.email, a.target_price, a.pct_drop,
                   p.name AS product_name, p.id AS product_ref,
                   ph.price AS current_price
            FROM alerts a
            JOIN products p ON p.id = a.product_ref
            JOIN price_history ph ON ph.product_ref = p.id
            WHERE a.active = 1
              AND ph.scraped_at = (
                  SELECT MAX(scraped_at) FROM price_history WHERE product_ref = p.id
              )
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_products_with_latest_price(self):
        rows = self.conn.execute(
            """
            SELECT p.id, p.name, p.category, p.source, p.url,
                   ph.price, ph.rating, ph.seller, ph.discount_pct,
                   ph.stock_status, ph.scraped_at
            FROM products p
            JOIN price_history ph ON ph.product_ref = p.id
            WHERE ph.scraped_at = (
                SELECT MAX(scraped_at) FROM price_history WHERE product_ref = p.id
            )
            ORDER BY ph.price ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_price_stats(self, days: int = 7):
        """Aggregate stats for dashboard."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self.conn.execute(
            """
            SELECT COUNT(DISTINCT product_ref) as products_tracked,
                   COUNT(*) as total_records,
                   AVG(price) as avg_price,
                   MIN(price) as min_price,
                   MAX(price) as max_price,
                   AVG(discount_pct) as avg_discount
            FROM price_history
            WHERE scraped_at >= ?
            """,
            (cutoff,),
        ).fetchone()
