"""Native notification policy for decoded ComfoConnect alarms."""

from __future__ import annotations

from enum import StrEnum

from aiocomfoconnect.const import ERRORS, ERRORS_140
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

CONF_ALARM_NOTIFICATIONS = "alarm_notifications"
DATA_NOTIFICATIONS = "comfoconnect_notifications"
ALARM_RECHECK_ERROR_ID = 100

# The callback supplies decoded text, not firmware. Match both the code and the
# library's definition: e.g. 79 is a filter reminder now, but an old postheater fault.
FILTER_REMINDERS = frozenset([(code, ERRORS[code]) for code in (77, 78, 79)] + [(code, ERRORS_140[code]) for code in (73, 74, 75)])


class AlarmNotificationMode(StrEnum):
    """Which alarms create native Home Assistant notifications."""

    OFF = "off"
    FAULTS = "faults"
    ALL = "faults_and_maintenance"


class AlarmNotifications:
    """Keep one combined notification, including dismissal state across reloads."""

    def __init__(self, hass: HomeAssistant, uuid: str, mode: str = AlarmNotificationMode.OFF) -> None:
        """Initialize the delivery policy for one ventilation unit."""
        self.hass = hass
        self.notification_id = f"comfoconnect_alarm_{uuid}"
        self.mode = mode
        self._alarms: dict[int, dict[int, str]] = {}
        self._last_delivered: dict[int, dict[int, str]] | None = None
        self._remove_options_listener: CALLBACK_TYPE | None = None
        self._closed = False

    @callback
    def listen_to_options(self, entry: ConfigEntry) -> None:
        """Listen for the entry's lifetime, including setup retries and unloads."""
        self._remove_options_listener = entry.add_update_listener(self._async_update_options)

    async def _async_update_options(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Apply persisted choices even while the bridge is not loaded."""
        self.set_mode(entry.options.get(CONF_ALARM_NOTIFICATIONS, AlarmNotificationMode.OFF))

    @callback
    def close(self) -> None:
        """Release the entry listener and dismiss the notice when removed."""
        self._closed = True
        if self._remove_options_listener is not None:
            self._remove_options_listener()
            self._remove_options_listener = None
        self.dismiss()

    @callback
    def set_mode(self, mode: str) -> None:
        """Apply an option to the current alarms without reconnecting the bridge."""
        if self._closed:
            return
        if self.mode == mode:
            if mode == AlarmNotificationMode.OFF:
                self.dismiss()
            return
        self.mode = mode
        self._publish()

    @callback
    def update(self, node_id: int, errors: dict[int, str]) -> None:
        """Accept confirmed node reports; a recheck cannot confirm removals."""
        if self._closed:
            return
        confirmed = {code: message for code, message in errors.items() if code != ALARM_RECHECK_ERROR_ID}
        if ALARM_RECHECK_ERROR_ID in errors:
            if not confirmed:
                return
            self._alarms.setdefault(node_id, {}).update(confirmed)
        else:
            self._alarms[node_id] = confirmed
        self._publish()

    @callback
    def dismiss(self) -> None:
        """Dismiss the unit's native notification."""
        persistent_notification.async_dismiss(self.hass, self.notification_id)

    @callback
    def _publish(self) -> None:
        """Only deliver changes to the selected alarms, respecting dismissal."""
        selected = {}
        if self.mode != AlarmNotificationMode.OFF:
            for node_id, errors in self._alarms.items():
                eligible = {
                    code: message
                    for code, message in errors.items()
                    if self.mode == AlarmNotificationMode.ALL or (code, message) not in FILTER_REMINDERS
                }
                if eligible:
                    selected[node_id] = eligible
        if selected == self._last_delivered:
            return
        self._last_delivered = selected
        if not selected:
            self.dismiss()
            return

        faults = any((code, message) not in FILTER_REMINDERS for errors in selected.values() for code, message in errors.items())
        title = "ComfoConnect needs attention" if faults else "ComfoConnect filter maintenance"
        lines = ["The ventilation unit reported active alarms." if faults else "The ventilation unit reported filter maintenance reminders."]
        for maintenance, heading in ((False, "Faults and other alarms"), (True, "Filter maintenance")):
            entries = [
                f"- Node {node_id}, **{code}**: {message}"
                for node_id, errors in sorted(selected.items())
                for code, message in sorted(errors.items())
                if ((code, message) in FILTER_REMINDERS) == maintenance
            ]
            if entries:
                lines.extend(["", f"### {heading}", "", *entries])
        persistent_notification.async_create(self.hass, "\n".join(lines), title=title, notification_id=self.notification_id)
