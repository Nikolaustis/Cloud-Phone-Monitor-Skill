import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProductRecord(BaseModel):
    platform: str = ""
    source_url: str = ""
    crawl_time_utc: str = ""
    crawl_time_local: str = ""
    region_selected: Optional[str] = None
    server_region: Optional[str] = None
    currency: Optional[str] = None
    product_category: Optional[str] = None
    product_name: Optional[str] = None
    product_model: Optional[str] = None
    device_model: Optional[str] = None
    android_version: Optional[str] = None
    cpu: Optional[str] = None
    ram: Optional[str] = None
    storage: Optional[str] = None
    price: Optional[str] = None
    original_price: Optional[str] = None
    discount_price: Optional[str] = None
    billing_period: Optional[str] = None
    duration: Optional[str] = None
    stock_status: Optional[str] = None
    promotion_text: Optional[str] = None
    promotion_start_time: Optional[str] = None
    promotion_end_time: Optional[str] = None
    raw_text: Optional[str] = None
    extraction_method: str = ""
    confidence: str = "low"
    screenshot_path: Optional[str] = None
    html_path: Optional[str] = None
    api_response_path: Optional[str] = None
    notes: Optional[str] = None
    record_hash: str = Field(default="")

    def compute_hash(self) -> str:
        material = {
            "platform": self.platform,
            "region_selected": self.region_selected,
            "server_region": self.server_region,
            "product_model": self.product_model,
            "product_name": self.product_name,
            "device_model": self.device_model,
            "android_version": self.android_version,
            "billing_period": self.billing_period,
            "duration": self.duration,
            "price": self.price,
            "currency": self.currency,
        }
        data = json.dumps(material, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:24]

    def finalize(self) -> "ProductRecord":
        self.record_hash = self.compute_hash()
        return self

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump()


PRODUCT_COLUMNS = list(ProductRecord.model_fields.keys())
