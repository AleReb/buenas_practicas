import unittest
from datetime import datetime

from historico_v3 import _decode_cursor, _encode_cursor, _parse_date


class CursorTests(unittest.TestCase):
    def test_cursor_round_trip(self):
        fecha = datetime(2026, 7, 27, 12, 30, 45)
        encoded = _encode_cursor(1028, fecha, 12345)
        self.assertEqual(_decode_cursor(encoded), (1028, fecha, 12345))

    def test_invalid_cursor(self):
        with self.assertRaises(ValueError):
            _decode_cursor("no-es-un-cursor")

    def test_dates(self):
        self.assertEqual(_parse_date("2026-07-27", "fecha").isoformat(), "2026-07-27")


if __name__ == "__main__":
    unittest.main()
