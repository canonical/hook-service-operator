# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from types import TracebackType

import requests
from typing_extensions import Self, Type


class HTTPClient:
    def __init__(self, token_url: str) -> None:
        self._token_url = token_url.rstrip("/")
        self._session = requests.Session()
        self._session.verify = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType,
    ) -> None:
        self._session.close()

    def get_access_token(self, client_id: str, client_secret: str) -> str:
        response = self._session.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
            },
            auth=(client_id, client_secret),
        )
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]
