from __future__ import annotations

from typing import Iterable

from ..schemas import ConnectorError
from .akshare import AkshareConnector
from .base import ConnectorSpec
from .cninfo import CninfoConnector
from .official import OfficialAnnouncementConnector
from .policy import PolicyConnector
from .tenders import TenderConnector
from .tushare import TushareConnector


class ConnectorRegistry:
    def __init__(self, specs: Iterable[ConnectorSpec]) -> None:
        self._specs = {spec.name: spec for spec in specs}

    @classmethod
    def builtin(cls) -> "ConnectorRegistry":
        return cls(default_connector_specs())

    def list(self) -> list[ConnectorSpec]:
        return [self._specs[name] for name in sorted(self._specs)]

    def require(self, name: str) -> ConnectorSpec:
        try:
            return self._specs[name]
        except KeyError as error:
            raise ConnectorError(f"connector not found: {name}") from error

    def create(self, name: str, **kwargs: object) -> object:
        spec = self.require(name)
        return spec.factory(**kwargs)


def default_connector_specs() -> list[ConnectorSpec]:
    return [
        ConnectorSpec(
            name="akshare",
            title="AkShare 数据源",
            factory=AkshareConnector,
            kind="sdk",
            description="按 AkShare 函数名获取原始表格数据。",
        ),
        ConnectorSpec(
            name="cninfo",
            title="巨潮资讯 HTTP JSON",
            factory=CninfoConnector,
            kind="http_json",
            requires_url=True,
            description="获取巨潮资讯公告、查询接口等 JSON 响应。",
        ),
        ConnectorSpec(
            name="official_announcement",
            title="交易所/官方公告 HTTP JSON",
            factory=OfficialAnnouncementConnector,
            kind="http_json",
            requires_url=True,
            description="获取交易所或官方平台公告 JSON 响应。",
        ),
        ConnectorSpec(
            name="policy",
            title="政策来源 HTTP JSON",
            factory=PolicyConnector,
            kind="http_json",
            requires_url=True,
            description="获取政策、监管、政府平台 JSON 响应。",
        ),
        ConnectorSpec(
            name="tenders",
            title="招投标来源 HTTP JSON",
            factory=TenderConnector,
            kind="http_json",
            requires_url=True,
            description="获取招投标、采购平台 JSON 响应。",
        ),
        ConnectorSpec(
            name="tushare",
            title="Tushare Pro",
            factory=TushareConnector,
            kind="sdk",
            description="按 Tushare API 名称获取原始表格数据。",
        ),
    ]
