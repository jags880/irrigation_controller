"""Binary sensor entities for Smart Irrigation AI."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Irrigation AI binary sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    zones_info = data.get("zones_info", [])

    entities = [
        IrrigationRunningSensor(coordinator, entry),
        RainSensorTrippedSensor(coordinator, entry),
        WateringNeededSensor(coordinator, entry),
        WeatherSkipSensor(coordinator, entry),
    ]

    # Zone-specific binary sensors
    for zone in zones_info:
        zone_id = zone.get("zone_id") or zone.get("entity_id")
        zone_name = zone.get("name", f"Zone {zone.get('zone_number', '?')}")

        # Skip zones without valid ID
        if not zone_id:
            _LOGGER.warning("Skipping zone binary sensor creation - no valid zone ID: %s", zone)
            continue

        entities.extend([
            ZoneNeedsWaterSensor(coordinator, entry, zone_id, zone_name),
            ZoneRunningSensor(coordinator, entry, zone_id, zone_name),
        ])

    async_add_entities(entities)


class SmartIrrigationBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Smart Irrigation binary sensors."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_type = sensor_type
        self._attr_name = f"Smart Irrigation {name}"
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

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


class IrrigationRunningSensor(SmartIrrigationBinarySensorBase):
    """Binary sensor for irrigation running status."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "running", "Running")
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:sprinkler"

    @property
    def is_on(self) -> bool:
        """Return if irrigation is running."""
        if self.coordinator.data is None:
            return False

        schedule = self.coordinator.data.get("schedule", {})
        return schedule.get("is_running", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        schedule = self.coordinator.data.get("schedule", {})
        return {
            "current_zone": schedule.get("current_zone"),
        }


class RainSensorTrippedSensor(SmartIrrigationBinarySensorBase):
    """Binary sensor for rain sensor status."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "rain_sensor", "Rain Detected")
        self._attr_device_class = BinarySensorDeviceClass.MOISTURE
        self._attr_icon = "mdi:weather-rainy"

    @property
    def is_on(self) -> bool:
        """Return if rain is detected."""
        if self.coordinator.data is None:
            return False

        rain_sensor = self.coordinator.data.get("rain_sensor", {})
        return rain_sensor.get("tripped", False) or rain_sensor.get("is_raining", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        rain_sensor = self.coordinator.data.get("rain_sensor", {})
        return {
            "intensity": rain_sensor.get("intensity"),
            "rain_rate": rain_sensor.get("external_rain_rate"),
            "rain_delay_active": rain_sensor.get("rain_delay_active"),
            "rain_factor": rain_sensor.get("rain_factor"),
        }


class WateringNeededSensor(SmartIrrigationBinarySensorBase):
    """Binary sensor indicating if any zone needs water."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "watering_needed", "Watering Needed")
        self._attr_icon = "mdi:water-alert"

    @property
    def is_on(self) -> bool:
        """Return if any zone needs water."""
        if self.coordinator.data is None:
            return False

        recommendations = self.coordinator.data.get("recommendations", {})
        return any(
            hasattr(r, 'should_water') and r.should_water
            for r in recommendations.values()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        recommendations = self.coordinator.data.get("recommendations", {})
        zones_needing = []

        for zone_id, rec in recommendations.items():
            if hasattr(rec, 'should_water') and rec.should_water:
                zones_needing.append({
                    "zone_id": zone_id,
                    "zone_name": rec.zone_name if hasattr(rec, 'zone_name') else zone_id,
                    "duration": rec.duration_minutes if hasattr(rec, 'duration_minutes') else 0,
                    "urgency": rec.factors.get("soil_analysis", {}).get("urgency") if hasattr(rec, 'factors') else None,
                })

        return {
            "zones_needing_water": len(zones_needing),
            "zones": zones_needing,
        }


class WeatherSkipSensor(SmartIrrigationBinarySensorBase):
    """Binary sensor indicating if weather is causing a skip."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "weather_skip", "Weather Skip Active")
        self._attr_icon = "mdi:weather-cloudy-alert"

    @property
    def is_on(self) -> bool:
        """Return if weather is causing irrigation to be skipped."""
        if self.coordinator.data is None:
            return False

        recommendations = self.coordinator.data.get("recommendations", {})

        for rec in recommendations.values():
            if hasattr(rec, 'factors'):
                weather_factor = rec.factors.get("weather_factor", 1.0)
                if weather_factor < 0.3:
                    return True

        weather = self.coordinator.data.get("weather", {})
        condition = weather.get("condition", "").lower()
        if "rain" in condition and "light" not in condition:
            return True

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        weather = self.coordinator.data.get("weather", {})
        rain_sensor = self.coordinator.data.get("rain_sensor", {})

        skip_reasons = []

        if rain_sensor.get("is_raining"):
            skip_reasons.append(f"Rain detected ({rain_sensor.get('intensity', 'unknown')} intensity)")

        if weather.get("precipitation", 0) > 0.5:
            skip_reasons.append(f"Recent precipitation ({weather.get('precipitation')}in)")

        recommendations = self.coordinator.data.get("recommendations", {})
        for rec in recommendations.values():
            if hasattr(rec, 'skip_reason') and rec.skip_reason:
                if rec.skip_reason not in skip_reasons:
                    skip_reasons.append(rec.skip_reason)
                break

        return {
            "weather_condition": weather.get("condition"),
            "weather_factor": recommendations.get(list(recommendations.keys())[0], {}).factors.get("weather_factor") if recommendations else None,
            "skip_reasons": skip_reasons,
        }


class ZoneNeedsWaterSensor(SmartIrrigationBinarySensorBase):
    """Binary sensor for zone water need."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_needs_water",
            f"{zone_name} Needs Water",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_icon = "mdi:water-alert"

    @property
    def is_on(self) -> bool:
        """Return if zone needs water."""
        if self.coordinator.data is None:
            return False

        recommendations = self.coordinator.data.get("recommendations", {})
        rec = recommendations.get(self._zone_id)

        if rec and hasattr(rec, 'should_water'):
            return rec.should_water

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        recommendations = self.coordinator.data.get("recommendations", {})
        rec = recommendations.get(self._zone_id)

        if rec and hasattr(rec, 'factors'):
            return {
                "recommended_duration": rec.duration_minutes,
                "water_amount_inches": rec.water_amount_inches,
                "confidence": rec.confidence,
                "priority": rec.priority,
                "skip_reason": rec.skip_reason,
            }

        return {}


class ZoneRunningSensor(SmartIrrigationBinarySensorBase):
    """Binary sensor for zone running status."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_running",
            f"{zone_name} Running",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:sprinkler-variant"

    @property
    def is_on(self) -> bool:
        """Return if zone is running."""
        if self.coordinator.data is None:
            return False

        zones = self.coordinator.data.get("zones", {})
        zone_status = zones.get(self._zone_id, {})

        return zone_status.get("running", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        zones = self.coordinator.data.get("zones", {})
        zone_status = zones.get(self._zone_id, {})

        return {
            "remaining_runtime": zone_status.get("remaining_runtime", 0),
        }
