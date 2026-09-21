"""Technical indicators for market data."""


def __getattr__(name: str):
    if name in ("compute_all", "PRESETS"):
        from market_data_kit.indicators.composite import compute_all, PRESETS
        globals()["compute_all"] = compute_all
        globals()["PRESETS"] = PRESETS
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["compute_all", "PRESETS"]
