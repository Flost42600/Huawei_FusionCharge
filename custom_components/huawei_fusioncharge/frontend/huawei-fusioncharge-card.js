/*
 * Huawei FusionCharge card for Home Assistant.
 * Shipped with the huawei_fusioncharge integration and loaded automatically.
 *
 *   type: custom:huawei-fusioncharge-card
 *   device_id: <optional, when several chargers are configured>
 *   title: <optional>
 *
 * Entities are found by themselves (platform + translation key), whatever
 * the language of the installation.
 */

const DOMAIN = "huawei_fusioncharge";
const CARD_VERSION = "0.1.3";

const T = {
  fr: {
    charging: "En charge",
    waiting: "En attente",
    idle: "Au repos",
    plugged: "Véhicule branché",
    offline: "Hors ligne",
    reauth: "Reconnexion requise",
    cloudDown: "Cloud injoignable",
    online: "En ligne",
    charge: "Charge",
    schedule: "Programmation",
    on: "Activée",
    off: "Désactivée",
    chargeOn: "En cours",
    chargeOff: "Arrêtée",
    mode: "Mode de travail",
    normal: "Normale",
    green: "Énergie verte",
    modeHint: "Programmation active : chaque plage applique son propre mode.",
    session: "Session",
    duration: "Durée",
    plans: "Plages programmées",
    noPlans: "Aucune plage",
    everyDay: "Tous les jours",
    oneTime: "ponctuelle",
    daysPerWeek: (n) => `${n} jour${n > 1 ? "s" : ""} par semaine`,
    unchecked: "décochée",
    lastSeen: "Dernière communication",
    ago: (s) => (s < 60 ? `il y a ${s} s` : s < 3600 ? `il y a ${Math.round(s / 60)} min` : `il y a ${Math.round(s / 3600)} h`),
    readOnly: "Commandes désactivées dans les options de l'intégration",
    notFound: "Aucune borne Huawei FusionCharge trouvée.",
    pending: "Envoi…",
  },
  en: {
    charging: "Charging",
    waiting: "Waiting",
    idle: "Idle",
    plugged: "Vehicle plugged in",
    offline: "Offline",
    reauth: "Login required",
    cloudDown: "Cloud unreachable",
    online: "Online",
    charge: "Charging",
    schedule: "Schedule",
    on: "On",
    off: "Off",
    chargeOn: "Running",
    chargeOff: "Stopped",
    mode: "Working mode",
    normal: "Normal",
    green: "Green energy",
    modeHint: "Schedule on: each plan applies its own mode.",
    session: "Session",
    duration: "Duration",
    plans: "Schedule plans",
    noPlans: "No plan",
    everyDay: "Every day",
    oneTime: "one-time",
    daysPerWeek: (n) => `${n} day${n > 1 ? "s" : ""} a week`,
    unchecked: "unchecked",
    lastSeen: "Last communication",
    ago: (s) => (s < 60 ? `${s} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`),
    readOnly: "Commands are disabled in the integration options",
    notFound: "No Huawei FusionCharge charger found.",
    pending: "Sending…",
  },
};

const ICONS = {
  bolt: "M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 3h1l-1 7h3.5c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z",
  sun: "M12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10m0-5 2.4 3.4h-4.8L12 2M4.9 4.9l4 1.1-3 3-1-4.1M2 12l3.4-2.4v4.8L2 12m2.9 7.1 1.1-4 3 3-4.1 1m7.1 2.9-2.4-3.4h4.8L12 22m7.1-2.9-4-1.1 3-3 1 4.1M22 12l-3.4 2.4V9.6L22 12m-2.9-7.1-1.1 4-3-3 4.1-1z",
  calendar: "M19 19H5V8h14m-3-7v2H8V1H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-1V1m-1 11h-5v5h5v-5z",
  plug: "M16 7V3h-2v4h-4V3H8v4h-.01C6.9 7 6 7.9 6 9v5.5L9.5 18v3h5v-3l3.5-3.5V9c0-1.1-.9-2-2-2z",
  cloud: "M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z",
  clock: "M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16m0-18a10 10 0 1 1 0 20 10 10 0 0 1 0-20m.5 5v5.25l4.5 2.67-.75 1.23L11 13V7h1.5z",
};

