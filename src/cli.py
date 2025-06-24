# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to access the service CLI."""

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import BinaryIO, List, Optional, TextIO

from ops.model import Container
from ops.pebble import Error, ExecError

from env_vars import EnvVars

VERSION_REGEX = re.compile(r"App Version:\s*(?P<version>\S+)\s*$")

logger = logging.getLogger(__name__)


@dataclass
class CmdExecConfig:
    """Command Execution Config."""

    service_context: Optional[str] = None
    environment: EnvVars = field(default_factory=dict)
    timeout: int = 20
    stdin: Optional[str | bytes | TextIO | BinaryIO] = None


class CommandLine:
    """A class to handle command line interactions with the service."""

    def __init__(self, container: Container):
        self.container = container

    def get_service_version(self) -> Optional[str]:
        """Get the service version."""
        cmd = ["hook-service", "version"]

        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the service version: %s", err)
            return None

        matched = VERSION_REGEX.search(stdout)
        return matched.group("version") if matched else None

    def _run_cmd(
        self,
        cmd: List[str],
        exec_config: CmdExecConfig = CmdExecConfig(),
    ) -> str:
        logger.debug(f"Running command: {cmd}")

        process = self.container.exec(cmd, **asdict(exec_config))
        try:
            stdout, _ = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return stdout
