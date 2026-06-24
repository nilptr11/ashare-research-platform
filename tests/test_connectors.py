import json
from types import SimpleNamespace

import pandas as pd

from ashare_research.cli import main
from ashare_research.connectors import AkshareConnector, ConnectorRegistry, ConnectorSpec, HttpJsonConnector, HttpPayload
from ashare_research.schemas import SourceResponse


def test_akshare_connector_calls_named_function():
    module = SimpleNamespace(stock_zh_a_spot_em=lambda symbol: pd.DataFrame([{"symbol": symbol, "price": 10.5}]))

    response = AkshareConnector(module=module).fetch("stock_zh_a_spot_em", {"symbol": "全部"}, fields=["symbol"])

    assert response.source == "akshare"
    assert response.rows == 1
    assert response.columns == ("symbol",)
    assert response.frame.iloc[0]["symbol"] == "全部"


def test_http_json_connector_uses_transport_and_normalizes_data():
    def transport(method, url, params, headers, body):
        assert method == "POST"
        assert url == "https://example.com/api"
        assert params == {"query": "AI"}
        assert headers == {"User-Agent": "ashare-test"}
        assert body == {"page": 1}
        return HttpPayload(
            status=200,
            body=json.dumps({"data": [{"title": "policy", "value": 1}]}),
            headers={},
            url=url,
        )

    response = HttpJsonConnector(transport=transport).fetch(
        "policy_search",
        {
            "url": "https://example.com/api",
            "method": "POST",
            "query": "AI",
            "headers": {"User-Agent": "ashare-test"},
            "body": {"page": 1},
        },
    )

    assert response.source == "http_json"
    assert response.rows == 1
    assert response.params["status"] == 200
    assert response.frame.iloc[0]["title"] == "policy"


def test_connector_registry_lists_builtin_connectors():
    names = {spec.name for spec in ConnectorRegistry.builtin().list()}

    assert {"tushare", "akshare", "cninfo", "official_announcement", "policy", "tenders"} <= names


def test_cli_connectors_list_and_fetch_with_raw_store(monkeypatch, capsys, tmp_path):
    class FakeConnector:
        source = "fake"

        def fetch(self, api_name, params, fields=None):
            frame = pd.DataFrame([{"name": "record", "value": params["value"]}])
            return SourceResponse(
                source=self.source,
                api_name=api_name,
                params=dict(params),
                fields=tuple(fields or ()),
                rows=len(frame),
                columns=tuple(frame.columns),
                requested_at="2026-06-24T18:00:00+08:00",
                frame=frame,
            )

    registry = ConnectorRegistry(
        [
            ConnectorSpec(
                name="fake",
                title="Fake",
                factory=lambda **_: FakeConnector(),
                kind="test",
            )
        ]
    )
    monkeypatch.setattr(ConnectorRegistry, "builtin", classmethod(lambda cls: registry))

    exit_code = main(["--data-dir", str(tmp_path), "connectors", "list", "--format", "json"])
    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload[0]["name"] == "fake"

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "connectors",
            "fetch",
            "fake",
            "api",
            "-p",
            "value=42",
            "--fields",
            "name,value",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "fake"
    assert payload["preview"][0]["value"] == "42"
    assert payload["raw_path"]
