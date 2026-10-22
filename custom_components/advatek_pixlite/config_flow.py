"""UI setup, reconfiguration and reauthentication."""

import probatio

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    InvalidAuth,
    PixLiteClient,
    PixLiteError,
    UnsupportedDevice,
    normalize_host,
)
from .const import DOMAIN


class PixLiteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._form("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._form("reconfigure", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._form("reauth_confirm", user_input)

    async def _form(self, step, user_input):
        errors = {}
        entry = None
        if step == "reconfigure":
            entry = self._get_reconfigure_entry()
        elif step == "reauth_confirm":
            entry = self._get_reauth_entry()
        defaults = dict(entry.data) if entry else {}
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
                if entry:
                    if entry.unique_id != client.unique_id:
                        return self.async_abort(reason="wrong_device")
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                self._abort_if_unique_id_configured()
                title = (
                    client.version.get("nickname")
                    or client.constants["dev"]["prodName"]
                )
                return self.async_create_entry(title=title, data=data)
            defaults.update(user_input)
        schema = probatio.Schema(
            {
                probatio.Required("host", default=defaults.get("host", "")): str,
                probatio.Required(
                    "username", default=defaults.get("username", "admin")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "admin", "label": "Administrator"},
                            {"value": "oper", "label": "Operator"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                probatio.Optional(
                    "password", default=defaults.get("password", "")
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                probatio.Required(
                    "use_ssl", default=defaults.get("use_ssl", False)
                ): bool,
                probatio.Optional(
                    "port",
                    **({"default": defaults["port"]} if "port" in defaults else {}),
                ): probatio.Port(),
            }
        )
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)
