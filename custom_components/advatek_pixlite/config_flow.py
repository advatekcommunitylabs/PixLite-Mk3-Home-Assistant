"""UI setup, discovery confirmation, reconfiguration and reauthentication."""

import probatio
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ._adar import normalize_mac
from .adar_flow import AdarFlow
from .api import (
    InvalidAuth,
    InvalidCertificate,
    InvalidMAC,
    PixLiteClient,
    PixLiteError,
    UnsupportedDevice,
    normalize_host,
)
from .const import DOMAIN


class PixLiteConfigFlow(AdarFlow, config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a manually addressed or discovered controller."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["discover", "manual"])

    async def async_step_manual(self, user_input=None):
        return await self._form("manual", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._form("reconfigure", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._form("reauth_confirm", user_input)

    def _client(self, data):
        return PixLiteClient(async_get_clientsession(self.hass), **data)

    async def _identify(self, data):
        """Read and normalize the MAC through an authenticated API connection."""
        client = self._client(data)
        try:
            await client.initialize()
            identity = normalize_mac(client.unique_id)
        except InvalidMAC:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            raise PixLiteError("Invalid controller identity response") from err
        return client, identity

    async def _form(self, step, user_input):
        errors = {}
        entry = None
        if step == "reconfigure":
            entry = self._get_reconfigure_entry()
        elif step == "reauth_confirm":
            entry = self._get_reauth_entry()
        defaults = dict(entry.data) if entry else {}
        if step == "discovery_confirm":
            if self._selected is None:
                return self.async_abort(reason="invalid_discovery")
            defaults["host"] = self._selected.host
        if user_input is not None:
            data = dict(user_input)
            if step == "discovery_confirm":
                data["host"] = self._selected.host
            data.setdefault("password", "")
            data["port"] = data.get("port") or None
            try:
                data["host"] = normalize_host(data["host"])
                client, identity = await self._identify(data)
            except InvalidMAC:
                errors["expected_mac"] = "invalid_mac"
            except ValueError:
                errors["host"] = "invalid_host"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidCertificate as err:
                errors["base"] = err.reason
            except UnsupportedDevice:
                errors["base"] = "unsupported_device"
            except PixLiteError:
                errors["base"] = "cannot_connect"
            else:
                expected = (
                    entry.unique_id
                    if entry
                    else self._selected.mac
                    if step == "discovery_confirm"
                    else identity
                )
                if identity != expected:
                    errors["base"] = "identity_mismatch"
                else:
                    await self.async_set_unique_id(identity, raise_on_progress=False)
                    if entry:
                        return self.async_update_reload_and_abort(
                            entry, data_updates=data
                        )
                    self._abort_if_unique_id_configured()
                    title = (
                        client.version.get("nickname")
                        or client.constants["dev"]["prodName"]
                    )
                    return self.async_create_entry(title=title, data=data)
            defaults.update(user_input)
        fields = {}
        if step != "discovery_confirm":
            fields[probatio.Required("host", default=defaults.get("host", ""))] = str
        fields.update(
            {
                probatio.Required(
                    "username", default=defaults.get("username", "oper")
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
                    "expected_mac", default=defaults.get("expected_mac", "")
                ): str,
                probatio.Optional("port", default=defaults.get("port") or 0): probatio.All(
                    probatio.Coerce(int), probatio.Range(min=0, max=65535)
                ),
            }
        )
        return self.async_show_form(
            step_id=step,
            data_schema=probatio.Schema(fields),
            errors=errors,
            description_placeholders={"host": defaults.get("host", "")},
        )
