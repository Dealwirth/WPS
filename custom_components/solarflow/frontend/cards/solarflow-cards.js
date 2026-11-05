/**
 * SolarFlow – Dashboard-Karten.
 *
 * Vier fertige Karten zum Ziehen in jede Oberfläche:
 *   - custom:solarflow-status-card   (Zustand + Einspeisung)
 *   - custom:solarflow-gauge-card    (Einspeisung als Bogen)
 *   - custom:solarflow-safety-card   (die zehn Schutz-Ebenen)
 *   - custom:solarflow-mode-card     (Betriebsart umschalten)
 *
 * Bewusst ohne Abhängigkeit zum HA-Frontend: reine Custom Elements mit Shadow
 * DOM. Kein LitElement, kein Bundle-Import – läuft in jeder HA-Version.
 */

const STYLE = `
  :host { --sf-amber:#ffb020; --sf-coral:#ff6b4a; --sf-violet:#7b5cff; --sf-teal:#12c6a5; display:block; }
  ha-card, .card { display:block; border-radius:18px; background: var(--card-background-color, #fff);
    box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12)); overflow:hidden; color: var(--primary-text-color,#111); }
  .head { display:flex; align-items:center; gap:12px; padding:16px 18px 8px; }
  .logo { font-size:22px; width:42px; height:42px; border-radius:14px; display:grid; place-items:center;
    background: linear-gradient(135deg, var(--sf-amber), var(--sf-coral)); }
  .title { font-weight:700; font-size:16px; }
  .sub { font-size:12px; opacity:.6; }
  .body { padding:8px 18px 18px; }
  .chip { display:inline-block; padding:5px 12px; border-radius:999px; font-weight:700; font-size:13px; }
  .chip.normal { background: rgba(18,198,165,.18); color:#12c6a5; }
  .chip.boost { background: rgba(255,176,32,.22); color:#c98a00; }
  .row { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px dashed var(--divider-color, rgba(0,0,0,.1)); }
  .row:last-child { border-bottom:none; }
  .big { font-size:30px; font-weight:800; }
  .modes { display:flex; gap:8px; margin-top:12px; }
  .mode { flex:1; padding:10px; border-radius:12px; border:1px solid var(--divider-color, rgba(0,0,0,.1));
    background:none; cursor:pointer; color: var(--primary-text-color); font: inherit; }
  .mode.sel { background: linear-gradient(135deg, var(--sf-amber), var(--sf-coral)); color:#241300; border:none; font-weight:700; }
  .layer { display:flex; justify-content:space-between; align-items:center; padding:6px 0; font-size:13px; }
  .dot { width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:8px; }
  .dot.ok { background: var(--sf-teal); } .dot.warn { background: var(--sf-amber); }
  .dot.blocked { background: var(--sf-coral); } .dot.active { background: var(--sf-violet); }
  .gaugewrap { display:flex; align-items:center; gap:16px; }
  svg { width:130px; }
  .track { fill:none; stroke: var(--divider-color, rgba(0,0,0,.12)); stroke-width:12; stroke-linecap:round; }
  .fill { fill:none; stroke: var(--sf-amber); stroke-width:12; stroke-linecap:round; transition: stroke-dashoffset .6s ease; }
  .warnbox { background: rgba(255,176,32,.14); color:#a06a00; padding:8px 12px; border-radius:10px; font-size:12.5px; margin-top:10px; }
`;

