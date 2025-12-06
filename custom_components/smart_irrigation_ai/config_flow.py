"""Config flow for Smart Irrigation AI integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_RACHIO_API_KEY,
    CONF_WEATHER_ENTITY,
    CONF_MOISTURE_SENSORS,
    CONF_RAIN_SENSOR,
    CONF_WATERING_DAYS,
    CONF_WATERING_START_TIME,
    CONF_WATERING_END_TIME,
    CONF_MAX_DAILY_RUNTIME,
    CONF_CYCLE_SOAK_ENABLED,
    CONF_ZONES,
    ZONE_TYPES,
    SOIL_TYPES,
    SLOPE_TYPES,
    SUN_EXPOSURE,
    NOZZLE_TYPES,
    DEFAULT_MAX_DAILY_RUNTIME,
    DEFAULT_START_TIME,
    DEFAULT_END_TIME,
)
from .rachio.api import RachioAPI

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_RACHIO_API_KEY): str,
})


async def validate_rachio_api(hass: HomeAssistant, api_key: str) -> dict[str, Any]:
    """Validate the Rachio API key and get device info."""
    api = RachioAPI(api_key=api_key, hass=hass)

    if not await api.async_verify_connection():
        raise ValueError("Failed to connect to Rachio API")

    device_info = await api.async_get_device_info()
    zones = await api.async_get_zones()

    return {
        "device_name": device_info.get("name", "Rachio Controller"),
        "device_id": device_info.get("id"),
        "zones": zones,
    }


class SmartIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Irrigation AI."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_key: str | None = None
        self._device_info: dict[str, Any] = {}
        self._zones: list[dict[str, Any]] = []
        self._zones_config: dict[str, dict[str, Any]] = {}
        self._current_zone_index = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - Rachio API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_rachio_api(self.hass, user_input[CONF_RACHIO_API_KEY])
                self._api_key = user_input[CONF_RACHIO_API_KEY]
                self._device_info = info
                self._zones = info["zones"]

                # Check if already configured
                await self.async_set_unique_id(info["device_id"])
                self._abort_if_unique_id_configured()

                return await self.async_step_weather()

            except ValueError:
                errors["base"] = "invalid_api_key"
            except Exception:
                _LOGGER.exception("Unexpected error validating Rachio API")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "rachio_url": "https://app.rach.io/account/settings",
            },
        )

    async def async_step_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure weather entity."""
        if user_input is not None:
            self._weather_entity = user_input.get(CONF_WEATHER_ENTITY)
            self._rain_sensor = user_input.get(CONF_RAIN_SENSOR)
            return await self.async_step_schedule()

        # Get available weather entities
        weather_entities = [
            state.entity_id
            for state in self.hass.states.async_all("weather")
        ]

        # Get available rain sensors
        rain_sensors = [
            state.entity_id
            for state in self.hass.states.async_all("binary_sensor")
            if "rain" in state.entity_id.lower() or "moisture" in state.entity_id.lower()
        ]

        data_schema = vol.Schema({
            vol.Optional(CONF_WEATHER_ENTITY): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=weather_entities,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(CONF_RAIN_SENSOR): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=rain_sensors,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
        })

        return self.async_show_form(
            step_id="weather",
            data_schema=data_schema,
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure watering schedule."""
        if user_input is not None:
            self._watering_days = user_input.get(CONF_WATERING_DAYS, [0, 2, 4, 6])
            self._start_time = user_input.get(CONF_WATERING_START_TIME, DEFAULT_START_TIME)
            self._end_time = user_input.get(CONF_WATERING_END_TIME, DEFAULT_END_TIME)
            self._max_runtime = user_input.get(CONF_MAX_DAILY_RUNTIME, DEFAULT_MAX_DAILY_RUNTIME)
            self._cycle_soak = user_input.get(CONF_CYCLE_SOAK_ENABLED, True)

            # Start zone configuration
            self._current_zone_index = 0
            if self._zones:
                return await self.async_step_zone()
            else:
                return await self.async_step_moisture_sensors()

        days_options = [
            {"value": "0", "label": "Monday"},
            {"value": "1", "label": "Tuesday"},
            {"value": "2", "label": "Wednesday"},
            {"value": "3", "label": "Thursday"},
            {"value": "4", "label": "Friday"},
            {"value": "5", "label": "Saturday"},
            {"value": "6", "label": "Sunday"},
        ]

        data_schema = vol.Schema({
            vol.Optional(
                CONF_WATERING_DAYS,
                default=["0", "2", "4", "6"],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=days_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                ),
            ),
            vol.Optional(
                CONF_WATERING_START_TIME,
                default=DEFAULT_START_TIME,
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_WATERING_END_TIME,
                default=DEFAULT_END_TIME,
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_MAX_DAILY_RUNTIME,
                default=DEFAULT_MAX_DAILY_RUNTIME,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=480,
                    step=5,
                    unit_of_measurement="minutes",
                    mode=selector.NumberSelectorMode.BOX,
                ),
            ),
            vol.Optional(
                CONF_CYCLE_SOAK_ENABLED,
                default=True,
            ): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="schedule",
            data_schema=data_schema,
        )

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure individual zone."""
        if user_input is not None:
            zone = self._zones[self._current_zone_index]
            zone_id = zone["id"]

            self._zones_config[zone_id] = {
                "name": zone.get("name", f"Zone {zone.get('zone_number', self._current_zone_index + 1)}"),
                "zone_type": user_input.get("zone_type", "cool_season_grass"),
                "soil_type": user_input.get("soil_type", "loam"),
                "slope": user_input.get("slope", "flat"),
                "sun_exposure": user_input.get("sun_exposure", "full_sun"),
                "nozzle_type": user_input.get("nozzle_type", "fixed_spray"),
                "enabled": user_input.get("enabled", True),
            }

            self._current_zone_index += 1

            if self._current_zone_index < len(self._zones):
                return await self.async_step_zone()
            else:
                return await self.async_step_moisture_sensors()

        zone = self._zones[self._current_zone_index]
        zone_name = zone.get("name", f"Zone {zone.get('zone_number', self._current_zone_index + 1)}")

        zone_type_options = [
            {"value": k, "label": v["name"]}
            for k, v in ZONE_TYPES.items()
        ]

        soil_type_options = [
            {"value": k, "label": v["name"]}
            for k, v in SOIL_TYPES.items()
        ]

        slope_options = [
            {"value": k, "label": v["name"]}
            for k, v in SLOPE_TYPES.items()
        ]

        sun_options = [
            {"value": k, "label": v["name"]}
            for k, v in SUN_EXPOSURE.items()
        ]

        nozzle_options = [
            {"value": k, "label": v["name"]}
            for k, v in NOZZLE_TYPES.items()
        ]

        data_schema = vol.Schema({
            vol.Optional("zone_type", default="cool_season_grass"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=zone_type_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional("soil_type", default="loam"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=soil_type_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional("slope", default="flat"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=slope_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional("sun_exposure", default="full_sun"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sun_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional("nozzle_type", default="fixed_spray"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=nozzle_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional("enabled", default=True): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="zone",
            data_schema=data_schema,
            description_placeholders={
                "zone_name": zone_name,
                "zone_number": str(self._current_zone_index + 1),
                "total_zones": str(len(self._zones)),
            },
        )

    async def async_step_moisture_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure moisture sensors for zones."""
        if user_input is not None:
            self._moisture_sensors = {}
            for zone in self._zones:
                zone_id = zone["id"]
                sensor_key = f"moisture_{zone_id}"
                if sensor_key in user_input and user_input[sensor_key]:
                    self._moisture_sensors[zone_id] = user_input[sensor_key]

            return self._create_entry()

        # Get available moisture sensors (Ecowitt and others)
        moisture_sensors = []
        for state in self.hass.states.async_all("sensor"):
            if any(keyword in state.entity_id.lower() for keyword in ["moisture", "soil", "humidity"]):
                moisture_sensors.append(state.entity_id)

        if not moisture_sensors:
            # No sensors found, skip this step
            self._moisture_sensors = {}
            return self._create_entry()

        # Build schema with optional sensor for each zone
        schema_dict = {}
        for zone in self._zones:
            zone_id = zone["id"]
            zone_name = zone.get("name", f"Zone {zone.get('zone_number', '?')}")

            schema_dict[vol.Optional(f"moisture_{zone_id}")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": "", "label": "None"}] + [
                        {"value": s, "label": s} for s in moisture_sensors
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            )

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="moisture_sensors",
            data_schema=data_schema,
            description_placeholders={
                "sensor_count": str(len(moisture_sensors)),
            },
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        data = {
            CONF_RACHIO_API_KEY: self._api_key,
            CONF_WEATHER_ENTITY: getattr(self, '_weather_entity', None),
            CONF_RAIN_SENSOR: getattr(self, '_rain_sensor', None),
            CONF_WATERING_DAYS: [int(d) for d in getattr(self, '_watering_days', [0, 2, 4, 6])],
            CONF_WATERING_START_TIME: getattr(self, '_start_time', DEFAULT_START_TIME),
            CONF_WATERING_END_TIME: getattr(self, '_end_time', DEFAULT_END_TIME),
            CONF_MAX_DAILY_RUNTIME: getattr(self, '_max_runtime', DEFAULT_MAX_DAILY_RUNTIME),
            CONF_CYCLE_SOAK_ENABLED: getattr(self, '_cycle_soak', True),
            CONF_ZONES: self._zones_config,
            CONF_MOISTURE_SENSORS: getattr(self, '_moisture_sensors', {}),
        }

        return self.async_create_entry(
            title=self._device_info.get("device_name", "Smart Irrigation AI"),
            data=data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SmartIrrigationOptionsFlow(config_entry)


class SmartIrrigationOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Irrigation AI."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        days_options = [
            {"value": "0", "label": "Monday"},
            {"value": "1", "label": "Tuesday"},
            {"value": "2", "label": "Wednesday"},
            {"value": "3", "label": "Thursday"},
            {"value": "4", "label": "Friday"},
            {"value": "5", "label": "Saturday"},
            {"value": "6", "label": "Sunday"},
        ]

        current_days = [str(d) for d in data.get(CONF_WATERING_DAYS, [0, 2, 4, 6])]

        data_schema = vol.Schema({
            vol.Optional(
                CONF_WATERING_DAYS,
                default=current_days,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=days_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                ),
            ),
            vol.Optional(
                CONF_WATERING_START_TIME,
                default=data.get(CONF_WATERING_START_TIME, DEFAULT_START_TIME),
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_WATERING_END_TIME,
                default=data.get(CONF_WATERING_END_TIME, DEFAULT_END_TIME),
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_MAX_DAILY_RUNTIME,
                default=data.get(CONF_MAX_DAILY_RUNTIME, DEFAULT_MAX_DAILY_RUNTIME),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=480,
                    step=5,
                    unit_of_measurement="minutes",
                    mode=selector.NumberSelectorMode.BOX,
                ),
            ),
            vol.Optional(
                CONF_CYCLE_SOAK_ENABLED,
                default=data.get(CONF_CYCLE_SOAK_ENABLED, True),
            ): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
