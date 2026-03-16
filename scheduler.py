"""
Scheduler
=========
Orchestrates the daily scraping + alert + analysis pipeline.

Can be run directly or triggered via cron / GitHub Actions:

    # Run full pipeline
    python scheduler.py

    # Crontab entry (daily at 8 AM)
    0 8 * * * cd /path/to/ecommerce-price-tracker && python scheduler.py >> logs/cron.log 2>&1

    # GitHub Actions: see .github/workflows/daily_scrape.yml
"""

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/scheduler_{datetime.utcnow().strftime('%Y%m%d')}.log"),
    ],
)
logger = logging.getLogger("scheduler")

Path("logs").mkdir(exist_ok=True)

# ─── Pipeline Steps ──────────────────────────────────────────────────────────

SPIDERS = [
    ("amazon", {"query": "laptop",     "max_pages": "3"}),
    ("amazon", {"query": "smartphone", "max_pages": "3"}),
    ("daraz",  {"query": "laptop",     "max_pages": "3"}),
    ("daraz",  {"query": "phone",      "max_pages": "3"}),
]


def run_spiders():
    logger.info("─── Starting Scrapy spiders ───")
    for spider_name, kwargs in SPIDERS:
        args = " ".join(f"-a {k}={v}" for k, v in kwargs.items())
        cmd = f"scrapy crawl {spider_name} {args} -s JOBDIR=.scrapy/jobs/{spider_name}"
        logger.info(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            logger.error(f"Spider '{spider_name}' exited with code {result.returncode}")


def run_alerts():
    logger.info("─── Checking price alerts ───")
    from alerts.price_alert import AlertChecker
    checker = AlertChecker(dry_run=False)
    checker.run()


def run_analysis():
    logger.info("─── Running market analysis ───")
    from analysis.market_analysis import generate_full_report
    report = generate_full_report(days=30)
    logger.info(f"Analysis complete: {report['total_records']} records, "
                f"{len(report['best_value_products'])} top value products identified")


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start = datetime.utcnow()
    logger.info(f"{'='*60}")
    logger.info(f"  Pipeline started at {start.isoformat()}")
    logger.info(f"{'='*60}")

    try:
        run_spiders()
        run_alerts()
        run_analysis()
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        sys.exit(1)

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info(f"Pipeline complete in {elapsed:.1f}s")
