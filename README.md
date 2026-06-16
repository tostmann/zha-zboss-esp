# ESP32-C6 ZBOSS adapter for Home Assistant ZHA

HACS-installable custom component that lets the Home Assistant **ZHA**
integration use the **ZBOSS NCP Serial Protocol** as exposed by
[`tostmann/esp-coordinator`](https://github.com/tostmann/esp-coordinator)
on ESP32-C6 hardware.

> **Status**: 0.3.x — early. Works against `esp-coordinator` v1.1.22+ and
> `zigpy-zboss` 2.0.1 on Home Assistant Core 2026.x. Bug reports welcome.
>
> **0.3.1 changelog**: capped `zigpy-zboss` to `<2.0.2`. zigpy-zboss 2.0.2
> changed how the network key is read at startup — it now issues the
> `GetNwkKeys` NCP command instead of a raw NVRAM dataset read — and the
> `esp-coordinator` firmware does not implement that command yet, so on 2.0.2
> the adapter cannot resume an already-formed network (startup aborts with
> `ControllerException: … GetNwkKeys returned no usable network key`). The cap
> will be lifted once a firmware release adds `GET_NWK_KEYS` support.
>
> **0.3.0 changelog**: re-pinned to `zigpy-zboss>=2.0.1`. The three runtime
> compatibility shims this component used to carry are **removed** — all three
> were fixed upstream in zigpy-zboss 2.0.0 / 2.0.1, and one of them (the
> post-formation `node_info.nwk` override) would now conflict with the upstream
> fix. The component now does exactly one thing: register the `zboss` RadioType
> with ZHA.
>
> **0.2.0 changelog**: the integration gained a config entry (config flow).
> Previous 0.1.x releases were `config_flow: false` with no load trigger, so
> Home Assistant never ran the integration's setup and ZBOSS never appeared
> in ZHA's radio picker (issue #1). After updating, **add the integration
> once** (step 5 below) — that activates it on every restart.

## What it does

ZHA in stock HA does not list ZBOSS as a radio type. The Python library
[`zigpy-zboss`](https://github.com/kardia-as/zigpy-zboss) speaks the right wire
protocol and — as of the 2.0.x line (2026) — is modern and actively maintained
again. What stock HA is still missing is simply the wiring that exposes it to
ZHA's radio picker.

This component:

1. **Declares `zigpy-zboss>=2.0.1,<2.0.2` as a Python requirement** so HACS pulls
   it into the HA Python environment automatically.
2. **Extends ZHA's `RadioType` enum** with a `zboss` member so the UI radio
   picker in the ZHA add-integration flow offers ZBOSS as a choice. The patch
   is idempotent — a no-op if `zboss` is already present.

Earlier releases (≤ 0.2.x) also carried three runtime shims that patched
`zigpy-zboss` 1.2.0 back into working order against current zigpy. Those are
gone as of 0.3.0: all three were fixed upstream in zigpy-zboss 2.0.0 / 2.0.1.

The component itself has no entities and no settings. It loads through a
single-instance config entry whose only purpose is to run the RadioType
registration on every Home Assistant start — early enough that ZBOSS is
registered before ZHA's own add-integration flow reads the radio-type list.

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
`custom_components/` folder, then `pip install "zigpy-zboss>=2.0.1,<2.0.2"` into
your HA Python environment, and restart.

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

The library-side bugs that used to need patching here have already landed
upstream — see [`kardia-as/zigpy-zboss#19`](https://github.com/kardia-as/zigpy-zboss/issues/19)
and the 2.0.x release line. What remains is the ZHA wiring: a `RadioType.zboss`
member upstream in `home-assistant/core` ZHA is a longer conversation (the
`adapter:zboss` is labeled "experimental"). When/if that lands, this component
becomes obsolete.

## Pointers

- Firmware: [`tostmann/esp-coordinator`](https://github.com/tostmann/esp-coordinator), web flasher at https://install.busware.de/zboss/
- Alternative Zigbee host stack: [`tostmann/zigbee2mqtt`](https://github.com/tostmann/zigbee2mqtt) (`ghcr.io/tostmann/zigbee2mqtt-esp32:latest`) — Z2M instead of ZHA
- Upstream library: [`kardia-as/zigpy-zboss`](https://github.com/kardia-as/zigpy-zboss)

## License

MIT — see [LICENSE](LICENSE).