const STATE_ENTITY = "sensor.solarflow_zustand";
const L = {
  de: { feedin: "Einspeisung", state: "Zustand", storage: "Speicher", layers: "Schutz-Ebenen", mode: "Betriebsart", normal: "Normal", boost: "Überschuss", off: "Aus", shadow: "Schatten", active: "Aktiv", blocked: "Blockiert", ok: "Frei", warn: "Achtung", noData: "Keine Daten" },
  en: { feedin: "Feed-in", state: "State", storage: "Storage", layers: "Safety layers", mode: "Mode", normal: "Normal", boost: "Surplus", off: "Off", shadow: "Shadow", active: "Active", blocked: "Blocked", ok: "Clear", warn: "Attention", noData: "No data" },
};
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class SFBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._snap = null;
    this._bound = false;
  }
  setConfig(config) {
    this._config = config || {};
  }
  getCardSize() {
    return 3;
  }
  set hass(hass) {
    this._hass = hass;
    if (!this._bound && hass) {
      this._bound = true;
      this._subscribe();
    }
    this._render();
  }
  get hass() {
    return this._hass;
  }
  async _subscribe() {
    try {
      this._unsub = await this._hass.connection.subscribeMessage(
        (msg) => {
          this._snap = msg;
          this._render();
        },
        { type: "solarflow/snapshot" }
      );
    } catch (e) {
      /* Karte funktioniert auch ohne Snapshot über Entitäten */
    }
  }
  disconnectedCallback() {
    if (this._unsub) this._unsub();
    this._unsub = null;
    this._bound = false;
  }
  _lang() {
    return (this._hass && (this._hass.language || "").startsWith("en")) ? "en" : "de";
  }
  t(key) {
    return (L[this._lang()] || L.de)[key] || key;
  }
  _attrs() {
    const st = this._hass && this._hass.states[STATE_ENTITY];
    return (st && st.attributes) || {};
  }
  _render() {
    if (!this._hass) return;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>${this._template()}`;
    this._wire();
  }
  _wire() {
    this.shadowRoot.querySelectorAll("[data-mode]").forEach((el) =>
      el.addEventListener("click", async () => {
        await this._hass.connection.sendMessagePromise({ type: "solarflow/set_mode", mode: el.dataset.mode });
      })
    );
  }
  _template() {
    return "";
  }
}

class SolarFlowStatusCard extends SFBase {
  _template() {
    const a = this._attrs();
    const s = this._snap || {};
    const feed = s.feed_in_w != null ? s.feed_in_w : a.einspeisung_w;
    const storage = s.storage_temp != null ? s.storage_temp : a.speicher_c;
    const isBoost = s.state === "boost" || (this._hass.states[STATE_ENTITY] || {}).state === "Überschuss";
    return `<ha-card>
      <div class="head"><div class="logo">☀️</div>
        <div><div class="title">SolarFlow</div><div class="sub">${this.t("state")}</div></div>
        <div style="margin-left:auto"><span class="chip ${isBoost ? "boost" : "normal"}">${isBoost ? this.t("boost") : this.t("normal")}</span></div>
      </div>
      <div class="body">
        <div class="row"><span>${this.t("feedin")}</span><span class="big">${feed != null ? Math.round(feed) : "–"} W</span></div>
        <div class="row"><span>${this.t("storage")}</span><span>${storage != null ? storage + " °C" : "–"}</span></div>
        ${a.blockiert ? `<div class="warnbox">🛡 ${esc(a.grund || this.t("blocked"))}</div>` : ""}
      </div></ha-card>`;
  }
  static getStubConfig() {
    return {};
  }
}

class SolarFlowGaugeCard extends SFBase {
  _template() {
    const a = this._attrs();
    const s = this._snap || {};
    const feed = s.feed_in_w != null ? s.feed_in_w : a.einspeisung_w || 0;
    const pct = Math.max(0, Math.min(100, (feed / 3000) * 100));
    const len = 220;
    return `<ha-card>
      <div class="head"><div class="logo">⚡</div><div><div class="title">${this.t("feedin")}</div></div></div>
      <div class="body"><div class="gaugewrap">
        <svg viewBox="0 0 200 120">
          <path class="track" d="M20 110 A80 80 0 0 1 180 110" />
          <path class="fill" d="M20 110 A80 80 0 0 1 180 110" style="stroke-dasharray:${len};stroke-dashoffset:${len - (len * pct) / 100}" />
        </svg>
        <div><div class="big">${Math.round(feed)} W</div><div class="sub">${this.t("feedin")}</div></div>
      </div></div></ha-card>`;
  }
  static getStubConfig() {
    return {};
  }
}

class SolarFlowSafetyCard extends SFBase {
  _template() {
    const layers = (this._snap || {}).layers || [];
    const de = this._lang() === "de";
    const rows = layers
      .map(
        (l) => `<div class="layer"><span><span class="dot ${l.status}"></span>${l.idx}. ${esc(de ? l.name_de : l.name_en)}</span>
        <span class="sub">${l.status === "blocked" ? this.t("blocked") : l.status === "warn" ? this.t("warn") : this.t("ok")}</span></div>`
      )
      .join("");
    return `<ha-card>
      <div class="head"><div class="logo">🛡️</div><div><div class="title">${this.t("layers")}</div></div></div>
      <div class="body">${layers.length === 0 ? `<div class="sub">${this.t("noData")}</div>` : rows}</div></ha-card>`;
  }
  static getStubConfig() {
    return {};
  }
}

class SolarFlowModeCard extends SFBase {
  _template() {
    const mode = this._snap ? this._snap.mode : null;
    const btns = ["off", "shadow", "active"]
      .map((m) => `<button class="mode ${mode === m ? "sel" : ""}" data-mode="${m}">${this.t(m)}</button>`)
      .join("");
    return `<ha-card>
      <div class="head"><div class="logo">🎛️</div><div><div class="title">${this.t("mode")}</div></div></div>
      <div class="body"><div class="modes">${btns}</div></div></ha-card>`;
  }
  static getStubConfig() {
    return {};
  }
}

customElements.define("solarflow-status-card", SolarFlowStatusCard);
customElements.define("solarflow-gauge-card", SolarFlowGaugeCard);
customElements.define("solarflow-safety-card", SolarFlowSafetyCard);
customElements.define("solarflow-mode-card", SolarFlowModeCard);

window.customCards = window.customCards || [];
window.customCards.push(
  { type: "solarflow-status-card", name: "SolarFlow Status", description: "Zustand und Einspeisung / State and feed-in" },
  { type: "solarflow-gauge-card", name: "SolarFlow Gauge", description: "Einspeisung als Bogen / Feed-in as a gauge" },
  { type: "solarflow-safety-card", name: "SolarFlow Sicherheit", description: "Zehn Schutz-Ebenen / Ten safety layers" },
  { type: "solarflow-mode-card", name: "SolarFlow Betriebsart", description: "Aus/Schatten/Aktiv / Off/Shadow/Active" }
);
