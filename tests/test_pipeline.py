from pathlib import Path

import ezdxf
import fitz
from ezdxf import units as ezunits

from vectordraft.calibration import CalibrationProfile
from vectordraft.gcode import export_gcode
from vectordraft.importers import load_document
from vectordraft.model import Polyline, VectorDocument
from vectordraft.optimizer import clean_document, sort_document
from vectordraft.serial_stream import iter_gcode_commands, stream_commands


def test_svg_to_gcode_pipeline(tmp_path: Path) -> None:
    svg = tmp_path / "shape.svg"
    svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
        <path id="square" d="M 10 10 L 90 10 L 90 90 L 10 90 Z" stroke="black" fill="none"/>
        </svg>""",
        encoding="utf-8",
    )

    document = load_document(svg)
    document = sort_document(clean_document(document))
    gcode = export_gcode(document)

    assert len(document.paths) == 1
    assert "G21" in gcode
    assert "G1 X90.000 Y10.000" in gcode
    assert "M2 ; end" in gcode


def test_hpgl_subset_import(tmp_path: Path) -> None:
    hpgl = tmp_path / "shape.hpgl"
    hpgl.write_text("IN;SP1;PU0,0;PD400,0,400,400;PU;", encoding="utf-8")

    document = load_document(hpgl)

    assert len(document.paths) == 2
    assert document.paths[0].points == [(0.0, 0.0), (10.0, 0.0)]
    assert document.paths[1].points == [(10.0, 0.0), (10.0, 10.0)]


def test_dxf_line_import(tmp_path: Path) -> None:
    dxf = tmp_path / "line.dxf"
    drawing = ezdxf.new()
    drawing.units = ezunits.MM
    drawing.modelspace().add_line((0, 0), (25, 0), dxfattribs={"layer": "walls"})
    drawing.saveas(dxf)

    document = load_document(dxf)

    assert len(document.paths) == 1
    assert document.paths[0].layer == "walls"
    assert round(document.paths[0].length_mm, 3) == 25.0


def test_pdf_line_import(tmp_path: Path) -> None:
    pdf = tmp_path / "line.pdf"
    document = fitz.open()
    page = document.new_page(width=72, height=72)
    page.draw_line((0, 0), (72, 0), color=(0, 0, 0))
    document.save(pdf)

    loaded = load_document(pdf)

    assert len(loaded.paths) == 1
    assert round(loaded.paths[0].length_mm, 3) == 25.4


def test_calibration_profile_offsets_and_scales_points() -> None:
    profile = CalibrationProfile.from_components(scale_x=2.0, scale_y=3.0, offset_x_mm=10.0, offset_y_mm=-5.0)

    assert profile.apply_point((4.0, 5.0)) == (18.0, 10.0)


def test_gcode_export_applies_calibration() -> None:
    document = VectorDocument(paths=[Polyline(points=[(0.0, 0.0), (10.0, 0.0)], layer="walls")])
    profile = CalibrationProfile.from_components(name="test", offset_x_mm=5.0, offset_y_mm=7.0)

    gcode = export_gcode(document, calibration=profile)

    assert "; Calibration: test" in gcode
    assert "G0 X5.000 Y7.000" in gcode
    assert "G1 X15.000 Y7.000" in gcode


def test_gcode_comment_stripping() -> None:
    commands = list(iter_gcode_commands(["G21 ; units", "(hello)", "G1 X1 Y1 (move)", ""]))

    assert commands == ["G21", "G1 X1 Y1"]


def test_stream_commands_stops_on_controller_error() -> None:
    fake = FakeSerial(["ok", "error: bad command", "ok"])

    result = stream_commands(["G21", "NOPE", "G90"], fake)

    assert result.commands_sent == 2
    assert result.errors == ["NOPE: error: bad command"]
    assert fake.writes == [b"G21\n", b"NOPE\n"]


class FakeSerial:
    def __init__(self, responses: list[str]) -> None:
        self.responses = [response.encode("ascii") + b"\n" for response in responses]
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def readline(self) -> bytes:
        return self.responses.pop(0) if self.responses else b""
