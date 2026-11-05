"""Hintergrund-Aktualisierung.

Der Coordinator läuft im konfigurierten Intervall, liest die Quellen und
stößt den Regelzyklus an. Fehler werden protokolliert und dürfen den
Coordinator nie dauerhaft anhalten.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_UPDATE_INTERVAL_SECONDS, DOMAIN
from .runtime import SolarFlowRuntime

_LOGGER = logging.getLogger(__name__)


class SolarFlowCoordinator(DataUpdateCoordinator[dict]):
    """Aktualisiert den Regelzyklus periodisch."""

    def __init__(self, hass: HomeAssistant, runtime: SolarFlowRuntime) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}",
            update_interval=__import__("datetime").timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS),
        )
        self.runtime = runtime

    async def _async_update_data(self) -> dict:
        try:
            await self.runtime.async_run_cycle()
            return self.runtime.snapshot()
        except Exception as err:  # pragma: no cover - defensiv
            _LOGGER.debug("SolarFlow Update fehlgeschlagen: %s", err)
            raise UpdateFailed(str(err)) from err
