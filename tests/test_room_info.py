import unittest
from unittest.mock import Mock

from utils.RoomInfo import RoomInfo


class RoomInfoQueryTimeoutTests(unittest.TestCase):
    @staticmethod
    def _successful_response():
        response = Mock()
        response.headers = {}
        response.json.return_value = {"ret_code": 0, "ret_content": []}
        return response

    def test_query_item_uses_custom_timeout(self):
        room_info = RoomInfo(
            cookie="session=test",
            xgh="20230001",
            query_timeout=300,
        )
        room_info._session = Mock()
        room_info._session.get.return_value = self._successful_response()

        room_info._query_item()

        self.assertEqual(room_info._session.get.call_args.kwargs["timeout"], 300)

    def test_query_timeout_defaults_to_twenty_seconds(self):
        room_info = RoomInfo(cookie="session=test", xgh="20230001")

        self.assertEqual(room_info.query_timeout, 20)

    def test_query_timeout_must_be_positive_number(self):
        for invalid_timeout in (0, -1, "300", True, None):
            with self.subTest(query_timeout=invalid_timeout):
                with self.assertRaises(ValueError):
                    RoomInfo(
                        cookie="session=test",
                        xgh="20230001",
                        query_timeout=invalid_timeout,
                    )


if __name__ == "__main__":
    unittest.main()
