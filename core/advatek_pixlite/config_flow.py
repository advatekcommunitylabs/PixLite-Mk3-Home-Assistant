"""Configure a PixLite Mk3 controller for monitoring."""

from typing import Any

from advatek_pixlite_client import (
    InvalidAuth,
    PixLiteClient,
    PixLiteError,
    UnsupportedDevice,
    normalize_host,
)
import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN


class PixLiteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Validate a controller connection and create its config entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect to a controller entered by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            data.setdefault("password", "")
            try:
                data["host"] = normalize_host(data["host"])
                client = PixLiteClient(async_get_clientsession(self.hass), **data)
                await client.initialize()
            except ValueError:
                errors["host"] = "invalid_host"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except UnsupportedDevice:
                errors["base"] = "unsupported_device"
            except PixLiteError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=client.version.get("nickname")
                    or client.constants["dev"]["prodName"],
                    data=data,
                )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=probatio.Schema(
                {
                    probatio.Required("host"): str,
                    probatio.Required("username", default="admin"): SelectSelector(
                        SelectSelectorConfig(
                            options=["admin", "oper"], mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    probatio.Optional("password", default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    probatio.Required("use_ssl", default=False): bool,
                    probatio.Optional("port"): probatio.Port(),
                }
            ),
        )
