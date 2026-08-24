from types import SimpleNamespace

import pandas as pd

from cloud_phone_monitor.scrapers.vsphone import VSPhoneScraper
from cloud_phone_monitor.utils.dashboard_export import (
    PURCHASE_MODE_NON_SUBSCRIPTION,
    PURCHASE_MODE_STANDARD,
    PURCHASE_MODE_SUBSCRIPTION,
    normalize_purchase_mode,
    signature_with_purchase_mode,
)
from cloud_phone_monitor.utils.price_quality import subscription_default_quality_rows


def _scraper_for_api_test() -> VSPhoneScraper:
    scraper = object.__new__(VSPhoneScraper)
    scraper.config = SimpleNamespace(timezone="UTC")
    scraper.blocked_reason = None
    scraper.collection_summary = {}
    scraper.selection_contexts = [
        {
            "device_model": "高端真机",
            "android_version": "10",
            "server_region": "Hong Kong",
        }
    ]
    scraper.context_artifacts = {}
    scraper.purchase_mode_artifacts = {}
    scraper.purchase_mode_evidence = {
        ("高端真机", "10", "Hong Kong", "subscription"): {
            "cards": [
                {
                    "product_model": "VIP",
                    "duration": "30 days",
                    "price": "5.99",
                    "original_price": "10.49",
                }
            ]
        },
        ("高端真机", "10", "Hong Kong", "non_subscription"): {
            "cards": [
                {
                    "product_model": "VIP",
                    "duration": "30 days",
                    "price": "10.49",
                    "original_price": "10.49",
                }
            ]
        },
    }
    scraper.api_candidates = [
        {
            "url": "https://api.vsphone.com/vsphone/api/vcCloudGood/getCloudGoodList_V5",
            "interactive_context": {
                "device_model": "高端真机",
                "android_version": "10",
                "server_region": "Hong Kong",
            },
            "response_json": {
                "data": {
                    "configs": [
                        {
                            "configName": "VIP",
                            "custom": False,
                            "sellOutFlag": False,
                            "icons": [],
                            "goodTimes": [
                                {
                                    "showContent": "30 days",
                                    "currentPrice": 599,
                                    "goodPrice": 599,
                                    "oldGoodPrice": 1049,
                                    "autoRenew": True,
                                },
                                {
                                    "showContent": "14 days",
                                    "currentPrice": 499,
                                    "goodPrice": 499,
                                    "oldGoodPrice": 699,
                                    "autoRenew": True,
                                },
                            ],
                        }
                    ]
                }
            },
        }
    ]
    return scraper


def test_vsphone_api_records_emit_verified_subscription_and_non_subscription() -> None:
    scraper = _scraper_for_api_test()
    records = scraper._records_from_api("https://cloud.vsphone.com/buy", "page.png", "page.html")

    rows = {(record.duration, record.purchase_mode): record for record in records}
    assert rows[("30 day", "subscription")].price == "5.99"
    assert rows[("30 day", "non_subscription")].price == "10.49"
    assert "quantity=1" in (rows[("30 day", "non_subscription")].notes or "")
    assert "footer_order_total_excluded" in (rows[("30 day", "non_subscription")].notes or "")
    assert ("14 day", "subscription") in rows
    assert ("14 day", "non_subscription") not in rows


def test_vsphone_non_subscription_requires_ui_verification() -> None:
    scraper = _scraper_for_api_test()
    scraper.purchase_mode_evidence.pop(("高端真机", "10", "Hong Kong", "non_subscription"))
    records = scraper._records_from_api("https://cloud.vsphone.com/buy", "page.png", "page.html")
    assert {record.purchase_mode for record in records} == {"subscription"}


def test_dashboard_purchase_mode_supports_vsphone_and_legacy_defaults() -> None:
    assert normalize_purchase_mode("UgPhone", None) == PURCHASE_MODE_SUBSCRIPTION
    assert normalize_purchase_mode("VSPhone", None) == PURCHASE_MODE_SUBSCRIPTION
    assert normalize_purchase_mode("VSPhone", "non_subscription") == PURCHASE_MODE_NON_SUBSCRIPTION
    assert normalize_purchase_mode("Redfinger", "non_subscription") == PURCHASE_MODE_STANDARD
    assert "purchase_mode=non_subscription" in signature_with_purchase_mode(
        "VSPhone", "cpu=8|ram=4GB", "non_subscription"
    )


def test_quality_comparison_excludes_non_subscription_for_ugphone_and_vsphone() -> None:
    frame = pd.DataFrame(
        [
            {"platform": "UgPhone", "purchase_mode": "subscription", "price": 1},
            {"platform": "UgPhone", "purchase_mode": "non_subscription", "price": 2},
            {"platform": "VSPhone", "purchase_mode": "subscription", "price": 3},
            {"platform": "VSPhone", "purchase_mode": "non_subscription", "price": 4},
            {"platform": "Redfinger", "purchase_mode": "standard", "price": 5},
        ]
    )
    filtered = subscription_default_quality_rows(frame)
    assert filtered["price"].tolist() == [1, 3, 5]


def test_json_safe_handles_nested_lists_and_numpy_arrays() -> None:
    import numpy as np

    from cloud_phone_monitor.utils.dashboard_export import json_safe

    value = {
        "ug_config_ids": ["config-a", "history_non_subscription"],
        "array": np.array([1, 2]),
        "missing": [pd.NA, float("nan")],
    }
    assert json_safe(value) == {
        "ug_config_ids": ["config-a", "history_non_subscription"],
        "array": [1, 2],
        "missing": [None, None],
    }


class _FakeConfirmationPage:
    def __init__(self) -> None:
        self.checked = True
        self.dialog_open = True
        self.clicked = False

    def evaluate(self, script, arg=None):
        if "desiredEnabled" in script:
            if self.dialog_open and arg and arg.get("desiredEnabled") is False:
                self.dialog_open = False
                self.checked = False
                self.clicked = True
                return {"found": True, "clicked": True, "buttonText": "Keep closed"}
            return {"found": False, "clicked": False, "buttonText": ""}
        return {"found": True, "checked": self.checked, "text": "Auto-Renewal"}

    def wait_for_timeout(self, _milliseconds):
        return None


def test_vsphone_disable_confirmation_accepts_keep_closed() -> None:
    scraper = object.__new__(VSPhoneScraper)
    scraper.collection_summary = {
        "auto_renew_confirmation_targets": 0,
        "auto_renew_confirmation_successes": 0,
    }
    scraper.logger = SimpleNamespace(debug=lambda *args, **kwargs: None)
    page = _FakeConfirmationPage()

    assert scraper._resolve_auto_renew_confirmation_dialog(
        page, desired_enabled=False, timeout_ms=500
    )
    assert page.clicked
    assert page.checked is False
    assert scraper.collection_summary["auto_renew_confirmation_successes"] == 1
