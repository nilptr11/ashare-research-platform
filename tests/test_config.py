import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tushare_fastcli.config import load_config, read_env_file


class ConfigTest(unittest.TestCase):
    def test_read_env_file_ignores_comments_and_unquotes_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".env"
            path.write_text(
                "\n".join(
                    [
                        "# comment",
                        "TUSHARE_TOKEN='token_from_file'",
                        'TUSHARE_PROXY_URL="https://proxy.example.com"',
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                read_env_file(path),
                {
                    "TUSHARE_TOKEN": "token_from_file",
                    "TUSHARE_PROXY_URL": "https://proxy.example.com",
                },
            )

    def test_load_config_prefers_cli_then_env_then_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".env"
            path.write_text(
                "TUSHARE_TOKEN=token_from_file\nTUSHARE_PROXY_URL=https://file.example.com\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"TUSHARE_TOKEN": "token_from_env"}, clear=True):
                config = load_config(token="token_from_cli", env_file=path)

            self.assertEqual(config.token, "token_from_cli")
            self.assertEqual(config.proxy_url, "https://file.example.com")
            self.assertEqual(config.points, 15000)
            self.assertFalse(config.allow_separate_permission)

    def test_blank_proxy_url_disables_env_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".env"
            path.write_text("TUSHARE_PROXY_URL=https://file.example.com\n", encoding="utf-8")

            config = load_config(proxy_url="", env_file=path)

            self.assertIsNone(config.proxy_url)

    def test_load_config_reads_points_and_permission_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".env"
            path.write_text(
                "TUSHARE_POINTS=12000\nTUSHARE_ALLOW_SEPARATE_PERMISSION=true\n",
                encoding="utf-8",
            )

            config = load_config(env_file=path)

            self.assertEqual(config.points, 12000)
            self.assertTrue(config.allow_separate_permission)


if __name__ == "__main__":
    unittest.main()
