"""Config flow for the ComfoConnect integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiocomfoconnect
import voluptuous as vol
from aiocomfoconnect import Bridge
from aiocomfoconnect.exceptions import AioComfoConnectError, ComfoConnectNotAllowed
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig, SelectSelectorMode
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.uuid import random_uuid_hex

from .const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN

DEFAULT_PIN = "0000"
COMFOCONNECT_MANUAL_BRIDGE_ID = "manual"
_LOGGER = logging.getLogger(__name__)


class ComfoConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a ComfoConnect config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the ComfoConnect config flow."""
        self.bridge: Bridge | None = None
        self.local_uuid: str | None = None
        self.discovered_bridges: dict[str, Bridge] | None = None

    async def async_step_import(self, import_config: ConfigType | None) -> ConfigFlowResult:
        """Import a config entry from configuration.yaml."""
        self.local_uuid = import_config.get("token")
        # Without a form to return to, an import that can't reach the bridge aborts in the manual step.
        return await self.async_step_manual({CONF_HOST: import_config[CONF_HOST]})

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Register again on a bridge that doesn't know us anymore, with the UUID we already use."""
        self.bridge = Bridge(entry_data[CONF_HOST], entry_data[CONF_UUID])
        self.local_uuid = entry_data[CONF_LOCAL_UUID]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask to register again, and do so when confirmed."""
        errors = {}
        if user_input is not None:
            try:
                return await self._register()
            except AioComfoConnectError:
                errors = {"base": "cannot_connect"}
            except Exception:
                _LOGGER.exception("Unexpected error while registering on the bridge")
                errors = {"base": "unknown"}

        return self.async_show_form(step_id="reauth_confirm", errors=errors, description_placeholders={CONF_HOST: self.bridge.host})

    async def async_step_user(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors = {}
        if user_input is not None:
            # User has chosen to manually enter a bridge
            if user_input[CONF_UUID] == COMFOCONNECT_MANUAL_BRIDGE_ID:
                return await self.async_step_manual()

            # User has selected a discovered bridge
            if user_input[CONF_UUID] is not None:
                self.bridge = self.discovered_bridges[user_input[CONF_UUID]]

                # Don't allow to configure the same bridge twice
                await self.async_set_unique_id(self.bridge.uuid, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                try:
                    return await self._register()
                except AioComfoConnectError:
                    errors = {"base": "cannot_connect"}
                except Exception:
                    _LOGGER.exception("Unexpected error while registering on the bridge")
                    errors = {"base": "unknown"}

        # Find bridges on the networks that Home Assistant is configured to use, and filter out the ones we already have configured
        broadcast_addresses = await network.async_get_ipv4_broadcast_addresses(self.hass)
        bridges = await aiocomfoconnect.discover_bridges(broadcast_addresses=broadcast_addresses)
        self.discovered_bridges = {bridge.uuid: bridge for bridge in bridges if bridge.uuid not in self._async_current_ids(False)}

        # Show the bridge selection form
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UUID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                *(SelectOptionDict(value=bridge.uuid, label=bridge.host) for bridge in self.discovered_bridges.values()),
                                # Translated through the selector's translation key.
                                SelectOptionDict(value=COMFOCONNECT_MANUAL_BRIDGE_ID, label=COMFOCONNECT_MANUAL_BRIDGE_ID),
                            ],
                            mode=SelectSelectorMode.LIST,
                            translation_key="bridge",
                        )
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input: ConfigType | None = None) -> ConfigFlowResult:
        """Handle manual bridge setup."""
        errors = {}
        if user_input is not None and user_input[CONF_HOST] is not None:
            # We need to discover the bridge to get its UUID
            bridges = await aiocomfoconnect.discover_bridges(user_input[CONF_HOST])
            if len(bridges) == 0:
                # Could not discover the bridge
                errors = {"base": "invalid_host"}
            else:
                self.bridge = bridges[0]
                # Don't allow to configure the same bridge twice
                await self.async_set_unique_id(self.bridge.uuid, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                try:
                    return await self._register()
                except AioComfoConnectError:
                    errors = {"base": "cannot_connect"}
                except Exception:
                    _LOGGER.exception("Unexpected error while registering on the bridge")
                    errors = {"base": "unknown"}
                if self.source == config_entries.SOURCE_IMPORT:
                    return self.async_abort(reason=errors["base"])

        return self.async_show_form(
            step_id="manual",
            errors=errors,
            data_schema=self.add_suggested_values_to_schema(vol.Schema({vol.Required(CONF_HOST): str}), user_input),
        )

    async def _register(self, pin: int | None = None) -> ConfigFlowResult:
        """Register on the bridge, raising AioComfoConnectError so the calling step can show its own error."""

        if self.local_uuid is None:
            # Generate our own UUID if non is provided
            self.local_uuid = random_uuid_hex()

        try:
            # LAN C reserves one byte of its 32-byte name buffer for the terminator.
            device_name = f"Home Assistant ({self.hass.config.location_name})"
            device_name = device_name.encode("utf-8")[:31].decode("utf-8", errors="ignore")
            # This connects to the bridge, registers us and starts a session.
            await self.bridge.register(
                self.local_uuid,
                device_name,
                pin or DEFAULT_PIN,
            )

        except ComfoConnectNotAllowed:
            # We are not registered yet and the bridge refused the PIN. Ask the user for a new PIN.
            errors = {"base": "invalid_pin"} if pin is not None else {}
            return await self.async_step_enter_pin({}, errors)

        finally:
            # Disconnect
            await self.bridge.disconnect()

        if self.source == config_entries.SOURCE_REAUTH:
            return self.async_update_reload_and_abort(self._get_reauth_entry())

        return self.async_create_entry(
            title=self.bridge.host,
            data={
                CONF_HOST: self.bridge.host,
                CONF_UUID: self.bridge.uuid,
                CONF_LOCAL_UUID: self.local_uuid,
            },
        )

    async def async_step_enter_pin(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Handle the PIN entry step."""
        if user_input and CONF_PIN in user_input:
            try:
                return await self._register(user_input[CONF_PIN])
            except AioComfoConnectError:
                errors = {"base": "cannot_connect"}
            except Exception:
                _LOGGER.exception("Unexpected error while registering on the bridge")
                errors = {"base": "unknown"}

        return self.async_show_form(
            step_id="enter_pin",
            errors=errors or {},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=0, max=9999, msg="A PIN must be between 0000 and 9999"),
                    )
                }
            ),
        )
