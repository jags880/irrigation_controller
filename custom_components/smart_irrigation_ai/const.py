"""Constants for Smart Irrigation AI integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "smart_irrigation_ai"
PLATFORMS: Final = ["sensor", "switch", "binary_sensor", "number", "select", "calendar"]

# Configuration keys
CONF_RACHIO_API_KEY: Final = "rachio_api_key"
CONF_WEATHER_ENTITY: Final = "weather_entity"
CONF_LOCATION_LAT: Final = "latitude"
CONF_LOCATION_LON: Final = "longitude"
CONF_MOISTURE_SENSORS: Final = "moisture_sensors"
CONF_RAIN_SENSOR: Final = "rain_sensor"
CONF_ZONES: Final = "zones"
CONF_WATERING_DAYS: Final = "watering_days"
CONF_WATERING_START_TIME: Final = "watering_start_time"
CONF_WATERING_END_TIME: Final = "watering_end_time"
CONF_MAX_DAILY_RUNTIME: Final = "max_daily_runtime"
CONF_CYCLE_SOAK_ENABLED: Final = "cycle_soak_enabled"

# Zone configuration
CONF_ZONE_ID: Final = "zone_id"
CONF_ZONE_NAME: Final = "zone_name"
CONF_ZONE_TYPE: Final = "zone_type"
CONF_SOIL_TYPE: Final = "soil_type"
CONF_SLOPE: Final = "slope"
CONF_SUN_EXPOSURE: Final = "sun_exposure"
CONF_NOZZLE_TYPE: Final = "nozzle_type"
CONF_MOISTURE_SENSOR: Final = "moisture_sensor"
CONF_ROOT_DEPTH: Final = "root_depth"
CONF_CROP_COEFFICIENT: Final = "crop_coefficient"

# Zone/vegetation types with crop coefficients
ZONE_TYPES: Final = {
    "cool_season_grass": {"name": "Cool Season Grass (Fescue, Bluegrass)", "kc": 0.80, "root_depth": 6},
    "warm_season_grass": {"name": "Warm Season Grass (Bermuda, St. Augustine)", "kc": 0.65, "root_depth": 8},
    "mixed_grass": {"name": "Mixed Grass", "kc": 0.72, "root_depth": 7},
    "shrubs": {"name": "Shrubs", "kc": 0.50, "root_depth": 18},
    "perennials": {"name": "Perennial Flowers", "kc": 0.60, "root_depth": 12},
    "annuals": {"name": "Annual Flowers", "kc": 0.70, "root_depth": 8},
    "trees": {"name": "Trees", "kc": 0.45, "root_depth": 36},
    "vegetables": {"name": "Vegetable Garden", "kc": 0.85, "root_depth": 12},
    "native_plants": {"name": "Native/Drought Tolerant", "kc": 0.35, "root_depth": 18},
    "groundcover": {"name": "Ground Cover", "kc": 0.55, "root_depth": 6},
    "new_sod": {"name": "New Sod (< 2 months)", "kc": 1.0, "root_depth": 2},
    "new_seed": {"name": "New Seed (< 3 months)", "kc": 1.1, "root_depth": 1},
}

# Soil types with infiltration rates (inches per hour)
SOIL_TYPES: Final = {
    "clay": {"name": "Clay", "infiltration_rate": 0.10, "water_holding_capacity": 0.20},
    "clay_loam": {"name": "Clay Loam", "infiltration_rate": 0.20, "water_holding_capacity": 0.18},
    "loam": {"name": "Loam", "infiltration_rate": 0.35, "water_holding_capacity": 0.17},
    "sandy_loam": {"name": "Sandy Loam", "infiltration_rate": 0.50, "water_holding_capacity": 0.12},
    "loamy_sand": {"name": "Loamy Sand", "infiltration_rate": 0.80, "water_holding_capacity": 0.10},
    "sand": {"name": "Sand", "infiltration_rate": 1.20, "water_holding_capacity": 0.08},
}

# Slope categories with runoff adjustments
SLOPE_TYPES: Final = {
    "flat": {"name": "Flat (0-3%)", "runoff_factor": 1.0},
    "slight": {"name": "Slight (3-6%)", "runoff_factor": 0.90},
    "moderate": {"name": "Moderate (6-9%)", "runoff_factor": 0.80},
    "steep": {"name": "Steep (9-12%)", "runoff_factor": 0.70},
    "very_steep": {"name": "Very Steep (>12%)", "runoff_factor": 0.60},
}

# Sun exposure with evaporation adjustments
SUN_EXPOSURE: Final = {
    "full_sun": {"name": "Full Sun (6+ hours)", "et_factor": 1.0},
    "partial_sun": {"name": "Partial Sun (4-6 hours)", "et_factor": 0.80},
    "partial_shade": {"name": "Partial Shade (2-4 hours)", "et_factor": 0.65},
    "full_shade": {"name": "Full Shade (<2 hours)", "et_factor": 0.50},
}

# Nozzle/sprinkler types with precipitation rates (inches per hour)
NOZZLE_TYPES: Final = {
    "fixed_spray": {"name": "Fixed Spray Heads", "precip_rate": 1.5},
    "rotary_nozzle": {"name": "Rotary Nozzles (MP Rotator)", "precip_rate": 0.5},
    "rotor": {"name": "Rotor Heads", "precip_rate": 0.4},
    "drip": {"name": "Drip Irrigation", "precip_rate": 0.2},
    "impact": {"name": "Impact Sprinklers", "precip_rate": 0.5},
    "bubbler": {"name": "Bubblers", "precip_rate": 1.0},
}

# Seasonal adjustment factors (Northern Hemisphere)
SEASONAL_FACTORS: Final = {
    1: 0.40,   # January
    2: 0.45,   # February
    3: 0.60,   # March
    4: 0.75,   # April
    5: 0.90,   # May
    6: 1.00,   # June
    7: 1.05,   # July
    8: 1.00,   # August
    9: 0.85,   # September
    10: 0.65,  # October
    11: 0.50,  # November
    12: 0.35,  # December
}

# AI Model thresholds
MOISTURE_THRESHOLD_DRY: Final = 30  # Below this = definitely water
MOISTURE_THRESHOLD_WET: Final = 70  # Above this = skip watering
MOISTURE_THRESHOLD_OPTIMAL: Final = 50  # Target moisture level

RAIN_THRESHOLD_LIGHT: Final = 0.1  # inches - slight adjustment
RAIN_THRESHOLD_MODERATE: Final = 0.25  # inches - reduce watering
RAIN_THRESHOLD_HEAVY: Final = 0.5  # inches - likely skip

WIND_THRESHOLD_HIGH: Final = 15  # mph - reduce efficiency
WIND_THRESHOLD_VERY_HIGH: Final = 25  # mph - may skip

TEMP_THRESHOLD_FREEZE: Final = 32  # °F - skip watering
TEMP_THRESHOLD_HOT: Final = 95  # °F - increase watering

# Default values
DEFAULT_MAX_DAILY_RUNTIME: Final = 180  # minutes
DEFAULT_WATERING_DAYS: Final = [0, 2, 4, 6]  # Mon, Wed, Fri, Sun
DEFAULT_START_TIME: Final = "05:00:00"
DEFAULT_END_TIME: Final = "08:00:00"

# Service names
SERVICE_RUN_ZONE: Final = "run_zone"
SERVICE_STOP_ALL: Final = "stop_all"
SERVICE_CALCULATE_SCHEDULE: Final = "calculate_schedule"
SERVICE_FORCE_RECALCULATE: Final = "force_recalculate"
SERVICE_SET_SEASONAL_ADJUSTMENT: Final = "set_seasonal_adjustment"
SERVICE_SKIP_NEXT_WATERING: Final = "skip_next_watering"
SERVICE_RAIN_DELAY: Final = "rain_delay"

# Update intervals
SCAN_INTERVAL_MINUTES: Final = 5
SCHEDULE_RECALC_HOURS: Final = 6

# Entity IDs
ENTITY_ID_PREFIX: Final = "smart_irrigation"

# Attributes
ATTR_NEXT_RUN: Final = "next_run"
ATTR_LAST_RUN: Final = "last_run"
ATTR_RECOMMENDED_DURATION: Final = "recommended_duration"
ATTR_MOISTURE_LEVEL: Final = "moisture_level"
ATTR_WATER_DEFICIT: Final = "water_deficit"
ATTR_ET_RATE: Final = "et_rate"
ATTR_ZONE_STATUS: Final = "zone_status"
ATTR_AI_CONFIDENCE: Final = "ai_confidence"
ATTR_SKIP_REASON: Final = "skip_reason"
ATTR_WEATHER_FACTOR: Final = "weather_factor"
ATTR_SEASONAL_FACTOR: Final = "seasonal_factor"
