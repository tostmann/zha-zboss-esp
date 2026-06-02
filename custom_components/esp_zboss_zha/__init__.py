"""ESP32-C6 ZBOSS adapter for ZHA — runtime patches.

This custom-component is a thin glue layer that:

1. Bundles `zigpy-zboss>=1.2.0` as a pip requirement (via manifest.json), so
   HACS pulls it into the HA Python environment.

2. Applies three runtime patches against `zigpy-zboss` v1.2.0 to bring it back
   to a working state against current zigpy / serialx:
     - `.name`-attribute access in `zigpy_zboss.uart.ZbossNcpProtocol`
       (replaces missing `serialx.LinuxSerial.name` with `port` fallback).
     - `ControllerApplication.start_network` propagating `NWKAddr` from
       `NWK.Formation.Rsp` into `state.node_info.nwk` (otherwise post-formation
       `int(state.node_info.nwk)` raises `TypeError`).
     - `voluptuous` schema lenience for `ota.providers` defaults.

3. Extends `zha.application.const.RadioType` with a `zboss` member so the ZHA
   "select radio type" config-flow step offers ZBOSS. The extended member
   maps to `zigpy_zboss.zigbee.application.ControllerApplication`.

All four patches are no-ops if the upstream bug is already fixed (idempotent
guards). Once `kardia-as/zigpy-zboss#19` and follow-up PRs land + ship in
HACS-PyPI, those patch blocks can be removed cleanly.

Tested against:
- ESP32-C6 + esp-coordinator v1.1.22 (tostmann fork)
- zigpy-zboss 1.2.0
- HA Core 2026.x

Source: https://github.com/tostmann/zha-zboss-esp
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imports only needed for type hints
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, RADIO_DESCRIPTION

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """YAML path — legacy / optional.

    Kept for back-compat with anyone who added `esp_zboss_zha:` to
    `configuration.yaml` under v0.1.x. As of v0.2.0 the supported way to load
    this integration is the config entry (`async_setup_entry`), created via
    **Settings → Devices & Services → Add Integration**. Both paths call the
    same idempotent patch routine, so having both active is harmless.
    """
    await _async_apply(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config-entry path — the supported one as of v0.2.0.

    Runs on every Home Assistant start, early enough that the `RadioType`
    extension is in place before ZHA's add-integration flow reads it. This is
    what fixes issue #1: with no config entry (and no `configuration.yaml`
    key) Home Assistant never called `async_setup`, so the patches never ran
    and ZBOSS never showed up in ZHA's radio picker.
    """
    await _async_apply(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Allow removing the entry.

    The patches are process-global enum/attribute mutations that can't be
    cleanly reverted at runtime, so unload is a no-op that simply succeeds; a
    Home Assistant restart fully clears them.
    """
    return True


async def _async_apply(hass: HomeAssistant) -> None:
    """Apply the compat patches and log the resulting RadioType members.

    The patch functions do synchronous file I/O when first importing
    `zigpy_zboss`, `zigpy`, `zha` (module load, schema scan, voluptuous
    compilation, etc.). HA's loop watchdog warns about blocking-on-event-loop
    if we do that on the event loop directly, so run the work in an executor
    thread.
    """
    applied = await hass.async_add_executor_job(_apply_all_patches)

    if applied:
        _LOGGER.info(
            "[%s] applied %d compat patch(es): %s",
            DOMAIN, len(applied), ", ".join(applied),
        )
    else:
        _LOGGER.info("[%s] no patches needed (upstream already fixed)", DOMAIN)

    # Post-patch verification — log RadioType members so the patch effect is
    # visible. Also runs in the executor to avoid loop blocking (importlib
    # on first import does file I/O).
    members = await hass.async_add_executor_job(_get_radio_type_members)
    if members is not None:
        _LOGGER.info(
            "[%s] post-patch RadioType members: %s (zboss present: %s)",
            DOMAIN, members, "zboss" in members,
        )


def _apply_all_patches() -> list[str]:
    """Apply all patches synchronously — call from an executor thread."""
    applied: list[str] = []
    if _patch_uart_name():
        applied.append("zigpy_zboss.uart.name")
    if _patch_application_node_info_nwk():
        applied.append("ControllerApplication.start_network nwk-propagation")
    if _patch_zigpy_ota_schema():
        applied.append("zigpy schema ota.providers lenience")
    if _patch_radio_type_zboss():
        applied.append("zha RadioType.zboss")
    return applied


def _get_radio_type_members() -> list[str] | None:
    """Return RadioType member names — call from an executor thread."""
    try:
        from zha.application.const import RadioType
        return list(RadioType._member_map_.keys())
    except ImportError:
        _LOGGER.warning("[%s] zha.application.const not importable", DOMAIN)
        return None


# ---------------------------------------------------------------------------
# Patch implementations — each returns True if it actually patched something,
# False if upstream already had the fix (idempotent).
# ---------------------------------------------------------------------------


def _patch_uart_name() -> bool:
    """Fix `ZbossNcpProtocol.name` access against `serialx.LinuxSerial`.

    Original: `return self._transport.serial.name`. `LinuxSerial` exposes
    `.port`, not `.name`, so this raises `AttributeError`. The exception
    propagates back from `ZBOSS.connect`, gets swallowed, and the next
    `request()` raises `"Coordinator is disconnected"`.
    """
    try:
        from zigpy_zboss import uart as _uart
    except ImportError:
        _LOGGER.debug("zigpy_zboss.uart not importable; skipping name patch")
        return False

    if getattr(_uart, "_esp_zboss_zha_name_patched", False):
        return False

    def _safe_name(self):
        ser = self._transport.serial
        return getattr(ser, "name",
                       getattr(ser, "port", "<unnamed>"))

    _uart.ZbossNcpProtocol.name = property(_safe_name)
    _uart._esp_zboss_zha_name_patched = True
    return True


def _patch_application_node_info_nwk() -> bool:
    """Propagate `NWK.Formation.Rsp.NWKAddr` into `state.node_info.nwk`.

    Without this, `ControllerApplication.start_network` reaches
    `self.devices[self.state.node_info.ieee] = ZbossCoordinator(self, ieee,
    self.state.node_info.nwk)` where `nwk` is None — `int(None)` raises.
    """
    try:
        from zigpy_zboss.zigbee import application as _zba
    except ImportError:
        _LOGGER.debug("zigpy_zboss.zigbee.application not importable; skipping")
        return False

    if getattr(_zba, "_esp_zboss_zha_nwk_patched", False):
        return False

    orig_form_network = getattr(_zba.ControllerApplication, "_form_network", None)
    if orig_form_network is None:
        _LOGGER.debug("no _form_network on ControllerApplication; skipping")
        return False

    async def patched_form_network(self, network_info, node_info):
        result = await orig_form_network(self, network_info, node_info)
        # After formation, refresh node_info.nwk from the live network state
        # in case the original path left it as None.
        if self.state.node_info.nwk is None:
            try:
                import zigpy_zboss.commands as c
                resp = await self._api.request(
                    c.NcpConfig.GetShortPANID.Req(TSN=self.get_sequence()),
                )
                # PANID returned is the coordinator's own short address (= 0x0000
                # for a coordinator in its own network), not the PAN ID. Use
                # zigpy.types.NWK literal 0x0000 since that's correct for a ZC.
                import zigpy.types as zt
                self.state.node_info.nwk = zt.NWK(0x0000)
                _LOGGER.debug(
                    "[esp_zboss_zha] patched node_info.nwk = 0x0000 "
                    "(coordinator, PAN ID was 0x%04x)", resp.PANID,
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "[esp_zboss_zha] could not patch node_info.nwk: %s", exc,
                )
        return result

    _zba.ControllerApplication._form_network = patched_form_network
    _zba._esp_zboss_zha_nwk_patched = True
    return True


def _patch_zigpy_ota_schema() -> bool:
    """Make zigpy's `cv_ota_provider` validator tolerate already-built
    provider objects.

    Current zigpy 1.4.x's `ota.providers` schema default contains
    `ZigpyOtaProvider`-like instances; the validator then calls `obj.get(...)`
    and raises `AttributeError`. We rebind `zigpy.config.validators.cv_ota_provider`
    to a lenient wrapper.

    **Limitation**: voluptuous compiles validators at `Schema(...)` construction
    time, so any schema that was already built before our rebind keeps the OLD
    function reference. That includes `ControllerApplication.SCHEMA` which is a
    class attribute compiled at module load. So this rebind catches only
    schemas constructed AFTER our setup runs — for ZHA's existing probe path
    the workaround is incomplete. Real fix needs to land in `kardia-as/zigpy-zboss`
    so newer release ships with a correct `ota.providers` default.

    Tracked in https://github.com/kardia-as/zigpy-zboss/issues/19 as part of
    the broader schema bit-rot discussion.
    """
    try:
        import zigpy.config.validators as _zv
    except ImportError:
        return False
    if getattr(_zv, "_esp_zboss_zha_ota_patched", False):
        return False

    orig = getattr(_zv, "cv_ota_provider", None)
    if orig is None:
        return False

    def lenient_cv_ota_provider(obj):
        # zigpy defaults inject provider INSTANCES rather than dicts; the
        # original validator assumes dict and crashes on `.get()`. Pass
        # instances through unchanged.
        if not isinstance(obj, dict):
            return obj
        return orig(obj)

    _zv.cv_ota_provider = lenient_cv_ota_provider
    _zv._esp_zboss_zha_ota_patched = True
    return True


def _patch_radio_type_zboss() -> bool:
    """Add `zboss` member to `zha.application.const.RadioType`.

    `RadioType` is an `enum.Enum` which Python intentionally locks against
    runtime extension. We inject via the internal `_member_map_` /
    `_value2member_map_` / `_member_names_` triplet — this is gross but is
    the only way without taking a dependency on `aenum`.

    NOTE: any caller that has already imported RadioType into a local
    namespace before this patch runs will still see the un-extended version.
    HA loads custom_components after core integrations, so config_flow code
    paths that import RadioType at module-load time may be cached. In that
    case the UI dropdown won't show ZBOSS until HA is restarted with this
    custom_component already installed (i.e. the second restart after
    install).
    """
    try:
        from zha.application.const import RadioType as _RadioType
        from zigpy_zboss.zigbee.application import (
            ControllerApplication as _ZbossCtrl,
        )
    except ImportError as exc:
        _LOGGER.debug("could not import zha/zigpy_zboss for RadioType: %s", exc)
        return False

    if "zboss" in _RadioType._member_map_:
        return False  # already extended

    # Build the new member as if it had been declared in the enum source:
    #     zboss = ("...description...", zigpy_zboss...ControllerApplication)
    value = (RADIO_DESCRIPTION, _ZbossCtrl)

    new_member = object.__new__(_RadioType)
    new_member._name_ = "zboss"
    new_member._value_ = value
    # __init__ runs the (description, controller_cls) constructor body
    # that populates `_desc` and `_ctrl_cls`.
    _RadioType.__init__(new_member, *value)

    _RadioType._member_map_["zboss"] = new_member
    # value2member_map maps full value tuple → member. Some enum operations
    # rely on this; missing it would still parse names but break by-value
    # lookups (RadioType(value)).
    try:
        _RadioType._value2member_map_[value] = new_member
    except TypeError:
        # tuple unhashable (e.g. if value contains an unhashable type).
        # In our case the description is a str + a class — both hashable.
        # Defensive: skip silently if some future zigpy_zboss changes shape.
        _LOGGER.debug("RadioType value not hashable; skipping value2member")
    _RadioType._member_names_.append("zboss")

    return True
