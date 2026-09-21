import socket

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    import news_data_kit as ndk
    monkeypatch.setenv("NDK_DATA_ROOT", str(tmp_path / "news"))
    monkeypatch.delenv("NDK_PROVIDERS", raising=False)
    monkeypatch.delenv("NDK_FEEDS_CONFIG", raising=False)
    ndk.reset()
    def denied(*args, **kwargs):
        raise RuntimeError("Unit tests cannot access the network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    yield
    ndk.reset()
