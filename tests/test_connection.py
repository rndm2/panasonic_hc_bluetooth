"""Exercise the installed HA wrapper's real route-selection and slot paths."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from custom_components.panasonic_hc.connection import PanasonicBleakClient, RoutePolicy


def route(source, rssi, *, remote=False, free=True):
    scanner = Mock()
    scanner.source = source
    scanner.connector = Mock() if remote else None
    if scanner.connector:
        scanner.connector.can_connect.return_value = free
    scanner.get_allocations.return_value = None
    device = BLEDevice("AA:BB:CC:DD:EE:FF", "Controller", {"source": source} if remote else {})
    return SimpleNamespace(
        scanner=scanner,
        ble_device=device,
        advertisement=SimpleNamespace(rssi=rssi),
        score_connection_path=lambda diff: rssi,
    )


def client_for(paths, policy):
    manager = Mock()
    manager.async_scanner_devices_by_address.return_value = paths
    manager.async_allocate_connection_slot.return_value = True
    with patch("habluetooth.wrappers.get_manager", return_value=manager):
        client = PanasonicBleakClient(paths[0].ble_device, route_policy=policy)
    return client, manager


def test_failed_local_route_skipped_only_for_this_controller():
    local, proxy = route("LOCAL", -40), route("PROXY", -85, remote=True)
    policy = RoutePolicy(excluded={"LOCAL"})
    client, manager = client_for([local, proxy], policy)
    backend = client._async_get_best_available_backend_and_device(manager)
    assert backend.scanner is proxy.scanner
    assert policy.selected == "PROXY"
    manager.async_allocate_connection_slot.assert_not_called()
    local.scanner._finished_connecting.assert_not_called()
    # A separate controller/client still sees and may select the local adapter.
    other, other_manager = client_for([local, proxy], RoutePolicy())
    with patch(
        "habluetooth.wrappers.get_platform_client_backend_type", return_value=(Mock, "test")
    ):
        assert (
            other._async_get_best_available_backend_and_device(other_manager).scanner
            is local.scanner
        )
    other_manager.async_allocate_connection_slot.assert_called_once_with(local.ble_device)


def test_confirmed_proxy_preferred_over_stronger_local():
    local, proxy = route("LOCAL", -40), route("PROXY", -85, remote=True)
    policy = RoutePolicy(preferred="PROXY")
    client, manager = client_for([local, proxy], policy)
    assert client._async_get_best_available_backend_and_device(manager).scanner is proxy.scanner
    manager.async_allocate_connection_slot.assert_not_called()


@pytest.mark.parametrize("missing", [False, True])
def test_unavailable_preferred_source_falls_back_to_free_path(missing):
    busy = route("PREFERRED", -50, remote=True, free=False)
    alternate = route("ALTERNATE", -80, remote=True)
    paths = [alternate] if missing else [busy, alternate]
    policy = RoutePolicy(preferred="PREFERRED")
    client, manager = client_for(paths, policy)
    assert client._async_get_best_available_backend_and_device(manager).scanner is alternate.scanner
    assert policy.selected == "ALTERNATE"


def test_all_excluded_routes_allocate_nothing():
    local = route("LOCAL", -40)
    policy = RoutePolicy(excluded={"LOCAL"})
    client, manager = client_for([local], policy)
    manager.async_current_scanners.return_value = []
    with pytest.raises(BleakError, match="No backend"):
        client._async_get_best_available_backend_and_device(manager)
    assert policy.selected is None
    manager.async_allocate_connection_slot.assert_not_called()
