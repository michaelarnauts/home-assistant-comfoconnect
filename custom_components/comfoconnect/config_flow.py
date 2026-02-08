"""Config flow for the ComfoConnect integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiocomfoconnect
import voluptuous as vol
from aiocomfoconnect import Bridge
from aiocomfoconnect.exceptions import AioComfoConnectTimeout, ComfoConnectNotAllowed
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.uuid import random_uuid_hex

from .const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN

DEFAULT_PIN = "0000"
COMFOCONNECT_MANUAL_BRIDGE_ID = "manual"
PIN_VALIDATOR = vol.All(
    vol.Coerce(int),
    vol.Range(min=0, max=9999, msg="A PIN must be between 0000 and 9999"),
)
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
        self.bridge = Bridge(user_input[CONF_HOST], user_input[CONF_UUID])
        self.local_uuid = user_input[CONF_LOCAL_UUID]

        return await self._register()

    async def async_step_user(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

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
                    return await self._register(None)
                except AioComfoConnectTimeout:
                    errors["base"] = "cannot_connect"

        # Find bridges on the network and filter out the ones we already have configured
        bridges = await aiocomfoconnect.discover_bridges()
        self.discovered_bridges = {bridge.uuid: bridge for bridge in bridges if bridge.uuid not in self._async_current_ids(False)}

        # Show the bridge selection form
        return self._show_user_form(errors, None)

    async def async_step_manual(self, user_input: ConfigType | None = None) -> FlowResult:
        """Handle manual bridge setup."""
        errors: dict[str, str] = {}
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
                except AioComfoConnectTimeout:
                    errors["base"] = "cannot_connect"

        return self._show_manual_form(errors, user_input.get(CONF_HOST) if user_input else None)

    def _show_user_form(self, errors: dict[str, str], selected_uuid: str | None) -> FlowResult:
        """Show the discovered bridge selection form."""
        if selected_uuid is not None:
            uuid_field = vol.Required(CONF_UUID, default=selected_uuid)
        else:
            uuid_field = vol.Required(CONF_UUID)

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    uuid_field: vol.In(
                        {
                            **{bridge.uuid: bridge.host for bridge in (self.discovered_bridges or {}).values()},
                            COMFOCONNECT_MANUAL_BRIDGE_ID: "Manually add a ComfoConnect LAN C Bridge",
                        }
                    ),
                }
            ),
        )

    def _show_manual_form(self, errors: dict[str, str], host: str | None) -> FlowResult:
        """Show the manual host entry form."""
        if host is not None:
            host_field = vol.Required(CONF_HOST, default=host)
        else:
            host_field = vol.Required(CONF_HOST)

        return self.async_show_form(
            step_id="manual",
            errors=errors,
            data_schema=vol.Schema({host_field: str}),
        )

    async def _register(self, pin: int | None = None) -> FlowResult:
        """Register on the bridge."""

        if self.local_uuid is None:
            self.local_uuid = random_uuid_hex()

        # Use Bridge._connect() for TCP-only connection without session start
        read_task = await self.bridge._connect(self.local_uuid)
        try:
            if pin is not None:
                try:
                    await self.bridge.cmd_register_app(
                        self.local_uuid,
                        f"Home Assistant ({self.hass.config.location_name})",
                        pin,
                    )
                except ComfoConnectNotAllowed:
                    pass

            try:
                await self.bridge.cmd_start_session(True)

            except ComfoConnectNotAllowed:
                if pin is not None:
                    return await self.async_step_enter_pin({}, {"base": "invalid_pin"})

                try:
                    await self.bridge.cmd_register_app(
                        self.local_uuid,
                        f"Home Assistant ({self.hass.config.location_name})",
                        DEFAULT_PIN,
                    )
                except ComfoConnectNotAllowed:
                    return await self.async_step_enter_pin({}, {})

                await self.bridge.cmd_start_session(True)

            except AioComfoConnectTimeout:
                # ComfoConnect Pro doesn't reply to StartSession for
                # unregistered UUIDs so reconnect before attempting registration.
                read_task.cancel()
                try:
                    await read_task
                except (asyncio.CancelledError, Exception):
                    pass
                read_task = await self.bridge._connect(self.local_uuid)

                register_pin = pin if pin is not None else DEFAULT_PIN
                try:
                    await self.bridge.cmd_register_app(
                        self.local_uuid,
                        f"Home Assistant ({self.hass.config.location_name})",
                        register_pin,
                    )
                except ComfoConnectNotAllowed:
                    if pin is not None:
                        return await self.async_step_enter_pin(
                            {}, {"base": "invalid_pin"}
                        )
                    return await self.async_step_enter_pin({}, {})

                await self.bridge.cmd_start_session(True)

        finally:
            read_task.cancel()
            try:
                await read_task
            except (asyncio.CancelledError, Exception):
                pass
            await self.bridge._disconnect()

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
            try:
                pin = PIN_VALIDATOR(user_input[CONF_PIN])
            except vol.Invalid:
                errors = {CONF_PIN: "invalid_pin"}
            else:
                try:
                    return await self._register(pin)
                except AioComfoConnectTimeout:
                    errors = {"base": "cannot_connect"}

        return self.async_show_form(
            step_id="enter_pin",
            errors=errors or {},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN): str
                }
            ),
        )
