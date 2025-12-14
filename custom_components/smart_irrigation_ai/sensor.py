"""Sensor entities for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ATTR_NEXT_RUN, ATTR_AI_CONFIDENCE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Irrigation AI sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    zones_info = data.get("zones_info", [])

    entities = []

    # Main controller sensors
    entities.extend([
        IrrigationStatusSensor(coordinator, entry),
        NextRunSensor(coordinator, entry),
        WeatherFactorSensor(coordinator, entry),
        SeasonalFactorSensor(coordinator, entry),
        TotalWaterUsageSensor(coordinator, entry),
    ])

    # Zone-specific sensors
    for zone in zones_info:
        zone_id = zone.get("zone_id") or zone.get("entity_id")
        zone_name = zone.get("name", f"Zone {zone.get('zone_number', '?')}")
        # Ensure zone_name starts with "Zone" for consistent entity naming
        if not zone_name.lower().startswith("zone"):
            zone_name = f"Zone {zone_name}"

        # Skip zones without valid ID
        if not zone_id:
            _LOGGER.warning("Skipping zone sensor creation - no valid zone ID: %s", zone)
            continue

        entities.extend([
            ZoneMoistureSensor(coordinator, entry, zone_id, zone_name),
            ZoneRecommendationSensor(coordinator, entry, zone_id, zone_name),
            ZoneWaterDeficitSensor(coordinator, entry, zone_id, zone_name),
            ZoneNextDurationSensor(coordinator, entry, zone_id, zone_name),
        ])

    async_add_entities(entities)


class SmartIrrigationSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Smart Irrigation sensors."""

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


class IrrigationStatusSensor(SmartIrrigationSensorBase):
    """Sensor for overall irrigation status."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "status", "Status")
        self._attr_icon = "mdi:sprinkler-variant"

    @property
    def native_value(self) -> str:
        """Return the status."""
        if self.coordinator.data is None:
            return "unknown"

        schedule = self.coordinator.data.get("schedule", {})

        if schedule.get("rain_delay_until"):
            return "rain_delay"

        if schedule.get("is_running"):
            return "running"

        if schedule.get("skip_next"):
            return "skip_scheduled"

        recommendations = self.coordinator.data.get("recommendations", {})
        zones_needing_water = sum(
            1 for r in recommendations.values()
            if hasattr(r, 'should_water') and r.should_water
        )

        if zones_needing_water > 0:
            return "scheduled"

        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        schedule = self.coordinator.data.get("schedule", {})
        recommendations = self.coordinator.data.get("recommendations", {})

        return {
            "next_run": schedule.get("next_run"),
            "last_run": schedule.get("last_run"),
            "zones_scheduled": len([
                r for r in recommendations.values()
                if hasattr(r, 'should_water') and r.should_water
            ]),
            "total_runtime_minutes": schedule.get("schedule", {}).get("total_runtime", 0),
            "rain_delay_until": schedule.get("rain_delay_until"),
            "last_update": self.coordinator.data.get("last_update"),
        }


class NextRunSensor(SmartIrrigationSensorBase):
    """Sensor for next scheduled run."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "next_run", "Next Run")
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self) -> datetime | None:
        """Return the next run time."""
        if self.coordinator.data is None:
            return None

        schedule = self.coordinator.data.get("schedule", {})
        next_run = schedule.get("next_run")

        if next_run:
            try:
                return datetime.fromisoformat(next_run)
            except (ValueError, TypeError):
                pass

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        schedule = self.coordinator.data.get("schedule", {})
        sched_data = schedule.get("schedule", {})

        return {
            "zones_to_water": sched_data.get("zones_to_water", 0),
            "total_runtime": sched_data.get("total_runtime", 0),
            "watering_days": schedule.get("watering_days", []),
        }


class WeatherFactorSensor(SmartIrrigationSensorBase):
    """Sensor for current weather adjustment factor."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "weather_factor", "Weather Factor")
        self._attr_native_unit_of_measurement = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:weather-partly-cloudy"

    @property
    def native_value(self) -> float | None:
        """Return the weather factor."""
        if self.coordinator.data is None:
            return None

        weather = self.coordinator.data.get("weather", {})

        # Get weather factor from first zone recommendation or weather data
        recommendations = self.coordinator.data.get("recommendations", {})
        for rec in recommendations.values():
            if hasattr(rec, 'factors'):
                return rec.factors.get("weather_factor")

        return 1.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        weather = self.coordinator.data.get("weather", {})

        return {
            "condition": weather.get("condition"),
            "temperature": weather.get("temperature"),
            "humidity": weather.get("humidity"),
            "wind_speed": weather.get("wind_speed"),
            "precipitation": weather.get("precipitation"),
            "precipitation_probability": weather.get("precipitation_probability"),
        }


class SeasonalFactorSensor(SmartIrrigationSensorBase):
    """Sensor for seasonal adjustment factor."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "seasonal_factor", "Seasonal Factor")
        self._attr_native_unit_of_measurement = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:leaf"

    @property
    def native_value(self) -> float | None:
        """Return the seasonal factor."""
        recommendations = self.coordinator.data.get("recommendations", {}) if self.coordinator.data else {}

        for rec in recommendations.values():
            if hasattr(rec, 'factors'):
                return rec.factors.get("seasonal_factor")

        # Calculate based on current month
        from .const import SEASONAL_FACTORS
        return SEASONAL_FACTORS.get(datetime.now().month, 1.0)


