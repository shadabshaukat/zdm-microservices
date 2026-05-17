from __future__ import annotations

from dataclasses import dataclass

from requests.auth import HTTPBasicAuth


@dataclass(frozen=True)
class AppContext:
    api_base: str
    auth: HTTPBasicAuth
    default_base: str
    default_user: str
    default_password: str
    username: str
    password: str
    section: str = ""
    previous_section: str | None = None

    def entering(self, section_key: str) -> bool:
        return self.section == section_key and self.previous_section != section_key
