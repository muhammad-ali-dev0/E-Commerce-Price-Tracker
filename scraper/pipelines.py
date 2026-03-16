"""
Scrapy Pipelines
================
Data processing pipeline stages:
  1. ValidationPipeline   – validates and cleans items
  2. DuplicatesPipeline   – drops exact duplicate records
  3. DatabasePipeline     – persists items to SQLite
  4. ExportPipeline       – writes daily CSV snapshots
"""

import csv
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── 1. Validation ────────────────────────────────────────────────────────────

class ValidationPipeline:
    """Drop items missing critical fields and normalise values."""

    REQUIRED_FIELDS = ("name", "price", "source")

    def process_item(self, item, spider):
        # Drop if required fields missing or price is non-positive
        for field in self.REQUIRED_FIELDS:
            if not item.get(field):
                raise DropItem(f"Missing required field '{field}': {item}")

        if item.get("price") and item["price"] <= 0:
            raise DropItem(f"Invalid price {item['price']}: {item}")

        # Normalise name
        item["name"] = item["name"].strip()[:500]

        # Clamp rating
        if item.get("rating") and not (0 <= item["rating"] <= 5):
            item["rating"] = max(0, min(5, item["rating"]))

        return item


# ─── 2. Deduplication ─────────────────────────────────────────────────────────

class DuplicatesPipeline:
    """In-memory deduplication within a single spider run."""

    def __init__(self):
        self.seen = set()

    def process_item(self, item, spider):
        key = hashlib.md5(
            f"{item.get('source')}-{item.get('product_id') or item.get('name')}-{item.get('seller')}".encode()
        ).hexdigest()

        if key in self.seen:
            raise DropItem(f"Duplicate item: {item.get('name')}")
        self.seen.add(key)
        return item


# ─── 3. SQLite Persistence ────────────────────────────────────────────────────

class DatabasePipeline:
    """Store every scraped record in SQLite for historical analysis."""

    def __init__(self):
        from database.models import Database
        self.db = Database()

    def open_spider(self, spider):
        self.db.connect()
        self.db.create_tables()
        logger.info("DatabasePipeline: connected to SQLite")

    def close_spider(self, spider):
        self.db.close()
        logger.info("DatabasePipeline: connection closed")

    def process_item(self, item, spider):
        self.db.insert_price_record(dict(item))
        return item


# ─── 4. CSV Snapshot Export ───────────────────────────────────────────────────

class ExportPipeline:
    """Append records to a daily CSV snapshot file."""

    def __init__(self):
        self.files = {}
        self.exporters = {}

    def open_spider(self, spider):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)

        path = export_dir / f"{spider.name}_{today}.csv"
        self.file = open(path, "a", newline="", encoding="utf-8")
        fieldnames = [
            "product_id", "name", "price", "original_price", "discount_pct",
            "rating", "review_count", "seller", "stock_status", "category",
            "url", "scraped_at", "source",
        ]
        self.writer = csv.DictWriter(self.file, fieldnames=fieldnames, extrasaction="ignore")
        if os.path.getsize(path) == 0:
            self.writer.writeheader()
        logger.info(f"ExportPipeline: writing to {path}")

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        self.writer.writerow(dict(item))
        return item


# ─── Scrapy built-in import ───────────────────────────────────────────────────

try:
    from scrapy.exceptions import DropItem
except ImportError:
    class DropItem(Exception):
        pass
