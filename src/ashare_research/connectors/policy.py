from __future__ import annotations

from .http import HttpJsonConnector


class PolicyConnector(HttpJsonConnector):
    source = "policy"
