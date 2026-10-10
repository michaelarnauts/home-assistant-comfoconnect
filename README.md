# Home Assistant Zehnder ComfoAirQ / ComfoCoolQ integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This is a custom integration for Home Assistant to integrate with the Zehnder ComfoAirQ ventilation system. It's using the [aiocomfoconnect](https://github.com/michaelarnauts/aiocomfoconnect) library.

This custom integration is an upgrade over the existing `comfoconnect` integration and is meant for testing purposes. The goal is eventually to replace the existing `comfoconnect`
integration in Home Assistant.

## Features

* Control ventilation speed
* Control ventilation mode (auto / manual)
* Control ComfoCool mode (auto / off)
* Configure passive-temperature and humidity ventilation controls
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

Choose **Boost duration**, then press **Start boost**. Changing the duration only saves your preference; it does not start or extend a running boost. The preference defaults to 60 minutes and is restored after restarting Home Assistant.

**Boost active** reports the unit's actual boost status. It is polled, so confirmation can take until the next update. Press **Stop boost** (previously named Cancel boost) to cancel a running boost. No remaining-time countdown is shown because the library only reports whether boost is active.

The original **Boost Mode** select remains available for existing automations, with the same unique ID and behavior: duration options start boost, `Off` cancels it, and `Active` reports status. It is disabled by default for new installations; existing enabled entities are retained. New automations should set Boost duration and press Start boost, and use Boost active to check the device's status.

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
