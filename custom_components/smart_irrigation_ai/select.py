"""Select entities for Smart Irrigation AI."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ZONE_TYPES, SOIL_TYPES, NOZZLE_TYPES, SUN_EXPOSURE, SLOPE_TYPES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Irrigation AI select entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    zones_info = data.get("zones_info", [])

    entities = [
        WateringModeSelect(coordinator, entry),
    ]

    # Zone-specific selects
    for zone in zones_info:
        zone_id = zone.get("zone_id") or zone.get("entity_id")
        zone_name = zone.get("name", f"Zone {zone.get('zone_number', '?')}")

        # Skip zones without valid ID
        if not zone_id:
            _LOGGER.warning("Skipping zone select entity creation - no valid zone ID: %s", zone)
            continue

        entities.extend([
            ZoneTypeSelect(coordinator, entry, zone_id, zone_name),
            ZoneSoilTypeSelect(coordinator, entry, zone_id, zone_name),
            ZoneNozzleTypeSelect(coordinator, entry, zone_id, zone_name),
            ZoneSunExposureSelect(coordinator, entry, zone_id, zone_name),
            ZoneSlopeSelect(coordinator, entry, zone_id, zone_name),
        ])

    async_add_entities(entities)


class SmartIrrigationSelectBase(CoordinatorEntity, SelectEntity):
    """Base class for Smart Irrigation select entities."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        entity_type: str,
        name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._entity_type = entity_type
        self._attr_name = f"Smart Irrigation {name}"
        self._attr_unique_id = f"{entry.entry_id}_{entity_type}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Smart Irrigation AI Controller",
            manufacturer="Smart Irrigation AI",
            model="AI Irrigation Controller",
            sw_version="1.0.0",
        )


class WateringModeSelect(SmartIrrigationSelectBase):
    """Select entity for watering mode."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entry, "watering_mode", "Watering Mode")
        self._attr_options = [
            "automatic",
            "eco",
            "aggressive",
            "manual_only",
            "disabled",
        ]
        self._attr_icon = "mdi:cog"
        self._current_option = "automatic"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        self._current_option = option

        # Adjust AI model behavior based on mode
        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]

        # Mode adjustments could be applied here
        # For now, just store the selection
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        mode_descriptions = {
            "automatic": "AI determines optimal watering based on all inputs",
            "eco": "Water conservation mode - reduced watering, higher thresholds",
            "aggressive": "Maximum growth mode - more frequent, deeper watering",
            "manual_only": "No automatic scheduling, manual control only",
            "disabled": "All watering disabled",
        }

        return {
            "description": mode_descriptions.get(self._current_option, ""),
        }


class ZoneTypeSelect(SmartIrrigationSelectBase):
    """Select entity for zone vegetation type."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_type",
            f"{zone_name} Vegetation Type",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_options = list(ZONE_TYPES.keys())
        self._attr_icon = "mdi:grass"
        self._current_option = "cool_season_grass"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        zones_config = self._entry.data.get("zones", {})
        zone_config = zones_config.get(self._zone_id, {})
        return zone_config.get("zone_type", self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        self._current_option = option

        # Update the AI model's zone configuration
        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        if self._zone_id in ai_model._zone_configs:
            ai_model._zone_configs[self._zone_id].zone_type = option

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        zone_info = ZONE_TYPES.get(self._current_option, {})
        return {
            "display_name": zone_info.get("name", self._current_option),
            "crop_coefficient": zone_info.get("kc"),
            "typical_root_depth": zone_info.get("root_depth"),
        }


class ZoneSoilTypeSelect(SmartIrrigationSelectBase):
    """Select entity for zone soil type."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_soil",
            f"{zone_name} Soil Type",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_options = list(SOIL_TYPES.keys())
        self._attr_icon = "mdi:terrain"
        self._current_option = "loam"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        zones_config = self._entry.data.get("zones", {})
        zone_config = zones_config.get(self._zone_id, {})
        return zone_config.get("soil_type", self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        self._current_option = option

        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        if self._zone_id in ai_model._zone_configs:
            ai_model._zone_configs[self._zone_id].soil_type = option

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        soil_info = SOIL_TYPES.get(self._current_option, {})
        return {
            "display_name": soil_info.get("name", self._current_option),
            "infiltration_rate": soil_info.get("infiltration_rate"),
            "water_holding_capacity": soil_info.get("water_holding_capacity"),
        }


class ZoneNozzleTypeSelect(SmartIrrigationSelectBase):
    """Select entity for zone nozzle type."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_nozzle",
            f"{zone_name} Nozzle Type",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_options = list(NOZZLE_TYPES.keys())
        self._attr_icon = "mdi:sprinkler-fire"
        self._current_option = "fixed_spray"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        zones_config = self._entry.data.get("zones", {})
        zone_config = zones_config.get(self._zone_id, {})
        return zone_config.get("nozzle_type", self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        self._current_option = option

        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        if self._zone_id in ai_model._zone_configs:
            ai_model._zone_configs[self._zone_id].nozzle_type = option

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        nozzle_info = NOZZLE_TYPES.get(self._current_option, {})
        return {
            "display_name": nozzle_info.get("name", self._current_option),
            "precipitation_rate": nozzle_info.get("precip_rate"),
        }


class ZoneSunExposureSelect(SmartIrrigationSelectBase):
    """Select entity for zone sun exposure."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_sun",
            f"{zone_name} Sun Exposure",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_options = list(SUN_EXPOSURE.keys())
        self._attr_icon = "mdi:white-balance-sunny"
        self._current_option = "full_sun"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        zones_config = self._entry.data.get("zones", {})
        zone_config = zones_config.get(self._zone_id, {})
        return zone_config.get("sun_exposure", self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        self._current_option = option

        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        if self._zone_id in ai_model._zone_configs:
            ai_model._zone_configs[self._zone_id].sun_exposure = option

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        sun_info = SUN_EXPOSURE.get(self._current_option, {})
        return {
            "display_name": sun_info.get("name", self._current_option),
            "et_factor": sun_info.get("et_factor"),
        }


class ZoneSlopeSelect(SmartIrrigationSelectBase):
    """Select entity for zone slope."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_slope",
            f"{zone_name} Slope",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_options = list(SLOPE_TYPES.keys())
        self._attr_icon = "mdi:slope-uphill"
        self._current_option = "flat"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        zones_config = self._entry.data.get("zones", {})
        zone_config = zones_config.get(self._zone_id, {})
        return zone_config.get("slope", self._current_option)

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        self._current_option = option

        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        if self._zone_id in ai_model._zone_configs:
            ai_model._zone_configs[self._zone_id].slope = option

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        slope_info = SLOPE_TYPES.get(self._current_option, {})
        return {
            "display_name": slope_info.get("name", self._current_option),
            "runoff_factor": slope_info.get("runoff_factor"),
        }
