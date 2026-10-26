"""The conftest autouse network guard must block live calls and allow loopback."""

import socket

import pytest
from conftest import NetworkBlockedError


def test_dns_lookup_to_external_host_is_blocked(network_attempts):
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("api.anthropic.com", 443)
    assert network_attempts == ["api.anthropic.com"]
    network_attempts.clear()


def test_connect_to_external_ip_is_blocked(network_attempts):
    with pytest.raises(NetworkBlockedError), socket.socket() as s:
        s.connect(("93.184.216.34", 80))
    assert network_attempts == ["93.184.216.34"]
    network_attempts.clear()


def test_swallowed_attempt_is_still_recorded(network_attempts):
    """Code that catches the error must not hide the live call: teardown asserts on this list."""
    try:
        socket.create_connection(("example.com", 80), timeout=1)
    except Exception:
        pass
    assert network_attempts == ["example.com"]
    network_attempts.clear()


def test_loopback_is_allowed(network_attempts):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket() as client:
            client.connect(server.getsockname())
    assert network_attempts == []
