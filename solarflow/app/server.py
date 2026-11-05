"""SolarFlow Add-on Server.

Ein schlanker HTTP-Server (aiohttp), der die Bedienoberflaeche ausliefert und
eine kleine JSON-API bereitstellt. Er laeuft im Add-on-Container und ist ueber
Home-Assistant-Ingress erreichbar – der Nutzer oeffnet ihn wie jede andere App.

Kein Token liegt jemals im Browser: die Oberflaeche spricht nur mit diesem
Server, der wiederum ueber den Supervisor mit Home Assistant spricht.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from aiohttp import web
from core.discovery import EntityInfo, suggest
from engine import SolarFlowEngine
from ha_client import HomeAssistantClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
_LOGGER = logging.getLogger("solarflow.server")

STATIC_DIR = Path(__file__).parent / "static"


def _options() -> dict[str, Any]:
    path = os.environ.get("SOLARFLOW_OPTIONS_FILE", "/data/options.json")
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def _suggestions(client: HomeAssistantClient) -> list[dict[str, Any]]:
    infos = [
        EntityInfo(
            entity_id=e["entity_id"],
            domain=e["domain"],
            name=e.get("name") or "",
            device_class=e.get("device_class"),
            unit=e.get("unit"),
            state=e.get("state"),
        )
        for e in client.entity_catalog()
    ]
    return [
        {
            "role": s.role,
            "label_de": s.label_de,
            "label_en": s.label_en,
            "entity_id": s.entity_id,
            "confidence": round(s.confidence, 2),
            "note_de": s.note_de,
            "candidates": s.candidates,
        }
        for s in suggest(infos)
    ]


async def create_app() -> web.Application:
    app = web.Application()

    client = HomeAssistantClient()
    engine = SolarFlowEngine(client, os.environ.get("SOLARFLOW_DATA_DIR", "/data"))
    engine.load(_options())
    app["client"] = client
    app["engine"] = engine

    # ---------------------------------------------------------------- #
    # Regelzyklus: alle 15 s und bei jeder Zustandsaenderung.
    # ---------------------------------------------------------------- #
    async def cycle_loop() -> None:
        while True:
            try:
                await engine.async_run_cycle()
            except Exception:  # defensiv
                _LOGGER.debug("Zyklus fehlgeschlagen", exc_info=True)
            # Sofort weiter, wenn sich eine Quelle aendert – sonst alle 15 s.
            await engine.wait_for_change(timeout=15)

    async def on_startup(_app: web.Application) -> None:
        await client.start()
        # Kurz warten, damit der erste Snapshot echte Werte hat.
        await client.wait_connected(timeout=25.0)
        engine.bind()
        _app["cycle_task"] = asyncio.create_task(cycle_loop())

    async def on_cleanup(_app: web.Application) -> None:
        task = _app.get("cycle_task")
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await client.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # ---------------------------------------------------------------- #
    # Statische Dateien
    # ---------------------------------------------------------------- #
    async def index(_req: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    app.router.add_get("/", index)
    app.router.add_static("/static", STATIC_DIR, name="static")

    # ---------------------------------------------------------------- #
    # API
    # ---------------------------------------------------------------- #
    async def health(_req: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "connected": client.connected})

    async def snapshot(_req: web.Request) -> web.Response:
        return web.json_response(engine.snapshot())

    async def entities(_req: web.Request) -> web.Response:
        return web.json_response(client.entity_catalog())

    async def suggestions(_req: web.Request) -> web.Response:
        return web.json_response(_suggestions(client))

    async def set_mode(req: web.Request) -> web.Response:
        body = await req.json()
        mode = str(body.get("mode", "shadow"))
        if mode not in ("off", "shadow", "active"):
            raise web.HTTPBadRequest(text="ungueltige Betriebsart")
        await engine.set_mode(mode)
        return web.json_response(engine.snapshot())

    async def set_settings(req: web.Request) -> web.Response:
        body = await req.json()
        values = body.get("settings", body)
        notes = await engine.set_settings(dict(values))
        return web.json_response({"notes": notes, "snapshot": engine.snapshot()})

    async def set_module(req: web.Request) -> web.Response:
        body = await req.json()
        ok, msg = await engine.set_module(str(body.get("module_id")), bool(body.get("enabled")))
        if not ok:
            raise web.HTTPBadRequest(text=msg)
        return web.json_response(engine.snapshot())

    async def set_emergency(req: web.Request) -> web.Response:
        body = await req.json()
        await engine.set_emergency(bool(body.get("on")))
        return web.json_response(engine.snapshot())

    async def set_boost(req: web.Request) -> web.Response:
        body = await req.json()
        await engine.force_boost(bool(body.get("on")))
        return web.json_response(engine.snapshot())

    async def set_sources(req: web.Request) -> web.Response:
        body = await req.json()
        await engine.set_sources(dict(body.get("sources", body)))
        engine.log("ok", "Quellen gespeichert.")
        await engine.async_run_cycle()
        return web.json_response(engine.snapshot())

    async def run_cycle(_req: web.Request) -> web.Response:
        await engine.async_run_cycle()
        return web.json_response(engine.snapshot())

    app.router.add_get("/api/health", health)
    app.router.add_get("/api/snapshot", snapshot)
    app.router.add_get("/api/entities", entities)
    app.router.add_get("/api/suggest", suggestions)
    app.router.add_post("/api/mode", set_mode)
    app.router.add_post("/api/settings", set_settings)
    app.router.add_post("/api/module", set_module)
    app.router.add_post("/api/emergency", set_emergency)
    app.router.add_post("/api/boost", set_boost)
    app.router.add_post("/api/sources", set_sources)
    app.router.add_post("/api/cycle", run_cycle)

    return app


def main() -> None:
    port = int(os.environ.get("SOLARFLOW_PORT", "8099"))
    web.run_app(create_app(), host="0.0.0.0", port=port, print=None)


if __name__ == "__main__":
    main()
