# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, call

from constants import GRPC_PORT, PORT
from services import PebbleService, WorkloadService


class TestWorkloadService:
    def test_open_port_opens_both_http_and_grpc(self, mocked_unit: MagicMock) -> None:
        workload_service = WorkloadService(mocked_unit)
        workload_service.open_port()

        mocked_unit.open_port.assert_has_calls([
            call(protocol="tcp", port=PORT),
            call(protocol="tcp", port=GRPC_PORT),
        ])
        assert mocked_unit.open_port.call_count == 2

    def test_open_port_with_specific_port(self, mocked_unit: MagicMock) -> None:
        workload_service = WorkloadService(mocked_unit)
        workload_service.open_port(port=1234)

        mocked_unit.open_port.assert_called_once_with(protocol="tcp", port=1234)


class TestPebbleService:
    def test_render_pebble_layer_includes_default_ports(self, mocked_unit: MagicMock) -> None:
        pebble_service = PebbleService(mocked_unit)
        layer = pebble_service.render_pebble_layer()

        services = layer.to_dict().get("services", {})
        hook_service = services.get("hook-service", {})
        env = hook_service.get("environment", {})

        assert env.get("PORT") == str(PORT)
        assert env.get("GRPC_PORT") == str(GRPC_PORT)
