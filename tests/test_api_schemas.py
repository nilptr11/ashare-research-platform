import json
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_api_schemas import parse_examples, parse_input_params
from ashare_data_provider.schemas import SchemaError, get_api_schema, load_api_schemas


class ApiSchemasTest(unittest.TestCase):
    def test_parse_input_params_reads_markdown_table(self) -> None:
        text = """
**输入参数**

名称 | 类型  | 必选 | 描述
---- | ----- | ---- | ----
ts_code | str | Y | 股票代码
trade_date | str | N | 交易日期

**输出参数**
"""

        params, status = parse_input_params(text)

        self.assertEqual(status, "ok")
        self.assertEqual(params[0]["name"], "ts_code")
        self.assertEqual(params[0]["required"], "Y")
        self.assertEqual(params[1]["name"], "trade_date")

    def test_parse_examples_extracts_literal_keyword_params(self) -> None:
        text = "df = pro.daily(ts_code='000001.SZ', trade_date='20260423')"

        self.assertEqual(
            parse_examples(text, "daily"),
            [{"ts_code": "000001.SZ", "trade_date": "20260423"}],
        )

    def test_parse_examples_keeps_no_arg_examples(self) -> None:
        text = "df = pro.fund_company()"

        self.assertEqual(parse_examples(text, "fund_company"), [{}])

    def test_load_api_schemas_reads_generated_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "api_schemas.json"
            path.write_text(
                json.dumps(
                    {
                        "schemas": {
                            "daily:27": {
                                "key": "daily:27",
                                "api_name": "daily",
                                "doc_id": "27",
                                "input_params": [
                                    {
                                        "name": "trade_date",
                                        "type": "str",
                                        "required": "N",
                                        "raw_required": "N",
                                        "description": "交易日期",
                                    }
                                ],
                                "required_params": [],
                                "optional_params": ["trade_date"],
                                "example_params": [{"trade_date": "20260423"}],
                                "default_params": {"trade_date": "20260423"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            schemas = load_api_schemas(path)

        self.assertIn("daily:27", schemas)
        self.assertEqual(schemas["daily:27"].params_by_name["trade_date"].type, "str")

    def test_get_api_schema_requires_disambiguation_for_duplicates(self) -> None:
        with self.assertRaises(SchemaError):
            get_api_schema("pro_bar")

    def test_get_api_schema_reads_daily_params(self) -> None:
        schema = get_api_schema("daily")

        self.assertEqual(schema.key, "daily:27")
        self.assertIn("trade_date", schema.params_by_name)


if __name__ == "__main__":
    unittest.main()
