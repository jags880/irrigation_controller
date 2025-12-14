"""Smart Irrigation AI - Intelligent irrigation control for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import voluptuous as vol

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
    CONF_ZONES,
)
from .coordinator import SmartIrrigationCoordinator
from .ai.irrigation_model import IrrigationAIModel
from .scheduling.scheduler import SmartScheduler
from .rachio.ha_controller import HAZoneController
from .panel import async_register_panel, async_unregister_panel, async_setup_panel_url

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

    # Register WebSocket API commands
    websocket_api.async_register_command(hass, websocket_get_status)
    websocket_api.async_register_command(hass, websocket_get_schedule)
    websocket_api.async_register_command(hass, websocket_get_history)

    # Register static path for panel files early in setup
    await async_setup_panel_url(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Irrigation AI from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Use Home Assistant's Rachio integration
    controller = HAZoneController(hass)

    # Retry zone discovery with delays to handle startup race conditions
    # The Rachio integration may not be fully loaded yet
    discovery = None
    max_retries = 5
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        discovery = await controller.async_discover_rachio_entities()
        if discovery.get("zones"):
            break
        if attempt < max_retries - 1:
            _LOGGER.debug(
                "No Rachio zones found (attempt %d/%d), retrying in %ds...",
                attempt + 1, max_retries, retry_delay
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 10)  # Exponential backoff, max 10s

    if not discovery or not discovery.get("zones"):
        _LOGGER.error(
            "No Rachio zones found in Home Assistant after %d attempts. "
            "Ensure the Rachio integration is set up and has zones configured.",
            max_retries
        )
        return False

    device_info = discovery.get("device_info", {})
    zones_info = discovery.get("zones", [])

    _LOGGER.info(
        "Using Home Assistant Rachio integration with %d zones",
        len(zones_info),
    )

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
        rachio_api=controller,
        ai_model=ai_model,
        use_ha_rachio=True,
    )

    # Create coordinator
    coordinator = SmartIrrigationCoordinator(
        hass=hass,
        entry=entry,
        rachio_api=controller,
        ai_model=ai_model,
        scheduler=scheduler,
        update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        use_ha_rachio=True,
    )

    # Store instances
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "rachio_api": controller,
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

    # Register sidebar panel
    await async_register_panel(hass)

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

    # Unregister panel
    await async_unregister_panel(hass)

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
    rachio_controller = data["rachio_api"]
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

        # zone_id is the entity_id when using HA Rachio
        await rachio_controller.async_run_zone(zone_id, duration)

        await coordinator.async_request_refresh()

    async def handle_stop_all(call: ServiceCall) -> None:
        """Handle stop_all service call."""
        await rachio_controller.async_stop_all()
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


# WebSocket API handlers
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get_status",
    }
)
@websocket_api.async_response
async def websocket_get_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get_status websocket command."""
    result = {"entries": []}

    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        if not isinstance(data, dict):
            continue

        coordinator = data.get("coordinator")
        ai_model = data.get("ai_model")
        scheduler = data.get("scheduler")

        if coordinator and ai_model and scheduler:
            status = ai_model.get_model_status()
            schedule = await scheduler.async_get_schedule()

            result["entries"].append({
                "entry_id": entry_id,
                "status": status,
                "schedule": schedule,
                "is_running": scheduler.is_running,
                "next_run": scheduler.next_run.isoformat() if scheduler.next_run else None,
                "last_run": scheduler.last_run.isoformat() if scheduler.last_run else None,
            })

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get_schedule",
    }
)
@websocket_api.async_response
async def websocket_get_schedule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get_schedule websocket command."""
    result = {"schedules": []}

    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        if not isinstance(data, dict):
            continue

        scheduler = data.get("scheduler")
        if scheduler:
            schedule = await scheduler.async_get_schedule()
            result["schedules"].append({
                "entry_id": entry_id,
                "schedule": schedule,
            })

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get_history",
        vol.Optional("days", default=30): int,
    }
)
@websocket_api.async_response
async def websocket_get_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get_history websocket command."""
    result = {"history": []}

    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        if not isinstance(data, dict):
            continue

        scheduler = data.get("scheduler")
        if scheduler:
            history = scheduler.get_run_history()
            result["history"].extend(history)

    connection.send_result(msg["id"], result)
