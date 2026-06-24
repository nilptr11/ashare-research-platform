from .akshare import AkshareConnector
from .base import ConnectorSpec
from .cninfo import CninfoConnector
from .http import HttpJsonConnector, HttpPayload
from .official import OfficialAnnouncementConnector
from .policy import PolicyConnector
from .registry import ConnectorRegistry, default_connector_specs
from .tenders import TenderConnector
from .tushare import TushareConnector

__all__ = [
    "AkshareConnector",
    "CninfoConnector",
    "ConnectorRegistry",
    "ConnectorSpec",
    "HttpJsonConnector",
    "HttpPayload",
    "OfficialAnnouncementConnector",
    "PolicyConnector",
    "TenderConnector",
    "TushareConnector",
    "default_connector_specs",
]
