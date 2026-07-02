import unittest

from cloud_phone_monitor.utils.dashboard_export import parse_duration_info


class DurationParsingTest(unittest.TestCase):
    def assert_duration(self, text, days, bucket, display, core):
        result = parse_duration_info(text)
        self.assertEqual(result["duration_days"], days)
        self.assertEqual(result["duration_bucket"], bucket)
        self.assertEqual(result["duration_display"], display)
        self.assertEqual(result["is_core_duration_bucket"], core)

    def test_hour_bucket_is_other(self):
        result = parse_duration_info("4 hour")
        self.assertAlmostEqual(result["duration_days"], 4 / 24, places=6)
        self.assertEqual(result["duration_bucket"], "other")
        self.assertEqual(result["duration_display"], "4小时")
        self.assertFalse(result["is_core_duration_bucket"])
        self.assertEqual(result["exclusion_reason"], "short_duration_not_core_bucket")

    def test_core_day_buckets(self):
        for text, days in [
            ("1 day", 1),
            ("3 days", 3),
            ("7 day", 7),
            ("15 days", 15),
            ("30 day", 30),
            ("2 months", 60),
            ("60 day", 60),
            ("15日", 15),
            (15, 15),
            ("15", 15),
            ("90 day", 90),
            ("180 day", 180),
            ("365 day", 365),
        ]:
            with self.subTest(text=text):
                self.assert_duration(text, days, days, f"{days}天", True)

    def test_non_core_day_bucket(self):
        self.assert_duration("45 days-Duet Pack", 45, "other", "45天", False)
        self.assert_duration("120 days", 120, "other", "120天", False)

    def test_device_count_text_is_not_duration(self):
        result = parse_duration_info("Get 2 Devices")
        self.assertIsNone(result["duration_days"])
        self.assertEqual(result["duration_bucket"], "unknown")
        self.assertEqual(result["duration_parse_status"], "failed")

    def test_promotion_date_is_not_duration(self):
        result = parse_duration_info("4.23-4.28 特价")
        self.assertIsNone(result["duration_days"])
        self.assertEqual(result["duration_bucket"], "unknown")
        self.assertEqual(result["duration_parse_status"], "failed")


if __name__ == "__main__":
    unittest.main()
