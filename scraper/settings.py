# ─── Scrapy Project Settings ──────────────────────────────────────────────────

BOT_NAME = "ecommerce_price_tracker"
SPIDER_MODULES = ["scraper.spiders"]
NEWSPIDER_MODULE = "scraper.spiders"

# Respect robots.txt in production; set False only for permitted targets
ROBOTSTXT_OBEY = True

# Polite crawling defaults (override per-spider as needed)
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.5

# Retry
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Caching (useful for development)
HTTPCACHE_ENABLED = False  # Enable in dev: True
HTTPCACHE_EXPIRATION_SECS = 86400
HTTPCACHE_DIR = ".scrapy/cache"

# Pipelines (order = priority; lower = runs first)
ITEM_PIPELINES = {
    "scraper.pipelines.ValidationPipeline":  100,
    "scraper.pipelines.DuplicatesPipeline":  200,
    "scraper.pipelines.DatabasePipeline":    300,
    "scraper.pipelines.ExportPipeline":      400,
}

# Default headers
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Feed exports (optional CLI override)
FEEDS = {}

# Telnet console (disable in production)
TELNETCONSOLE_ENABLED = False

# Encoding
FEED_EXPORT_ENCODING = "utf-8"
