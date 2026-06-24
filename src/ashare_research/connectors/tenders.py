from __future__ import annotations

from .http import HttpJsonConnector


class TenderConnector(HttpJsonConnector):
    source = "tenders"
