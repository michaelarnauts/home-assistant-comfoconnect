# Home Assistant Zehnder ComfoAirQ / ComfoCoolQ integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This is a custom integration for Home Assistant to integrate with the Zehnder ComfoAirQ ventilation system. It's using the [aiocomfoconnect](https://github.com/michaelarnauts/aiocomfoconnect) library.

This custom integration is an upgrade over the existing `comfoconnect` integration and is meant for testing purposes. The goal is eventually to replace the existing `comfoconnect`
integration in Home Assistant.

## Features

* Control ventilation speed
* Control ventilation mode (auto / manual)
* Control ComfoCool mode (auto / off)
* Show yearly energy totals and avoided heating/cooling measurements
* Show an Active alarms diagnostic binary sensor
* Show outside humidity after the preheater as an optional diagnostic sensor
* Configure passive-temperature and humidity ventilation controls
* Configure heating and cooling RMOT thresholds
* Configure the warm, normal and cool profile temperatures
* Control timed away mode
* Show various sensors

This integration supports the following additional features over the existing integration:

* Configurable through the UI
* Support for multiple bridges
* Allows to modify the balance mode, bypass mode, temperature profile and ventilation mode
* Changes to fan speed won't be reverted after 2 hours
* Support to clear alarms
* Ignores invalid sensor values at the beginning of a session (Workaround for bridge firmware bug)
* Throttles high frequency sensor updates (airflow & fan duty) to once every 10 seconds

**Note: Not all sensors are enabled by default. You can enable them on the integration page.**

### Boost mode

Choose a duration in Boost Mode to start a timer. Choose `Off`, or use Cancel boost, to stop it. `Active` reports a running timer; selecting it does not start or extend a timer.

For another duration, use the `comfoconnect.start_boost` action on the fan entity. The unit counts down to the second.

```yaml
action: comfoconnect.start_boost
target:
  entity_id: fan.comfoairq
data:
  duration: "02:30:00"
```

### Away mode

Choose a duration in Away Mode to start a timer. Choose `Off`, or use Cancel away, to stop it. `Active` reports a running timer; selecting it does not start or extend a timer.

Away Mode offers durations in minutes, 2/8/24 hours, and 7/14 days. Cancel the timer when you return early.

### Bypass timer

Choose a duration in Bypass timer to force bypass on for 10–60 minutes. Choose `Off` to restore automatic control. `Active` means bypass is forced on, including through Bypass Mode; selecting it only refreshes status.

### Alarm events

The `comfoconnect_alarm` event reports changed alarms and clears per node. Its payload contains `device_id` (the ventilation unit), `bridge_uuid`, `node_id`, and an `errors` list with `id` and `message` fields. A clear has an empty list. Repeated identical reports and startup reports without alarms do not fire an event. Alarms received before device registration have a null `device_id`.

### RMOT thresholds

Enable the Heating RMOT threshold and Cooling RMOT threshold number entities to configure the running mean outdoor temperature limits used for heating and cooling. The entities use the minimum, maximum, and step reported by the unit and are disabled by default.

### Profile temperatures

Enable the Warm, Normal and Cool profile temperature number entities to configure the comfort temperature of each temperature profile. The unit only uses them in the fixed temperature profile mode; in adaptive mode it derives the comfort temperature from the RMOT, but it still stores the values. The Target temperature sensor shows the comfort temperature the unit is currently using. Like the RMOT thresholds, they are disabled by default.

## Installation

### HACS

The easiest way to install this integration is through [HACS](https://hacs.xyz/).

1. Add this repository (`https://github.com/michaelarnauts/home-assistant-comfoconnect`) as a custom repository in HACS.
   See [here](https://hacs.xyz/docs/faq/custom_repositories) for more information.
2. Install the `Zehnder ComfoAirQ` integration.
3. Restart Home Assistant.

If you have the existing `comfoconnect` integration installed, the configuration should be picked up, but you might need to change your existing sensors ids.
You should also remove the old configuration from the `configuration.yaml` file.

If not, you can add the integration through the UI by going to the integrations page and adding the `Zehnder ComfoAirQ` integration.
