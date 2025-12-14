"""Panel registration for Smart Irrigation AI sidebar."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_FILENAME = "smart-irrigation-panel.js"
PANEL_TITLE = "Smart Irrigation"
PANEL_ICON = "mdi:sprinkler-variant"
PANEL_NAME = "smart-irrigation-panel"
PANEL_URL_PATH = "smart-irrigation"
# Use a custom path for serving panel files
STATIC_PATH = f"/{DOMAIN}_panel"


def get_panel_dir() -> Path:
    """Get the path to the panel www directory."""
    return Path(__file__).parent / "www"


async def async_setup_panel_url(hass: HomeAssistant) -> bool:
    """Register the static path for serving panel files. Call from async_setup."""
    panel_dir = get_panel_dir()
    panel_path = panel_dir / PANEL_FILENAME

    if not panel_path.exists():
        _LOGGER.error("Panel file not found: %s", panel_path)
        return False

    _LOGGER.info("Setting up panel static path: %s -> %s", STATIC_PATH, panel_dir)

    # Register static path for serving the panel JS using async method
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_PATH, str(panel_dir), cache_headers=False)]
        )
        _LOGGER.info("Static path registered successfully: %s", STATIC_PATH)
        return True
    except Exception as err:
        _LOGGER.warning("Static path registration issue: %s", err)
        # Try the older sync method as fallback
        try:
            hass.http.register_static_path(
                STATIC_PATH,
                str(panel_dir),
                cache_headers=False,
            )
            _LOGGER.info("Static path registered via fallback method: %s", STATIC_PATH)
            return True
        except Exception as err2:
            _LOGGER.debug("Fallback registration note: %s", err2)
            return True  # May already be registered


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Smart Irrigation panel in the sidebar."""
    panel_dir = get_panel_dir()
    panel_path = panel_dir / PANEL_FILENAME

    if not panel_path.exists():
        _LOGGER.error("Panel file not found: %s", panel_path)
        return

    _LOGGER.info("Registering panel from: %s", panel_path)

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
