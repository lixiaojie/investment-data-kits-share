"""Compatibility context manager that preserves the caller's network settings."""
from contextlib import contextmanager

@contextmanager
def clear_proxy():
    """Use the process's configured proxy settings unchanged."""
    yield
