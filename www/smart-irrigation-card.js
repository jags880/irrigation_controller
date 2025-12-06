/**
 * Smart Irrigation AI Card for Home Assistant
 * A custom Lovelace card for the Smart Irrigation AI integration
 */

class SmartIrrigationCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.content) {
      this._render();
    }
    this._updateContent();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Please define an entity');
    }
    this.config = config;
  }

  getCardSize() {
    return 5;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --primary-color: var(--ha-primary-color, #03a9f4);
          --success-color: #4caf50;
          --warning-color: #ff9800;
          --error-color: #f44336;
        }

        ha-card {
          padding: 16px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }

        .title {
          font-size: 1.2em;
          font-weight: 500;
        }

        .status-badge {
          padding: 4px 12px;
          border-radius: 12px;
          font-size: 0.85em;
          font-weight: 500;
          text-transform: uppercase;
        }

        .status-idle {
          background-color: var(--secondary-background-color);
          color: var(--secondary-text-color);
        }

        .status-running {
          background-color: var(--success-color);
          color: white;
        }

        .status-scheduled {
          background-color: var(--primary-color);
          color: white;
        }

        .status-rain_delay {
          background-color: var(--warning-color);
          color: white;
        }

        .status-skip_scheduled {
          background-color: var(--error-color);
          color: white;
        }

        .info-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }

        .info-item {
          display: flex;
          flex-direction: column;
          padding: 12px;
          background-color: var(--secondary-background-color);
          border-radius: 8px;
        }

        .info-label {
          font-size: 0.8em;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }

        .info-value {
          font-size: 1.1em;
          font-weight: 500;
        }

        .zones-section {
          margin-top: 16px;
        }

        .zones-header {
          font-size: 0.9em;
          font-weight: 500;
          margin-bottom: 8px;
          color: var(--secondary-text-color);
        }

        .zone-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 12px;
          margin-bottom: 4px;
          background-color: var(--secondary-background-color);
          border-radius: 6px;
        }

        .zone-name {
          font-weight: 500;
        }

        .zone-info {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .zone-duration {
          font-size: 0.9em;
          color: var(--secondary-text-color);
        }

        .zone-moisture {
          font-size: 0.85em;
          padding: 2px 8px;
          border-radius: 10px;
        }

        .moisture-dry {
          background-color: #ffebee;
          color: #c62828;
        }

        .moisture-low {
          background-color: #fff3e0;
          color: #e65100;
        }

        .moisture-optimal {
          background-color: #e8f5e9;
          color: #2e7d32;
        }

        .moisture-wet {
          background-color: #e3f2fd;
          color: #1565c0;
        }

        .actions {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }

        .action-button {
          flex: 1;
          padding: 10px;
          border: none;
          border-radius: 6px;
          font-size: 0.9em;
          cursor: pointer;
          transition: opacity 0.2s;
        }

        .action-button:hover {
          opacity: 0.8;
        }

        .action-primary {
          background-color: var(--primary-color);
          color: white;
        }

        .action-secondary {
          background-color: var(--secondary-background-color);
          color: var(--primary-text-color);
        }

        .action-danger {
          background-color: var(--error-color);
          color: white;
        }

        .weather-info {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          background-color: var(--secondary-background-color);
          border-radius: 6px;
          margin-bottom: 12px;
        }

        .weather-icon {
          font-size: 1.5em;
        }

        .weather-temp {
          font-size: 1.2em;
          font-weight: 500;
        }

        .weather-condition {
          font-size: 0.9em;
          color: var(--secondary-text-color);
        }

        .factor-bar {
          height: 4px;
          background-color: var(--secondary-background-color);
          border-radius: 2px;
          overflow: hidden;
          margin-top: 4px;
        }

        .factor-fill {
          height: 100%;
          border-radius: 2px;
          transition: width 0.3s;
        }
      </style>

      <ha-card>
        <div class="header">
          <span class="title">🌱 Smart Irrigation</span>
          <span class="status-badge" id="status-badge">--</span>
        </div>

        <div class="weather-info" id="weather-info">
          <span class="weather-icon" id="weather-icon">☀️</span>
          <span class="weather-temp" id="weather-temp">--°</span>
          <span class="weather-condition" id="weather-condition">--</span>
        </div>

        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Next Run</span>
            <span class="info-value" id="next-run">--</span>
          </div>
          <div class="info-item">
            <span class="info-label">Duration</span>
            <span class="info-value" id="total-duration">--</span>
          </div>
          <div class="info-item">
            <span class="info-label">Weather Factor</span>
            <span class="info-value" id="weather-factor">--</span>
            <div class="factor-bar">
              <div class="factor-fill" id="weather-factor-bar" style="width: 100%; background-color: var(--success-color);"></div>
            </div>
          </div>
          <div class="info-item">
            <span class="info-label">Seasonal</span>
            <span class="info-value" id="seasonal-factor">--</span>
            <div class="factor-bar">
              <div class="factor-fill" id="seasonal-factor-bar" style="width: 100%; background-color: var(--primary-color);"></div>
            </div>
          </div>
        </div>

        <div class="zones-section">
          <div class="zones-header">Zones</div>
          <div id="zones-list"></div>
        </div>

        <div class="actions">
          <button class="action-button action-primary" id="run-btn">▶ Run Now</button>
          <button class="action-button action-secondary" id="skip-btn">⏭ Skip Next</button>
          <button class="action-button action-danger" id="stop-btn">⏹ Stop</button>
        </div>
      </ha-card>
    `;

    this.content = this.shadowRoot.querySelector('ha-card');

    // Add event listeners
    this.shadowRoot.getElementById('run-btn').addEventListener('click', () => this._handleRun());
    this.shadowRoot.getElementById('skip-btn').addEventListener('click', () => this._handleSkip());
    this.shadowRoot.getElementById('stop-btn').addEventListener('click', () => this._handleStop());
  }

  _updateContent() {
    if (!this._hass || !this.config.entity) return;

    const stateObj = this._hass.states[this.config.entity];
    if (!stateObj) return;

    const state = stateObj.state;
    const attrs = stateObj.attributes;

    // Update status badge
    const statusBadge = this.shadowRoot.getElementById('status-badge');
    statusBadge.textContent = state.replace('_', ' ');
    statusBadge.className = `status-badge status-${state}`;

    // Update next run
    const nextRunEl = this.shadowRoot.getElementById('next-run');
    if (attrs.next_run) {
      const nextRun = new Date(attrs.next_run);
      nextRunEl.textContent = this._formatDateTime(nextRun);
    } else {
      nextRunEl.textContent = 'Not scheduled';
    }

    // Update duration
    const durationEl = this.shadowRoot.getElementById('total-duration');
    durationEl.textContent = attrs.total_runtime_minutes
      ? `${attrs.total_runtime_minutes} min`
      : '--';

    // Update weather (if weather entity configured)
    this._updateWeather();

    // Update factors (if factor sensors exist)
    this._updateFactors();

    // Update zones
    this._updateZones();
  }

  _updateWeather() {
    const weatherEntity = this.config.weather_entity;
    if (!weatherEntity) return;

    const weatherState = this._hass.states[weatherEntity];
    if (!weatherState) return;

    const weatherIcon = this.shadowRoot.getElementById('weather-icon');
    const weatherTemp = this.shadowRoot.getElementById('weather-temp');
    const weatherCondition = this.shadowRoot.getElementById('weather-condition');

    const condition = weatherState.state;
    weatherIcon.textContent = this._getWeatherIcon(condition);
    weatherTemp.textContent = `${weatherState.attributes.temperature || '--'}°`;
    weatherCondition.textContent = condition;
  }

  _updateFactors() {
    // Weather factor
    const weatherFactorEntity = this.config.weather_factor_entity;
    if (weatherFactorEntity) {
      const state = this._hass.states[weatherFactorEntity];
      if (state) {
        const value = parseFloat(state.state) || 1;
        this.shadowRoot.getElementById('weather-factor').textContent = `${(value * 100).toFixed(0)}%`;
        const bar = this.shadowRoot.getElementById('weather-factor-bar');
        bar.style.width = `${Math.min(value * 100, 150)}%`;
        bar.style.backgroundColor = value < 0.5 ? 'var(--warning-color)' : 'var(--success-color)';
      }
    }

    // Seasonal factor
    const seasonalFactorEntity = this.config.seasonal_factor_entity;
    if (seasonalFactorEntity) {
      const state = this._hass.states[seasonalFactorEntity];
      if (state) {
        const value = parseFloat(state.state) || 1;
        this.shadowRoot.getElementById('seasonal-factor').textContent = `${(value * 100).toFixed(0)}%`;
        const bar = this.shadowRoot.getElementById('seasonal-factor-bar');
        bar.style.width = `${value * 100}%`;
      }
    }
  }

  _updateZones() {
    const zonesContainer = this.shadowRoot.getElementById('zones-list');
    zonesContainer.innerHTML = '';

    const zones = this.config.zones || [];

    for (const zone of zones) {
      const zoneEntity = this._hass.states[zone.entity];
      const moistureEntity = zone.moisture_entity ? this._hass.states[zone.moisture_entity] : null;
      const recommendationEntity = zone.recommendation_entity ? this._hass.states[zone.recommendation_entity] : null;

      if (!zoneEntity) continue;

      const row = document.createElement('div');
      row.className = 'zone-row';

      const zoneName = document.createElement('span');
      zoneName.className = 'zone-name';
      zoneName.textContent = zone.name || zoneEntity.attributes.friendly_name || 'Zone';

      const zoneInfo = document.createElement('div');
      zoneInfo.className = 'zone-info';

      if (moistureEntity) {
        const moisture = document.createElement('span');
        moisture.className = 'zone-moisture';
        const value = parseFloat(moistureEntity.state);
        moisture.textContent = `${value.toFixed(0)}%`;

        if (value < 30) {
          moisture.classList.add('moisture-dry');
        } else if (value < 45) {
          moisture.classList.add('moisture-low');
        } else if (value < 70) {
          moisture.classList.add('moisture-optimal');
        } else {
          moisture.classList.add('moisture-wet');
        }

        zoneInfo.appendChild(moisture);
      }

      if (recommendationEntity && recommendationEntity.attributes.ai_duration) {
        const duration = document.createElement('span');
        duration.className = 'zone-duration';
        duration.textContent = `${recommendationEntity.attributes.ai_duration} min`;
        zoneInfo.appendChild(duration);
      }

      row.appendChild(zoneName);
      row.appendChild(zoneInfo);
      zonesContainer.appendChild(row);
    }
  }

  _formatDateTime(date) {
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (date.toDateString() === now.toDateString()) {
      return `Today ${timeStr}`;
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return `Tomorrow ${timeStr}`;
    } else {
      return `${date.toLocaleDateString([], { weekday: 'short' })} ${timeStr}`;
    }
  }

  _getWeatherIcon(condition) {
    const icons = {
      'sunny': '☀️',
      'clear-night': '🌙',
      'partlycloudy': '⛅',
      'cloudy': '☁️',
      'rainy': '🌧️',
      'pouring': '⛈️',
      'snowy': '🌨️',
      'fog': '🌫️',
      'windy': '💨',
    };
    return icons[condition.toLowerCase()] || '🌤️';
  }

  _handleRun() {
    this._hass.callService('smart_irrigation_ai', 'calculate_schedule', {});
  }

  _handleSkip() {
    this._hass.callService('smart_irrigation_ai', 'skip_next_watering', {});
  }

  _handleStop() {
    this._hass.callService('smart_irrigation_ai', 'stop_all', {});
  }

  static getStubConfig() {
    return {
      entity: 'sensor.smart_irrigation_status',
      weather_entity: 'weather.home',
      weather_factor_entity: 'sensor.smart_irrigation_weather_factor',
      seasonal_factor_entity: 'sensor.smart_irrigation_seasonal_factor',
      zones: []
    };
  }
}

customElements.define('smart-irrigation-card', SmartIrrigationCard);

// Register card
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'smart-irrigation-card',
  name: 'Smart Irrigation Card',
  description: 'A card for the Smart Irrigation AI integration',
  preview: true,
});
