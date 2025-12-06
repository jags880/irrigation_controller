"""AI Irrigation Model - Core decision engine for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, time
from typing import Any

from homeassistant.core import HomeAssistant

from .evapotranspiration import EvapotranspirationCalculator, ETTracker
from .weather_processor import WeatherProcessor
from .soil_analyzer import SoilAnalyzer, RainSensorProcessor
from .zone_optimizer import ZoneOptimizer, ZoneConfig, WateringRecommendation
from ..const import (
    ZONE_TYPES,
    SOIL_TYPES,
    CONF_ZONES,
    CONF_ZONE_TYPE,
    CONF_SOIL_TYPE,
    CONF_SLOPE,
    CONF_SUN_EXPOSURE,
    CONF_NOZZLE_TYPE,
    CONF_ROOT_DEPTH,
    CONF_LOCATION_LAT,
    CONF_LOCATION_LON,
    MOISTURE_THRESHOLD_DRY,
    MOISTURE_THRESHOLD_WET,
)

_LOGGER = logging.getLogger(__name__)


class IrrigationAIModel:
    """AI-powered irrigation decision engine.

    This model combines multiple data sources and algorithms to make
    intelligent irrigation decisions:

    1. Evapotranspiration (ET) calculation using Penman-Monteith
    2. Weather analysis (current + forecast)
    3. Soil moisture sensor data
    4. Rain sensor integration
    5. Zone-specific characteristics
    6. Seasonal adjustments
    7. Historical learning (future enhancement)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        zones_config: dict[str, dict[str, Any]],
    ) -> None:
        """Initialize the AI model.

        Args:
            hass: Home Assistant instance
            config: Integration configuration
            zones_config: Zone-specific configuration
        """
        self.hass = hass
        self.config = config
        self.zones_config = zones_config

        # Get location
        self.latitude = config.get(CONF_LOCATION_LAT) or hass.config.latitude
        self.longitude = config.get(CONF_LOCATION_LON) or hass.config.longitude
        self.elevation = hass.config.elevation or 0

        # Initialize components
        self.et_calculator = EvapotranspirationCalculator(
            latitude=self.latitude,
            elevation=self.elevation,
        )

        self.weather_processor = WeatherProcessor()
        self.soil_analyzer = SoilAnalyzer()
        self.rain_processor = RainSensorProcessor()

        # Initialize zone configs and ET trackers
        self._zone_configs: dict[str, ZoneConfig] = {}
        self._et_trackers: dict[str, ETTracker] = {}
        self._initialize_zones()

        # Initialize optimizer
        self.optimizer = ZoneOptimizer(
            zones=self._zone_configs,
            max_daily_runtime=config.get("max_daily_runtime", 180),
            watering_window_start=self._parse_time(config.get("watering_start_time", "05:00:00")),
            watering_window_end=self._parse_time(config.get("watering_end_time", "09:00:00")),
        )

        # Cache for recommendations
        self._last_recommendations: dict[str, WateringRecommendation] = {}
        self._last_calculation: datetime | None = None

    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        try:
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
        except (ValueError, IndexError):
            return time(5, 0)  # Default

    def _initialize_zones(self) -> None:
        """Initialize zone configurations and trackers."""
        for zone_id, zone_data in self.zones_config.items():
            zone_type = zone_data.get(CONF_ZONE_TYPE, "cool_season_grass")
            soil_type = zone_data.get(CONF_SOIL_TYPE, "loam")
            root_depth = zone_data.get(CONF_ROOT_DEPTH) or ZONE_TYPES.get(zone_type, {}).get("root_depth", 6)

            # Create zone config
            self._zone_configs[zone_id] = ZoneConfig(
                zone_id=zone_id,
                name=zone_data.get("name", f"Zone {zone_id}"),
                zone_type=zone_type,
                soil_type=soil_type,
                slope=zone_data.get(CONF_SLOPE, "flat"),
                sun_exposure=zone_data.get(CONF_SUN_EXPOSURE, "full_sun"),
                nozzle_type=zone_data.get(CONF_NOZZLE_TYPE, "fixed_spray"),
                root_depth=root_depth,
                area_sqft=zone_data.get("area_sqft", 1000),
                efficiency=zone_data.get("efficiency", 0.80),
                enabled=zone_data.get("enabled", True),
            )

            # Create ET tracker
            soil_info = SOIL_TYPES.get(soil_type, SOIL_TYPES["loam"])
            self._et_trackers[zone_id] = ETTracker(
                et_calculator=self.et_calculator,
                root_zone_depth_inches=root_depth,
                soil_water_capacity=soil_info.get("water_holding_capacity", 0.17),
                allowed_depletion=0.50,
            )

            # Configure soil analyzer
            self.soil_analyzer.configure_zone(
                zone_id=zone_id,
                soil_type=soil_type,
            )

    async def async_update_inputs(
        self,
        weather_data: dict[str, Any],
        moisture_data: dict[str, Any],
        rain_sensor_data: dict[str, Any],
    ) -> None:
        """Update all input data sources.

        Args:
            weather_data: Current weather and forecast data
            moisture_data: Soil moisture sensor readings
            rain_sensor_data: Rain sensor status
        """
        # Update weather
        self.weather_processor.update(
            current_weather=weather_data,
            forecast=weather_data.get("forecast", []),
        )

        # Update moisture
        self.soil_analyzer.update_all_moisture(moisture_data)

        # Update rain sensor
        self.rain_processor.update(
            tripped=rain_sensor_data.get("tripped", False),
            external_rain_rate=rain_sensor_data.get("external", {}).get("value"),
            rain_delay_expires=rain_sensor_data.get("rain_delay_expires"),
        )

        # Update ET trackers with daily ET calculation
        await self._update_et_trackers()

    async def _update_et_trackers(self) -> None:
        """Update ET trackers with current conditions."""
        try:
            # Get weather factors for ET calculation
            et_factors = self.weather_processor.get_et_factors()

            # Calculate reference ET
            today = date.today()
            temp_c = et_factors.get("temperature_c", 20)

            # Use simple Hargreaves method with estimated min/max
            # In production, you'd want actual min/max from weather history
            temp_range = 12  # Typical daily range
            temp_min = temp_c - temp_range / 2
            temp_max = temp_c + temp_range / 2

            et0_mm = self.et_calculator.calculate_et0_simple(
                date_val=today,
                temp_mean_c=temp_c,
                temp_min_c=temp_min,
                temp_max_c=temp_max,
            )

            et0_inches = self.et_calculator.mm_to_inches(et0_mm)

            # Apply solar factor from weather conditions
            et0_inches *= et_factors.get("solar_factor", 0.6)

            # Update each zone's ET tracker
            precipitation = self.weather_processor.get_precipitation_last_24h()

            for zone_id, tracker in self._et_trackers.items():
                zone_config = self._zone_configs.get(zone_id)
                if not zone_config:
                    continue

                # Calculate crop ET for this zone
                etc = self.et_calculator.calculate_etc(
                    et0_inches,
                    zone_config.crop_coefficient * zone_config.et_factor,
                )

                # Add to tracker (daily, so divide by update frequency)
                # Assuming updates every 6 hours = 4 times per day
                hourly_et = etc / 24
                tracker.add_et(hourly_et * 6)  # 6-hour increment

                # Add precipitation if any
                if precipitation > 0:
                    tracker.add_precipitation(precipitation / 4)  # Spread over day

            _LOGGER.debug("Updated ET trackers: ET0=%.3f inches/day", et0_inches)

        except Exception as err:
            _LOGGER.error("Error updating ET trackers: %s", err)

    async def async_get_recommendation(self, zone_id: str) -> WateringRecommendation:
        """Get irrigation recommendation for a specific zone.

        Args:
            zone_id: Zone identifier

        Returns:
            WateringRecommendation for the zone
        """
        zone_config = self._zone_configs.get(zone_id)
        if not zone_config:
            return WateringRecommendation(
                zone_id=zone_id,
                zone_name="Unknown",
                should_water=False,
                duration_minutes=0,
                water_amount_inches=0,
                confidence=0,
                priority=99,
                skip_reason="Zone not configured",
            )

        # Check for skip conditions
        should_skip, skip_reason = await self._check_skip_conditions(zone_id)
        if should_skip:
            return WateringRecommendation(
                zone_id=zone_id,
                zone_name=zone_config.name,
                should_water=False,
                duration_minutes=0,
                water_amount_inches=0,
                confidence=0.9,
                priority=99,
                skip_reason=skip_reason,
            )

        # Get all factors
        factors = await self._calculate_factors(zone_id)

        # Determine if watering is needed
        needs_water, water_amount = await self._calculate_water_need(zone_id, factors)

        if not needs_water or water_amount <= 0.01:
            return WateringRecommendation(
                zone_id=zone_id,
                zone_name=zone_config.name,
                should_water=False,
                duration_minutes=0,
                water_amount_inches=0,
                confidence=factors.get("confidence", 0.7),
                priority=99,
                factors=factors,
                skip_reason="Water not needed",
            )

        # Calculate duration
        duration = self.optimizer.calculate_base_duration(zone_config, water_amount)

        # Calculate priority
        soil_analysis = self.soil_analyzer.get_zone_analysis(zone_id)
        priorities = self.optimizer.prioritize_zones({zone_id: soil_analysis})
        priority = priorities.get(zone_id, 5)

        return WateringRecommendation(
            zone_id=zone_id,
            zone_name=zone_config.name,
            should_water=True,
            duration_minutes=duration,
            water_amount_inches=water_amount,
            confidence=factors.get("confidence", 0.7),
            priority=priority,
            factors=factors,
        )

    async def _check_skip_conditions(self, zone_id: str) -> tuple[bool, str]:
        """Check if watering should be skipped entirely.

        Returns:
            Tuple of (should_skip, reason)
        """
        # Check weather conditions
        weather_skip, weather_reason = self.weather_processor.should_skip_watering()
        if weather_skip:
            return True, weather_reason

        # Check rain sensor
        rain_skip, rain_reason = self.rain_processor.should_skip_watering()
        if rain_skip:
            return True, rain_reason

        # Check soil moisture
        moisture = self.soil_analyzer.get_moisture(zone_id)
        if moisture is not None and moisture > MOISTURE_THRESHOLD_WET:
            return True, f"Soil moisture high ({moisture:.0f}%)"

        return False, ""

    async def _calculate_factors(self, zone_id: str) -> dict[str, Any]:
        """Calculate all adjustment factors for a zone."""
        zone_config = self._zone_configs.get(zone_id)
        if not zone_config:
            return {}

        # Get individual factors
        weather_factor = self.weather_processor.get_weather_factor()
        rain_factor = self.rain_processor.get_rain_factor()
        moisture_factor = self.soil_analyzer.get_watering_factor(zone_id)
        seasonal_factor = self.optimizer.get_seasonal_factor()

        # Soil analysis
        soil_analysis = self.soil_analyzer.get_zone_analysis(zone_id)

        # ET tracker status
        et_tracker = self._et_trackers.get(zone_id)
        et_status = et_tracker.get_status() if et_tracker else {}

        # Calculate combined factor
        combined_factor = weather_factor * rain_factor * moisture_factor * seasonal_factor

        # Calculate confidence based on data availability
        confidence = 0.5  # Base confidence

        # Increase confidence if we have sensor data
        if self.soil_analyzer.get_moisture(zone_id) is not None:
            confidence += 0.2

        # Increase if weather data is fresh
        weather_status = self.weather_processor.get_status()
        if weather_status.get("last_update"):
            confidence += 0.15

        # Increase if ET tracking is active
        if et_status.get("cumulative_et", 0) > 0:
            confidence += 0.15

        confidence = min(0.95, confidence)

        return {
            "weather_factor": round(weather_factor, 2),
            "rain_factor": round(rain_factor, 2),
            "moisture_factor": round(moisture_factor, 2),
            "seasonal_factor": round(seasonal_factor, 2),
            "combined_factor": round(combined_factor, 2),
            "confidence": round(confidence, 2),
            "crop_coefficient": zone_config.crop_coefficient,
            "et_factor": zone_config.et_factor,
            "soil_analysis": soil_analysis,
            "et_status": et_status,
            "weather": {
                "temperature": self.weather_processor.current_temperature,
                "humidity": self.weather_processor.current_humidity,
                "condition": self.weather_processor.current_condition,
                "precip_24h": self.weather_processor.get_precipitation_last_24h(),
                "precip_forecast": self.weather_processor.get_precipitation_next_24h(),
            },
            "rain_sensor": self.rain_processor.get_status(),
        }

    async def _calculate_water_need(
        self, zone_id: str, factors: dict[str, Any]
    ) -> tuple[bool, float]:
        """Calculate water need for a zone.

        Returns:
            Tuple of (needs_water, water_amount_inches)
        """
        zone_config = self._zone_configs.get(zone_id)
        et_tracker = self._et_trackers.get(zone_id)

        if not zone_config:
            return False, 0

        # Method 1: Use ET tracker if available
        if et_tracker and et_tracker.needs_irrigation:
            water_needed = et_tracker.irrigation_needed_inches
            water_needed *= factors.get("combined_factor", 1.0)
            return True, max(0, water_needed)

        # Method 2: Use soil moisture if available
        moisture = self.soil_analyzer.get_moisture(zone_id)
        if moisture is not None:
            needs, urgency = self.soil_analyzer.needs_water(zone_id)
            if needs:
                # Estimate water based on deficit
                deficit_pct = self.soil_analyzer.calculate_water_deficit(zone_id)
                base_water = zone_config.root_depth * zone_config.water_holding_capacity * (deficit_pct / 100)
                water_needed = base_water * factors.get("combined_factor", 1.0)
                return True, max(0, water_needed)
            return False, 0

        # Method 3: Fall back to schedule-based with factors
        # Default to ~0.5" per watering, adjusted by factors
        base_water = 0.5
        water_needed = base_water * factors.get("combined_factor", 1.0)

        # Only water if combined factor suggests it
        if factors.get("combined_factor", 1.0) < 0.3:
            return False, 0

        return True, water_needed

    async def async_get_all_recommendations(self) -> dict[str, WateringRecommendation]:
        """Get recommendations for all zones.

        Returns:
            Dict of zone_id -> WateringRecommendation
        """
        recommendations = {}

        for zone_id in self._zone_configs:
            rec = await self.async_get_recommendation(zone_id)
            recommendations[zone_id] = rec
            self._last_recommendations[zone_id] = rec

        self._last_calculation = datetime.now()

        return recommendations

    async def async_get_recommended_duration(self, zone_id: str) -> int:
        """Get recommended duration for a zone in minutes.

        Args:
            zone_id: Zone identifier

        Returns:
            Duration in minutes
        """
        # Check cache first
        if zone_id in self._last_recommendations:
            rec = self._last_recommendations[zone_id]
            if rec.should_water:
                return rec.duration_minutes

        # Calculate fresh
        rec = await self.async_get_recommendation(zone_id)
        return rec.duration_minutes if rec.should_water else 0

    async def async_recalculate_all_zones(self) -> None:
        """Force recalculation of all zones."""
        self._last_recommendations.clear()
        await self.async_get_all_recommendations()

    async def async_get_optimized_schedule(self) -> list[dict[str, Any]]:
        """Get optimized watering schedule.

        Returns:
            Optimized schedule as list of zone operations
        """
        recommendations = await self.async_get_all_recommendations()

        # Get zone analyses for prioritization
        zone_analyses = self.soil_analyzer.get_all_zones_analysis()

        # Prioritize zones
        priorities = self.optimizer.prioritize_zones(zone_analyses)

        # Update recommendations with priorities
        rec_list = []
        for zone_id, rec in recommendations.items():
            rec.priority = priorities.get(zone_id, 99)
            rec_list.append(rec)

        # Optimize schedule
        schedule = self.optimizer.optimize_schedule(rec_list)

        return schedule

    def add_zone(self, zone_id: str, zone_data: dict[str, Any]) -> None:
        """Add or update a zone configuration."""
        self.zones_config[zone_id] = zone_data
        self._initialize_zones()

    def get_zone_config(self, zone_id: str) -> ZoneConfig | None:
        """Get zone configuration."""
        return self._zone_configs.get(zone_id)

    def get_model_status(self) -> dict[str, Any]:
        """Get overall model status."""
        return {
            "zones_configured": len(self._zone_configs),
            "last_calculation": self._last_calculation.isoformat() if self._last_calculation else None,
            "location": {"lat": self.latitude, "lon": self.longitude, "elevation": self.elevation},
            "weather_status": self.weather_processor.get_status(),
            "rain_status": self.rain_processor.get_status(),
            "zones_needing_water": sum(
                1 for r in self._last_recommendations.values() if r.should_water
            ),
        }
