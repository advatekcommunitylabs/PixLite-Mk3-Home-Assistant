"""Enable local custom integrations for Home Assistant runtime tests."""

import pytest


@pytest.fixture(autouse=True)
def enable_local_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load this repository's integration."""
