"""ESP32-C6 ZBOSS adapter for ZHA — RadioType registration.

This custom-component is a thin glue layer that:

1. Bundles `zigpy-zboss>=2.0.1` as a pip requirement (via manifest.json), so
   HACS pulls it into the HA Python environment.

2. Extends `zha.application.const.RadioType` with a `zboss` member so the ZHA
   "select radio type" config-flow step offers ZBOSS. The extended member
   maps to `zigpy_zboss.zigbee.application.ControllerApplication`.

The three `zigpy-zboss` runtime compatibility shims that earlier versions
carried — the `.name` accessor, post-formation `node_info.nwk` propagation, and
the `ota.providers` voluptuous lenience — are gone as of v0.3.0: all three were
fixed upstream in zigpy-zboss 2.0.0 / 2.0.1 (PRs #73 / #76; the library now
requires `zigpy>=0.92.0,<2`). They are not just unnecessary now — the
`node_info.nwk` override would actively conflict with the upstream fix
(`_form_network` sets `node_info.nwk = res.NWKAddr` itself). The RadioType
extension below is the only thing this component still does: ZHA core has no
`zboss` RadioType, so it must be injected at runtime.

The patch is a no-op if `zboss` is already a RadioType member (idempotent).

Tested against:
- ESP32-C6 + esp-coordinator (tostmann fork)
- zigpy-zboss 2.0.1
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
    """Apply the RadioType extension and log the resulting RadioType members.

    The patch function does synchronous file I/O when first importing
    `zigpy_zboss`, `zha` (module load, importlib). HA's loop watchdog warns
    about blocking-on-event-loop if we do that on the event loop directly, so
    run the work in an executor thread.
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
    """Apply the RadioType extension synchronously — call from an executor thread."""
    applied: list[str] = []
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
# Patch implementation — returns True if it actually patched something,
# False if `zboss` was already a RadioType member (idempotent).
# ---------------------------------------------------------------------------


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
