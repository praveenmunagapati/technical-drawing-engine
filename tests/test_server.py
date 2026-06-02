import json
from pathlib import Path

from fastapi.testclient import TestClient

from vectordraft.server import create_app


def _make_client(tmp_path: Path) -> TestClient:
    app = create_app(jobs_dir=tmp_path / "jobs")
    return TestClient(app)


def _demo_svg() -> bytes:
    return b"""<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
    <path id="square" d="M 10 10 L 90 10 L 90 90 L 10 90 Z" stroke="black" fill="none"/>
    </svg>"""


def test_root_serves_html(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "PlotCAD Studio" in resp.text


def test_upload_and_list_jobs(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # List jobs
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert any(j["id"] == job_id for j in jobs)


def test_job_detail(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    job_id = resp.json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "prepared"
    assert detail["path_count"] >= 1
    assert len(detail["layers"]) >= 1


def test_preview_svg(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    job_id = resp.json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/preview.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/svg+xml"
    assert "<svg" in resp.text


def test_gcode_download(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    job_id = resp.json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/gcode")
    assert resp.status_code == 200
    assert "G21" in resp.text
    assert "M2 ; end" in resp.text


def test_delete_job(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    job_id = resp.json()["job_id"]

    resp = client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 200

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 404


def test_pen_map_update(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    job_id = resp.json()["job_id"]

    resp = client.post(
        f"/api/jobs/{job_id}/pen-map",
        json={"square": "pen-2"},
    )
    assert resp.status_code == 200


def test_machine_status(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/api/machine/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "idle"


def test_machine_ports(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/api/machine/ports")
    assert resp.status_code == 200
    assert "ports" in resp.json()


def test_pen_library_endpoint(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/api/pen-library")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["pens"]) == 6
    assert data["name"] == "ISO Technical Pens"


def test_start_dry_run_plot(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.svg", _demo_svg(), "image/svg+xml")},
    )
    job_id = resp.json()["job_id"]

    resp = client.post(f"/api/jobs/{job_id}/plot?dry_run=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["started"] is True
    assert data["dry_run"] is True


def test_upload_invalid_file(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/jobs/upload",
        files={"file": ("test.txt", b"not a drawing", "text/plain")},
    )
    assert resp.status_code == 422


def test_job_not_found(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404
