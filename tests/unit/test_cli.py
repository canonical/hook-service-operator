# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import ExecError

from cli import CommandLine


class TestCommandLine:
    @pytest.fixture
    def command_line(self, mocked_container: MagicMock) -> CommandLine:
        return CommandLine(mocked_container)

    def test_get_service_version(self, command_line: CommandLine) -> None:
        expected = "v1.0.0"
        with patch.object(
            command_line,
            "_run_cmd",
            return_value=(f"App Version: {expected}", ""),
        ) as run_cmd:
            actual = command_line.get_service_version()
            assert actual == expected
            run_cmd.assert_called_with(["hook-service", "version"])

    def test_run_cmd(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd, expected_stdout, expected_stderr = ["cmd"], "stdout", "stderr"

        mocked_process = MagicMock(
            wait_output=MagicMock(return_value=(expected_stdout, expected_stderr))
        )
        mocked_container.exec.return_value = mocked_process

        actual_stdout, actual_stderr = command_line._run_cmd(cmd)

        assert actual_stdout == expected_stdout
        assert actual_stderr == expected_stderr
        mocked_container.exec.assert_called_once_with(
            cmd, service_context=None, timeout=20, environment={}, stdin=None
        )

    def test_run_cmd_failed(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd = ["cmd"]

        mocked_process = MagicMock(wait_output=MagicMock(side_effect=ExecError(cmd, 1, "", "")))
        mocked_container.exec.return_value = mocked_process

        with pytest.raises(ExecError):
            command_line._run_cmd(cmd)
