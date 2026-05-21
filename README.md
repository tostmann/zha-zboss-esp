# ESP32-C6 ZBOSS adapter for Home Assistant ZHA

HACS-installable custom component that lets the Home Assistant **ZHA**
integration use the **ZBOSS NCP Serial Protocol** as exposed by
[`tostmann/esp-coordinator`](https://github.com/tostmann/esp-coordinator)
on ESP32-C6 hardware.

> **Status**: 0.1.x — early. Works against `esp-coordinator` v1.1.22 and
> `zigpy-zboss` 1.2.0 on Home Assistant Core 2026.x. Bug reports welcome.

## What it does

ZHA in stock HA does not list ZBOSS as a radio type. The Python library
[`zigpy-zboss`](https://github.com/kardia-as/zigpy-zboss) exists and speaks
the right wire protocol — but it has been in maintenance mode since 2024 and
has bit-rotted against current zigpy/serialx, so a plain
`pip install zigpy-zboss` doesn't work in current HA.

This component:

1. **Declares `zigpy-zboss>=1.2.0` as a Python requirement** so HACS pulls it
   into the HA Python environment automatically.
2. **Applies three runtime patches** to `zigpy-zboss` to make it functional
   against current zigpy. All idempotent — no-ops if upstream releases a fix.
3. **Extends ZHA's `RadioType` enum** with a `zboss` member so the UI radio
   picker in the ZHA add-integration flow offers ZBOSS as a choice.

The component itself has no entity / no config flow — once installed and HA
is restarted, ZHA's own add-integration flow does the rest.

## Installation (HACS)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. In HACS → Integrations → ⋮ → Custom repositories, add
   `https://github.com/tostmann/zha-zboss-esp` with type "Integration".
3. Install "ESP32-C6 ZBOSS adapter for ZHA".
4. Restart Home Assistant.
5. After restart, go to **Settings → Devices & Services → Add Integration →
   Zigbee Home Automation**. Choose **Manually pick a serial port**, paste
   the `by-id` path of your coordinator (something like
   `/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_…`), and pick
   **ZBOSS** when prompted for radio type.

## Installation (manual)

If you can't use HACS, copy
`custom_components/esp_zboss_zha/` into your HA config directory's
`custom_components/` folder, then `pip install zigpy-zboss>=1.2.0` into your
HA Python environment, and restart.

## What if "ZBOSS" doesn't appear in the radio picker?

`RadioType` is a Python `enum.Enum` and we patch it at our `async_setup`
time. If ZHA's config-flow module had already imported `RadioType` into its
local namespace before our patch ran (Python import-cache), the dropdown
will still show only the original radio types until HA is restarted a second
time with this component already installed. This is a known quirk of
runtime-extending enums and is one of the items we hope to resolve upstream
(see [kardia-as/zigpy-zboss#19](https://github.com/kardia-as/zigpy-zboss/issues/19)).

## Why a custom component instead of an upstream PR?

We're tracking this in parallel — see the open
[discussion on `kardia-as/zigpy-zboss#19`](https://github.com/kardia-as/zigpy-zboss/issues/19)
for the upstream library-side path. Once the three library bugs land and ship
in a PyPI release, the patches in this component become no-ops.
A `RadioType.zboss` member upstream in `home-assistant/core` ZHA is a longer
conversation (the `adapter:zboss` is labeled "experimental"); when/if that
lands, this component becomes obsolete.

## Pointers

- Firmware: [`tostmann/esp-coordinator`](https://github.com/tostmann/esp-coordinator), web flasher at https://install.busware.de/zboss/
- Alternative Zigbee host stack: [`tostmann/zigbee2mqtt`](https://github.com/tostmann/zigbee2mqtt) (`ghcr.io/tostmann/zigbee2mqtt-esp32:latest`) — Z2M instead of ZHA
- Upstream library: [`kardia-as/zigpy-zboss`](https://github.com/kardia-as/zigpy-zboss)

## License

MIT — see [LICENSE](LICENSE).
