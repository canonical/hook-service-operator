# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from types import TracebackType

import requests
from typing_extensions import Self, Type

from constants import PORT


class HTTPClient:
    def __init__(self, token_url: str = "", base_url: str = f"http://localhost:{PORT}") -> None:
        self._token_url = token_url.rstrip("/")
        self._base_url = base_url.rstrip("/")
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

    def create_group(
        self,
        name: str,
        description: str,
        group_type: str = "local",
        access_token: str = "",
    ) -> str:
        """Create a group via the hook-service API.

        Args:
            name: Group name.
            description: Group description.
            group_type: Group type (default: "local").
            access_token: Optional JWT Bearer token. Omit for unauthenticated access.

        Returns:
            The ID of the created group.
        """
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        response = self._session.post(
            f"{self._base_url}/api/v0/authz/groups",
            headers=headers,
            json={"name": name, "description": description, "type": group_type},
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["id"]

    def delete_group(self, group_id: str, access_token: str = "") -> None:
        """Delete a group via the hook-service API.

        Args:
            group_id: The ID of the group to delete.
            access_token: Optional JWT Bearer token. Omit for unauthenticated access.
        """
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        response = self._session.delete(
            f"{self._base_url}/api/v0/authz/groups/{group_id}",
            headers=headers,
        )
        response.raise_for_status()

    def list_groups(self, access_token: str = "") -> list:
        """List all groups via the hook-service API.

        Args:
            access_token: Optional JWT Bearer token. Omit for unauthenticated access.

        Returns:
            List of group objects.
        """
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        response = self._session.get(
            f"{self._base_url}/api/v0/authz/groups",
            headers=headers,
        )
        response.raise_for_status()
        return response.json().get("data", [])
