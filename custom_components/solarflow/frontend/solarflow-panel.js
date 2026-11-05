/**
 * SolarFlow – Bedienoberfläche (Seitenleisten-Panel).
 *
 * Bewusst ohne jede Abhängigkeit zum Home-Assistant-Frontend (kein LitElement,
 * kein Bundle-Import). Ein reines Custom Element mit Shadow DOM rendert die
 * Seite aus einfachen Template-Strings. Dadurch lädt das Panel in jeder
 * HA-Version und auch offline zuverlässig.
 *
 * Deutsch und Englisch, umschaltbar. Vier Bereiche: Schutz-Ebenen, Module,
 * Einstellungen und Protokoll. Ein großer Regler und ein Not-Aus oben.
 */

const T = {
  de: {
    title: "SolarFlow",
    subtitle: "Wärme und Laden in die Sonne schieben – sicher.",
    mode: "Betriebsart",
    off: "Aus",
    shadow: "Schatten",
    active: "Aktiv",
    offHint: "Nur Schutz und Anzeige.",
    shadowHint: "Beobachten und vorschlagen, nicht schalten.",
    activeHint: "Automatik scharf, Grenzen bleiben aktiv.",
    feedin: "Einspeisung",
    storage: "Speicher",
    state: "Zustand",
    normal: "Normal",
    boost: "Überschuss",
    layers: "Schutz-Ebenen",
    store: "Module",
    settings: "Einstellungen",
    log: "Protokoll",
    emergency: "NOT-AUS",
    emergencyOn: "Not-Aus aktiv – alles gesperrt",
    reset: "Not-Aus aufheben",
    save: "Speichern",
    saved: "Gespeichert",
    why: "Warum gerade so?",
    mandatory: "Pflicht",
    blocked: "Blockiert",
    ok: "Frei",
    warn: "Achtung",
    activeLayer: "Aktiv",
    feedOn: "Ein bei (W)",
    feedOff: "Aus bei (W)",
    boostTemp: "Boost-Temperatur (°C)",
    normalTemp: "Normaltemperatur (°C)",
    minRun: "Mindestlaufzeit (min)",
    minPause: "Mindestpause (min)",
    maxAge: "Max. Datenalter (s)",
    sources: "Quellen",
    changed: "Umschaltungen",
    loading: "SolarFlow lädt …",
    noData: "Keine Daten – bitte Quellen prüfen.",
  },
  en: {
    title: "SolarFlow",
    subtitle: "Push heat and charging into the sun – safely.",
    mode: "Mode",
    off: "Off",
    shadow: "Shadow",
    active: "Active",
    offHint: "Protection and display only.",
    shadowHint: "Observe and suggest, do not switch.",
    activeHint: "Automation armed, limits stay active.",
    feedin: "Feed-in",
    storage: "Storage",
    state: "State",
    normal: "Normal",
    boost: "Surplus",
    layers: "Safety layers",
    store: "Modules",
    settings: "Settings",
    log: "Log",
    emergency: "EMERGENCY STOP",
    emergencyOn: "Emergency stop active – all locked",
    reset: "Clear emergency stop",
    save: "Save",
    saved: "Saved",
    why: "Why this state?",
    mandatory: "Required",
    blocked: "Blocked",
    ok: "Clear",
    warn: "Attention",
    activeLayer: "Active",
    feedOn: "On at (W)",
    feedOff: "Off at (W)",
    boostTemp: "Boost temperature (°C)",
    normalTemp: "Normal temperature (°C)",
    minRun: "Minimum run (min)",
    minPause: "Minimum pause (min)",
    maxAge: "Max data age (s)",
    sources: "Sources",
    changed: "Switches",
    loading: "SolarFlow loading …",
    noData: "No data – please check sources.",
  },
};

