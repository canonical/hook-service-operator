# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to access the service CLI."""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import BinaryIO, Optional, TextIO

from ops.model import Container
from ops.pebble import Error, ExecError

from constants import WORKLOAD_SERVICE
from env_vars import EnvVars
from exceptions import CharmError, CreateFgaStoreError, MigrationCheckError, MigrationError

VERSION_REGEX = re.compile(r"App Version:\s*(?P<version>\S+)\s*$")

logger = logging.getLogger(__name__)


@dataclass
class CmdExecConfig:
    """Command Execution Config."""

    service_context: Optional[str] = None
    environment: EnvVars = field(default_factory=dict)
    timeout: float = 20
    stdin: Optional[str | bytes | TextIO | BinaryIO] = None


class CommandLine:
    """A class to handle command line interactions with the service."""

    def __init__(self, container: Container):
        self.container = container

    def get_service_version(self) -> Optional[str]:
        """Get the service version."""
        cmd = ["hook-service", "version"]

        try:
            stdout, _ = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the service version: %s", err)
            return None

        matched = VERSION_REGEX.search(stdout)
        return matched.group("version") if matched else None

    def create_openfga_model(
        self,
        url: str,
        api_token: str,
        store_id: str,
    ) -> Optional[str]:
        cmd = [
            "hook-service",
            "create-fga-model",
            "--fga-api-url",
            url,
            "--fga-api-token",
            api_token,
            "--fga-store-id",
            store_id,
            "--format",
            "json",
        ]

        try:
            stdout, _ = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to create the OpenFGA model: %s", err)
            raise CreateFgaStoreError from err

        out = json.loads(stdout)
        return out.get("model_id")

    def migrate_up(self, dsn: str, timeout: float = 120) -> None:
        """Migrate the service up using the provided DSN.

        Args:
            dsn (str): The data source name used to connect to the service.
            timeout (float): The timeout for the migration command.

        Raises:
            MigrationError: If the migration fails.
        """
        cmd = [
            "hook-service",
            "migrate",
            "up",
            "--dsn",
            dsn,
            "-f",
            "json",
        ]

        try:
            self._run_cmd(
                cmd,
                exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE, timeout=timeout),
            )
        except Error as err:
            logger.error("Failed to migrate up the service: %s", err)
            raise MigrationError from err

    def migrate_down(self, dsn: str, version: Optional[str] = None, timeout: float = 120) -> None:
        """Migrate the service down to a specific version using the provided DSN.

        Args:
            dsn (str): The data source name used to connect to the service.
            version (Optional[str]): The target version to migrate down to. If None, migrates down all the way.
            timeout (float): The timeout for the migration command.

        Raises:
            MigrationError: If the migration fails.
        """
        cmd = [
            "hook-service",
            "migrate",
            "down",
            "--dsn",
            dsn,
            "-f",
            "json",
        ]

        if version:
            cmd.extend([version])

        try:
            self._run_cmd(
                cmd,
                exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE, timeout=timeout),
            )
        except Error as err:
            logger.error("Failed to migrate down the service: %s", err)
            raise MigrationError from err

    def migration_check(self, dsn: str) -> bool:
        """Check the migration status of the service using the provided DSN.

        Args:
            dsn (str): The data source name used to connect to the service.

        Returns:
            bool: True if the migration status is "ok", False otherwise.

        Raises:
            MigrationCheckError: If the migration check fails or returns an error.
        """
        cmd = [
            "hook-service",
            "migrate",
            "check",
            "--dsn",
            dsn,
            "-f",
            "json",
        ]

        try:
            stdout, stderr = self._run_cmd(
                cmd,
                exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
            )
        except Error as err:
            logger.error("Failed to check migration status: %s", err)
            raise MigrationCheckError("Failed to check migration status") from err

        if stderr:
            logger.error("Migration check error: %s", stderr)
            raise MigrationCheckError(f"Migration check error: {stderr}")

        out = json.loads(stdout)

        return out.get("status") == "ok"

    def import_groups(
        self,
        dsn: str,
        driver: str,
        domain: str,
        consumer_key: str,
        consumer_secret: str,
        sync: bool = False,
        openfga_host: str = "",
        openfga_store_id: str = "",
        openfga_token: str = "",
        openfga_model_id: str = "",
        timeout: float = 300,
    ) -> str:
        """Run the import command.

        Args:
            dsn (str): The data source name used to connect to the service.
            driver (str): The import driver to use.
            domain (str): External API domain.
            consumer_key (str): External API consumer key.
            consumer_secret (str): External API consumer secret.
            sync (bool): Reconcile the DB with driver data, removing stale groups and memberships.
            openfga_host (str): OpenFGA API host (required when sync=True and authorization is enabled).
            openfga_store_id (str): OpenFGA store ID.
            openfga_token (str): OpenFGA API token.
            openfga_model_id (str): OpenFGA authorization model ID.
            timeout (float): The timeout for the command.

        Returns:
            str: stdout of the command.
        """
        cmd = [
            "hook-service",
            "import",
            "--driver",
            driver,
            "--dsn",
            dsn,
            "--domain",
            domain,
            "--consumer-key",
            consumer_key,
            "--consumer-secret",
            consumer_secret,
        ]

        if sync:
            cmd.append("--sync")

        if openfga_host:
            cmd.extend(["--openfga-host", openfga_host])
        if openfga_store_id:
            cmd.extend(["--openfga-store-id", openfga_store_id])
        if openfga_token:
            cmd.extend(["--openfga-token", openfga_token])
        if openfga_model_id:
            cmd.extend(["--openfga-model-id", openfga_model_id])

        try:
            stdout, _ = self._run_cmd(
                cmd,
                exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE, timeout=timeout),
            )
        except Error as err:
            logger.error("Failed to run import groups: %s", err)
            raise CharmError("Failed to run import command") from err

        return stdout

    def users_delete(self, dsn: str, user_id: str) -> None:
        """Remove a user from all groups.

        Args:
            dsn (str): The data source name used to connect to the service.
            user_id (str): The user ID (email) to remove from all groups.

        Raises:
            CharmError: If the command fails.
        """
        cmd = [
            "hook-service",
            "users",
            "delete",
            user_id,
            "--dsn",
            dsn,
        ]

        try:
            self._run_cmd(cmd, exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE))
        except Error as err:
            logger.error("Failed to delete user %s: %s", user_id, err)
            raise CharmError("Failed to run users delete command") from err

    def users_list_groups(self, dsn: str, user_id: str) -> str:
        """List all groups a user belongs to.

        Args:
            dsn (str): The data source name used to connect to the service.
            user_id (str): The user ID (email) to list groups for.

        Returns:
            str: JSON-encoded list of groups.

        Raises:
            CharmError: If the command fails.
        """
        cmd = [
            "hook-service",
            "users",
            "list-groups",
            user_id,
            "--dsn",
            dsn,
            "--format",
            "json",
        ]

        try:
            stdout, _ = self._run_cmd(
                cmd, exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE)
            )
        except Error as err:
            logger.error("Failed to list groups for user %s: %s", user_id, err)
            raise CharmError("Failed to run users list-groups command") from err

        return stdout

    def users_set_groups(self, dsn: str, user_id: str, group_ids: list[str]) -> None:
        """Replace a user's group memberships.

        Args:
            dsn (str): The data source name used to connect to the service.
            user_id (str): The user ID (email) whose memberships to replace.
            group_ids (list[str]): The group IDs to assign to the user.

        Raises:
            CharmError: If the command fails.
        """
        cmd = [
            "hook-service",
            "users",
            "set-groups",
            user_id,
            "--dsn",
            dsn,
        ]
        for group_id in group_ids:
            cmd.extend(["--group", group_id])

        try:
            self._run_cmd(cmd, exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE))
        except Error as err:
            logger.error("Failed to set groups for user %s: %s", user_id, err)
            raise CharmError("Failed to run users set-groups command") from err

    def groups_add_users(self, dsn: str, group_id: str, user_ids: list[str]) -> None:
        """Add users to a group.

        Args:
            dsn (str): The data source name used to connect to the service.
            group_id (str): The group ID to add users to.
            user_ids (list[str]): The user IDs (emails) to add.

        Raises:
            CharmError: If the command fails.
        """
        cmd = [
            "hook-service",
            "groups",
            "add-users",
            group_id,
            "--dsn",
            dsn,
        ]
        for user_id in user_ids:
            cmd.extend(["--user", user_id])

        try:
            self._run_cmd(cmd, exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE))
        except Error as err:
            logger.error("Failed to add users to group %s: %s", group_id, err)
            raise CharmError("Failed to run groups add-users command") from err

    def groups_remove_users(self, dsn: str, group_id: str, user_ids: list[str]) -> None:
        """Remove users from a group.

        Args:
            dsn (str): The data source name used to connect to the service.
            group_id (str): The group ID to remove users from.
            user_ids (list[str]): The user IDs (emails) to remove.

        Raises:
            CharmError: If the command fails.
        """
        cmd = [
            "hook-service",
            "groups",
            "remove-users",
            group_id,
            "--dsn",
            dsn,
        ]
        for user_id in user_ids:
            cmd.extend(["--user", user_id])

        try:
            self._run_cmd(cmd, exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE))
        except Error as err:
            logger.error("Failed to remove users from group %s: %s", group_id, err)
            raise CharmError("Failed to run groups remove-users command") from err

    def groups_list_users(self, dsn: str, group_id: str) -> str:
        """List all users in a group.

        Args:
            dsn (str): The data source name used to connect to the service.
            group_id (str): The group ID to list users for.

        Returns:
            str: JSON-encoded list of users.

        Raises:
            CharmError: If the command fails.
        """
        cmd = [
            "hook-service",
            "groups",
            "list-users",
            group_id,
            "--dsn",
            dsn,
            "--format",
            "json",
        ]

        try:
            stdout, _ = self._run_cmd(
                cmd, exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE)
            )
        except Error as err:
            logger.error("Failed to list users in group %s: %s", group_id, err)
            raise CharmError("Failed to run groups list-users command") from err

        return stdout

    def _run_cmd(
        self,
        cmd: list[str],
        exec_config: Optional[CmdExecConfig] = None,
    ) -> tuple[str, str]:
        if exec_config is None:
            exec_config = CmdExecConfig()
        logger.debug("Running command: %s", cmd)

        process = self.container.exec(cmd, **asdict(exec_config))
        try:
            stdout, stderr = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return stdout, stderr
