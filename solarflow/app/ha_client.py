"""Verbindung von SolarFlow zu Home Assistant.

Das Add-on laeuft neben Home Assistant und spricht ueber den Supervisor-Proxy
mit dem Kern: REST fuer Aktionen, WebSocket fuer Live-Zustaende. Beides nutzt
denselben ``SUPERVISOR_TOKEN`` – es wird nie im Browser sichtbar.

Faellt die Verbindung aus, verbindet der Client selbsttaetig neu und meldet
den Zustand ehrlich weiter. Ein Fehler darf das Add-on nie anhalten.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger("solarflow.ha")

StateCallback = Callable[[dict[str, dict[str, Any]]], Awaitable[None] | None]


def _supervisor_token() -> str:
    return os.environ.get("SUPERVISOR_TOKEN", "") or os.environ.get("SOLARFLOW_HA_TOKEN", "")


class HomeAssistantClient:
    """Schlanker, selbstheilender HA-Client."""

    def __init__(self) -> None:
        self._token = _supervisor_token()
        # Standard: Supervisor-Proxy im Add-on. Fuer lokale Tests uebersteuerbar.
        self._rest = os.environ.get("SOLARFLOW_HA_REST", "http://supervisor/core/api")
        self._ws_url = os.environ.get("SOLARFLOW_HA_WS", "ws://supervisor/core/websocket")
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._states: dict[str, dict[str, Any]] = {}
        self._callbacks: list[StateCallback] = []
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._listen_task: asyncio.Task | None = None
        self._ws_ready = asyncio.Event()
        self.connected = False
        self.last_error: str | None = None

    # ------------------------------------------------------------------ #
    # Lebenszyklus
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def wait_connected(self, timeout: float = 20.0) -> bool:
        try:
            await asyncio.wait_for(self._ws_ready.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def stop(self) -> None:
        for task in (self._listen_task, self._reader_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self._session:
            await self._session.close()

    def add_state_callback(self, cb: StateCallback) -> None:
        self._callbacks.append(cb)

    # ------------------------------------------------------------------ #
    # REST
    # ------------------------------------------------------------------ #
    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def rest_get(self, path: str) -> Any:
        if not self._session:
            raise RuntimeError("Client nicht gestartet")
        timeout = aiohttp.ClientTimeout(total=15)
        async with self._session.get(f"{self._rest}{path}", headers=self._headers, timeout=timeout) as r:
            r.raise_for_status()
            return await r.json()

    async def call_service(self, domain: str, service: str, data: dict[str, Any], entity_id: str | None = None) -> None:
        """Ruft einen HA-Dienst auf (blocking, damit Fehler sofort sichtbar sind)."""
        if not self._session:
            raise RuntimeError("Client nicht gestartet")
        body = dict(data)
        if entity_id:
            body["entity_id"] = entity_id
        timeout = aiohttp.ClientTimeout(total=20)
        url = f"{self._rest}/services/{domain}/{service}"
        async with self._session.post(url, headers=self._headers, json=body, timeout=timeout) as r:
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"{domain}.{service} -> HTTP {r.status}: {text[:200]}")

    async def fetch_states(self) -> list[dict[str, Any]]:
        data = await self.rest_get("/states")
        return list(data) if isinstance(data, list) else []

    # ------------------------------------------------------------------ #
    # WebSocket
    # ------------------------------------------------------------------ #
    async def _listen_loop(self) -> None:
        delay = 1.0
        while True:
            try:
                await self._connect_ws()
                delay = 1.0
                # Erst alle Zustaende laden, dann Live-Updates abonnieren.
                states = await self._ws_command({"type": "get_states"})
                self._states = {s["entity_id"]: s for s in states}
                assert self._ws is not None
                await self._ws.send_json(
                    {"id": self._next_id(), "type": "subscribe_events", "event_type": "state_changed"}
                )
                await self._notify()
                _LOGGER.info("Mit Home Assistant verbunden (%d Entitaeten).", len(self._states))
                if self._reader_task:
                    await self._reader_task
            except asyncio.CancelledError:
                raise
            except Exception as err:  # defensiv: nie abstuerzen
                self.last_error = str(err)
                _LOGGER.warning("HA-WebSocket getrennt (%s) – neuer Versuch in %.0fs", err, delay)
            finally:
                self.connected = False
                self._ws_ready.clear()
                if self._reader_task:
                    self._reader_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._reader_task
                    self._reader_task = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    async def _connect_ws(self) -> None:
        """Handshake, dann sofort den Leser starten (sonst kein Kommando moeglich)."""
        assert self._session is not None
        self._ws = await self._session.ws_connect(self._ws_url, heartbeat=30, timeout=15)
        hello = await self._ws.receive_json()
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unerwartete WS-Begruessung: {hello.get('type')}")
        await self._ws.send_json({"type": "auth", "access_token": self._token})
        auth = await self._ws.receive_json()
        if auth.get("type") != "auth_ok":
            raise RuntimeError("WS-Authentifizierung fehlgeschlagen")
        self.connected = True
        self.last_error = None
        self._ws_ready.set()
        self._reader_task = asyncio.create_task(self._read_loop())

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def _ws_command(self, msg: dict[str, Any]) -> Any:
        assert self._ws is not None
        mid = self._next_id()
        msg = {**msg, "id": mid}
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send_json(msg)
        return await asyncio.wait_for(fut, timeout=20)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self._handle(data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def _handle(self, data: dict[str, Any]) -> None:
        mtype = data.get("type")
        if mtype == "result":
            fut = self._pending.pop(data.get("id"), None)
            if fut and not fut.done():
                if data.get("success"):
                    fut.set_result(data.get("result"))
                else:
                    fut.set_exception(RuntimeError(str(data.get("error"))))
        elif mtype == "event":
            ev = data.get("event", {})
            if ev.get("event_type") == "state_changed":
                new = ev.get("data", {}).get("new_state")
                if new and new.get("entity_id"):
                    self._states[new["entity_id"]] = new
                    await self._notify()

    async def _notify(self) -> None:
        for cb in list(self._callbacks):
            try:
                res = cb(self._states)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:  # defensiv
                _LOGGER.debug("State-Callback fehlgeschlagen", exc_info=True)

    # ------------------------------------------------------------------ #
    # Zugriff
    # ------------------------------------------------------------------ #
    def state(self, entity_id: str | None) -> dict[str, Any] | None:
        if not entity_id:
            return None
        return self._states.get(entity_id)

    def value(self, entity_id: str | None) -> float | None:
        st = self.state(entity_id)
        if st is None:
            return None
        try:
            return float(st.get("state"))
        except (ValueError, TypeError):
            return None

    def entity_catalog(self) -> list[dict[str, Any]]:
        """Kompakter Katalog fuer die Auswahl in der Oberflaeche."""
        out = []
        for eid, st in self._states.items():
            attrs = st.get("attributes", {})
            out.append(
                {
                    "entity_id": eid,
                    "domain": eid.split(".")[0],
                    "name": attrs.get("friendly_name", eid),
                    "device_class": attrs.get("device_class"),
                    "unit": attrs.get("unit_of_measurement"),
                    "state": st.get("state"),
                }
            )
        out.sort(key=lambda e: (e["domain"], e["entity_id"]))
        return out