const STYLE = `
  :host {
    --sf-amber: #ffb020; --sf-coral: #ff6b4a; --sf-violet: #7b5cff; --sf-teal: #12c6a5;
    display: block; min-height: 100vh; color: #eef1ff;
    background: radial-gradient(1200px 600px at 15% -10%, #1b2150 0%, #0b1030 45%, #070a1c 100%);
    font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
  }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 20px 18px 60px; }
  .wrap.alarm { box-shadow: inset 0 0 0 4px var(--sf-coral); }
  header { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .logo { font-size: 30px; width: 56px; height: 56px; border-radius: 18px; display: grid; place-items: center;
    background: linear-gradient(135deg, var(--sf-amber), var(--sf-coral)); box-shadow: 0 10px 30px rgba(255,140,60,.35); }
  h1 { margin: 0; font-size: 26px; letter-spacing: .5px; }
  header p { margin: 2px 0 0; opacity: .7; font-size: 13px; }
  .head-actions { display: flex; gap: 10px; }
  button { cursor: pointer; border: none; border-radius: 12px; font: inherit; padding: 10px 16px; }
  .ghost { background: rgba(255,255,255,.08); color: #eef1ff; }
  .danger { background: linear-gradient(135deg,#ff5d5d,#c22); color: #fff; font-weight: 700; }
  .danger.pulse { animation: pulse 1.2s infinite; }
  @keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,80,80,.6);} 50% { box-shadow: 0 0 0 12px rgba(255,80,80,0);} }
  .hero { margin-top: 22px; display: grid; grid-template-columns: 300px 1fr; gap: 22px;
    background: linear-gradient(135deg, rgba(255,176,32,.10), rgba(123,92,255,.12));
    border: 1px solid rgba(255,255,255,.09); border-radius: 24px; padding: 22px; }
  .gauge { position: relative; }
  .gauge svg { width: 100%; }
  .track { fill: none; stroke: rgba(255,255,255,.12); stroke-width: 14; stroke-linecap: round; }
  .fill { fill: none; stroke: var(--sf-amber); stroke-width: 14; stroke-linecap: round; transition: stroke-dashoffset .6s ease; }
  .gauge-val { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .gauge-val strong { font-size: 40px; line-height: 1; }
  .gauge-val span { font-size: 14px; opacity: .7; }
  .gauge-val em { font-style: normal; font-size: 12px; opacity: .6; margin-top: 4px; }
  .hero-info { display: flex; flex-direction: column; gap: 12px; }
  .chip { align-self: flex-start; padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 14px; }
  .chip.normal { background: rgba(18,198,165,.2); color: #6ef2d6; }
  .chip.boost { background: rgba(255,176,32,.22); color: #ffd27a; }
  .stat { display: flex; justify-content: space-between; border-bottom: 1px dashed rgba(255,255,255,.12); padding-bottom: 6px; }
  .stat span { opacity: .7; }
  .why { font-size: 13px; opacity: .85; background: rgba(255,255,255,.05); padding: 8px 10px; border-radius: 10px; }
  .modes { display: flex; gap: 10px; margin-top: 6px; }
  .mode { flex: 1; text-align: left; background: rgba(255,255,255,.06); color: #eef1ff; padding: 12px; }
  .mode b { display: block; font-size: 15px; }
  .mode small { opacity: .6; font-size: 11px; }
  .mode.sel { background: linear-gradient(135deg, var(--sf-amber), var(--sf-coral)); color: #241300; }
  .tabs { display: flex; gap: 8px; margin: 24px 0 14px; flex-wrap: wrap; }
  .tab { background: rgba(255,255,255,.06); color: #eef1ff; }
  .tab.sel { background: linear-gradient(135deg, var(--sf-violet), var(--sf-teal)); color: #fff; }
  h2 { font-size: 16px; margin: 22px 0 10px; opacity: .85; }
  .layers { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }
  .layer { display: grid; grid-template-columns: 34px 1fr auto; gap: 6px 10px; align-items: center;
    background: rgba(255,255,255,.05); border-radius: 14px; padding: 10px 12px; border-left: 4px solid #4a5580; }
  .layer.ok { border-left-color: var(--sf-teal); }
  .layer.warn { border-left-color: var(--sf-amber); }
  .layer.blocked { border-left-color: var(--sf-coral); }
  .layer.active { border-left-color: var(--sf-violet); }
  .idx { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: rgba(255,255,255,.1); font-size: 12px; }
  .lname { font-weight: 600; }
  .lstatus { font-size: 11px; opacity: .8; }
  .ldetail { grid-column: 2 / -1; font-size: 12px; opacity: .65; }
  .steps { margin: 0; padding-left: 20px; font-size: 13px; }
  .steps li { margin: 4px 0; }
  .steps li.s-warn { color: #ffd27a; } .steps li.s-blocked { color: #ff9b8a; }
  .store { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
  .card { display: flex; gap: 12px; align-items: flex-start; background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.08); border-radius: 16px; padding: 14px; }
  .card.on { background: linear-gradient(135deg, rgba(18,198,165,.14), rgba(123,92,255,.14)); border-color: rgba(18,198,165,.4); }
  .cicon { font-size: 22px; }
  .cbody { flex: 1; }
  .ctitle { font-weight: 700; display: flex; align-items: center; gap: 8px; }
  .badge { font-size: 10px; background: rgba(255,255,255,.15); padding: 2px 8px; border-radius: 999px; }
  .csum { font-size: 12.5px; opacity: .8; margin-top: 4px; }
  .creason { font-size: 11.5px; opacity: .55; margin-top: 4px; font-style: italic; }
  .switch { position: relative; width: 46px; height: 26px; flex: none; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch span { position: absolute; inset: 0; background: rgba(255,255,255,.2); border-radius: 999px; transition: .2s; }
  .switch span::before { content: ""; position: absolute; width: 20px; height: 20px; left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: .2s; }
  .switch input:checked + span { background: linear-gradient(135deg, var(--sf-teal), var(--sf-violet)); }
  .switch input:checked + span::before { transform: translateX(20px); }
  .switch input:disabled + span { opacity: .4; }
  .srow { display: grid; grid-template-columns: 220px 1fr 70px; gap: 12px; align-items: center; margin: 8px 0; }
  .srow label { font-size: 13px; opacity: .85; }
  .srow output { text-align: right; font-variant-numeric: tabular-nums; opacity: .9; }
  input[type=range] { accent-color: var(--sf-amber); }
  .primary { margin-top: 16px; background: linear-gradient(135deg, var(--sf-teal), var(--sf-violet)); color: #fff; font-weight: 700; }
  .sources { display: grid; gap: 6px; }
  .src { display: flex; justify-content: space-between; font-size: 12.5px; background: rgba(255,255,255,.04); padding: 8px 10px; border-radius: 10px; }
  .src code { opacity: .8; }
  .log { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; max-height: 420px; overflow: auto; }
  .le { display: grid; grid-template-columns: 70px 1fr; gap: 10px; padding: 6px 10px; border-radius: 8px; background: rgba(255,255,255,.04); }
  .le.warn { background: rgba(255,176,32,.12); } .le.err { background: rgba(255,90,90,.14); } .le.ok { background: rgba(18,198,165,.1); }
  .le time { opacity: .6; }
  .loading { padding: 60px; text-align: center; opacity: .7; }
  @media (max-width: 760px) { .hero { grid-template-columns: 1fr; } .srow { grid-template-columns: 1fr; } }
`;

