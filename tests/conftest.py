"""Permit protocol tests on hosts where HA itself is not installed."""
import importlib.util

collect_ignore = ["ha"] if importlib.util.find_spec("homeassistant") is None else []
