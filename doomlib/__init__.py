"""Shared game library: navigation, combat, items, policy and reporting."""
import sys


def ensure_utf8_stdio():
    """Switch console output to UTF-8 so Russian text works on Windows (cp1252).

    No-op when streams cannot be reconfigured (pipes, StringIO in tests).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            pass
