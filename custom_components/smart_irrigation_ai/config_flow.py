"""Config flow for Smart Irrigation AI integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_WEATHER_ENTITY,
    CONF_MOISTURE_SENSORS,
    CONF_RAIN_SENSOR,
    CONF_WATERING_DAYS,
    CONF_SCHEDULE_MODE,
    CONF_SCHEDULE_TIME,
    CONF_SCHEDULE_SUN_EVENT,
    CONF_SUN_OFFSET,
    CONF_CYCLE_SOAK_ENABLED,
    CONF_ZONES,
    CONF_USE_HA_RACHIO,
    ZONE_TYPES,
    SOIL_TYPES,
    SLOPE_TYPES,
    SUN_EXPOSURE,
    NOZZLE_TYPES,
    DEFAULT_WATERING_DAYS,
    DEFAULT_SCHEDULE_MODE,
    DEFAULT_SCHEDULE_TIME,
    DEFAULT_SUN_OFFSET,
    SCHEDULE_MODE_START_AT,
    SCHEDULE_MODE_FINISH_BY,
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
)
from .rachio.ha_controller import HAZoneController

_LOGGER = logging.getLogger(__name__)


async def discover_rachio_zones(hass: HomeAssistant) -> dict[str, Any]:
    """Discover Rachio zones from Home Assistant integration."""
    controller = HAZoneController(hass)
    return await controller.async_discover_rachio_entities()


class SmartIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Irrigation AI."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._device_info: dict[str, Any] = {}
        self._zones: list[dict[str, Any]] = []
        self._zones_config: dict[str, dict[str, Any]] = {}
        self._current_zone_index = 0
        self._rain_sensors: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - discover Rachio zones."""
        errors: dict[str, str] = {}

        # Check if Rachio integration is available
        rachio_available = await self._check_rachio_integration()

        if not rachio_available:
            return self.async_abort(reason="rachio_not_found")

        # Discover existing Rachio entities
        _LOGGER.info("Discovering Rachio entities from Home Assistant...")
        discovery = await discover_rachio_zones(self.hass)
        self._zones = discovery.get("zones", [])
        self._device_info = discovery.get("device_info", {})
        self._rain_sensors = discovery.get("rain_sensors", [])

        _LOGGER.info(
            "Discovery results: %d zones, %d rain sensors, device: %s",
            len(self._zones),
            len(self._rain_sensors),
            self._device_info.get("name", "Unknown"),
        )

        if not self._zones:
            # Log all Rachio entities for debugging
            entity_reg = er.async_get(self.hass)
            rachio_entities = [
                e.entity_id for e in entity_reg.entities.values()
                if e.platform == "rachio"
            ]
            _LOGGER.error(
                "No Rachio zones found. Available Rachio entities: %s",
                rachio_entities,
            )
            return self.async_abort(reason="no_rachio_zones")

        # Set unique ID based on device
        device_id = self._device_info.get("id", "smart_irrigation_ai")
        await self.async_set_unique_id(f"smart_irrigation_{device_id}")
        self._abort_if_unique_id_configured()

        return await self.async_step_weather()

    async def _check_rachio_integration(self) -> bool:
        """Check if Rachio integration is set up."""
        entity_reg = er.async_get(self.hass)

        for entity in entity_reg.entities.values():
            if entity.platform == "rachio":
                return True
        return False

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

        # Get rain sensors (Rachio + external)
        rain_sensor_options = []

        # Add discovered Rachio rain sensors
        for sensor in self._rain_sensors:
            rain_sensor_options.append({
                "value": sensor["entity_id"],
                "label": f"{sensor['name']} (Rachio)",
            })

        # Add other rain/moisture binary sensors
        for state in self.hass.states.async_all("binary_sensor"):
            if "rain" in state.entity_id.lower():
                if state.entity_id not in [s["entity_id"] for s in self._rain_sensors]:
                    rain_sensor_options.append({
                        "value": state.entity_id,
                        "label": state.attributes.get("friendly_name", state.entity_id),
                    })

        data_schema = vol.Schema({
            vol.Optional(CONF_WEATHER_ENTITY): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": e, "label": e} for e in weather_entities],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(CONF_RAIN_SENSOR): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=rain_sensor_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ) if rain_sensor_options else vol.Optional(CONF_RAIN_SENSOR),
        })

        return self.async_show_form(
            step_id="weather",
            data_schema=data_schema,
            description_placeholders={
                "zone_count": str(len(self._zones)),
            },
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure watering schedule."""
        if user_input is not None:
            self._watering_days = user_input.get(CONF_WATERING_DAYS, ["0", "2", "4", "6"])
            self._schedule_mode = user_input.get(CONF_SCHEDULE_MODE, SCHEDULE_MODE_START_AT)

            # Handle time type selection
            time_type = user_input.get("time_type", "specific")
            if time_type == "specific":
                self._schedule_time = user_input.get(CONF_SCHEDULE_TIME, DEFAULT_SCHEDULE_TIME)
                self._schedule_sun_event = None
                self._sun_offset = 0
            else:
                self._schedule_time = None
                self._schedule_sun_event = user_input.get(CONF_SCHEDULE_SUN_EVENT, SUN_EVENT_SUNRISE)
                self._sun_offset = user_input.get(CONF_SUN_OFFSET, DEFAULT_SUN_OFFSET)

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

        schedule_mode_options = [
            {"value": SCHEDULE_MODE_START_AT, "label": "Start watering at"},
            {"value": SCHEDULE_MODE_FINISH_BY, "label": "Finish watering by"},
        ]

        time_type_options = [
            {"value": "specific", "label": "Specific time"},
            {"value": "sun", "label": "Based on sunrise/sunset"},
        ]

        sun_event_options = [
            {"value": SUN_EVENT_SUNRISE, "label": "Sunrise"},
            {"value": SUN_EVENT_SUNSET, "label": "Sunset"},
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
            vol.Required(
                CONF_SCHEDULE_MODE,
                default=SCHEDULE_MODE_START_AT,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=schedule_mode_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Required(
                "time_type",
                default="specific",
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=time_type_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                CONF_SCHEDULE_TIME,
                default=DEFAULT_SCHEDULE_TIME,
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_SCHEDULE_SUN_EVENT,
                default=SUN_EVENT_SUNRISE,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sun_event_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                CONF_SUN_OFFSET,
                default=0,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-120,
                    max=120,
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

            # Use entity_id for HA mode, zone id for API mode
            zone_key = zone.get("entity_id") or zone.get("id")

            self._zones_config[zone_key] = {
                "name": zone.get("name", f"Zone {zone.get('zone_number', self._current_zone_index + 1)}"),
                "entity_id": zone.get("entity_id"),
                "zone_id": zone.get("id") or zone.get("zone_id"),
                "zone_number": zone.get("zone_number", self._current_zone_index + 1),
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
            for zone_key in self._zones_config:
                sensor_key = f"moisture_{zone_key}"
                if sensor_key in user_input and user_input[sensor_key]:
                    self._moisture_sensors[zone_key] = user_input[sensor_key]

            return self._create_entry()

        # Get available moisture sensors (Ecowitt and others)
        moisture_sensors = []
        for state in self.hass.states.async_all("sensor"):
            entity_id = state.entity_id.lower()
            if any(keyword in entity_id for keyword in ["moisture", "soil", "humidity"]):
                # Skip weather-related humidity sensors
                if "weather" not in entity_id and "indoor" not in entity_id:
                    moisture_sensors.append({
                        "value": state.entity_id,
                        "label": state.attributes.get("friendly_name", state.entity_id),
                    })

        if not moisture_sensors:
            # No sensors found, skip this step
            self._moisture_sensors = {}
            return self._create_entry()

        # Build schema with optional sensor for each zone
        schema_dict = {}
        for zone_key, zone_config in self._zones_config.items():
            zone_name = zone_config.get("name", zone_key)

            options = [{"value": "", "label": "None (use AI estimates)"}] + moisture_sensors

            schema_dict[vol.Optional(f"moisture_{zone_key}")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
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
            CONF_USE_HA_RACHIO: True,  # Always use HA Rachio integration
            CONF_WEATHER_ENTITY: getattr(self, '_weather_entity', None),
            CONF_RAIN_SENSOR: getattr(self, '_rain_sensor', None),
            CONF_WATERING_DAYS: [int(d) for d in getattr(self, '_watering_days', ["0", "2", "4", "6"])],
            CONF_SCHEDULE_MODE: getattr(self, '_schedule_mode', SCHEDULE_MODE_START_AT),
            CONF_SCHEDULE_TIME: getattr(self, '_schedule_time', DEFAULT_SCHEDULE_TIME),
            CONF_SCHEDULE_SUN_EVENT: getattr(self, '_schedule_sun_event', None),
            CONF_SUN_OFFSET: getattr(self, '_sun_offset', DEFAULT_SUN_OFFSET),
            CONF_CYCLE_SOAK_ENABLED: getattr(self, '_cycle_soak', True),
            CONF_ZONES: self._zones_config,
            CONF_MOISTURE_SENSORS: getattr(self, '_moisture_sensors', {}),
        }

        title = self._device_info.get("name", "Smart Irrigation AI")

        return self.async_create_entry(
            title=title,
            data=data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SmartIrrigationOptionsFlow()


class SmartIrrigationOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Irrigation AI."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._schedule_settings: dict[str, Any] = {}
        self._zones_config: dict[str, dict[str, Any]] = {}
        self._zone_keys: list[str] = []
        self._current_zone_index: int = 0
        self._moisture_sensors: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow - schedule settings."""
        if user_input is not None:
            # Process the time type
            time_type = user_input.pop("time_type", "specific")
            if time_type == "specific":
                user_input[CONF_SCHEDULE_SUN_EVENT] = None
                user_input[CONF_SUN_OFFSET] = 0
            else:
                user_input[CONF_SCHEDULE_TIME] = None

            # Convert watering_days from strings back to integers
            if CONF_WATERING_DAYS in user_input:
                user_input[CONF_WATERING_DAYS] = [
                    int(d) for d in user_input[CONF_WATERING_DAYS]
                ]

            # Store schedule settings and move to zone configuration
            self._schedule_settings = user_input

            # Get zones and moisture sensors from config
            data = {**dict(self.config_entry.data), **dict(self.config_entry.options)}
            zones = data.get(CONF_ZONES, {})
            self._zones_config = dict(zones) if zones else {}
            self._zone_keys = list(self._zones_config.keys())
            self._current_zone_index = 0

            # Preserve moisture sensor settings
            moisture_sensors = data.get(CONF_MOISTURE_SENSORS, {})
            self._moisture_sensors = dict(moisture_sensors) if moisture_sensors else {}

            if self._zone_keys:
                return await self.async_step_zone()
            else:
                # No zones to configure, save and exit
                return self._save_options()

        # Merge data with options to get current effective config
        # Use dict() to ensure we have mutable dicts, not MappingProxyType
        data = {**dict(self.config_entry.data), **dict(self.config_entry.options)}

        days_options = [
            {"value": "0", "label": "Monday"},
            {"value": "1", "label": "Tuesday"},
            {"value": "2", "label": "Wednesday"},
            {"value": "3", "label": "Thursday"},
            {"value": "4", "label": "Friday"},
            {"value": "5", "label": "Saturday"},
            {"value": "6", "label": "Sunday"},
        ]

        schedule_mode_options = [
            {"value": SCHEDULE_MODE_START_AT, "label": "Start watering at"},
            {"value": SCHEDULE_MODE_FINISH_BY, "label": "Finish watering by"},
        ]

        time_type_options = [
            {"value": "specific", "label": "Specific time"},
            {"value": "sun", "label": "Based on sunrise/sunset"},
        ]

        sun_event_options = [
            {"value": SUN_EVENT_SUNRISE, "label": "Sunrise"},
            {"value": SUN_EVENT_SUNSET, "label": "Sunset"},
        ]

        # Safely get watering days with fallback for None values
        watering_days = data.get(CONF_WATERING_DAYS)
        if not watering_days:
            watering_days = DEFAULT_WATERING_DAYS
        current_days = [str(d) for d in watering_days]

        current_time_type = "sun" if data.get(CONF_SCHEDULE_SUN_EVENT) else "specific"

        # Safely get sun_offset with fallback for None
        sun_offset = data.get(CONF_SUN_OFFSET)
        if sun_offset is None:
            sun_offset = DEFAULT_SUN_OFFSET

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
            vol.Required(
                CONF_SCHEDULE_MODE,
                default=data.get(CONF_SCHEDULE_MODE) or SCHEDULE_MODE_START_AT,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=schedule_mode_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Required(
                "time_type",
                default=current_time_type,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=time_type_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                CONF_SCHEDULE_TIME,
                default=data.get(CONF_SCHEDULE_TIME) or DEFAULT_SCHEDULE_TIME,
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_SCHEDULE_SUN_EVENT,
                default=data.get(CONF_SCHEDULE_SUN_EVENT) or SUN_EVENT_SUNRISE,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sun_event_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                CONF_SUN_OFFSET,
                default=sun_offset,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-120,
                    max=120,
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

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure individual zone."""
        if user_input is not None:
            zone_key = self._zone_keys[self._current_zone_index]
            current_zone = self._zones_config.get(zone_key, {})

            # Update zone config with user input while preserving other fields
            current_zone.update({
                "zone_type": user_input.get("zone_type", "cool_season_grass"),
                "soil_type": user_input.get("soil_type", "loam"),
                "slope": user_input.get("slope", "flat"),
                "sun_exposure": user_input.get("sun_exposure", "full_sun"),
                "nozzle_type": user_input.get("nozzle_type", "fixed_spray"),
                "enabled": user_input.get("enabled", True),
            })
            self._zones_config[zone_key] = current_zone

            self._current_zone_index += 1

            if self._current_zone_index < len(self._zone_keys):
                return await self.async_step_zone()
            else:
                return await self.async_step_moisture_sensors()

        zone_key = self._zone_keys[self._current_zone_index]
        zone_config = self._zones_config.get(zone_key, {})
        zone_name = zone_config.get("name", f"Zone {self._current_zone_index + 1}")

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
            vol.Optional(
                "zone_type",
                default=zone_config.get("zone_type", "cool_season_grass"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=zone_type_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                "soil_type",
                default=zone_config.get("soil_type", "loam"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=soil_type_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                "slope",
                default=zone_config.get("slope", "flat"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=slope_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                "sun_exposure",
                default=zone_config.get("sun_exposure", "full_sun"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sun_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                "nozzle_type",
                default=zone_config.get("nozzle_type", "fixed_spray"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=nozzle_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional("enabled", default=zone_config.get("enabled", True)): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="zone",
            data_schema=data_schema,
            description_placeholders={
                "zone_name": zone_name,
                "zone_number": str(self._current_zone_index + 1),
                "total_zones": str(len(self._zone_keys)),
            },
        )

    async def async_step_moisture_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure moisture sensors for zones."""
        if user_input is not None:
            self._moisture_sensors = {}
            for zone_key in self._zones_config:
                sensor_key = f"moisture_{zone_key}"
                if sensor_key in user_input and user_input[sensor_key]:
                    self._moisture_sensors[zone_key] = user_input[sensor_key]

            return self._save_options()

        # Get available moisture sensors (Ecowitt and others)
        moisture_sensors = []
        for state in self.hass.states.async_all("sensor"):
            entity_id = state.entity_id.lower()
            if any(keyword in entity_id for keyword in ["moisture", "soil", "humidity"]):
                # Skip weather-related humidity sensors
                if "weather" not in entity_id and "indoor" not in entity_id:
                    moisture_sensors.append({
                        "value": state.entity_id,
                        "label": state.attributes.get("friendly_name", state.entity_id),
                    })

        if not moisture_sensors:
            # No sensors found, skip this step but allow clearing existing mappings
            self._moisture_sensors = {}
            return self._save_options()

        # Build schema with optional sensor for each zone
        schema_dict = {}
        for zone_key, zone_config in self._zones_config.items():
            zone_name = zone_config.get("name", zone_key)
            current_sensor = self._moisture_sensors.get(zone_key, "")

            options = [{"value": "", "label": "None (use AI estimates)"}] + moisture_sensors

            schema_dict[vol.Optional(f"moisture_{zone_key}", default=current_sensor)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
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

    def _save_options(self) -> FlowResult:
        """Save all options including zones and moisture sensors."""
        # Combine schedule settings with zone config and moisture sensors
        options_data = {
            **self._schedule_settings,
            CONF_ZONES: self._zones_config,
            CONF_MOISTURE_SENSORS: self._moisture_sensors,
        }
        return self.async_create_entry(title="", data=options_data)
