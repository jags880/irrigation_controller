"""Panel registration for Smart Irrigation AI sidebar."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "/smart-irrigation-panel"
PANEL_FILENAME = "smart-irrigation-panel.js"
PANEL_TITLE = "Smart Irrigation"
PANEL_ICON = "mdi:sprinkler-variant"
PANEL_NAME = "smart-irrigation-panel"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Smart Irrigation panel in the sidebar."""
    # Get the path to our panel file
    panel_path = Path(__file__).parent / "www" / PANEL_FILENAME

    if not panel_path.exists():
        _LOGGER.warning("Panel file not found: %s", panel_path)
        return

    # Register static path for serving the panel JS
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            url_path=f"/smart_irrigation_ai/{PANEL_FILENAME}",
            path=str(panel_path),
            cache_headers=False,
        )
    ])

    # Register the panel
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path="smart-irrigation",
        config={
            "_panel_custom": {
                "name": PANEL_NAME,
                "embed_iframe": False,
                "trust_external": False,
                "module_url": f"/smart_irrigation_ai/{PANEL_FILENAME}",
            }
        },
        require_admin=False,
    )

    _LOGGER.info("Smart Irrigation panel registered")


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister the panel."""
    try:
        frontend.async_remove_panel(hass, "smart-irrigation")
        _LOGGER.info("Smart Irrigation panel unregistered")
    except Exception as err:
        _LOGGER.debug("Error unregistering panel: %s", err)
