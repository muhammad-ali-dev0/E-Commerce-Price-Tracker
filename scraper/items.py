import scrapy
from dataclasses import dataclass
from datetime import datetime


class ProductItem(scrapy.Item):
    """Scrapy Item for e-commerce product data."""
    product_id    = scrapy.Field()
    name          = scrapy.Field()
    price         = scrapy.Field()
    original_price= scrapy.Field()
    discount_pct  = scrapy.Field()
    rating        = scrapy.Field()
    review_count  = scrapy.Field()
    seller        = scrapy.Field()
    stock_status  = scrapy.Field()
    stock_count   = scrapy.Field()
    category      = scrapy.Field()
    url           = scrapy.Field()
    image_url     = scrapy.Field()
    scraped_at    = scrapy.Field()
    source        = scrapy.Field()   # amazon / daraz / aliexpress
