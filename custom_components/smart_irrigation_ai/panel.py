"""Panel registration for Smart Irrigation AI sidebar."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_FILENAME = "smart-irrigation-panel.js"
PANEL_TITLE = "Smart Irrigation"
PANEL_ICON = "mdi:sprinkler-variant"
PANEL_NAME = "smart-irrigation-panel"
PANEL_URL_PATH = "smart-irrigation"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Smart Irrigation panel in the sidebar."""
    # Get the path to our panel file
    panel_path = Path(__file__).parent / "www" / PANEL_FILENAME

    if not panel_path.exists():
        _LOGGER.error("Panel file not found: %s", panel_path)
        return

    # Register static path for serving the panel JS
    try:
        hass.http.register_static_path(
            f"/smart_irrigation_ai/{PANEL_FILENAME}",
            str(panel_path),
            cache_headers=False,
        )
    except Exception as err:
        _LOGGER.debug("Static path may already be registered: %s", err)

    # Register the custom panel
    try:
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name=PANEL_NAME,
            frontend_url_path=PANEL_URL_PATH,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"/smart_irrigation_ai/{PANEL_FILENAME}",
            embed_iframe=False,
            require_admin=False,
        )
        _LOGGER.info("Smart Irrigation panel registered successfully")
    except Exception as err:
        _LOGGER.error("Failed to register panel: %s", err)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister the panel."""
    try:
        hass.components.frontend.async_remove_panel(PANEL_URL_PATH)
        _LOGGER.info("Smart Irrigation panel unregistered")
    except Exception as err:
        _LOGGER.debug("Error unregistering panel: %s", err)
