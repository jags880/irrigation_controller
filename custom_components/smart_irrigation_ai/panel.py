"""Panel registration for Smart Irrigation AI sidebar."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_FILENAME = "smart-irrigation-panel.js"
PANEL_TITLE = "Smart Irrigation"
PANEL_ICON = "mdi:sprinkler-variant"
PANEL_NAME = "smart-irrigation-panel"
PANEL_URL_PATH = "smart-irrigation"
# Use a custom API path for serving panel files - this is more reliable
# than hacsfiles which requires HACS to manage the path
STATIC_PATH = f"/api/{DOMAIN}/static"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Smart Irrigation panel in the sidebar."""
    # Get the path to our panel file
    panel_dir = Path(__file__).parent / "www"
    panel_path = panel_dir / PANEL_FILENAME

    if not panel_path.exists():
        _LOGGER.error("Panel file not found: %s", panel_path)
        return

    _LOGGER.info("Registering panel from: %s", panel_path)

    # Register static path for serving the panel JS
    # Using /api/{domain}/static pattern for reliable serving
    try:
        hass.http.register_static_path(
            STATIC_PATH,
            str(panel_dir),
            cache_headers=False,
        )
        _LOGGER.info("Static path registered: %s -> %s", STATIC_PATH, panel_dir)
    except Exception as err:
        # Path may already be registered from previous load - continue anyway
        _LOGGER.debug("Static path registration note (may already exist): %s", err)

    # Register the custom panel using frontend's built-in panel method
    try:
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={
                "_panel_custom": {
                    "name": PANEL_NAME,
                    "module_url": f"{STATIC_PATH}/{PANEL_FILENAME}",
                    "embed_iframe": False,
                    "trust_external": True,  # Allow loading lit-element from CDN
                }
            },
            require_admin=False,
        )
        _LOGGER.info("Smart Irrigation panel registered at /%s", PANEL_URL_PATH)
    except Exception as err:
        _LOGGER.error("Failed to register panel: %s", err)
        import traceback
        _LOGGER.error(traceback.format_exc())


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister the panel."""
    try:
        from homeassistant.components.frontend import async_remove_panel
        async_remove_panel(hass, PANEL_URL_PATH)
        _LOGGER.info("Smart Irrigation panel unregistered")
    except Exception as err:
        _LOGGER.debug("Error unregistering panel: %s", err)
