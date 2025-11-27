# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to access the service CLI."""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import BinaryIO, List, Optional, TextIO

from ops.model import Container
from ops.pebble import Error, ExecError

from constants import WORKLOAD_SERVICE
from env_vars import EnvVars
from exceptions import MigrationCheckError, MigrationError

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
            "--dsn",
            dsn,
            "-f",
            "json",
            "up",
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
            "--dsn",
            dsn,
            "-f",
            "json",
            "down",
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
            "--dsn",
            dsn,
            "-f",
            "json",
            "check",
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

    def _run_cmd(
        self,
        cmd: List[str],
        exec_config: CmdExecConfig = CmdExecConfig(),
    ) -> tuple[str, str]:
        logger.debug(f"Running command: {cmd}")

        process = self.container.exec(cmd, **asdict(exec_config))
        try:
            stdout, stderr = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return stdout, stderr
