# ESP32-C6 ZBOSS adapter for Home Assistant ZHA

HACS-installable custom component that lets the Home Assistant **ZHA**
integration use the **ZBOSS NCP Serial Protocol** as exposed by
[`tostmann/esp-coordinator`](https://github.com/tostmann/esp-coordinator)
on ESP32-C6 hardware.

> **Status**: 0.2.x — early. Works against `esp-coordinator` v1.1.22+ and
> `zigpy-zboss` 1.2.0 on Home Assistant Core 2026.x. Bug reports welcome.
>
> **0.2.0 changelog**: the integration now has a config entry (config flow).
> Previous 0.1.x releases were `config_flow: false` with no load trigger, so
> Home Assistant never ran the integration's setup and ZBOSS never appeared
> in ZHA's radio picker (issue #1). After updating, **add the integration
> once** (step 5 below) — that activates the patches on every restart.

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

The component itself has no entities and no settings. It loads through a
single-instance config entry whose only purpose is to run the patches on
every Home Assistant start — early enough that ZBOSS is registered before
ZHA's own add-integration flow reads the radio-type list.

## Installation (HACS)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. In HACS → Integrations → ⋮ → Custom repositories, add
   `https://github.com/tostmann/zha-zboss-esp` with type "Integration".
3. Install "ESP32-C6 ZBOSS adapter for ZHA".
4. Restart Home Assistant.
5. **Add this integration once** so it loads: **Settings → Devices &
   Services → Add Integration → "ESP32-C6 ZBOSS adapter for ZHA"** → Submit.
   (There is nothing to configure; this step is what activates the patches.
   It only needs to be done once — the entry then loads on every restart.)
6. Now add the coordinator: **Add Integration → Zigbee Home Automation**.
   Choose **Manually pick a serial port**, paste the `by-id` path of your
   coordinator (something like
   `/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_…`), and pick
   **ZBOSS** when prompted for radio type.

## Installation (manual)

If you can't use HACS, copy
`custom_components/esp_zboss_zha/` into your HA config directory's
`custom_components/` folder, then `pip install zigpy-zboss>=1.2.0` into your
HA Python environment, and restart.

## What if "ZBOSS" doesn't appear in the radio picker?

First, make sure you actually completed **step 5** — adding the "ESP32-C6
ZBOSS adapter for ZHA" integration. Just installing it in HACS is *not*
enough; without the config entry the integration never loads and the radio
type is never registered. This was the cause of issue #1.

To confirm the integration loaded, check **Settings → System → Logs** (or
`home-assistant.log`) for a line like:

```
[esp_zboss_zha] applied N compat patch(es): ...
[esp_zboss_zha] post-patch RadioType members: [...] (zboss present: True)
```

If you don't see those lines, the integration didn't run — re-check step 5.

If the lines are present (`zboss present: True`) but the dropdown still
omits ZBOSS, restart Home Assistant once: ZHA may have imported its radio
list before our entry was set up. With the config entry in place this is
deterministic after one restart, because the entry is set up early on every
boot. Remaining edge cases are tracked upstream
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