class TotalWaterUsageSensor(SmartIrrigationSensorBase):
    """Sensor for total water usage."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "water_usage", "Estimated Water Usage")
        self._attr_native_unit_of_measurement = "gal"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:water"

    @property
    def native_value(self) -> float | None:
        """Return estimated water usage in gallons."""
        if self.coordinator.data is None:
            return 0

        schedule = self.coordinator.data.get("schedule", {}).get("schedule", {})
        zones = schedule.get("zones", [])

        # Estimate gallons based on water inches and area
        # Assume average zone area of 1000 sqft
        total_gallons = 0
        for zone in zones:
            water_inches = zone.get("water_amount_inches", 0)
            area_sqft = 1000  # Default assumption
            # 1 inch of water over 1 sqft = 0.623 gallons
            gallons = water_inches * area_sqft * 0.623
            total_gallons += gallons

        return round(total_gallons, 1)


class ZoneMoistureSensor(SmartIrrigationSensorBase):
    """Sensor for zone soil moisture."""

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
            f"zone_{zone_id}_moisture",
            f"{zone_name} Moisture",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:water-percent"

    @property
    def native_value(self) -> float | None:
        """Return the moisture level."""
        if self.coordinator.data is None:
            return None

        moisture = self.coordinator.data.get("moisture", {})
        zone_moisture = moisture.get(self._zone_id, {})

        return zone_moisture.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        recommendations = self.coordinator.data.get("recommendations", {}) if self.coordinator.data else {}
        rec = recommendations.get(self._zone_id)

        if rec and hasattr(rec, 'factors'):
            soil_analysis = rec.factors.get("soil_analysis", {})
            return {
                "status": soil_analysis.get("status"),
                "needs_water": soil_analysis.get("needs_water"),
                "urgency": soil_analysis.get("urgency"),
                "trend": soil_analysis.get("trend"),
                "water_deficit_pct": soil_analysis.get("water_deficit_pct"),
            }

        return {}


class ZoneRecommendationSensor(SmartIrrigationSensorBase):
    """Sensor for zone AI recommendation."""

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
            f"zone_{zone_id}_recommendation",
            f"{zone_name} Recommendation",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_icon = "mdi:brain"

    @property
    def native_value(self) -> str:
        """Return the recommendation."""
        if self.coordinator.data is None:
            return "unknown"

        recommendations = self.coordinator.data.get("recommendations", {})
        rec = recommendations.get(self._zone_id)

        if rec is None:
            return "no_data"

        if hasattr(rec, 'should_water'):
            if rec.should_water:
                return f"water_{rec.duration_minutes}min"
            elif rec.skip_reason:
                return f"skip_{rec.skip_reason.lower().replace(' ', '_')[:20]}"
            else:
                return "skip"

        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        recommendations = self.coordinator.data.get("recommendations", {}) if self.coordinator.data else {}
        rec = recommendations.get(self._zone_id)

        if rec and hasattr(rec, 'to_dict'):
            return rec.to_dict()
        elif rec and hasattr(rec, 'factors'):
            return {
                "should_water": rec.should_water,
                "duration_minutes": rec.duration_minutes,
                "water_amount_inches": rec.water_amount_inches,
                "confidence": rec.confidence,
                "priority": rec.priority,
                "skip_reason": rec.skip_reason,
                **rec.factors,
            }

        return {}


class ZoneWaterDeficitSensor(SmartIrrigationSensorBase):
    """Sensor for zone water deficit."""

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
            f"zone_{zone_id}_deficit",
            f"{zone_name} Water Deficit",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:water-minus"

    @property
    def native_value(self) -> float | None:
        """Return the water deficit percentage."""
        recommendations = self.coordinator.data.get("recommendations", {}) if self.coordinator.data else {}
        rec = recommendations.get(self._zone_id)

        if rec and hasattr(rec, 'factors'):
            et_status = rec.factors.get("et_status", {})
            return et_status.get("depletion_percent")

        return None


class ZoneNextDurationSensor(SmartIrrigationSensorBase):
    """Sensor for zone recommended duration."""

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
            f"zone_{zone_id}_duration",
            f"{zone_name} Recommended Duration",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self) -> int | None:
        """Return the recommended duration."""
        recommendations = self.coordinator.data.get("recommendations", {}) if self.coordinator.data else {}
        rec = recommendations.get(self._zone_id)

        if rec and hasattr(rec, 'duration_minutes'):
            return rec.duration_minutes

        return None
