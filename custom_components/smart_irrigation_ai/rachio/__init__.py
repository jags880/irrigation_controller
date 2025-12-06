"""Rachio API integration for Smart Irrigation AI."""
# Only import HAZoneController by default - api.py and controller.py
# are legacy modules that require aiohttp and may have compatibility issues.
# They can be imported directly if needed.
from .ha_controller import HAZoneController

__all__ = ["HAZoneController"]
