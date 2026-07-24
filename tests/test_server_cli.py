"""forget-server lifecycle CLI — service-file generation is pure and testable."""
from forget.cli import launchd_plist, systemd_unit, SERVICE_LABEL


def test_launchd_plist_shape() -> None:
    plist = launchd_plist("/usr/bin/python3", "127.0.0.1", 8123)
    assert SERVICE_LABEL in plist
    assert "<string>--port</string><string>8123</string>" in plist
    assert "<string>127.0.0.1</string>" in plist
    assert "MEM1_DB_PATH" in plist and "KeepAlive" in plist


def test_systemd_unit_shape() -> None:
    unit = systemd_unit("/usr/bin/python3", "127.0.0.1", 8123)
    assert "ExecStart=/usr/bin/python3 -m uvicorn forget.server:app --host 127.0.0.1 --port 8123" in unit
    assert "Restart=always" in unit and "MEM1_DB_PATH" in unit


def test_mcp_initialize_reports_installed_version() -> None:
    # Issue #5: initialize answered "0.1.0" for three releases running — a
    # server you can't identify is a server you can't file bugs against.
    # __version__ derives from the installed dist (pyproject), with a
    # "+source" marker when running from a bare source tree.
    import forget
    from forget.mcp import handle_mcp_rpc

    response = handle_mcp_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    version = response["result"]["serverInfo"]["version"]
    assert version == forget.__version__
    assert version != "0.1.0"
