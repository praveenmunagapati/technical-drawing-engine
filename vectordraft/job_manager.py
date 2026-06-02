"""Job queue manager for PlotCAD Studio."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from vectordraft.calibration import CalibrationProfile
from vectordraft.gcode import estimate_plot_time, export_gcode
from vectordraft.importers import load_document
from vectordraft.model import (
    JobPackage,
    PenLibrary,
    PlotSettings,
    VectorDocument,
)
from vectordraft.optimizer import (
    add_bounds_warnings,
    clean_document,
    merge_contiguous,
    remove_zero_length,
    sort_document,
)
from vectordraft.svg_preview import render_svg

# Job statuses
UPLOADED = "uploaded"
PREPARED = "prepared"
QUEUED = "queued"
PLOTTING = "plotting"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

ProgressCallback = Callable[[str, int, int, str], None]  # job_id, sent, total, command


class JobManager:
    """Manages plot jobs on disk with thread-safe single-job plotting."""

    def __init__(self, jobs_dir: str | Path) -> None:
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._active_job_id: str | None = None
        self._cancel_requested = False

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return summaries of all jobs, newest first."""
        jobs: list[dict[str, Any]] = []
        for job_dir in sorted(self.jobs_dir.iterdir(), reverse=True):
            if not job_dir.is_dir():
                continue
            status_file = job_dir / "status.json"
            if status_file.exists():
                try:
                    data = json.loads(status_file.read_text(encoding="utf-8"))
                    data["id"] = job_dir.name
                    jobs.append(data)
                except Exception:
                    continue
        return jobs

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return full job details or None."""
        job_dir = self.jobs_dir / job_id
        status_file = job_dir / "status.json"
        if not status_file.exists():
            return None
        data = json.loads(status_file.read_text(encoding="utf-8"))
        data["id"] = job_id

        # Add document info if available
        doc_file = job_dir / "document.json"
        if doc_file.exists():
            doc = VectorDocument.model_validate_json(doc_file.read_text(encoding="utf-8"))
            data["layers"] = doc.layers
            data["path_count"] = len(doc.paths)
            data["draw_length_mm"] = round(doc.total_draw_length_mm, 2)
            bounds = doc.bounds
            if bounds:
                data["bounds"] = {
                    "min_x": round(bounds[0], 2),
                    "min_y": round(bounds[1], 2),
                    "max_x": round(bounds[2], 2),
                    "max_y": round(bounds[3], 2),
                }
            data["warnings"] = doc.warnings
            data["page"] = {
                "name": doc.page.name,
                "width_mm": doc.page.width_mm,
                "height_mm": doc.page.height_mm,
            }

        # Add pen assignments if available
        pen_file = job_dir / "pen_assignments.json"
        if pen_file.exists():
            data["pen_assignments"] = json.loads(pen_file.read_text(encoding="utf-8"))

        return data

    def upload(
        self,
        filename: str,
        file_bytes: bytes,
        *,
        page_preset: str | None = None,
        auto_scale: bool = False,
        rotate_deg: float = 0.0,
        curve_step_mm: float = 1.0,
        simplify_mm: float = 0.0,
    ) -> str:
        """Import a file, prepare the document, and return the job ID."""
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Save source file
        source_path = job_dir / filename
        source_path.write_bytes(file_bytes)

        try:
            # Import and process
            from vectordraft.model import PageSpec

            page = PageSpec.preset(page_preset) if page_preset else None
            doc = load_document(source_path, page=page, curve_step_mm=curve_step_mm)
            
            if rotate_deg != 0.0:
                from vectordraft.calibration import rotate_document
                doc = rotate_document(doc, rotate_deg)
                
            if auto_scale and page:
                from vectordraft.calibration import scale_to_fit
                doc = scale_to_fit(doc, page, margin_mm=5.0)
                
            doc = clean_document(doc, simplify_mm=simplify_mm)
            doc = remove_zero_length(doc)
            doc = merge_contiguous(doc)
            doc = sort_document(doc)
            doc = add_bounds_warnings(doc, margin_mm=5.0)

            # Estimate plot time
            est_time = estimate_plot_time(doc)

            # Save processed document
            (job_dir / "document.json").write_text(
                doc.model_dump_json(indent=2), encoding="utf-8"
            )

            # Generate SVG preview
            svg = render_svg(doc)
            (job_dir / "preview.svg").write_text(svg, encoding="utf-8")

            # Save status
            status = {
                "status": PREPARED,
                "source_filename": filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "estimated_duration_s": round(est_time, 1),
                "path_count": len(doc.paths),
                "layer_count": len(doc.layers),
                "draw_length_mm": round(doc.total_draw_length_mm, 2),
                "page_name": doc.page.name,
                "page_width_mm": doc.page.width_mm,
                "page_height_mm": doc.page.height_mm,
                "warning_count": len(doc.warnings),
            }
            self._save_status(job_id, status)
            return job_id

        except Exception as exc:
            self._save_status(job_id, {
                "status": FAILED,
                "source_filename": filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            })
            raise

    def update_pen_map(self, job_id: str, pen_assignments: dict[str, str]) -> None:
        """Update layer→pen assignments for a job."""
        job_dir = self.jobs_dir / job_id
        if not job_dir.exists():
            raise FileNotFoundError(f"Job {job_id} not found.")
        (job_dir / "pen_assignments.json").write_text(
            json.dumps(pen_assignments, indent=2), encoding="utf-8"
        )

    def get_preview_svg(self, job_id: str) -> str | None:
        """Return the SVG preview for a job."""
        svg_path = self.jobs_dir / job_id / "preview.svg"
        if svg_path.exists():
            return svg_path.read_text(encoding="utf-8")
        return None

    def get_gcode(self, job_id: str, *, pen_library: PenLibrary | None = None) -> str | None:
        """Generate and return G-code for a job."""
        job_dir = self.jobs_dir / job_id
        doc_file = job_dir / "document.json"
        if not doc_file.exists():
            return None

        doc = VectorDocument.model_validate_json(doc_file.read_text(encoding="utf-8"))
        settings = PlotSettings(page=doc.page)

        # Load pen assignments if available
        pen_file = job_dir / "pen_assignments.json"
        if pen_file.exists():
            assignments = json.loads(pen_file.read_text(encoding="utf-8"))
            if pen_library:
                pen_library = pen_library.model_copy(update={"layer_map": assignments})

        gcode = export_gcode(doc, settings=settings, pen_library=pen_library)

        # Cache it
        (job_dir / "output.gcode").write_text(gcode, encoding="utf-8")
        return gcode

    def delete_job(self, job_id: str) -> bool:
        """Delete a job directory."""
        job_dir = self.jobs_dir / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
            return True
        return False

    def start_plot(
        self,
        job_id: str,
        *,
        port: str,
        dry_run: bool = False,
        pen_library: PenLibrary | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Start plotting a job. Blocking. Returns result dict."""
        with self._lock:
            if self._active_job_id is not None:
                raise RuntimeError(f"Already plotting job {self._active_job_id}")
            self._active_job_id = job_id
            self._cancel_requested = False

        try:
            self._update_status(job_id, PLOTTING)

            # Generate gcode
            gcode = self.get_gcode(job_id, pen_library=pen_library)
            if gcode is None:
                raise FileNotFoundError(f"No document for job {job_id}")

            if dry_run:
                from vectordraft.serial_stream import iter_gcode_commands

                commands = list(iter_gcode_commands(gcode))
                for i, cmd in enumerate(commands, 1):
                    if self._cancel_requested:
                        self._update_status(job_id, CANCELLED)
                        return {"status": CANCELLED, "commands_sent": i - 1}
                    if progress:
                        progress(job_id, i, len(commands), cmd)

                self._update_status(job_id, COMPLETED)
                return {"status": COMPLETED, "commands_sent": len(commands), "dry_run": True}

            else:
                from vectordraft.serial_stream import StreamSettings, stream_gcode

                def _progress(index: int, command: str, response: str) -> None:
                    if progress:
                        progress(job_id, index, 0, f"{command} -> {response}")

                result = stream_gcode(gcode, port=port, progress=_progress)
                status = COMPLETED if not result.errors else FAILED
                self._update_status(job_id, status)
                return {
                    "status": status,
                    "commands_sent": result.commands_sent,
                    "errors": result.errors,
                }

        except Exception as exc:
            self._update_status(job_id, FAILED, error=str(exc))
            raise
        finally:
            with self._lock:
                self._active_job_id = None

    def cancel_plot(self) -> str | None:
        """Request cancellation of the active plot. Returns job ID or None."""
        with self._lock:
            if self._active_job_id:
                self._cancel_requested = True
                return self._active_job_id
        return None

    @property
    def active_job_id(self) -> str | None:
        with self._lock:
            return self._active_job_id

    def _save_status(self, job_id: str, data: dict[str, Any]) -> None:
        status_file = self.jobs_dir / job_id / "status.json"
        status_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _update_status(self, job_id: str, status: str, *, error: str | None = None) -> None:
        job = self.get_job(job_id) or {}
        job["status"] = status
        if error:
            job["error"] = error
        job.pop("id", None)
        self._save_status(job_id, job)