function svgIcon(name, size = 20) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true"><path fill="currentColor" d="${ICONS[name]}"/></svg>`;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function popcount(n) {
  let c = 0;
  for (let v = Number(n) || 0; v; v &= v - 1) c++;
  return c;
}

class HuaweiFusionChargeCard extends HTMLElement {
  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = config || {};
    this._busy = {};
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._signature = null;
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  set hass(hass) {
    this._hass = hass;
    const map = this._findEntities();
    this._map = map;
    const ids = Object.values(map);
    const signature = JSON.stringify([
      ids.map((id) => [id, hass.states[id]?.state, hass.states[id]?.last_updated]),
      this._busy,
      hass.language,
      Math.floor(Date.now() / 15000),
    ]);
    if (signature === this._signature) return;
    this._signature = signature;
    this._render();
  }

  _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return T[lang] || T.en;
  }

  _findEntities() {
    const entities = this._hass?.entities || {};
    const mine = Object.values(entities).filter((e) => e.platform === DOMAIN);
    let deviceId = this._config.device_id;
    if (!deviceId && mine.length) deviceId = mine[0].device_id;
    const map = {};
    for (const e of mine) {
      if (e.device_id !== deviceId || !e.translation_key) continue;
      const domain = e.entity_id.split(".")[0];
      map[`${domain}.${e.translation_key}`] = e.entity_id;
    }
    this._deviceId = deviceId;
    return map;
  }

  _state(key) {
    const id = this._map[key];
    return id ? this._hass.states[id] : undefined;
  }

  _num(key) {
    const s = this._state(key);
    const v = s ? parseFloat(s.state) : NaN;
    return Number.isFinite(v) ? v : null;
  }

  _format(value, digits) {
    const locale = this._hass?.locale?.language || this._hass?.language || "fr";
    return new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  }

  _localTime(hhmm) {
    if (!hhmm || !/^\d{1,2}:\d{2}/.test(hhmm)) return hhmm || "";
    const [h, m] = hhmm.split(":").map(Number);
    const now = new Date();
    const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), h, m));
    const tz = this._hass?.config?.time_zone;
    try {
      return new Intl.DateTimeFormat(this._hass?.language || "fr", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(date);
    } catch (e) {
      return hhmm;
    }
  }

  _epochTime(ms) {
    const value = Number(ms);
    if (!Number.isFinite(value)) return String(ms ?? "");
    try {
      return new Intl.DateTimeFormat(this._hass?.language || "fr", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: this._hass?.config?.time_zone,
      }).format(new Date(value));
    } catch (e) {
      return String(ms);
    }
  }

  _deviceName() {
    if (this._config.title) return this._config.title;
    const device = this._hass?.devices?.[this._deviceId];
    return device?.name_by_user || device?.name || "Borne";
  }

  _status() {
    const t = this._t();
    const reauth = this._state("binary_sensor.reauth_needed")?.state === "on";
    const cloud = this._state("binary_sensor.cloud_connected")?.state;
    const online = this._state("binary_sensor.charger_online")?.state;
    const power = this._num("sensor.power");
    if (reauth) return { key: "reauth", label: t.reauth, tone: "error" };
    if (cloud === "off") return { key: "cloud", label: t.cloudDown, tone: "error" };
    if (online === "off") return { key: "offline", label: t.offline, tone: "error" };
    const statusObj = this._state("sensor.status");
    const code = statusObj?.state;
    const label = statusObj && this._hass.formatEntityState ? this._hass.formatEntityState(statusObj) : null;
    if (["fault", "alarm"].includes(code)) return { key: code, label: label || code, tone: "error" };
    if ((power !== null && power > 0.05) || ["charging", "green_charging", "charging_starting"].includes(code))
      return { key: "charging", label: ["charging", "green_charging", "charging_starting"].includes(code) && label ? label : t.charging, tone: "charging" };
    if (["scheduled_waiting", "green_waiting", "orderly_waiting"].includes(code))
      return { key: code, label: label || t.waiting, tone: "waiting" };
    if (["plugged", "charging_ended"].includes(code)) return { key: code, label: label || t.plugged, tone: "plugged" };
    return { key: "idle", label: label || t.idle, tone: "idle" };
  }

  _charger(status) {
    // A generic wall box: body, status ring, display and cable to a holster.
    const charging = status.tone === "charging";
    return `
      <svg class="charger ${status.tone}" viewBox="0 0 140 220" role="img" aria-label="${esc(status.label)}">
        <defs>
          <linearGradient id="body" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="var(--fc-body-top)"/>
            <stop offset="1" stop-color="var(--fc-body-bottom)"/>
          </linearGradient>
          <radialGradient id="glow" cx="50%" cy="50%" r="50%">
            <stop offset="0.55" stop-color="var(--fc-tone)" stop-opacity="0.45"/>
            <stop offset="1" stop-color="var(--fc-tone)" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <ellipse cx="70" cy="200" rx="48" ry="5" class="shadow"/>
        <path class="cable ${charging ? "flow" : ""}" d="M70 150 C 70 182, 112 178, 116 150 L 116 120"/>
        <rect x="22" y="8" width="96" height="150" rx="22" fill="url(#body)" class="body"/>
        <rect x="22" y="8" width="96" height="150" rx="22" class="body-edge"/>
        <circle cx="70" cy="70" r="40" fill="url(#glow)" class="halo"/>
        <circle cx="70" cy="70" r="27" class="ring-track"/>
        <circle cx="70" cy="70" r="27" class="ring" pathLength="100"/>
        <g transform="translate(58 58)" class="ring-icon">${svgIcon(charging ? "bolt" : "plug", 24).replace("<svg", '<svg x="0" y="0"')}</g>
        <rect x="44" y="118" width="52" height="16" rx="8" class="display"/>
        <circle cx="54" cy="126" r="3" class="led"/>
        <rect x="62" y="124" width="26" height="4" rx="2" class="display-line"/>
        <rect x="108" y="96" width="16" height="30" rx="6" class="holster"/>
        <rect x="64" y="150" width="12" height="10" rx="3" class="plug-out"/>
      </svg>`;
  }

  _plans() {
    const t = this._t();
    const plans = this._state("sensor.plan_count")?.attributes?.plans;
    if (!Array.isArray(plans)) return "";
    if (!plans.length) return `<div class="plans"><div class="section-title">${t.plans}</div><div class="muted">${t.noPlans}</div></div>`;
    const rows = plans
      .map((p) => {
        const green = Number(p.charge_mode) === 1;
        const oneTime = p.repeat === false;
        const days = oneTime ? t.oneTime : Number(p.repeat_period) === 127 ? t.everyDay : t.daysPerWeek(popcount(p.repeat_period));
        const enabled = p.valid !== false;
        const power = p.max_charge_power_kw != null ? `${this._format(p.max_charge_power_kw, 1)} kW` : "";
        return `
          <div class="plan ${enabled ? "" : "disabled"}">
            <span class="plan-icon ${green ? "green" : "normal"}">${svgIcon(green ? "sun" : "bolt", 16)}</span>
            <span class="plan-time">${esc(oneTime ? this._epochTime(p.start_utc) : this._localTime(p.start_utc))} – ${esc(oneTime ? this._epochTime(p.stop_utc) : this._localTime(p.stop_utc))}</span>
            <span class="plan-days">${esc(days)}${enabled ? "" : ` · ${t.unchecked}`}</span>
            <span class="plan-power">${esc(power)}</span>
          </div>`;
      })
      .join("");
    return `<div class="plans"><div class="section-title">${t.plans}</div>${rows}</div>`;
  }

  _tile(key, icon, label, on, stateText, controllable) {
    const busy = this._busy[key];
    return `
      <button class="tile ${on ? "on" : ""} ${controllable ? "" : "readonly"}" data-action="${key}" ${controllable && !busy ? "" : "disabled"} aria-pressed="${on ? "true" : "false"}">
        <span class="tile-top">
          <span class="tile-icon">${svgIcon(icon, 22)}</span>
          <span class="switch ${on ? "on" : ""}" aria-hidden="true"><span class="knob"></span></span>
        </span>
        <span class="tile-label">${esc(label)}</span>
        <span class="tile-state">${esc(busy ? this._t().pending : stateText)}</span>
      </button>`;
  }

  _render() {
    const t = this._t();
    const root = this.shadowRoot;
    if (!this._hass) return;
    if (!Object.keys(this._map).length) {
      root.innerHTML = `<ha-card><div class="empty">${t.notFound}</div></ha-card>`;
      return;
    }
    const status = this._status();
    const power = this._num("sensor.power");
    const energy = this._num("sensor.session_energy");
    const durationS = this._num("sensor.session_duration");
    const chargeSwitch = this._state("switch.charge");
    const scheduleSwitch = this._state("switch.schedule");
    const scheduleOn = (scheduleSwitch || this._state("binary_sensor.schedule_active"))?.state === "on";
    const chargeOn = chargeSwitch ? chargeSwitch.state === "on" : power !== null && power > 0.05;
    const modeSelect = this._state("select.working_mode_select");
    const mode = (modeSelect || this._state("sensor.working_mode"))?.state;
    const controllable = Boolean(chargeSwitch);
    const last = this._state("sensor.last_success")?.state;
    const lastS = last && !isNaN(Date.parse(last)) ? Math.max(0, Math.round((Date.now() - Date.parse(last)) / 1000)) : null;
    const duration =
      durationS !== null ? `${Math.floor(durationS / 3600)} h ${String(Math.floor((durationS % 3600) / 60)).padStart(2, "0")}` : "–";

    root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="header">
          <div class="title">${esc(this._deviceName())}</div>
          <div class="pill ${status.tone}"><span class="dot"></span>${esc(status.tone === "error" ? status.label : t.online)}</div>
        </div>
        <div class="hero tone-${status.tone}">
          ${this._charger(status)}
          <div class="figures">
            <div class="status-label">${esc(status.label)}</div>
            <div class="power"><span class="value">${power !== null ? this._format(power, 1) : "–"}</span><span class="unit">kW</span></div>
            <div class="stats">
              <div><span class="stat-label">${t.session}</span><span class="stat-value">${energy !== null ? this._format(energy, 2) + " kWh" : "–"}</span></div>
              <div><span class="stat-label">${t.duration}</span><span class="stat-value">${duration}</span></div>
            </div>
          </div>
        </div>
        <div class="tiles">
          ${this._tile("charge", "bolt", t.charge, chargeOn, chargeOn ? t.chargeOn : t.chargeOff, controllable)}
          ${this._tile("schedule", "calendar", t.schedule, scheduleOn, scheduleOn ? t.on : t.off, Boolean(scheduleSwitch))}
        </div>
        <div class="mode">
          <div class="section-title">${t.mode}</div>
          <div class="segmented ${scheduleOn ? "dimmed" : ""}" role="radiogroup">
            <button class="seg ${mode === "normal" ? "active normal" : ""}" data-mode="normal" ${modeSelect && !this._busy.mode ? "" : "disabled"} role="radio" aria-checked="${mode === "normal"}">${svgIcon("bolt", 16)}${t.normal}</button>
            <button class="seg ${mode === "pv_preferred" ? "active green" : ""}" data-mode="pv_preferred" ${modeSelect && !this._busy.mode ? "" : "disabled"} role="radio" aria-checked="${mode === "pv_preferred"}">${svgIcon("sun", 16)}${t.green}</button>
          </div>
          ${scheduleOn ? `<div class="hint">${t.modeHint}</div>` : ""}
        </div>
        ${this._plans()}
        <div class="footer">
          <span>${svgIcon("clock", 14)} ${t.lastSeen} : ${lastS !== null ? t.ago(lastS) : "–"}</span>
          ${controllable ? "" : `<span class="muted">${t.readOnly}</span>`}
        </div>
      </ha-card>`;

    root.querySelectorAll("[data-action]").forEach((el) =>
      el.addEventListener("click", () => this._toggle(el.dataset.action))
    );
    root.querySelectorAll("[data-mode]").forEach((el) =>
      el.addEventListener("click", () => this._setMode(el.dataset.mode))
    );
    root.querySelector(".title")?.addEventListener("click", () => this._moreInfo("sensor.power"));
  }

  async _run(key, call) {
    this._busy = { ...this._busy, [key]: true };
    this._signature = null;
    this._render();
    try {
      await call();
    } catch (err) {
      this.dispatchEvent(
        new CustomEvent("hass-notification", { detail: { message: err?.message || String(err) }, bubbles: true, composed: true })
      );
    } finally {
      const busy = { ...this._busy };
      delete busy[key];
      this._busy = busy;
      this._signature = null;
      if (this._hass) this.hass = this._hass;
    }
  }

  _toggle(key) {
    const entityId = this._map[`switch.${key}`];
    if (!entityId) return;
    const on = this._hass.states[entityId]?.state === "on";
    this._run(key, () => this._hass.callService("switch", on ? "turn_off" : "turn_on", { entity_id: entityId }));
  }

  _setMode(option) {
    const entityId = this._map["select.working_mode_select"];
    if (!entityId || this._hass.states[entityId]?.state === option) return;
    this._run("mode", () => this._hass.callService("select", "select_option", { entity_id: entityId, option }));
  }

  _moreInfo(key) {
    const entityId = this._map[key];
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }
}

const STYLE = `
  :host {
    --fc-charging: var(--success-color, #2e9d5b);
    --fc-waiting: var(--info-color, #3b82c4);
    --fc-idle: var(--secondary-text-color, #7a7f87);
    --fc-error: var(--error-color, #d64545);
    --fc-green: #3f9d4a;
    --fc-normal: #2f74c0;
    --fc-body-top: #4a4f57;
    --fc-body-bottom: #23262b;
    --fc-tone: var(--fc-idle);
  }
  ha-card { padding: 16px; overflow: hidden; }
  .empty { padding: 8px; color: var(--secondary-text-color); }
  .header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .title { font-size: 1.15rem; font-weight: 600; color: var(--primary-text-color); cursor: pointer; }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 0.8rem; padding: 4px 10px; border-radius: 999px;
          background: color-mix(in srgb, var(--fc-charging) 14%, transparent); color: var(--fc-charging); white-space: nowrap; }
  .pill .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  .pill.error { background: color-mix(in srgb, var(--fc-error) 14%, transparent); color: var(--fc-error); }
  .hero { display: grid; grid-template-columns: 128px 1fr; gap: 16px; align-items: center; margin: 12px 0 16px; }
  .tone-charging { --fc-tone: var(--fc-charging); }
  .tone-waiting { --fc-tone: var(--fc-waiting); }
  .tone-idle { --fc-tone: var(--fc-idle); }
  .tone-plugged { --fc-tone: var(--fc-waiting); }
  .tone-error { --fc-tone: var(--fc-error); }
  .charger { width: 128px; height: auto; display: block; }
  .charger .shadow { fill: #000; opacity: .12; }
  .charger .body-edge { fill: none; stroke: rgba(255,255,255,.08); stroke-width: 1.5; }
  .charger .ring-track { fill: none; stroke: rgba(255,255,255,.10); stroke-width: 6; }
  .charger .ring { fill: none; stroke: var(--fc-tone); stroke-width: 6; stroke-linecap: round;
                   stroke-dasharray: 100; stroke-dashoffset: 0; transform: rotate(-90deg); transform-origin: 70px 70px; }
  .charger .ring-icon { color: var(--fc-tone); }
  .charger .halo { opacity: .9; }
  .charger.charging .halo { animation: breathe 2.4s ease-in-out infinite; transform-origin: 70px 70px; }
  .charger.charging .ring { stroke-dasharray: 70 30; animation: spin 2.8s linear infinite; }
  .charger.idle .halo { opacity: 0; }
  .charger .display { fill: #15171a; stroke: rgba(255,255,255,.08); }
  .charger .led { fill: var(--fc-tone); }
  .charger .display-line { fill: rgba(255,255,255,.18); }
  .charger .holster { fill: #2b2f35; stroke: rgba(255,255,255,.08); }
  .charger .plug-out { fill: #1b1d21; }
  .charger .cable { fill: none; stroke: #2b2f35; stroke-width: 7; stroke-linecap: round; }
  .charger .cable.flow { stroke: var(--fc-tone); stroke-dasharray: 6 8; animation: flow 1s linear infinite; }
  @keyframes spin { to { transform: rotate(270deg); } }
  @keyframes breathe { 0%,100% { opacity: .35; transform: scale(.92); } 50% { opacity: 1; transform: scale(1.06); } }
  @keyframes flow { to { stroke-dashoffset: -28; } }
  @media (prefers-reduced-motion: reduce) { .charger * { animation: none !important; } }
  .figures { min-width: 0; }
  .tone-error .power, .tone-error .stats { opacity: .45; }
  .status-label { color: var(--fc-tone); font-weight: 600; font-size: 0.95rem; }
  .power { display: flex; align-items: baseline; gap: 6px; margin: 2px 0 10px; color: var(--primary-text-color); }
  .power .value { font-size: 2.6rem; font-weight: 600; line-height: 1; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .power .unit { font-size: 1rem; color: var(--secondary-text-color); }
  .stats { display: flex; gap: 20px; flex-wrap: wrap; }
  .stats > div { display: flex; flex-direction: column; }
  .stat-label { font-size: 0.75rem; color: var(--secondary-text-color); }
  .stat-value { font-size: 1rem; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .tile { display: flex; flex-direction: column; align-items: stretch; gap: 2px; padding: 12px; border-radius: 14px; border: 1px solid var(--divider-color, rgba(0,0,0,.12));
          background: var(--secondary-background-color, rgba(0,0,0,.03)); color: var(--primary-text-color); font: inherit; text-align: left; cursor: pointer; min-width: 0; }
  .tile:disabled { cursor: default; }
  .tile.readonly { opacity: .75; }
  .tile.on { border-color: color-mix(in srgb, var(--fc-charging) 45%, transparent); background: color-mix(in srgb, var(--fc-charging) 10%, transparent); }
  .tile-icon { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; flex: none;
               background: var(--card-background-color, #fff); color: var(--secondary-text-color); }
  .tile.on .tile-icon { color: var(--fc-charging); }
  .tile-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .tile-label { font-weight: 600; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tile-state { font-size: 0.8rem; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .switch { width: 36px; height: 20px; border-radius: 999px; background: var(--disabled-color, #bdbdbd); position: relative; flex: none; transition: background .2s; }
  .switch .knob { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: left .2s; box-shadow: 0 1px 2px rgba(0,0,0,.3); }
  .switch.on { background: var(--fc-charging); }
  .switch.on .knob { left: 18px; }
  .section-title { font-size: 0.8rem; font-weight: 600; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; margin: 16px 0 8px; }
  .segmented { display: grid; grid-template-columns: 1fr 1fr; padding: 3px; border-radius: 12px; background: var(--secondary-background-color, rgba(0,0,0,.05)); gap: 3px; }
  .segmented.dimmed { opacity: .7; }
  .seg { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0; border-radius: 9px; padding: 9px 8px; font: inherit; font-size: .9rem;
         background: transparent; color: var(--secondary-text-color); cursor: pointer; }
  .seg:disabled { cursor: default; }
  .seg.active { background: var(--card-background-color, #fff); color: var(--primary-text-color); box-shadow: 0 1px 3px rgba(0,0,0,.15); font-weight: 600; }
  .seg.active.green svg { color: var(--fc-green); }
  .seg.active.normal svg { color: var(--fc-normal); }
  .hint { font-size: .78rem; color: var(--secondary-text-color); margin-top: 6px; }
  .plan { display: grid; grid-template-columns: 28px auto 1fr auto; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .plan:first-of-type { border-top: 0; }
  .plan.disabled { opacity: .5; }
  .plan-icon { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; }
  .plan-icon.green { color: var(--fc-green); background: color-mix(in srgb, var(--fc-green) 14%, transparent); }
  .plan-icon.normal { color: var(--fc-normal); background: color-mix(in srgb, var(--fc-normal) 14%, transparent); }
  .plan-time { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .plan-days { font-size: .8rem; color: var(--secondary-text-color); }
  .plan-power { font-size: .85rem; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .muted { color: var(--secondary-text-color); font-size: .8rem; }
  .footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px; margin-top: 14px; font-size: .78rem; color: var(--secondary-text-color); }
  .footer svg { vertical-align: -2px; }
  @media (max-width: 420px) {
    .hero { grid-template-columns: 96px 1fr; gap: 12px; }
    .charger { width: 96px; }
    .power .value { font-size: 2.1rem; }
  }
`;

if (!customElements.get("huawei-fusioncharge-card")) {
  customElements.define("huawei-fusioncharge-card", HuaweiFusionChargeCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "huawei-fusioncharge-card",
    name: "Huawei FusionCharge",
    description: "État et commandes de la borne Huawei FusionCharge.",
    preview: true,
  });
  console.info(`%c HUAWEI-FUSIONCHARGE-CARD %c ${CARD_VERSION} `, "background:#2e9d5b;color:#fff", "");
}
