# 🛒 E-Commerce Price Tracker

> **Automated price intelligence for Amazon & Daraz** — daily Scrapy scraping, SQLite history, interactive analytics dashboard, and real-time email alerts.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Scrapy](https://img.shields.io/badge/Scrapy-2.11-60A839?style=flat-square&logo=scrapy&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white)

---

## ✨ Features

| Feature                     | Details                                                          |
| --------------------------- | ---------------------------------------------------------------- |
| **Multi-platform scraping** | Amazon (US) + Daraz (PK) with rotating user-agents               |
| **Daily automation**        | GitHub Actions cron — runs at 06:00 UTC every day                |
| **SQLite history**          | Full price history with per-seller granularity                   |
| **Interactive dashboard**   | Chart.js analytics: trends, scatter plots, seller matrix         |
| **Price drop alerts**       | Email notifications when price hits your target                  |
| **Market analysis**         | Seller competition, rating/price correlation, best-value scoring |
| **CSV snapshots**           | Daily export files for Tableau / Power BI                        |

---

## 📁 Project Structure

```
ecommerce-price-tracker/
├── scraper/
│   ├── spiders/
│   │   ├── amazon_spider.py     # Amazon search scraper
│   │   └── daraz_spider.py      # Daraz.pk scraper
│   ├── items.py                 # Scrapy item definitions
│   ├── pipelines.py             # Validate → Dedupe → DB → CSV
│   └── settings.py              # Scrapy configuration
│
├── database/
│   └── models.py                # SQLite schema + query helpers
│
├── alerts/
│   └── price_alert.py           # Price drop email alert system
│
├── analysis/
│   └── market_analysis.py       # Competition & correlation analysis
│
├── dashboard/
│   └── index.html               # Interactive analytics dashboard
│
├── data/
│   ├── price_tracker.db         # SQLite database (git-ignored)
│   ├── exports/                 # Daily CSV snapshots
│   └── sample/demo_data.json    # Demo data for dashboard
│
├── .github/workflows/
│   └── daily_scrape.yml         # GitHub Actions pipeline
│
├── scheduler.py                 # Orchestrates full pipeline
└── requirements.txt
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/ecommerce-price-tracker.git
cd ecommerce-price-tracker
pip install -r requirements.txt
```

### 2. Run a spider

```bash
# Scrape Amazon laptops (3 pages)
scrapy crawl amazon -a query="laptop" -a max_pages=3

# Scrape Daraz phones
scrapy crawl daraz -a query="smartphone" -a max_pages=5

# Save output to JSON
scrapy crawl amazon -a query="monitor" -o data/exports/monitors.json
```

### 3. Open the dashboard

```bash
open dashboard/index.html
# or just double-click it — no server needed
```

### 4. Run the full daily pipeline

```bash
python scheduler.py
```

---

## 📊 Dashboard Preview

The `dashboard/index.html` file is a fully self-contained analytics interface:

- **Price Trend Chart** — multi-product comparison with 30-day history
- **Seller Comparison Table** — ranked by average price with discount badges
- **Rating vs Price Scatter** — 4-quadrant value analysis (Best Value / Premium / Budget Risk / Avoid)
- **Market Competition Chart** — products per seller + average discount overlay
- **Alert Panel** — set price targets directly in the UI

---

## 🔔 Price Drop Alerts

Configure SMTP credentials in `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_COOLDOWN_HOURS=24
```

Add an alert via Python:

```python
from database.models import Database

with Database() as db:
    db.add_alert(
        product_id=1,
        email="you@email.com",
        target_price=950.00,
        pct_drop=10,          # also alert on 10%+ drops
    )
```

Run the checker manually:

```bash
python -m alerts.price_alert           # live mode
python -m alerts.price_alert --dry-run # preview without sending
```

---

## 📈 Market Analysis

```bash
# Full analysis (last 30 days)
python -m analysis.market_analysis

# Filter by category
python -m analysis.market_analysis --category electronics --days 14
```

Sample output:

```
============================================================
  Market Report: 1,847 records analysed
  Top Sellers by avg price:
    Daraz                          avg: $290
    Amazon                         avg: $487
    BestBuy                        avg: $620

  Rating/Price Correlation: 0.2841
  (Weak positive — value is NOT tied to price)

  Best Value Products:
    Anker 65W USB-C Charger             $29   ★4.5
    Logitech MX Master 3                $79   ★4.6
    Sony WH-1000XM5 Headphones          $249  ★4.7
============================================================
```

---

## ⚙️ GitHub Actions Automation

The workflow in `.github/workflows/daily_scrape.yml`:

1. Runs daily at **06:00 UTC**
2. Restores the SQLite DB from cache
3. Executes all spiders
4. Checks and dispatches price alerts
5. Runs market analysis
6. Uploads CSV exports + JSON reports as artifacts
7. Saves updated DB to cache

Set the following **repository secrets** for email alerts:

| Secret          | Value              |
| --------------- | ------------------ |
| `SMTP_HOST`     | `smtp.gmail.com`   |
| `SMTP_PORT`     | `587`              |
| `SMTP_USER`     | your Gmail address |
| `SMTP_PASSWORD` | Gmail App Password |

---

## 🧰 Tech Stack

- **Scrapy 2.11** — spider framework with auto-throttle & retry
- **SQLite** — lightweight persistent storage with WAL mode
- **Chart.js 4** — client-side interactive charts
- **GitHub Actions** — free daily cron with artifact storage
- **Python stdlib** — `smtplib`, `sqlite3`, `csv`, `statistics`
