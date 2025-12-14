/**
 * Smart Irrigation AI Panel for Home Assistant
 *
 * Provides a sidebar panel with:
 * - Dashboard overview with current status
 * - Zone controls
 * - AI recommendations
 * - Watering calendar with history and schedule
 */

// Import lit from CDN - Home Assistant allows this with trust_external: true
import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit@2.8.0/index.js?module";

const DOMAIN = "smart_irrigation_ai";

class SmartIrrigationPanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      panel: { type: Object },
      _data: { type: Object },
      _loading: { type: Boolean },
      _activeTab: { type: String },
      _calendarMonth: { type: Object },
      _calendarEvents: { type: Array },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
        padding: 16px;
        background: var(--primary-background-color);
        min-height: 100vh;
      }

      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        flex-wrap: wrap;
        gap: 16px;
      }

      h1 {
        margin: 0;
        color: var(--primary-text-color);
        font-size: 24px;
        font-weight: 400;
      }

      .tabs {
        display: flex;
        border-bottom: 1px solid var(--divider-color);
        margin-bottom: 16px;
      }

      .tab {
        padding: 12px 24px;
        cursor: pointer;
        border-bottom: 2px solid transparent;
        color: var(--secondary-text-color);
        font-weight: 500;
        transition: all 0.2s;
      }

      .tab:hover {
        color: var(--primary-text-color);
      }

      .tab.active {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }

      .content {
        max-width: 1200px;
      }

      .card {
        background: var(--card-background-color);
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
      }

      .card-header {
        font-size: 18px;
        font-weight: 500;
        margin-bottom: 16px;
        color: var(--primary-text-color);
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .card-header ha-icon {
        color: var(--primary-color);
      }

      .status-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
      }

      .status-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .status-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        text-transform: uppercase;
      }

      .status-value {
        font-size: 20px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .status-value.running {
        color: var(--success-color, #4caf50);
      }

      .status-value.warning {
        color: var(--warning-color, #ff9800);
      }

      .zone-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .zone-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px;
        background: var(--secondary-background-color);
        border-radius: 8px;
      }

      .zone-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .zone-name {
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .zone-status {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .zone-recommendation {
        font-size: 12px;
        padding: 4px 8px;
        border-radius: 4px;
        background: var(--primary-color);
        color: white;
      }

      .zone-recommendation.skip {
        background: var(--secondary-text-color);
      }

      .zone-actions {
        display: flex;
        gap: 8px;
      }

      .btn {
        padding: 8px 16px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        transition: all 0.2s;
      }

      .btn-primary {
        background: var(--primary-color);
        color: white;
      }

      .btn-primary:hover {
        opacity: 0.9;
      }

      .btn-secondary {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
      }

      .btn-danger {
        background: var(--error-color, #f44336);
        color: white;
      }

      .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      /* Calendar Styles */
      .calendar-container {
        margin-top: 16px;
      }

      .calendar-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
      }

      .calendar-nav {
        display: flex;
        gap: 8px;
      }

      .calendar-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 4px;
      }

      .calendar-day-header {
        padding: 8px;
        text-align: center;
        font-weight: 500;
        color: var(--secondary-text-color);
        font-size: 12px;
      }

      .calendar-day {
        min-height: 80px;
        padding: 8px;
        background: var(--secondary-background-color);
        border-radius: 4px;
        position: relative;
      }

      .calendar-day.other-month {
        opacity: 0.5;
      }

      .calendar-day.today {
        border: 2px solid var(--primary-color);
      }

      .calendar-day-number {
        font-weight: 500;
        margin-bottom: 4px;
      }

      .calendar-event {
        font-size: 10px;
        padding: 2px 4px;
        border-radius: 2px;
        margin-bottom: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .calendar-event.scheduled {
        background: var(--primary-color);
        color: white;
      }

      .calendar-event.completed {
        background: var(--success-color, #4caf50);
        color: white;
      }

      .calendar-event.skipped {
        background: var(--warning-color, #ff9800);
        color: white;
      }

      .calendar-event.rain-delay {
        background: var(--info-color, #2196f3);
        color: white;
      }

      .ai-decision {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px;
        background: var(--secondary-background-color);
        border-radius: 8px;
        margin-bottom: 12px;
      }

      .ai-decision.will-water {
        border-left: 4px solid var(--success-color, #4caf50);
      }

      .ai-decision.skip-water {
        border-left: 4px solid var(--warning-color, #ff9800);
      }

      .ai-badge {
        background: var(--primary-color);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 600;
      }

      .factors-list {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
      }

      .factor-chip {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        background: var(--secondary-background-color);
        border-radius: 16px;
        font-size: 12px;
      }

      .factor-chip.positive {
        background: rgba(76, 175, 80, 0.2);
        color: var(--success-color, #4caf50);
      }

      .factor-chip.negative {
        background: rgba(244, 67, 54, 0.2);
        color: var(--error-color, #f44336);
      }

      .loading {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 40px;
      }

      @media (max-width: 600px) {
        :host {
          padding: 8px;
        }

        .calendar-grid {
          font-size: 12px;
        }

        .calendar-day {
          min-height: 60px;
          padding: 4px;
        }
      }
    `;
  }

  constructor() {
    super();
    this._data = {};
    this._loading = true;
    this._activeTab = "dashboard";
    this._calendarMonth = new Date();
    this._calendarEvents = [];
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadData();
    this._loadCalendarEvents();
    // Refresh every 30 seconds
    this._refreshInterval = setInterval(() => this._loadData(), 30000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
    }
  }

  async _loadData() {
    if (!this.hass) return;

    try {
      // Get all Smart Irrigation entities
      const entities = Object.keys(this.hass.states).filter(
        (e) => e.startsWith("sensor.smart_irrigation") ||
               e.startsWith("switch.smart_irrigation") ||
               e.startsWith("binary_sensor.smart_irrigation") ||
               e.startsWith("calendar.smart_irrigation")
      );

      const data = {
        zones: [],
        schedule: {},
        weather: {},
        recommendations: {},
      };

      // Parse entity data
      for (const entityId of entities) {
        const state = this.hass.states[entityId];
        if (!state) continue;

        if (entityId.includes("next_run")) {
          data.schedule.nextRun = state.state;
          data.schedule.attributes = state.attributes;
        } else if (entityId.includes("zone_") && entityId.includes("switch")) {
          data.zones.push({
            entityId,
            name: state.attributes.friendly_name || entityId,
            state: state.state,
            attributes: state.attributes,
          });
        } else if (entityId.includes("ai_status")) {
          data.aiStatus = state.state;
          data.aiAttributes = state.attributes;
        } else if (entityId.includes("weather_factor")) {
          data.weather.factor = state.state;
        } else if (entityId.includes("is_running")) {
          data.isRunning = state.state === "on";
        }
      }

      // Get AI recommendations via service call if available
      try {
        const response = await this.hass.callWS({
          type: "smart_irrigation_ai/get_status",
        });
        if (response) {
          data.fullStatus = response;
        }
      } catch (e) {
        // Service might not be registered yet
      }

      this._data = data;
      this._loading = false;
    } catch (err) {
      console.error("Error loading Smart Irrigation data:", err);
      this._loading = false;
    }
  }

  async _loadCalendarEvents() {
    if (!this.hass) return;

    const calendarEntity = Object.keys(this.hass.states).find(
      (e) => e.startsWith("calendar.smart_irrigation")
    );

    if (calendarEntity) {
      try {
        const start = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth(), 1);
        const end = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth() + 1, 0);

        const events = await this.hass.callApi(
          "GET",
          `calendars/${calendarEntity}?start=${start.toISOString()}&end=${end.toISOString()}`
        );

        this._calendarEvents = events || [];
      } catch (e) {
        console.error("Error loading calendar events:", e);
        this._calendarEvents = [];
      }
    }
  }

  _setTab(tab) {
    this._activeTab = tab;
  }

  _previousMonth() {
    this._calendarMonth = new Date(
      this._calendarMonth.getFullYear(),
      this._calendarMonth.getMonth() - 1,
      1
    );
    this._loadCalendarEvents();
  }

  _nextMonth() {
    this._calendarMonth = new Date(
      this._calendarMonth.getFullYear(),
      this._calendarMonth.getMonth() + 1,
      1
    );
    this._loadCalendarEvents();
  }

  async _runZone(entityId) {
    await this.hass.callService("switch", "turn_on", {
      entity_id: entityId,
    });
    this._loadData();
  }

  async _stopZone(entityId) {
    await this.hass.callService("switch", "turn_off", {
      entity_id: entityId,
    });
    this._loadData();
  }

  async _stopAll() {
    await this.hass.callService(DOMAIN, "stop_all", {});
    this._loadData();
  }

  async _runSchedule() {
    await this.hass.callService(DOMAIN, "calculate_schedule", {});
    this._loadData();
  }

  async _skipNext() {
    await this.hass.callService(DOMAIN, "skip_next_watering", {});
    this._loadData();
  }

  async _setRainDelay(hours) {
    await this.hass.callService(DOMAIN, "rain_delay", { hours });
    this._loadData();
  }

  render() {
    if (this._loading) {
      return html`
        <div class="loading">
          <ha-circular-progress active></ha-circular-progress>
        </div>
      `;
    }

    return html`
      <div class="header">
        <h1>
          <ha-icon icon="mdi:sprinkler-variant"></ha-icon>
          Smart Irrigation AI
        </h1>
        <div>
          <button class="btn btn-primary" @click=${this._runSchedule}>
            <ha-icon icon="mdi:refresh"></ha-icon>
            Recalculate
          </button>
          ${this._data.isRunning
            ? html`
                <button class="btn btn-danger" @click=${this._stopAll}>
                  <ha-icon icon="mdi:stop"></ha-icon>
                  Stop All
                </button>
              `
            : ""}
        </div>
      </div>

      <div class="tabs">
        <div
          class="tab ${this._activeTab === "dashboard" ? "active" : ""}"
          @click=${() => this._setTab("dashboard")}
        >
          Dashboard
        </div>
        <div
          class="tab ${this._activeTab === "zones" ? "active" : ""}"
          @click=${() => this._setTab("zones")}
        >
          Zones
        </div>
        <div
          class="tab ${this._activeTab === "calendar" ? "active" : ""}"
          @click=${() => this._setTab("calendar")}
        >
          Calendar
        </div>
        <div
          class="tab ${this._activeTab === "settings" ? "active" : ""}"
          @click=${() => this._setTab("settings")}
        >
          Settings
        </div>
      </div>

      <div class="content">
        ${this._activeTab === "dashboard" ? this._renderDashboard() : ""}
        ${this._activeTab === "zones" ? this._renderZones() : ""}
        ${this._activeTab === "calendar" ? this._renderCalendar() : ""}
        ${this._activeTab === "settings" ? this._renderSettings() : ""}
      </div>
    `;
  }

  _renderDashboard() {
    const schedule = this._data.schedule || {};
    const aiAttrs = this._data.aiAttributes || {};

    return html`
      <!-- Status Overview -->
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:gauge"></ha-icon>
          Status Overview
        </div>
        <div class="status-grid">
          <div class="status-item">
            <span class="status-label">System Status</span>
            <span class="status-value ${this._data.isRunning ? "running" : ""}">
              ${this._data.isRunning ? "Running" : "Idle"}
            </span>
          </div>
          <div class="status-item">
            <span class="status-label">Next Scheduled Run</span>
            <span class="status-value">
              ${schedule.nextRun && schedule.nextRun !== "unknown"
                ? this._formatDateTime(schedule.nextRun)
                : "Not scheduled"}
            </span>
          </div>
          <div class="status-item">
            <span class="status-label">Zones Configured</span>
            <span class="status-value">${this._data.zones?.length || 0}</span>
          </div>
          <div class="status-item">
            <span class="status-label">AI Confidence</span>
            <span class="status-value">
              ${aiAttrs.confidence ? `${Math.round(aiAttrs.confidence * 100)}%` : "N/A"}
            </span>
          </div>
        </div>
      </div>

      <!-- AI Decision -->
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:robot"></ha-icon>
          AI Decision for Today
        </div>
        ${this._renderAIDecision()}
      </div>

      <!-- Quick Actions -->
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:lightning-bolt"></ha-icon>
          Quick Actions
        </div>
        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
          <button class="btn btn-primary" @click=${this._runSchedule}>
            Run AI Schedule Now
          </button>
          <button class="btn btn-secondary" @click=${this._skipNext}>
            Skip Next Watering
          </button>
          <button class="btn btn-secondary" @click=${() => this._setRainDelay(24)}>
            Rain Delay (24h)
          </button>
          <button class="btn btn-secondary" @click=${() => this._setRainDelay(48)}>
            Rain Delay (48h)
          </button>
        </div>
      </div>

      <!-- Weather Factors -->
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
          Weather & Environmental Factors
        </div>
        ${this._renderFactors()}
      </div>
    `;
  }

  _renderAIDecision() {
    const attrs = this._data.aiAttributes || {};
    const willWater = attrs.zones_needing_water > 0;

    return html`
      <div class="ai-decision ${willWater ? "will-water" : "skip-water"}">
        <span class="ai-badge">AI</span>
        <div>
          <strong>
            ${willWater
              ? `Watering recommended for ${attrs.zones_needing_water} zone(s)`
              : "No watering needed today"}
          </strong>
          <div style="font-size: 12px; color: var(--secondary-text-color);">
            ${attrs.skip_reason || "Based on current conditions and soil moisture levels"}
          </div>
        </div>
      </div>
    `;
  }

  _renderFactors() {
    const attrs = this._data.aiAttributes || {};
    const factors = [
      { name: "Weather", value: attrs.weather_factor, icon: "mdi:weather-cloudy" },
      { name: "Soil Moisture", value: attrs.moisture_factor, icon: "mdi:water-percent" },
      { name: "Rain Sensor", value: attrs.rain_factor, icon: "mdi:weather-rainy" },
      { name: "Seasonal", value: attrs.seasonal_factor, icon: "mdi:calendar" },
    ];

    return html`
      <div class="factors-list">
        ${factors.map((factor) => {
          const value = parseFloat(factor.value) || 1;
          const isPositive = value >= 1;
          return html`
            <div class="factor-chip ${isPositive ? "positive" : "negative"}">
              <ha-icon icon="${factor.icon}" style="--mdc-icon-size: 16px;"></ha-icon>
              ${factor.name}: ${(value * 100).toFixed(0)}%
            </div>
          `;
        })}
      </div>
    `;
  }

  _renderZones() {
    return html`
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:sprinkler"></ha-icon>
          Irrigation Zones
        </div>
        <div class="zone-list">
          ${this._data.zones?.length
            ? this._data.zones.map((zone) => this._renderZoneItem(zone))
            : html`<p>No zones configured</p>`}
        </div>
      </div>
    `;
  }

  _renderZoneItem(zone) {
    const isRunning = zone.state === "on";
    const recommendation = zone.attributes?.ai_recommendation;

    return html`
      <div class="zone-item">
        <div class="zone-info">
          <span class="zone-name">${zone.name}</span>
          <span class="zone-status">
            ${isRunning ? "Currently running" : "Idle"}
            ${zone.attributes?.last_run
              ? ` | Last run: ${this._formatDateTime(zone.attributes.last_run)}`
              : ""}
          </span>
          ${recommendation
            ? html`
                <span class="zone-recommendation ${recommendation.should_water ? "" : "skip"}">
                  ${recommendation.should_water
                    ? `${recommendation.duration_minutes} min recommended`
                    : recommendation.skip_reason || "Skip"}
                </span>
              `
            : ""}
        </div>
        <div class="zone-actions">
          ${isRunning
            ? html`
                <button class="btn btn-danger" @click=${() => this._stopZone(zone.entityId)}>
                  Stop
                </button>
              `
            : html`
                <button class="btn btn-primary" @click=${() => this._runZone(zone.entityId)}>
                  Run
                </button>
              `}
        </div>
      </div>
    `;
  }

  _renderCalendar() {
    const year = this._calendarMonth.getFullYear();
    const month = this._calendarMonth.getMonth();
    const monthName = this._calendarMonth.toLocaleDateString("en-US", { month: "long", year: "numeric" });

    // Get days in month
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDayOfWeek = firstDay.getDay();
    const daysInMonth = lastDay.getDate();

    // Build calendar grid
    const days = [];
    const today = new Date();

    // Previous month days
    const prevMonthLastDay = new Date(year, month, 0).getDate();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      days.push({
        day: prevMonthLastDay - i,
        otherMonth: true,
        date: new Date(year, month - 1, prevMonthLastDay - i),
      });
    }

    // Current month days
    for (let d = 1; d <= daysInMonth; d++) {
      const date = new Date(year, month, d);
      days.push({
        day: d,
        otherMonth: false,
        isToday: date.toDateString() === today.toDateString(),
        date,
      });
    }

    // Next month days
    const remaining = 42 - days.length;
    for (let d = 1; d <= remaining; d++) {
      days.push({
        day: d,
        otherMonth: true,
        date: new Date(year, month + 1, d),
      });
    }

    return html`
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:calendar"></ha-icon>
          Irrigation Calendar
        </div>

        <div class="calendar-container">
          <div class="calendar-header">
            <h3>${monthName}</h3>
            <div class="calendar-nav">
              <button class="btn btn-secondary" @click=${this._previousMonth}>
                <ha-icon icon="mdi:chevron-left"></ha-icon>
              </button>
              <button class="btn btn-secondary" @click=${this._nextMonth}>
                <ha-icon icon="mdi:chevron-right"></ha-icon>
              </button>
            </div>
          </div>

          <div class="calendar-grid">
            ${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(
              (day) => html`<div class="calendar-day-header">${day}</div>`
            )}
            ${days.map((d) => this._renderCalendarDay(d))}
          </div>
        </div>
      </div>

      <!-- Legend -->
      <div class="card">
        <div class="card-header">Legend</div>
        <div style="display: flex; gap: 16px; flex-wrap: wrap;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <div class="calendar-event scheduled" style="width: 60px;">Scheduled</div>
            <span>Upcoming watering</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <div class="calendar-event completed" style="width: 60px;">Complete</div>
            <span>Completed watering</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <div class="calendar-event skipped" style="width: 60px;">Skipped</div>
            <span>AI decided to skip</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <div class="calendar-event rain-delay" style="width: 60px;">Rain</div>
            <span>Rain delay</span>
          </div>
        </div>
      </div>
    `;
  }

  _renderCalendarDay(dayInfo) {
    const events = this._getEventsForDay(dayInfo.date);

    return html`
      <div
        class="calendar-day ${dayInfo.otherMonth ? "other-month" : ""} ${dayInfo.isToday ? "today" : ""}"
      >
        <div class="calendar-day-number">${dayInfo.day}</div>
        ${events.slice(0, 3).map(
          (event) => html`
            <div class="calendar-event ${event.type}">${event.summary}</div>
          `
        )}
        ${events.length > 3 ? html`<div style="font-size: 10px;">+${events.length - 3} more</div>` : ""}
      </div>
    `;
  }

  _getEventsForDay(date) {
    const dayStr = date.toISOString().split("T")[0];
    const events = [];

    // Find events for this day from calendar events
    for (const event of this._calendarEvents) {
      const eventStart = new Date(event.start?.dateTime || event.start?.date);
      if (eventStart.toISOString().split("T")[0] === dayStr) {
        events.push({
          summary: event.summary?.substring(0, 15) || "Irrigation",
          type: event.summary?.includes("Complete")
            ? "completed"
            : event.summary?.includes("Skip")
            ? "skipped"
            : event.summary?.includes("Rain")
            ? "rain-delay"
            : "scheduled",
        });
      }
    }

    return events;
  }

  _renderSettings() {
    const schedule = this._data.schedule?.attributes || {};

    return html`
      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:cog"></ha-icon>
          Schedule Settings
        </div>
        <p>
          Configure settings in Home Assistant under
          <strong>Settings > Devices & Services > Smart Irrigation AI > Configure</strong>
        </p>

        <div class="status-grid" style="margin-top: 16px;">
          <div class="status-item">
            <span class="status-label">Schedule Mode</span>
            <span class="status-value">${schedule.schedule_mode || "start_at"}</span>
          </div>
          <div class="status-item">
            <span class="status-label">Watering Days</span>
            <span class="status-value">
              ${this._formatWateringDays(schedule.watering_days)}
            </span>
          </div>
          <div class="status-item">
            <span class="status-label">Cycle & Soak</span>
            <span class="status-value">${schedule.cycle_soak ? "Enabled" : "Disabled"}</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <ha-icon icon="mdi:information"></ha-icon>
          About
        </div>
        <p>
          <strong>Smart Irrigation AI</strong> uses artificial intelligence to optimize your
          irrigation schedule based on weather conditions, soil moisture, and plant needs.
        </p>
        <p style="font-size: 12px; color: var(--secondary-text-color);">
          Version 1.0.0
        </p>
      </div>
    `;
  }

  _formatDateTime(isoString) {
    try {
      const date = new Date(isoString);
      return date.toLocaleString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  }

  _formatWateringDays(days) {
    if (!days || !days.length) return "Not set";
    const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    return days.map((d) => dayNames[d] || d).join(", ");
  }
}

customElements.define("smart-irrigation-panel", SmartIrrigationPanel);
