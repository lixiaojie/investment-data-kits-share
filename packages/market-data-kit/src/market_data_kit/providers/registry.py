"""Only public providers; optional services must be explicitly enabled."""
from __future__ import annotations

from importlib import import_module, util

FACTORIES = {
    "yfinance": ("yfinance_provider", "YfinanceProvider", "yfinance"),
    "akshare": ("akshare_provider", "AkshareProvider", "akshare"),
    "push2": ("push2", "Push2Provider", None),
    "futu": ("futu_provider", "FutuProvider", "futu"),
    "tushare": ("tushare_provider", "TushareProvider", "tushare"),
    "fred": ("fred_provider", "FredProvider", None),
    "china_macro": ("china_macro_provider", "ChinaMacroProvider", "akshare"),
    "commodity": ("commodity_provider", "CommodityProvider", "yfinance"),
    "stub": ("stub", "StubProvider", None),
}
_instances = {}


def get_provider(name):
    if name not in _instances:
        module, cls, _ = FACTORIES[name]
        _instances[name] = getattr(import_module(f".{module}", __package__), cls)()
    return _instances[name]


def reset_registry():
    for instance in _instances.values():
        close = getattr(instance, "close", None)
        if close:
            close()
    _instances.clear()


def status():
    from ..config import get_config
    enabled = get_config().providers
    return [{"name": name, "enabled": name in enabled,
             "dependency_installed": dep is None or util.find_spec(dep) is not None,
             "network_verified": False}
            for name, (_, _, dep) in FACTORIES.items() if name != "stub"]
