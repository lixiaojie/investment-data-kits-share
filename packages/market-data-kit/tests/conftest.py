import socket

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    import market_data_kit as kit
    monkeypatch.setenv("MDK_DATA_ROOT", str(tmp_path / "market"))
    monkeypatch.delenv("MDK_USE_STUBS", raising=False)
    monkeypatch.delenv("MDK_PROVIDERS", raising=False)
    kit.reset()
    def denied(*args, **kwargs):
        raise RuntimeError("Unit tests cannot access the network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    yield
    kit.reset()
