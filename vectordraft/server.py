"""PlotCAD Studio web server — FastAPI backend."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from vectordraft.job_manager import JobManager
from vectordraft.model import PenLibrary
from vectordraft.serial_stream import available_ports

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_JOBS_DIR = Path.cwd() / "plotcad_jobs"


def create_app(*, jobs_dir: Path | None = None) -> FastAPI:
    """Create and configure the PlotCAD Studio FastAPI app."""
    _jobs_dir = jobs_dir or DEFAULT_JOBS_DIR
    manager = JobManager(_jobs_dir)
    pen_library = PenLibrary.iso_default()
    ws_clients: list[WebSocket] = []

    app = FastAPI(title="PlotCAD Studio", version="0.1.0")

    # Serve static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---------- UI root ----------

    @app.get("/", response_class=HTMLResponse)
    async def root():
        index = STATIC_DIR / "index.html"
        return HTMLResponse(index.read_text(encoding="utf-8"))

    # ---------- Jobs API ----------

    @app.post("/api/jobs/preview_raw")
    async def preview_raw_job(
        file: UploadFile = File(...),
        page: str | None = Query(None),
        auto_scale: bool = Query(False),
        rotate_deg: float = Query(0.0),
        curve_step_mm: float = Query(1.0),
    ):
        if not file.filename:
            raise HTTPException(400, "No filename provided.")
        contents = await file.read()
        
        import tempfile
        from pathlib import Path
        from vectordraft.formats import load_document
        from vectordraft.model import PageSpec
        from vectordraft.exporter import document_to_svg
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / file.filename
            temp_path.write_bytes(contents)
            try:
                page_spec = PageSpec.preset(page) if page else None
                doc = load_document(temp_path, page=page_spec, curve_step_mm=curve_step_mm)
                if rotate_deg != 0.0:
                    from vectordraft.calibration import rotate_document
                    doc = rotate_document(doc, rotate_deg)
                if auto_scale and page_spec:
                    from vectordraft.calibration import scale_to_fit
                    doc = scale_to_fit(doc, page_spec, margin_mm=5.0)
                    
                svg = document_to_svg(doc)
                return Response(content=svg, media_type="image/svg+xml")
            except Exception as exc:
                raise HTTPException(422, f"Preview failed: {exc}")

    @app.post("/api/jobs/upload")
    async def upload_job(
        file: UploadFile = File(...),
        page: str | None = Query(None, description="Page preset, e.g. A1"),
        auto_scale: bool = Query(False, description="Auto scale to fit page"),
        rotate_deg: float = Query(0.0, description="Rotation angle in degrees"),
        curve_step_mm: float = Query(1.0),
        simplify_mm: float = Query(0.0),
    ):
        if not file.filename:
            raise HTTPException(400, "No filename provided.")
        contents = await file.read()
        try:
            job_id = manager.upload(
                file.filename,
                contents,
                page_preset=page,
                auto_scale=auto_scale,
                rotate_deg=rotate_deg,
                curve_step_mm=curve_step_mm,
                simplify_mm=simplify_mm,
            )
        except Exception as exc:
            raise HTTPException(422, f"Import failed: {exc}")
        await _broadcast(ws_clients, {"type": "job_created", "job_id": job_id})
        return {"job_id": job_id, **manager.get_job(job_id)}

    @app.get("/api/jobs")
    async def list_jobs():
        return manager.list_jobs()

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = manager.get_job(job_id)
        if job is None:
            raise HTTPException(404, "Job not found.")
        return job

    @app.delete("/api/jobs/{job_id}")
    async def delete_job(job_id: str):
        if not manager.delete_job(job_id):
            raise HTTPException(404, "Job not found.")
        await _broadcast(ws_clients, {"type": "job_deleted", "job_id": job_id})
        return {"deleted": True}

    @app.get("/api/jobs/{job_id}/preview.svg")
    async def job_preview_svg(job_id: str):
        svg = manager.get_preview_svg(job_id)
        if svg is None:
            raise HTTPException(404, "Preview not found.")
        return Response(content=svg, media_type="image/svg+xml")

    @app.get("/api/jobs/{job_id}/gcode")
    async def job_gcode(job_id: str):
        gcode = manager.get_gcode(job_id, pen_library=pen_library)
        if gcode is None:
            raise HTTPException(404, "G-code not available.")
        return PlainTextResponse(gcode, media_type="text/plain")

    @app.post("/api/jobs/{job_id}/pen-map")
    async def update_pen_map(job_id: str, assignments: dict[str, str]):
        try:
            manager.update_pen_map(job_id, assignments)
        except FileNotFoundError:
            raise HTTPException(404, "Job not found.")
        return {"updated": True}

    @app.post("/api/jobs/{job_id}/plot")
    async def start_plot(
        job_id: str,
        port: str = Query("", description="Serial port"),
        dry_run: bool = Query(True),
    ):
        job = manager.get_job(job_id)
        if job is None:
            raise HTTPException(404, "Job not found.")

        loop = asyncio.get_event_loop()

        def _safe_broadcast(data: dict) -> None:
            try:
                asyncio.run_coroutine_threadsafe(_broadcast(ws_clients, data), loop)
            except RuntimeError:
                pass  # Event loop closed (e.g. during shutdown)

        def _progress(jid: str, sent: int, total: int, command: str) -> None:
            _safe_broadcast({
                "type": "plot_progress",
                "job_id": jid,
                "sent": sent,
                "total": total,
                "command": command,
            })

        def _run_plot():
            try:
                result = manager.start_plot(
                    job_id,
                    port=port or "dry-run",
                    dry_run=dry_run,
                    pen_library=pen_library,
                    progress=_progress,
                )
                _safe_broadcast({
                    "type": "plot_complete",
                    "job_id": job_id,
                    **result,
                })
            except Exception as exc:
                _safe_broadcast({
                    "type": "plot_error",
                    "job_id": job_id,
                    "error": str(exc),
                })

        thread = threading.Thread(target=_run_plot, daemon=True)
        thread.start()
        return {"started": True, "job_id": job_id, "dry_run": dry_run}

    @app.post("/api/jobs/cancel")
    async def cancel_plot():
        job_id = manager.cancel_plot()
        if job_id:
            await _broadcast(ws_clients, {"type": "plot_cancelled", "job_id": job_id})
            return {"cancelled": True, "job_id": job_id}
        return {"cancelled": False}

    # ---------- Machine API ----------

    @app.get("/api/machine/status")
    async def machine_status():
        active = manager.active_job_id
        return {
            "state": "plotting" if active else "idle",
            "active_job_id": active,
        }

    @app.get("/api/machine/ports")
    async def machine_ports():
        return {"ports": available_ports()}

    # ---------- Pen Library API ----------

    @app.get("/api/pen-library")
    async def get_pen_library():
        return pen_library.model_dump()

    # ---------- WebSocket ----------

    @app.websocket("/ws/status")
    async def websocket_status(ws: WebSocket):
        await ws.accept()
        ws_clients.append(ws)
        try:
            while True:
                # Keep alive — client can send pings
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            pass
        finally:
            if ws in ws_clients:
                ws_clients.remove(ws)

    return app


async def _broadcast(clients: list[WebSocket], data: dict[str, Any]) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    message = json.dumps(data)
    disconnected: list[WebSocket] = []
    for ws in clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in clients:
            clients.remove(ws)
