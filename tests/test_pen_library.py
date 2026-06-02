from pathlib import Path

from vectordraft.gcode import estimate_plot_time, export_gcode
from vectordraft.model import PenLibrary, PenProfile, Polyline, VectorDocument


def test_iso_default_library_has_six_pens() -> None:
    library = PenLibrary.iso_default()

    assert len(library.pens) == 6
    assert library.default_pen_id == "pen-4"
    assert library.pens[3].nominal_width_mm == 0.35


def test_resolve_pen_by_layer() -> None:
    library = PenLibrary(
        pens=[
            PenProfile(id="thin", nominal_width_mm=0.18),
            PenProfile(id="thick", nominal_width_mm=0.50),
        ],
        layer_map={"walls": "thick", "dimensions": "thin"},
        default_pen_id="thin",
    )

    assert library.resolve_pen(layer="walls").id == "thick"
    assert library.resolve_pen(layer="dimensions").id == "thin"


def test_resolve_pen_by_color() -> None:
    library = PenLibrary(
        pens=[
            PenProfile(id="red-pen", color="#ff0000"),
            PenProfile(id="blue-pen", color="#0000ff"),
        ],
        color_map={"#ff0000": "red-pen", "#0000ff": "blue-pen"},
        default_pen_id="red-pen",
    )

    assert library.resolve_pen(color="#0000ff").id == "blue-pen"
    assert library.resolve_pen(color="#FF0000").id == "red-pen"


def test_resolve_pen_by_width() -> None:
    library = PenLibrary.iso_default()

    pen = library.resolve_pen(width=0.25)
    assert pen.nominal_width_mm == 0.25

    pen = library.resolve_pen(width=0.50)
    assert pen.nominal_width_mm == 0.50


def test_resolve_pen_falls_back_to_default() -> None:
    library = PenLibrary(
        pens=[PenProfile(id="only-pen", nominal_width_mm=0.35)],
        default_pen_id="only-pen",
    )

    pen = library.resolve_pen(layer="nonexistent", color="#abcdef", width=99.0)
    assert pen.id == "only-pen"


def test_library_save_and_load(tmp_path: Path) -> None:
    library = PenLibrary.iso_default()
    json_path = tmp_path / "pens.json"
    library.save(json_path)

    loaded = PenLibrary.load(json_path)

    assert loaded.name == library.name
    assert len(loaded.pens) == len(library.pens)
    assert loaded.pens[0].nominal_width_mm == library.pens[0].nominal_width_mm


def test_library_as_dict() -> None:
    library = PenLibrary(
        pens=[
            PenProfile(id="a", nominal_width_mm=0.18),
            PenProfile(id="b", nominal_width_mm=0.35),
        ]
    )

    d = library.as_dict()

    assert set(d.keys()) == {"a", "b"}
    assert d["a"].nominal_width_mm == 0.18


def test_gcode_with_pen_library() -> None:
    library = PenLibrary(
        pens=[
            PenProfile(id="pen-thin", nominal_width_mm=0.18, draw_feed_mm_min=1800.0),
            PenProfile(id="pen-thick", nominal_width_mm=0.50, draw_feed_mm_min=1200.0),
        ],
        layer_map={"walls": "pen-thick", "dims": "pen-thin"},
        default_pen_id="pen-thin",
    )
    document = VectorDocument(
        paths=[
            Polyline(points=[(0, 0), (100, 0)], layer="walls"),
            Polyline(points=[(0, 10), (100, 10)], layer="dims"),
        ]
    )

    gcode = export_gcode(document, pen_library=library)

    assert "PEN pen-thick" in gcode
    assert "PEN pen-thin" in gcode
    assert "M0 ; CHANGE TO PEN pen-thin" in gcode
    assert "F1200" in gcode
    assert "F1800" in gcode


def test_estimate_plot_time_nonzero() -> None:
    document = VectorDocument(
        paths=[
            Polyline(points=[(0, 0), (100, 0)], layer="default"),
            Polyline(points=[(0, 10), (100, 10)], layer="default"),
        ]
    )

    time_s = estimate_plot_time(document)

    assert time_s > 0
    # 200mm of drawing at 2400mm/min ≈ 5s + dwell + travel
    assert time_s < 60  # Sanity upper bound
