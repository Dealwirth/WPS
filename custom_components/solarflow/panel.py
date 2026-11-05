"""Seitenleisten-Panel und Dashboard-Karten.

Registriert das SolarFlow-Panel (Lovelace-unabhängig) und liefert die
Dashboard-Karten als statische Dateien unter ``/solarflow_cards/``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    CARDS_URL,
    DOMAIN,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PANEL_WEBCOMPONENT,
    STATIC_URL,
)

_LOGGER = logging.getLogger(__name__)


def _read_manifest_version() -> str:
    """Manifest-Version lesen (läuft im Executor, nicht im Event-Loop)."""
    try:
        manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
        return str(manifest.get("version", "0"))
    except Exception:  # pragma: no cover - defensiv
        return "0"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Panel und statische Dateien einmalig registrieren."""
    if hass.data.get(f"{DOMAIN}_panel_ready"):
        return

    base = Path(__file__).parent / "frontend"
    cards = base / "cards"
    # Cache-Buster aus der Manifest-Version, damit Browser nach einem Update
    # garantiert die neue Fassung laden. Dateizugriff läuft im Executor, damit
    # der Event-Loop nicht blockiert.
    version = await hass.async_add_executor_job(_read_manifest_version)

    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(STATIC_URL, str(base), cache_headers=False),
                StaticPathConfig(CARDS_URL, str(cards), cache_headers=False),
            ]
        )
    except RuntimeError:
        # Bereits registriert – unkritisch.
        _LOGGER.debug("SolarFlow statische Pfade waren bereits registriert")

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_WEBCOMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{STATIC_URL}/solarflow-panel.js?v={version}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
        config={"domain": DOMAIN},
    )

    # Karten als Lovelace-Ressourcen registrieren (idempotent).
    try:
        await _async_register_cards(hass, version)
    except Exception as err:  # pragma: no cover - defensiv
        _LOGGER.debug("Karten konnten nicht automatisch registriert werden: %s", err)

    hass.data[f"{DOMAIN}_panel_ready"] = True


async def _async_register_cards(hass: HomeAssistant, version: str = "0") -> None:
    """Fügt die Karten-JS als Lovelace-Ressource hinzu, falls noch nicht da."""
    url = f"{CARDS_URL}/solarflow-cards.js?v={version}"
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        return
    try:
        existing = resources.async_items()
    except Exception:
        existing = []
    if any(r.get("url", "").startswith(CARDS_URL) for r in existing):
        return
    try:
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:
        pass
