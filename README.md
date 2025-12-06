# Smart Irrigation AI for Home Assistant

An AI-powered irrigation controller integration for Home Assistant that replaces the scheduling capabilities of your Rachio controller with intelligent, data-driven watering decisions.

## Features

### AI-Powered Decision Making
- **Evapotranspiration (ET) Calculation**: Uses the FAO Penman-Monteith equation to calculate actual water loss from your landscape
- **Weather Integration**: Adjusts watering based on current conditions and forecasts from your local weather station
- **Soil Moisture Sensors**: Integrates with Ecowitt and other soil moisture sensors for real-time data
- **Rain Sensor Integration**: Uses your Rachio's rain sensor as intelligent input (not just on/off)
- **Seasonal Adjustments**: Automatically adjusts watering based on time of year
- **Zone-Specific Optimization**: Each zone is configured with its unique characteristics

### Smart Scheduling
- **Replaces Rachio Scheduling**: Takes full control of when and how long to water
- **Dynamic Duration**: Calculates optimal watering time based on current conditions
- **Cycle & Soak**: Automatically splits watering to prevent runoff on slopes
- **Priority-Based**: Waters most critical zones first when time is limited
- **Weather Skip**: Intelligently skips watering when rain is detected or forecasted

### Zone Configuration
Configure each zone with:
- **Vegetation Type**: Cool/warm season grass, shrubs, flowers, vegetables, trees, etc.
- **Soil Type**: Clay, loam, sand, and variations
- **Slope**: Flat to very steep with automatic runoff prevention
- **Sun Exposure**: Full sun to full shade
- **Sprinkler Type**: Fixed spray, rotors, drip, MP rotators, etc.

### Home Assistant Integration
- Full configuration flow UI
- Sensors for moisture, recommendations, weather factors
- Switches for zone control
- Calendar entity for schedule visualization
- Custom Lovelace card
- Services for manual control

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Add"
7. Search for "Smart Irrigation AI" and install
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/smart_irrigation_ai` folder to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant

## Configuration

### Prerequisites

1. **Rachio Controller**: You need a Rachio irrigation controller
2. **Home Assistant Rachio Integration** (Recommended): Set up the official [Rachio integration](https://www.home-assistant.io/integrations/rachio/) first
3. **OR Rachio API Key**: If not using the HA integration, get your API key from https://app.rach.io/account/settings
4. **Weather Entity**: A weather integration (e.g., OpenWeatherMap, Home Assistant Weather)
5. **Optional**: Soil moisture sensors (Ecowitt recommended)

### Two Integration Modes

#### Mode 1: Using Home Assistant Rachio Integration (Recommended)

If you already have the Rachio integration set up in Home Assistant:
- **Automatic zone discovery** from existing Rachio entities
- **No duplicate API calls** - uses HA services to control zones
- **Leverages existing rain sensor** entities
- Works with your existing Rachio entities

#### Mode 2: Direct Rachio API

If you don't have the Rachio HA integration:
- Connect directly using your Rachio API key
- Manages API calls independently
- Full feature set available

### Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Smart Irrigation AI"
3. Choose integration mode:
   - If Rachio integration detected: Choose "Use Home Assistant Rachio Integration" (recommended)
   - Otherwise: Enter your Rachio API key
4. Select your weather entity and optional rain sensor
5. Configure your watering schedule (days, time window)
6. Configure each zone's characteristics (vegetation, soil, slope, sun, sprinkler type)
7. Optionally assign moisture sensors to zones

## Entities Created

### Sensors
| Entity | Description |
|--------|-------------|
| `sensor.smart_irrigation_status` | Overall system status |
| `sensor.smart_irrigation_next_run` | Next scheduled watering time |
| `sensor.smart_irrigation_weather_factor` | Current weather adjustment (0-150%) |
| `sensor.smart_irrigation_seasonal_factor` | Seasonal adjustment factor |
| `sensor.smart_irrigation_water_usage` | Estimated water usage (gallons) |
| `sensor.smart_irrigation_zone_X_moisture` | Zone soil moisture (if sensor configured) |
| `sensor.smart_irrigation_zone_X_recommendation` | AI recommendation for zone |
| `sensor.smart_irrigation_zone_X_duration` | Recommended watering duration |
| `sensor.smart_irrigation_zone_X_deficit` | Water deficit percentage |

### Binary Sensors
| Entity | Description |
|--------|-------------|
| `binary_sensor.smart_irrigation_running` | Is irrigation currently running |
| `binary_sensor.smart_irrigation_rain_detected` | Rain sensor triggered |
| `binary_sensor.smart_irrigation_watering_needed` | Any zone needs water |
| `binary_sensor.smart_irrigation_weather_skip` | Weather causing skip |
| `binary_sensor.smart_irrigation_zone_X_needs_water` | Zone needs water |
| `binary_sensor.smart_irrigation_zone_X_running` | Zone currently running |

### Switches
| Entity | Description |
|--------|-------------|
| `switch.smart_irrigation_scheduler` | Enable/disable automatic scheduling |
| `switch.smart_irrigation_rain_delay` | Toggle rain delay |
| `switch.smart_irrigation_zone_X` | Manual zone control |

### Number Entities
| Entity | Description |
|--------|-------------|
| `number.smart_irrigation_max_runtime` | Maximum daily runtime (minutes) |
| `number.smart_irrigation_rain_delay_hours` | Rain delay duration |
| `number.smart_irrigation_seasonal_adjustment` | Manual seasonal adjustment (%) |
| `number.smart_irrigation_zone_X_adjustment` | Zone duration adjustment (%) |

### Select Entities
| Entity | Description |
|--------|-------------|
| `select.smart_irrigation_watering_mode` | Watering mode (auto/eco/aggressive) |
| `select.smart_irrigation_zone_X_type` | Zone vegetation type |
| `select.smart_irrigation_zone_X_soil` | Zone soil type |
| `select.smart_irrigation_zone_X_sun` | Zone sun exposure |
| `select.smart_irrigation_zone_X_slope` | Zone slope |
| `select.smart_irrigation_zone_X_nozzle` | Sprinkler type |

### Calendar
| Entity | Description |
|--------|-------------|
| `calendar.smart_irrigation_schedule` | Irrigation schedule calendar |

## Services

### `smart_irrigation_ai.run_zone`
Start a specific zone.
```yaml
service: smart_irrigation_ai.run_zone
data:
  zone_id: "zone_123"
  duration: 15  # Optional, uses AI recommendation if not specified
