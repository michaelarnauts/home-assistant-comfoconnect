"""Config flow for the ComfoConnect integration."""

from __future__ import annotations

import logging
from typing import Any

import aiocomfoconnect
import voluptuous as vol
from aiocomfoconnect import Bridge
from aiocomfoconnect.exceptions import ComfoConnectNotAllowed
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.data_entry_flow import FlowResult
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
        """Initialize the Hue flow."""
        self.bridge: Bridge | None = None
        self.local_uuid: str | None = None
        self.discovered_bridges: dict[str, Bridge] | None = None

    async def async_step_import(self, import_config: ConfigType | None) -> FlowResult:
        """Import a config entry from configuration.yaml."""
        self.local_uuid = import_config.get("token")
        return await self.async_step_manual({CONF_HOST: import_config[CONF_HOST]})

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle a flow reauth."""
        # Discover the bridge so we know which type it is, since a ComfoConnect Pro needs to be
        # registered differently than a LAN C. Fall back to the stored data when it doesn't answer.
        bridges = await aiocomfoconnect.discover_bridges(user_input[CONF_HOST])
        discovered_bridge = next((bridge for bridge in bridges if bridge.uuid == user_input[CONF_UUID]), None)
        self.bridge = discovered_bridge or Bridge(user_input[CONF_HOST], user_input[CONF_UUID])
        self.local_uuid = user_input[CONF_LOCAL_UUID]

        return await self._register()

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initiated by the user."""

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

                return await self._register()

        # Find bridges on the networks that Home Assistant is configured to use, and filter out the ones we already have configured
        broadcast_addresses = await network.async_get_ipv4_broadcast_addresses(self.hass)
        bridges = await aiocomfoconnect.discover_bridges(broadcast_addresses=broadcast_addresses)
        self.discovered_bridges = {bridge.uuid: bridge for bridge in bridges if bridge.uuid not in self._async_current_ids(False)}

        # Show the bridge selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UUID): vol.In(
                        {
                            **{bridge.uuid: bridge.host for bridge in self.discovered_bridges.values()},
                            COMFOCONNECT_MANUAL_BRIDGE_ID: "Manually add a ComfoConnect LAN C Bridge",
                        }
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input: ConfigType | None = None) -> FlowResult:
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

                return await self._register()

        return self.async_show_form(
            step_id="manual",
            errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
        )

    async def _register(self, pin: int = None) -> FlowResult:
        """Register on the bridge."""

        if self.local_uuid is None:
            # Generate our own UUID if non is provided
            self.local_uuid = random_uuid_hex()

        try:
            # This connects to the bridge, checks if we are registered already by starting a session,
            # and registers us when we are not.
            await self.bridge.register(
                self.local_uuid,
                "Home Assistant (%s)" % self.hass.config.location_name,
                pin or DEFAULT_PIN,
            )

        except ComfoConnectNotAllowed:
            # We are not registered yet and the bridge refused the PIN. Ask the user for a new PIN.
            errors = {"base": "invalid_pin"} if pin is not None else {}
            return await self.async_step_enter_pin({}, errors)

        finally:
            # Disconnect
            await self.bridge.disconnect()

        if self.context.get("source") == config_entries.SOURCE_REAUTH:
            self.hass.async_create_task(self.hass.config_entries.async_reload(self.context["entry_id"]))
            return self.async_abort(reason="reauth_successful")

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
    ) -> FlowResult:
        """Handle the PIN entry step."""
        if user_input and CONF_PIN in user_input:
            return await self._register(user_input[CONF_PIN])

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
