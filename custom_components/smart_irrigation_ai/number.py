"""Number entities for Smart Irrigation AI."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DEFAULT_MAX_DAILY_RUNTIME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Irrigation AI number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    zones_info = data.get("zones_info", [])

    entities = [
        MaxDailyRuntimeNumber(coordinator, entry),
        RainDelayHoursNumber(coordinator, entry),
        SeasonalAdjustmentNumber(coordinator, entry),
    ]

    # Zone-specific adjustments
    for zone in zones_info:
        zone_id = zone.get("zone_id") or zone.get("entity_id")
        zone_name = zone.get("name", f"Zone {zone.get('zone_number', '?')}")

        # Skip zones without valid ID
        if not zone_id:
            _LOGGER.warning("Skipping zone number entity creation - no valid zone ID: %s", zone)
            continue

        entities.append(
            ZoneDurationAdjustmentNumber(coordinator, entry, zone_id, zone_name)
        )

    async_add_entities(entities)


class SmartIrrigationNumberBase(CoordinatorEntity, NumberEntity):
    """Base class for Smart Irrigation number entities."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        entity_type: str,
        name: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._entity_type = entity_type
        self._attr_name = f"Smart Irrigation {name}"
        self._attr_unique_id = f"{entry.entry_id}_{entity_type}"
        self._attr_mode = NumberMode.BOX

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


class MaxDailyRuntimeNumber(SmartIrrigationNumberBase):
    """Number entity for maximum daily runtime."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "max_runtime", "Max Daily Runtime")
        self._attr_native_min_value = 10
        self._attr_native_max_value = 480
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_icon = "mdi:timer-cog"
        self._value = entry.data.get("max_daily_runtime", DEFAULT_MAX_DAILY_RUNTIME)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        self._value = int(value)

        # Update the scheduler
        scheduler = self.hass.data[DOMAIN][self._entry.entry_id]["scheduler"]
        scheduler._max_runtime = self._value

        self.async_write_ha_state()


class RainDelayHoursNumber(SmartIrrigationNumberBase):
    """Number entity for rain delay duration."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "rain_delay_hours", "Rain Delay Hours")
        self._attr_native_min_value = 0
        self._attr_native_max_value = 168  # 1 week
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_icon = "mdi:weather-rainy"

    @property
    def native_value(self) -> float:
        """Return the current value."""
        if self.coordinator.data is None:
            return 0

        schedule = self.coordinator.data.get("schedule", {})
        rain_delay = schedule.get("rain_delay_until")

        if rain_delay:
            from datetime import datetime
            try:
                delay_until = datetime.fromisoformat(rain_delay)
                remaining = (delay_until - dt_util.now()).total_seconds() / 3600
                return max(0, round(remaining))
            except (ValueError, TypeError):
                pass

        return 0

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        scheduler = self.hass.data[DOMAIN][self._entry.entry_id]["scheduler"]

        if value > 0:
            await scheduler.async_set_rain_delay(int(value))
        else:
            await scheduler.async_cancel_rain_delay()

        await self.coordinator.async_request_refresh()


class SeasonalAdjustmentNumber(SmartIrrigationNumberBase):
    """Number entity for manual seasonal adjustment."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "seasonal_adjustment", "Seasonal Adjustment")
        self._attr_native_min_value = 0
        self._attr_native_max_value = 200
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:percent"
        self._value = 100  # 100% = no adjustment

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        self._value = value

        # Update the AI model's seasonal factor
        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        # Apply custom seasonal adjustment
        # This could override the automatic seasonal factor
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        from .const import SEASONAL_FACTORS
        from datetime import datetime

        auto_factor = SEASONAL_FACTORS.get(datetime.now().month, 1.0)

        return {
            "auto_seasonal_factor": auto_factor,
            "effective_factor": (self._value / 100) * auto_factor,
        }


class ZoneDurationAdjustmentNumber(SmartIrrigationNumberBase):
    """Number entity for zone duration adjustment."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}_adjustment",
            f"{zone_name} Duration Adjustment",
        )
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_native_min_value = 0
        self._attr_native_max_value = 200
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:tune-vertical"
        self._value = 100  # 100% = no adjustment

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        self._value = value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        recommendations = self.coordinator.data.get("recommendations", {}) if self.coordinator.data else {}
        rec = recommendations.get(self._zone_id)

        base_duration = rec.duration_minutes if rec and hasattr(rec, 'duration_minutes') else 0
        adjusted_duration = int(base_duration * self._value / 100)

        return {
            "base_duration": base_duration,
            "adjusted_duration": adjusted_duration,
        }
