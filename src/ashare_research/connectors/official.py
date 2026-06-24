from __future__ import annotations

from .http import HttpJsonConnector


class OfficialAnnouncementConnector(HttpJsonConnector):
    source = "official_announcement"
