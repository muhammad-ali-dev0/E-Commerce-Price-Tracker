"""
Daraz Price Spider
==================
Scrapes product listings from Daraz.pk (South Asian e-commerce).
Daraz uses a JSON API internally — this spider targets the API
endpoints for more reliable extraction than HTML parsing.

Usage:
    scrapy crawl daraz -a query="phone" -a max_pages=5
"""

import json
import re
import scrapy
from datetime import datetime
from scraper.items import ProductItem


class DarazSpider(scrapy.Spider):
    name = "daraz"
    allowed_domains = ["daraz.pk", "www.daraz.pk"]
    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    API_URL = (
        "https://www.daraz.pk/catalog/?_keyori=ss&from=input"
        "&page={page}&q={query}&sort=priceasc"
    )

    def __init__(self, query="smartphone", max_pages=5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.max_pages = int(max_pages)

    def start_requests(self):
        for page in range(1, self.max_pages + 1):
            yield scrapy.Request(
                url=self.API_URL.format(page=page, query=self.query.replace(" ", "+")),
                headers=self._headers(),
                callback=self.parse,
                meta={"page": page},
            )

    def _headers(self):
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120 Safari/537.36"
            ),
            "Referer": "https://www.daraz.pk/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def parse(self, response):
        """Extract product cards from Daraz search results."""
        products = response.css("div[data-qa-locator='product-item']")
        self.logger.info(f"Page {response.meta['page']}: {len(products)} products")

        for product in products:
            yield self._extract_product(product)

    def _extract_product(self, product):
        """Parse a single Daraz product tile."""
        name = product.css("div.title--wFj93 a::text").get("").strip()
        product_url = product.css("div.title--wFj93 a::attr(href)").get("")
        if product_url and not product_url.startswith("http"):
            product_url = "https:" + product_url

        # Prices
        price_text = product.css("span.currency--GVKjl::text").get("0")
        price = self._clean_price(price_text)

        original_price_text = product.css(
            "del.currency--GVKjl::text"
        ).get("")
        original_price = self._clean_price(original_price_text) if original_price_text else None

        discount_pct = None
        discount_text = product.css("span.percent--dCJsE::text").get("")
        if discount_text:
            match = re.search(r"\d+", discount_text)
            discount_pct = int(match.group()) if match else None

        # Rating
        rating_text = product.css("span.score--ULMGn::text").get("0")
        try:
            rating = float(rating_text)
        except ValueError:
            rating = None

        review_count_text = product.css("span.count--DZ9M0::text").get("0")
        review_count_text = re.sub(r"[^\d]", "", review_count_text)
        review_count = int(review_count_text) if review_count_text else 0

        seller = product.css("span.seller--rdKgz::text").get("Daraz Seller")
        image_url = product.css("img.image--hYVJM::attr(src)").get("")

        # Daraz rarely shows stock on listing page
        stock_status = "In Stock"
        sold_count = product.css("span.sold--PfCOl::text").get("")

        return ProductItem(
            product_id=re.search(r"-i(\d+)-", product_url or ""),
            name=name,
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            rating=rating,
            review_count=review_count,
            seller=seller,
            stock_status=stock_status,
            stock_count=None,
            category=self.query,
            url=product_url,
            image_url=image_url,
            scraped_at=datetime.utcnow().isoformat(),
            source="daraz",
        )

    @staticmethod
    def _clean_price(raw: str) -> float | None:
        cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
