"""
Market Competition Analysis
============================
Analyses scraped price data to surface:
  1. Price trend (rolling averages, volatility)
  2. Seller competition matrix
  3. Rating vs Price correlation
  4. Category price distribution
  5. Best-value products (price/rating score)
  6. Discount depth analysis

Outputs: analysis/reports/{date}_market_report.json + CSV summaries

Usage:
    python -m analysis.market_analysis
    python -m analysis.market_analysis --category electronics --days 30
"""

import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
REPORT_DIR = Path("analysis/reports")


# ─── Data Loader ──────────────────────────────────────────────────────────────

def load_data(db=None, days: int = 30) -> list[dict]:
    """
    Load price history from the database.
    Falls back to CSV files in data/exports/ if no DB provided.
    """
    if db:
        return db.get_all_products_with_latest_price()

    # CSV fallback (useful for standalone testing)
    import csv, glob
    rows = []
    for path in sorted(glob.glob("data/exports/*.csv"))[-7:]:
        with open(path, encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    return rows


# ─── Analysis Functions ───────────────────────────────────────────────────────

def price_trend_analysis(history: list[dict]) -> dict:
    """
    Compute rolling 7-day average prices and detect trends.
    Returns: {product_id: {dates, prices, rolling_avg, trend_direction}}
    """
    from collections import defaultdict
    by_product = defaultdict(list)
    for row in history:
        by_product[row.get("product_ref") or row.get("product_id")].append(row)

    results = {}
    for pid, records in by_product.items():
        records.sort(key=lambda r: r.get("scraped_at", ""))
        prices = [float(r["price"]) for r in records if r.get("price")]
        dates  = [r.get("scraped_at", "")[:10] for r in records if r.get("price")]
        if len(prices) < 2:
            continue

        # Simple rolling average (window=3)
        rolling = []
        for i in range(len(prices)):
            window = prices[max(0, i - 2): i + 1]
            rolling.append(round(sum(window) / len(window), 2))

        # Trend: linear slope over last N points
        n = min(7, len(prices))
        recent = prices[-n:]
        trend = "stable"
        if len(recent) >= 2:
            slope = (recent[-1] - recent[0]) / len(recent)
            if slope < -0.5:
                trend = "decreasing"
            elif slope > 0.5:
                trend = "increasing"

        results[pid] = {
            "name": records[0].get("name", ""),
            "dates": dates,
            "prices": prices,
            "rolling_avg": rolling,
            "current_price": prices[-1],
            "min_price": min(prices),
            "max_price": max(prices),
            "volatility": round(statistics.stdev(prices), 2) if len(prices) > 1 else 0,
            "trend": trend,
        }
    return results


def seller_competition_matrix(records: list[dict]) -> list[dict]:
    """
    Build a seller comparison: who offers the most products, cheapest avg price.
    """
    seller_data: dict[str, Any] = defaultdict(lambda: {
        "total_products": 0,
        "prices": [],
        "ratings": [],
        "categories": set(),
    })

    for r in records:
        seller = r.get("seller") or "Unknown"
        price  = r.get("price")
        rating = r.get("rating")
        cat    = r.get("category", "")

        seller_data[seller]["total_products"] += 1
        if price:
            seller_data[seller]["prices"].append(float(price))
        if rating:
            seller_data[seller]["ratings"].append(float(rating))
        seller_data[seller]["categories"].add(cat)

    matrix = []
    for seller, data in seller_data.items():
        prices = data["prices"]
        ratings = data["ratings"]
        matrix.append({
            "seller": seller,
            "total_products": data["total_products"],
            "avg_price": round(statistics.mean(prices), 2) if prices else None,
            "min_price": round(min(prices), 2) if prices else None,
            "max_price": round(max(prices), 2) if prices else None,
            "avg_rating": round(statistics.mean(ratings), 2) if ratings else None,
            "categories": list(data["categories"]),
            "price_competitiveness": "high" if prices and statistics.mean(prices) < 100 else "medium",
        })

    return sorted(matrix, key=lambda x: (x["avg_price"] or 99999))


def rating_price_correlation(records: list[dict]) -> dict:
    """
    Pearson correlation between price and rating.
    Also identify value quadrants: Low price + High rating = "Best Value".
    """
    paired = [
        (float(r["price"]), float(r["rating"]))
        for r in records
        if r.get("price") and r.get("rating")
    ]
    if len(paired) < 5:
        return {"correlation": None, "data_points": len(paired)}

    prices  = [p[0] for p in paired]
    ratings = [p[1] for p in paired]

    # Pearson r
    n = len(paired)
    mean_p = sum(prices) / n
    mean_r = sum(ratings) / n
    cov = sum((p - mean_p) * (r - mean_r) for p, r in paired) / n
    std_p = statistics.stdev(prices) or 1
    std_r = statistics.stdev(ratings) or 1
    corr = cov / (std_p * std_r)

    med_price  = statistics.median(prices)
    med_rating = statistics.median(ratings)

    quadrants = {"best_value": [], "premium": [], "budget_risk": [], "avoid": []}
    for r in records:
        if not (r.get("price") and r.get("rating")):
            continue
        p, rat = float(r["price"]), float(r["rating"])
        name = r.get("name", "?")[:40]
        if p <= med_price and rat >= med_rating:
            quadrants["best_value"].append(name)
        elif p > med_price and rat >= med_rating:
            quadrants["premium"].append(name)
        elif p <= med_price and rat < med_rating:
            quadrants["budget_risk"].append(name)
        else:
            quadrants["avoid"].append(name)

    return {
        "correlation": round(corr, 4),
        "interpretation": (
            "Strong positive" if corr > 0.5 else
            "Weak positive" if corr > 0.1 else
            "Neutral" if abs(corr) <= 0.1 else
            "Weak negative" if corr > -0.5 else
            "Strong negative"
        ),
        "data_points": n,
        "quadrants": {k: v[:5] for k, v in quadrants.items()},
    }


def discount_depth_report(records: list[dict]) -> dict:
    """Analyse discount patterns: which categories / sellers discount most."""
    by_category: dict[str, list] = defaultdict(list)
    by_seller:   dict[str, list] = defaultdict(list)

    for r in records:
        disc = r.get("discount_pct")
        if disc is None:
            continue
        disc = float(disc)
        by_category[r.get("category", "unknown")].append(disc)
        by_seller[r.get("seller",   "unknown")].append(disc)

    def summarise(d: dict):
        return {
            k: {
                "avg_discount": round(statistics.mean(v), 1),
                "max_discount": round(max(v), 1),
                "count": len(v),
            }
            for k, v in d.items() if v
        }

    return {
        "by_category": summarise(by_category),
        "by_seller":   summarise(by_seller),
    }


def best_value_products(records: list[dict], top_n: int = 10) -> list[dict]:
    """
    Score each product by (rating / price) * 100.
    Higher = better value per dollar.
    """
    scored = []
    for r in records:
        price  = float(r["price"])  if r.get("price")  else None
        rating = float(r["rating"]) if r.get("rating") else None
        if not price or not rating or price == 0:
            continue
        value_score = round((rating / price) * 100, 4)
        scored.append({
            "name": r.get("name", "")[:60],
            "price": price,
            "rating": rating,
            "seller": r.get("seller", ""),
            "category": r.get("category", ""),
            "value_score": value_score,
            "discount_pct": r.get("discount_pct"),
            "url": r.get("url", ""),
        })
    return sorted(scored, key=lambda x: x["value_score"], reverse=True)[:top_n]


# ─── Report Generator ─────────────────────────────────────────────────────────

def generate_full_report(db=None, days: int = 30, category: str = None) -> dict:
    """Run all analyses and compile a structured market report."""
    records = load_data(db, days)
    if category:
        records = [r for r in records if (r.get("category") or "").lower() == category.lower()]

    logger.info(f"Analysing {len(records)} records...")

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "period_days": days,
        "category_filter": category,
        "total_records": len(records),
        "seller_competition": seller_competition_matrix(records),
        "rating_price_analysis": rating_price_correlation(records),
        "discount_depth": discount_depth_report(records),
        "best_value_products": best_value_products(records),
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.utcnow().strftime('%Y%m%d_%H%M')}_market_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {report_path}")
    return report


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Market Competition Analysis")
    parser.add_argument("--days",     type=int, default=30, help="Days of history to analyse")
    parser.add_argument("--category", type=str, default=None, help="Filter by category")
    args = parser.parse_args()

    report = generate_full_report(days=args.days, category=args.category)
    print(f"\n{'='*60}")
    print(f"  Market Report: {report['total_records']} records analysed")
    print(f"  Top Sellers by avg price:")
    for s in report["seller_competition"][:5]:
        print(f"    {s['seller']:<30} avg: ${s['avg_price']}")
    print(f"\n  Rating/Price Correlation: {report['rating_price_analysis']['correlation']}")
    print(f"  ({report['rating_price_analysis']['interpretation']})")
    print(f"\n  Best Value Products:")
    for p in report["best_value_products"][:3]:
        print(f"    {p['name']:<45} ${p['price']} ★{p['rating']}")
    print(f"{'='*60}")
