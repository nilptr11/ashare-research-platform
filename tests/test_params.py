import unittest

from tushare_fastcli.params import ParameterError, merge_params, parse_param_pair


class ParamParsingTest(unittest.TestCase):
    def test_parse_param_pair_keeps_plain_value_as_string(self) -> None:
        self.assertEqual(parse_param_pair("start_date=20240101"), ("start_date", "20240101"))

    def test_parse_param_pair_supports_json_value(self) -> None:
        self.assertEqual(parse_param_pair("limit:=100"), ("limit", 100))

    def test_merge_params_order_allows_pair_override(self) -> None:
        params = merge_params('{"ts_code":"000001.SZ","start_date":"20230101"}', None, ["start_date=20240101"])
        self.assertEqual(params, {"ts_code": "000001.SZ", "start_date": "20240101"})

    def test_invalid_pair_raises(self) -> None:
        with self.assertRaises(ParameterError):
            parse_param_pair("bad")


if __name__ == "__main__":
    unittest.main()
