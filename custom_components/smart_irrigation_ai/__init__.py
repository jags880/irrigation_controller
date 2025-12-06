"""Smart Irrigation AI - Intelligent irrigation control for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL_MINUTES,
    SERVICE_RUN_ZONE,
    SERVICE_STOP_ALL,
    SERVICE_CALCULATE_SCHEDULE,
    SERVICE_FORCE_RECALCULATE,
    SERVICE_SKIP_NEXT_WATERING,
    SERVICE_RAIN_DELAY,
    CONF_RACHIO_API_KEY,
    CONF_ZONES,
)
from .coordinator import SmartIrrigationCoordinator
from .rachio.api import RachioAPI
from .ai.irrigation_model import IrrigationAIModel
from .scheduling.scheduler import SmartScheduler

_LOGGER = logging.getLogger(__name__)

PLATFORMS_TO_SETUP: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CALENDAR,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Smart Irrigation AI component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Irrigation AI from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize Rachio API client
    rachio_api = RachioAPI(
        api_key=entry.data[CONF_RACHIO_API_KEY],
        hass=hass,
    )

    # Verify API connection
    if not await rachio_api.async_verify_connection():
        _LOGGER.error("Failed to connect to Rachio API")
        return False

    # Get device and zone information from Rachio
    device_info = await rachio_api.async_get_device_info()
    zones_info = await rachio_api.async_get_zones()

    # Initialize AI model
    ai_model = IrrigationAIModel(
        hass=hass,
        config=entry.data,
        zones_config=entry.data.get(CONF_ZONES, {}),
    )

    # Initialize scheduler
    scheduler = SmartScheduler(
        hass=hass,
        config=entry.data,
        rachio_api=rachio_api,
        ai_model=ai_model,
    )

    # Create coordinator
    coordinator = SmartIrrigationCoordinator(
        hass=hass,
        entry=entry,
        rachio_api=rachio_api,
        ai_model=ai_model,
        scheduler=scheduler,
        update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
    )

    # Store instances
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "rachio_api": rachio_api,
        "ai_model": ai_model,
        "scheduler": scheduler,
        "device_info": device_info,
        "zones_info": zones_info,
    }

    # Register device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Smart Irrigation AI Controller",
        manufacturer="Smart Irrigation AI",
        model="AI Irrigation Controller",
        sw_version="1.0.0",
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_TO_SETUP)

    # Register services
    await async_register_services(hass, entry)

    # Start the scheduler
    await scheduler.async_start()

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info("Smart Irrigation AI setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop the scheduler
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data:
        scheduler = data.get("scheduler")
        if scheduler:
            await scheduler.async_stop()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS_TO_SETUP)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services for Smart Irrigation AI."""
    data = hass.data[DOMAIN][entry.entry_id]
    rachio_api = data["rachio_api"]
    scheduler = data["scheduler"]
    ai_model = data["ai_model"]
    coordinator = data["coordinator"]

    async def handle_run_zone(call: ServiceCall) -> None:
        """Handle run_zone service call."""
        zone_id = call.data.get("zone_id")
        duration = call.data.get("duration")  # minutes

        if duration is None:
            # Get AI-recommended duration
            duration = await ai_model.async_get_recommended_duration(zone_id)

        await rachio_api.async_run_zone(zone_id, duration * 60)  # Convert to seconds
        await coordinator.async_request_refresh()

    async def handle_stop_all(call: ServiceCall) -> None:
        """Handle stop_all service call."""
        await rachio_api.async_stop_all()
        await coordinator.async_request_refresh()

    async def handle_calculate_schedule(call: ServiceCall) -> None:
        """Handle calculate_schedule service call."""
        await scheduler.async_calculate_schedule()
        await coordinator.async_request_refresh()

    async def handle_force_recalculate(call: ServiceCall) -> None:
        """Handle force_recalculate service call."""
        await ai_model.async_recalculate_all_zones()
        await scheduler.async_calculate_schedule()
        await coordinator.async_request_refresh()

    async def handle_skip_next_watering(call: ServiceCall) -> None:
        """Handle skip_next_watering service call."""
        zone_id = call.data.get("zone_id")
        await scheduler.async_skip_next(zone_id)
        await coordinator.async_request_refresh()

    async def handle_rain_delay(call: ServiceCall) -> None:
        """Handle rain_delay service call."""
        hours = call.data.get("hours", 24)
        await scheduler.async_set_rain_delay(hours)
        await coordinator.async_request_refresh()

    # Register services
    hass.services.async_register(DOMAIN, SERVICE_RUN_ZONE, handle_run_zone)
    hass.services.async_register(DOMAIN, SERVICE_STOP_ALL, handle_stop_all)
    hass.services.async_register(DOMAIN, SERVICE_CALCULATE_SCHEDULE, handle_calculate_schedule)
    hass.services.async_register(DOMAIN, SERVICE_FORCE_RECALCULATE, handle_force_recalculate)
    hass.services.async_register(DOMAIN, SERVICE_SKIP_NEXT_WATERING, handle_skip_next_watering)
    hass.services.async_register(DOMAIN, SERVICE_RAIN_DELAY, handle_rain_delay)