```

### `smart_irrigation_ai.stop_all`
Stop all running zones.
```yaml
service: smart_irrigation_ai.stop_all
```

### `smart_irrigation_ai.calculate_schedule`
Recalculate the irrigation schedule.
```yaml
service: smart_irrigation_ai.calculate_schedule
```

### `smart_irrigation_ai.force_recalculate`
Force complete recalculation of all zones.
```yaml
service: smart_irrigation_ai.force_recalculate
```

### `smart_irrigation_ai.skip_next_watering`
Skip the next scheduled watering.
```yaml
service: smart_irrigation_ai.skip_next_watering
data:
  zone_id: "zone_123"  # Optional, skips all if not specified
```

### `smart_irrigation_ai.rain_delay`
Set a rain delay.
```yaml
service: smart_irrigation_ai.rain_delay
data:
  hours: 24
```

## How the AI Works

### 1. Evapotranspiration (ET) Calculation
The system uses the FAO Penman-Monteith equation to calculate how much water your plants are losing:

- **Temperature**: Higher temps = more water loss
- **Humidity**: Lower humidity = more water loss
- **Wind**: More wind = more water loss
- **Solar radiation**: More sun = more water loss

### 2. Crop Coefficients
Each vegetation type has a crop coefficient (Kc) that adjusts the base ET:

| Vegetation | Kc | Notes |
|------------|-----|-------|
| New seed | 1.1 | Needs extra water |
| New sod | 1.0 | Establishing roots |
| Cool season grass | 0.80 | Fescue, bluegrass |
| Warm season grass | 0.65 | Bermuda, St. Augustine |
| Vegetables | 0.85 | High water need |
| Annuals | 0.70 | Flowers |
| Shrubs | 0.50 | Established |
| Native plants | 0.35 | Drought tolerant |

### 3. Weather Adjustments
Real-time weather data adjusts watering:

- **Rain detected**: Reduce or skip
- **Rain forecasted**: Reduce proportionally
- **High temperature**: Increase watering
- **High wind**: Reduce (poor efficiency)
- **High humidity**: Reduce (less ET)
- **Freezing**: Skip entirely

### 4. Soil Moisture Integration
When moisture sensors are configured:

- Water when moisture drops below threshold
- Skip when moisture is adequate
- Calculate exact amount needed to reach field capacity
- Track depletion trends

### 5. Cycle & Soak
Prevents runoff by splitting watering into cycles:

- Calculates based on soil infiltration rate
- Adjusts for slope
- Allows soil to absorb between cycles

## Example Automations

### Notify When Watering Starts
```yaml
automation:
  - alias: "Irrigation Started Notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.smart_irrigation_running
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Irrigation Started"
          message: >
            Smart Irrigation is running.
            Estimated duration: {{ state_attr('sensor.smart_irrigation_status', 'total_runtime_minutes') }} minutes
```

### Auto Rain Delay from Weather
```yaml
automation:
  - alias: "Rain Delay When Raining"
    trigger:
      - platform: state
        entity_id: weather.home
        attribute: condition
        to: "rainy"
    action:
      - service: smart_irrigation_ai.rain_delay
        data:
          hours: 24
```

### Weekly Summary
```yaml
automation:
  - alias: "Weekly Irrigation Summary"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - service: notify.mobile_app
        data:
          title: "Weekly Irrigation Summary"
          message: >
            Last week's water usage: {{ states('sensor.smart_irrigation_water_usage') }} gallons
```

## Custom Lovelace Card

Add the custom card to your Lovelace resources:

```yaml
resources:
  - url: /local/smart-irrigation-card.js
    type: module
```

Then add the card to your dashboard:

```yaml
type: custom:smart-irrigation-card
entity: sensor.smart_irrigation_status
weather_entity: weather.home
weather_factor_entity: sensor.smart_irrigation_weather_factor
seasonal_factor_entity: sensor.smart_irrigation_seasonal_factor
zones:
  - entity: switch.smart_irrigation_zone_1
    name: Front Lawn
    moisture_entity: sensor.smart_irrigation_zone_1_moisture
    recommendation_entity: sensor.smart_irrigation_zone_1_recommendation
```

## Troubleshooting

### Integration won't connect
- Verify your Rachio API key at https://app.rach.io
- Check your internet connection
- Ensure Rachio servers are operational

### Zones not watering
- Check if scheduler is enabled
- Verify rain delay is not active
- Check weather skip status
- Review zone recommendations in Developer Tools

### Moisture sensors not updating
- Verify sensor entity IDs in configuration
- Check sensor battery levels
- Ensure sensors are reporting to Home Assistant

### Weather factor always 1.0
- Verify weather entity is configured
- Check weather entity is providing data
- Review weather entity attributes

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- FAO for the Penman-Monteith equation documentation
- Rachio for their API
- Home Assistant community for inspiration

## Support

- Report bugs via GitHub Issues
- Ask questions in Home Assistant Community forums
- Check the wiki for additional documentation
