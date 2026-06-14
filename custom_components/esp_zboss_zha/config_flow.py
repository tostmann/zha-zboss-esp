"""Single-instance config flow for the ESP32-C6 ZBOSS adapter for ZHA.

This integration has **no settings** — its entire job is to run the runtime
patch in `__init__.py` that extends `zha.application.const.RadioType` with a
`zboss` member (so ZHA's radio picker offers ZBOSS). As of v0.3.0 the three
`zigpy-zboss` compatibility shims are gone — they were fixed upstream in
zigpy-zboss 2.0.x.

The config flow exists solely so Home Assistant loads the integration through a
normal config entry. That matters because, before v0.2.0, the integration was
declared `config_flow: false` with no `dependencies` and no `configuration.yaml`
key — so Home Assistant never invoked `async_setup` and the patches never ran.
HACS only downloads the files; it does not trigger a YAML integration's setup.
The symptom was issue #1 ("Cannot find ZBOSS"): files installed, restarted, but
ZBOSS never appeared in ZHA's radio picker because the patch code never executed.

With a config entry, `async_setup_entry` runs on every Home Assistant start —
early, before the user opens ZHA's add-integration flow — so the `RadioType`
extension is deterministically in place when ZHA builds its radio dropdown.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN, NAME


class EspZbossZhaConfigFlow(ConfigFlow, domain=DOMAIN):
    """User-initiated, single-instance, no-input config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle the single setup step.

        There is nothing to configure, so the first invocation shows a bare
        confirmation form and the second creates the (only) entry. A second
        instance is refused — the patches are process-global.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(step_id="user")

        return self.async_create_entry(title=NAME, data={})
