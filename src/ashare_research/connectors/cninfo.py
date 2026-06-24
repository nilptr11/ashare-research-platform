from __future__ import annotations

from .http import HttpJsonConnector


class CninfoConnector(HttpJsonConnector):
    source = "cninfo"
