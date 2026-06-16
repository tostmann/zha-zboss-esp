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

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.start import async_at_started

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

    Runs on every Home Assistant start. Applies the `RadioType` extension, then
    arms a one-shot self-heal for the load-order race described below.
    """
    await _async_apply(hass)

    # Load-order race: this integration and `zha` set up concurrently
    # (asyncio.gather over a bootstrap stage), and ZHA resolves
    # `RadioType[<radio_type>]` eagerly during its own config-entry setup. If
    # ZHA wins the race it raises `KeyError('zboss')` and its entry lands in
    # SETUP_ERROR *before* our patch does. There is no manifest-level ordering
    # fix: config-entry setup does not resolve `dependencies` /
    # `after_dependencies` (only the YAML setup path does), and the two
    # integrations are unordered within the stage. So we don't try to win the
    # race — we heal it: once HA has fully started (every setup is final and the
    # patch is long applied), reload any zboss ZHA entry that failed.
    async_at_started(hass, _async_heal_zboss_zha_entries)
    return True


async def _async_heal_zboss_zha_entries(hass: HomeAssistant) -> None:
    """Reload zboss ZHA entries that lost the RadioType load-order race.

    A no-op in the common case where ZHA set up cleanly (entry already LOADED).
    """
    for zha_entry in hass.config_entries.async_entries("zha"):
        if (
            zha_entry.data.get("radio_type") == "zboss"
            and zha_entry.state is not ConfigEntryState.LOADED
        ):
            _LOGGER.warning(
                "[%s] ZHA entry '%s' is %s; reloading now that RadioType.zboss "
                "is registered (load-order race)",
                DOMAIN, zha_entry.title, zha_entry.state,
            )
            await hass.config_entries.async_reload(zha_entry.entry_id)


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
