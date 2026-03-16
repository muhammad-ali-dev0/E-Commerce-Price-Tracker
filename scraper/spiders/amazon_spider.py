"""
Amazon Price Spider
===================
Scrapes product listings from Amazon search results.
Handles pagination, anti-bot measures, and extracts
full product details including pricing and seller info.

Usage:
    scrapy crawl amazon -a query="laptop" -a max_pages=5
    scrapy crawl amazon -a category="electronics" -o data/amazon.json
"""

import re
import scrapy
from datetime import datetime
from scraper.items import ProductItem


class AmazonSpider(scrapy.Spider):
    name = "amazon"
    allowed_domains = ["amazon.com"]
    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "RETRY_TIMES": 3,
        "COOKIES_ENABLED": True,
    }

    def __init__(self, query="laptop", category=None, max_pages=3, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.category = category
        self.max_pages = int(max_pages)
        self.current_page = 1

    def start_requests(self):
        search_url = f"https://www.amazon.com/s?k={self.query.replace(' ', '+')}"
        yield scrapy.Request(
            url=search_url,
            headers=self._get_headers(),
            callback=self.parse,
            meta={"page": 1},
        )

    def _get_headers(self):
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

    def parse(self, response):
        """Parse search result listings."""
        page = response.meta.get("page", 1)
        products = response.css("div[data-component-type='s-search-result']")
        self.logger.info(f"Page {page}: found {len(products)} products")

        for product in products:
            yield from self._parse_product_card(product, response)

        # Pagination
        if page < self.max_pages:
            next_page = response.css("a.s-pagination-next::attr(href)").get()
            if next_page:
                yield scrapy.Request(
                    url=response.urljoin(next_page),
                    headers=self._get_headers(),
                    callback=self.parse,
                    meta={"page": page + 1},
                )

    def _parse_product_card(self, product, response):
        """Extract data from a single product card."""
        product_url = product.css("a.a-link-normal.s-no-outline::attr(href)").get()
        if not product_url:
            return

        # Extract ASIN (Amazon product ID)
        asin = product.attrib.get("data-asin", "")

        # Price parsing
        price_whole = product.css("span.a-price-whole::text").get("0").replace(",", "")
        price_fraction = product.css("span.a-price-fraction::text").get("00")
        price = float(f"{price_whole}.{price_fraction}") if price_whole != "0" else None

        original_price_raw = product.css(
            "span.a-price.a-text-price span.a-offscreen::text"
        ).get("").replace("$", "").replace(",", "")
        original_price = float(original_price_raw) if original_price_raw else None

        discount_pct = None
        if price and original_price and original_price > price:
            discount_pct = round((1 - price / original_price) * 100, 1)

        # Rating & reviews
        rating_text = product.css("span.a-icon-alt::text").get("")
        rating = float(re.search(r"[\d.]+", rating_text).group()) if re.search(r"[\d.]+", rating_text) else None
        review_count_raw = product.css("span.a-size-base.s-underline-text::text").get("0")
        review_count = int(review_count_raw.replace(",", "")) if review_count_raw.replace(",", "").isdigit() else 0

        # Seller
        seller = product.css("span.a-size-base-plus.a-color-base::text").get("")

        # Stock
        stock_status = "In Stock"
        stock_badge = product.css("span.a-color-price::text").get("")
        if "out of stock" in stock_badge.lower():
            stock_status = "Out of Stock"
        elif "only" in stock_badge.lower():
            stock_status = "Low Stock"
            stock_count = re.search(r"\d+", stock_badge)
            if stock_count:
                stock_count = int(stock_count.group())

        item = ProductItem(
            product_id=asin,
            name=product.css("span.a-size-base-plus.a-color-base.a-text-normal::text").get("").strip(),
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            rating=rating,
            review_count=review_count,
            seller=seller or "Amazon",
            stock_status=stock_status,
            stock_count=None,
            category=self.category or self.query,
            url=response.urljoin(product_url),
            image_url=product.css("img.s-image::attr(src)").get(""),
            scraped_at=datetime.utcnow().isoformat(),
            source="amazon",
        )
        yield item

        # Optionally follow to product detail page for full info
        # yield scrapy.Request(
        #     url=response.urljoin(product_url),
        #     callback=self.parse_product_detail,
        #     meta={"item": item},
        # )

    def parse_product_detail(self, response):
        """Deep scrape: full seller list, Q&A, specs."""
        item = response.meta["item"]
        # Extract detailed seller table
        sellers = []
        for row in response.css("#olpLinkWidget_feature_div .olp-padding-right"):
            seller_name = row.css(".olpSellerName span::text").get("").strip()
            seller_price = row.css(".olpOfferPrice::text").get("").replace("$", "").strip()
            if seller_name and seller_price:
                sellers.append({"name": seller_name, "price": seller_price})
        item["seller"] = sellers[0]["name"] if sellers else item.get("seller")
        yield item