const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class SolarFlowPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._snap = null;
    this._lang = localStorage.getItem("solarflow_lang") || (navigator.language || "de").slice(0, 2);
    if (this._lang !== "de" && this._lang !== "en") this._lang = "de";
    this._tab = "home";
    this._draft = null;
    this._bound = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._bound && hass) {
      this._bound = true;
      this._subscribe();
    }
  }
  get hass() {
    return this._hass;
  }

  disconnectedCallback() {
    if (this._unsub) this._unsub();
    this._unsub = null;
    this._bound = false;
  }

  async _subscribe() {
    try {
      this._unsub = await this._hass.connection.subscribeMessage(
        (msg) => {
          this._snap = msg;
          if (!this._draft) this._draft = { ...msg.settings };
          this._render();
        },
        { type: "solarflow/snapshot" }
      );
    } catch (e) {
      this._render();
    }
  }

  t(key) {
    return (T[this._lang] || T.de)[key] || key;
  }

  async _send(msg) {
    try {
      return await this._hass.connection.sendMessagePromise(msg);
    } catch (e) {
      return null;
    }
  }

  async _setMode(mode) {
    const r = await this._send({ type: "solarflow/set_mode", mode });
    if (r) {
      this._snap = r;
      this._render();
    }
  }

  async _emergency(on) {
    const r = await this._send({ type: "solarflow/emergency", on });
    if (r) {
      this._snap = r;
      this._render();
    }
  }

  async _saveSettings() {
    const r = await this._send({ type: "solarflow/set_settings", settings: this._draft });
    if (r) {
      this._snap = r;
      this._draft = { ...r.settings };
      this._render();
      this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message: this.t("saved") }, bubbles: true, composed: true }));
    }
  }

  async _toggleModule(id, enabled) {
    const r = await this._send({ type: "solarflow/set_module", module_id: id, enabled });
    if (r && this._snap) {
      this._snap = { ...this._snap, modules: r.modules };
      this._render();
    }
  }

  _num(key, value) {
    this._draft = { ...this._draft, [key]: Number(value) };
    const out = this.shadowRoot.querySelector(`output[data-out="${key}"]`);
    if (out) out.textContent = String(value);
  }

  _statusLabel(status) {
    if (status === "blocked") return this.t("blocked");
    if (status === "warn") return this.t("warn");
    if (status === "active") return this.t("activeLayer");
    return this.t("ok");
  }

  _render() {
    const s = this._snap;
    if (!s) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><div class="wrap"><div class="loading">${this.t("loading")}</div></div>`;
      return;
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>${this._template(s)}`;
    this._wire();
  }

  _wire() {
    const r = this.shadowRoot;
    r.querySelectorAll("[data-mode]").forEach((el) => el.addEventListener("click", () => this._setMode(el.dataset.mode)));
    r.querySelectorAll("[data-emergency]").forEach((el) =>
      el.addEventListener("click", () => this._emergency(el.dataset.emergency === "1"))
    );
    r.querySelectorAll("[data-tab]").forEach((el) => el.addEventListener("click", () => { this._tab = el.dataset.tab; this._render(); }));
    const lang = r.querySelector("[data-lang]");
    if (lang) lang.addEventListener("click", () => { this._lang = this._lang === "de" ? "en" : "de"; localStorage.setItem("solarflow_lang", this._lang); this._render(); });
    const save = r.querySelector("[data-save]");
    if (save) save.addEventListener("click", () => this._saveSettings());
    r.querySelectorAll("input[data-range]").forEach((el) => el.addEventListener("input", () => this._num(el.dataset.range, el.value)));
    r.querySelectorAll("input[data-module]").forEach((el) =>
      el.addEventListener("change", () => this._toggleModule(el.dataset.module, el.checked))
    );
  }

  _template(s) {
    return `<div class="wrap ${s.emergency_stop ? "alarm" : ""}">
      ${this._header(s)} ${this._hero(s)} ${this._tabs()}
      <div class="panel">
        ${this._tab === "home" ? this._home(s) : ""}
        ${this._tab === "store" ? this._store(s) : ""}
        ${this._tab === "settings" ? this._settings(s) : ""}
        ${this._tab === "log" ? this._log(s) : ""}
      </div>
    </div>`;
  }

  _header(s) {
    return `<header>
      <div class="brand"><div class="logo">☀️</div><div><h1>${this.t("title")}</h1><p>${this.t("subtitle")}</p></div></div>
      <div class="head-actions">
        <button class="ghost" data-lang>${this._lang.toUpperCase()}</button>
        <button class="danger ${s.emergency_stop ? "pulse" : ""}" data-emergency="${s.emergency_stop ? "0" : "1"}">
          ${s.emergency_stop ? this.t("reset") : this.t("emergency")}</button>
      </div>
    </header>`;
  }

  _hero(s) {
    const pct = Math.max(-100, Math.min(100, ((s.feed_in_w || 0) / 3000) * 100));
    const len = 251;
    const off = len - (len * Math.max(0, pct)) / 100;
    const stateLabel = s.state === "boost" ? this.t("boost") : this.t("normal");
    const modes = ["off", "shadow", "active"]
      .map(
        (m) => `<button class="mode ${s.mode === m ? "sel" : ""}" data-mode="${m}">
          <b>${this.t(m)}</b><small>${this.t(m + "Hint")}</small></button>`
      )
      .join("");
    return `<section class="hero">
      <div class="gauge">
        <svg viewBox="0 0 200 120">
          <path class="track" d="M20 110 A80 80 0 0 1 180 110" />
          <path class="fill" d="M20 110 A80 80 0 0 1 180 110" style="stroke-dasharray:${len};stroke-dashoffset:${off}" />
        </svg>
        <div class="gauge-val"><strong>${s.feed_in_w != null ? Math.round(s.feed_in_w) : "–"}</strong><span>W</span><em>${this.t("feedin")}</em></div>
      </div>
      <div class="hero-info">
        <div class="chip ${s.state}">${stateLabel}</div>
        <div class="stat"><span>${this.t("storage")}</span><b>${s.storage_temp != null ? s.storage_temp + " °C" : "–"}</b></div>
        <div class="stat"><span>${this.t("changed")}</span><b>${s.machine_changes}</b></div>
        <div class="why">${s.blocked ? "🛡 " : "✅ "}${esc(s.reason_de || "")}</div>
        <div class="modes">${modes}</div>
      </div>
    </section>`;
  }

  _tabs() {
    const tabs = [["home", this.t("layers")], ["store", this.t("store")], ["settings", this.t("settings")], ["log", this.t("log")]];
    return `<nav class="tabs">${tabs
      .map(([id, label]) => `<button class="tab ${this._tab === id ? "sel" : ""}" data-tab="${id}">${label}</button>`)
      .join("")}</nav>`;
  }

  _home(s) {
    const layers = (s.layers || [])
      .map(
        (l) => `<div class="layer ${l.status}">
          <div class="idx">${l.idx}</div>
          <div class="lname">${esc(this._lang === "de" ? l.name_de : l.name_en)}</div>
          <div class="lstatus">${this._statusLabel(l.status)}</div>
          <div class="ldetail">${esc(this._lang === "de" ? l.detail_de : l.detail_en)}</div>
        </div>`
      )
      .join("");
    const steps = (s.steps || []).map((st) => `<li class="s-${st.status}">${esc(st.text)}</li>`).join("");
    return `<h2>${this.t("layers")}</h2><div class="layers">${layers}</div>
      <h2>${this.t("why")}</h2><ol class="steps">${steps}</ol>`;
  }

  _store(s) {
    const cats = { base: "🧩", devices: "🔧", energy: "⚡", intelligence: "🧠", safety: "🛡️" };
    const cards = (s.modules || [])
      .map(
        (m) => `<div class="card ${m.enabled ? "on" : ""}">
          <div class="cicon">${cats[m.category] || "📦"}</div>
          <div class="cbody">
            <div class="ctitle">${esc(this._lang === "de" ? m.name_de : m.name_en)}${!m.optional ? `<span class="badge">${this.t("mandatory")}</span>` : ""}</div>
            <div class="csum">${esc(this._lang === "de" ? m.summary_de : m.summary_en)}</div>
            <div class="creason">${esc(this._lang === "de" ? m.reason_de : m.reason_en)}</div>
          </div>
          <label class="switch"><input type="checkbox" data-module="${m.module_id}" ${m.enabled ? "checked" : ""} ${!m.optional ? "disabled" : ""}/><span></span></label>
        </div>`
      )
      .join("");
    return `<h2>${this.t("store")}</h2><div class="store">${cards}</div>`;
  }

  _settings(s) {
    if (!this._draft) return "";
    const d = this._draft;
    const row = (key, label, min, max, step) => `<div class="srow">
      <label>${label}</label>
      <input type="range" data-range="${key}" min="${min}" max="${max}" step="${step}" value="${d[key]}"/>
      <output data-out="${key}">${d[key]}</output></div>`;
    const sources = Object.entries(s.sources || {})
      .map(([k, v]) => `<div class="src"><span>${esc(k)}</span><code>${esc(v || "–")}</code></div>`)
      .join("");
    return `<h2>${this.t("settings")}</h2>
      ${row("feed_in_on_w", this.t("feedOn"), 0, 8000, 50)}
      ${row("feed_in_off_w", this.t("feedOff"), 0, 8000, 50)}
      ${row("ww_boost_temp", this.t("boostTemp"), 40, 60, 1)}
      ${row("ww_normal_temp", this.t("normalTemp"), 35, 60, 1)}
      ${row("min_runtime_min", this.t("minRun"), 0, 120, 1)}
      ${row("min_pause_min", this.t("minPause"), 0, 120, 1)}
      ${row("sensor_max_age_s", this.t("maxAge"), 30, 1800, 10)}
      <button class="primary" data-save>${this.t("save")}</button>
      <h2>${this.t("sources")}</h2><div class="sources">${sources}</div>`;
  }

  _log(s) {
    const rows = (s.audit || []).map((e) => `<div class="le ${e.level}"><time>${esc(e.t)}</time><span>${esc(e.text)}</span></div>`).join("");
    return `<h2>${this.t("log")}</h2><div class="log">${rows}</div>`;
  }
}

customElements.define("solarflow-panel", SolarFlowPanel);
