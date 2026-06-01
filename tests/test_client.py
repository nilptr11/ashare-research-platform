import unittest

import pandas as pd

from tushare_fastcli.client import TushareCallError, TushareCaller, configure_tushare_proxy


class ClientTest(unittest.TestCase):
    def test_configure_proxy_can_reset_to_sdk_default(self) -> None:
        from tushare.pro import client as ts_client

        original_url = ts_client.DataApi._DataApi__http_url
        try:
            configure_tushare_proxy("https://proxy.example.com")
            self.assertEqual(ts_client.DataApi._DataApi__http_url, "https://proxy.example.com")

            configure_tushare_proxy(None)
            self.assertEqual(ts_client.DataApi._DataApi__http_url, original_url)
        finally:
            ts_client.DataApi._DataApi__http_url = original_url

    def test_error_dataframe_is_treated_as_call_error(self) -> None:
        result = pd.DataFrame([{"error": "请指定正确的接口名"}])

        with self.assertRaisesRegex(TushareCallError, "请指定正确的接口名"):
            TushareCaller._raise_for_error_frame("bo_cinema", result)


if __name__ == "__main__":
    unittest.main()
