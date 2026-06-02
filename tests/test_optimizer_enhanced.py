from vectordraft.model import PageSpec, Polyline, VectorDocument
from vectordraft.optimizer import (
    add_bounds_warnings,
    detect_out_of_bounds,
    merge_contiguous,
    remove_zero_length,
)


def test_merge_contiguous_joins_adjacent_segments() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(0, 0), (10, 0)], layer="a"),
            Polyline(points=[(10, 0), (10, 10)], layer="a"),
            Polyline(points=[(10, 10), (0, 10)], layer="a"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    merged = merge_contiguous(doc)

    assert len(merged.paths) == 1
    assert merged.paths[0].points == [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_merge_contiguous_respects_tolerance() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(0, 0), (10, 0)], layer="a"),
            Polyline(points=[(10.005, 0), (20, 0)], layer="a"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    merged = merge_contiguous(doc, tolerance_mm=0.01)
    assert len(merged.paths) == 1

    not_merged = merge_contiguous(doc, tolerance_mm=0.001)
    assert len(not_merged.paths) == 2


def test_merge_contiguous_does_not_join_different_layers() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(0, 0), (10, 0)], layer="a"),
            Polyline(points=[(10, 0), (20, 0)], layer="b"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    merged = merge_contiguous(doc)

    assert len(merged.paths) == 2


def test_detect_out_of_bounds_finds_violations() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(-5, 10), (10, 10)], layer="a"),
            Polyline(points=[(10, 10), (50, 10)], layer="b"),
            Polyline(points=[(10, 10), (10, 120)], layer="c"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    violations = detect_out_of_bounds(doc)

    # Path 0 goes negative X, path 2 exceeds Y
    assert len(violations) == 2
    indices = [v[0] for v in violations]
    assert 0 in indices
    assert 2 in indices


def test_detect_out_of_bounds_with_margin() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(3, 10), (50, 10)], layer="a"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    # Without margin: OK
    assert len(detect_out_of_bounds(doc)) == 0

    # With 5mm margin: path starts at x=3 < margin=5
    violations = detect_out_of_bounds(doc, margin_mm=5.0)
    assert len(violations) == 1


def test_remove_zero_length() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(0, 0), (10, 0)], layer="good"),
            Polyline(points=[(5, 5), (5.0000001, 5)], layer="tiny"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    cleaned = remove_zero_length(doc)

    assert len(cleaned.paths) == 1
    assert cleaned.paths[0].layer == "good"


def test_add_bounds_warnings_populates_warnings() -> None:
    doc = VectorDocument(
        paths=[
            Polyline(points=[(-2, 10), (50, 10)], layer="bad"),
            Polyline(points=[(10, 10), (50, 10)], layer="ok"),
        ],
        page=PageSpec(width_mm=100, height_mm=100),
    )

    warned = add_bounds_warnings(doc)

    assert len(warned.warnings) == 1
    assert "out of bounds" in warned.warnings[0]
    assert "bad" in warned.warnings[0]
