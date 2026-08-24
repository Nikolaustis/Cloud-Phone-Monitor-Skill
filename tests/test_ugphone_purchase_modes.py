from cloud_phone_monitor.schemas import ProductRecord


def test_purchase_mode_is_part_of_record_identity():
    common = {
        "platform": "UGPhone",
        "product_model": "UVIP",
        "server_region": "America",
        "duration": "30 day",
        "price": "9.99",
    }
    subscription = ProductRecord(**common, purchase_mode="subscription").finalize()
    one_time = ProductRecord(**common, purchase_mode="non_subscription").finalize()
    assert subscription.record_hash != one_time.record_hash


def test_meal_response_count_is_split_by_purchase_mode():
    from cloud_phone_monitor.scrapers.ugphone import UGPhoneScraper

    scraper = object.__new__(UGPhoneScraper)
    scraper.api_candidates = [
        {"url": "https://www.ugphone.com/api/apiv1/info/mealList", "request_payload": {"subscription": 1}},
        {"url": "https://www.ugphone.com/api/apiv1/info/mealList", "request_payload": {"subscription": 0}},
        {"url": "https://www.ugphone.com/api/apiv1/info/mealList", "request_payload": '{"subscription": 0}'},
        {"url": "https://www.ugphone.com/api/apiv1/info/configList2", "request_payload": {}},
    ]

    assert scraper._meal_response_count_for_mode(True) == 1
    assert scraper._meal_response_count_for_mode(False) == 2
