from __future__ import annotations

import unittest

from ogorodom_bot.services.time_utils import (
    format_local_datetime,
    iso,
    parse_local_datetime,
    parse_planting_date,
)


class TimeUtilsTests(unittest.TestCase):
    def test_parse_datetime_with_trailing_dot(self) -> None:
        value = parse_local_datetime("2026-05-25 12:00.", "Europe/Moscow")

        self.assertEqual(iso(value), "2026-05-25T09:00:00+00:00")

    def test_parse_russian_date_with_single_digit_hour(self) -> None:
        value = parse_local_datetime("25.05.2026 2:21", "Europe/Moscow")

        self.assertEqual(iso(value), "2026-05-24T23:21:00+00:00")

    def test_format_local_datetime(self) -> None:
        self.assertEqual(
            format_local_datetime("2026-05-25T09:00:00+00:00", "Europe/Moscow"),
            "25.05.2026 12:00",
        )

    def test_parse_planting_date_accepts_month_and_exact_date(self) -> None:
        self.assertEqual(parse_planting_date("май 2026", "Europe/Moscow"), "май 2026")
        self.assertEqual(parse_planting_date("05.2026", "Europe/Moscow"), "май 2026")
        self.assertEqual(parse_planting_date("2026-05", "Europe/Moscow"), "май 2026")
        self.assertEqual(parse_planting_date("2026-5-5", "Europe/Moscow"), "05.05.2026")
        self.assertEqual(parse_planting_date("2026-05-25", "Europe/Moscow"), "25.05.2026")
        self.assertIsNone(parse_planting_date("-", "Europe/Moscow"))


if __name__ == "__main__":
    unittest.main()
