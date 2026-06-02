from __future__ import annotations

import numpy as np
from shapely.geometry import LineString

from vectordraft.model import Bounds, PageSpec, Point, Polyline, VectorDocument


def clean_document(document: VectorDocument, *, simplify_mm: float = 0.0) -> VectorDocument:
    paths: list[Polyline] = []
    for path in document.paths:
        cleaned = _dedupe_consecutive(path.points)
        if simplify_mm > 0 and len(cleaned) > 2:
            simplified = LineString(cleaned).simplify(simplify_mm, preserve_topology=False)
            cleaned = [(float(x), float(y)) for x, y in simplified.coords]
        if len(cleaned) >= 2:
            paths.append(path.with_points(cleaned))
    return document.with_paths(paths)


def sort_document(document: VectorDocument, *, start: Point = (0.0, 0.0), group_by_pen: bool = True) -> VectorDocument:
    if group_by_pen:
        sorted_paths: list[Polyline] = []
        current = start
        for _, paths in sorted(document.grouped_by_pen().items()):
            group = nearest_neighbor_sort(paths, start=current)
            if group:
                current = group[-1].end
            sorted_paths.extend(group)
        return document.with_paths(sorted_paths)
    return document.with_paths(nearest_neighbor_sort(document.paths, start=start))


def nearest_neighbor_sort(paths: list[Polyline], *, start: Point = (0.0, 0.0)) -> list[Polyline]:
    if not paths:
        return []

    unused = np.ones(len(paths), dtype=bool)
    starts = np.array([path.start for path in paths], dtype=float)
    ends = np.array([path.end for path in paths], dtype=float)
    current = np.array(start, dtype=float)
    ordered: list[Polyline] = []

    while unused.any():
        start_distances = np.linalg.norm(starts - current, axis=1)
        end_distances = np.linalg.norm(ends - current, axis=1)
        best_distances = np.minimum(start_distances, end_distances)
        best_distances[~unused] = np.inf
        index = int(np.argmin(best_distances))
        reverse = end_distances[index] < start_distances[index]
        chosen = paths[index].reversed() if reverse else paths[index]
        ordered.append(chosen)
        current = np.array(chosen.end, dtype=float)
        unused[index] = False

    return ordered


def estimate_travel_mm(paths: list[Polyline], *, start: Point = (0.0, 0.0)) -> float:
    current = start
    total = 0.0
    for path in paths:
        total += float(np.linalg.norm(np.array(path.start) - np.array(current)))
        current = path.end
    return total


def merge_contiguous(
    document: VectorDocument,
    *,
    tolerance_mm: float = 0.01,
) -> VectorDocument:
    """Join polylines whose end/start points are within tolerance.

    Merges chains greedily in order. Only merges paths on the same layer
    with the same pen/color assignment.
    """
    if not document.paths:
        return document

    merged: list[Polyline] = []
    current = document.paths[0]

    for next_path in document.paths[1:]:
        # Only merge if same layer and pen
        if (
            current.layer == next_path.layer
            and current.pen == next_path.pen
            and current.color == next_path.color
            and _distance(current.end, next_path.start) <= tolerance_mm
        ):
            # Extend current with next_path's points (skip duplicate junction)
            combined = list(current.points) + list(next_path.points[1:])
            current = current.with_points(combined)
        else:
            merged.append(current)
            current = next_path

    merged.append(current)
    return document.with_paths(merged)


def detect_out_of_bounds(
    document: VectorDocument,
    *,
    margin_mm: float = 0.0,
) -> list[tuple[int, Polyline, str]]:
    """Return a list of (index, path, reason) for paths outside the page area.

    The page area is [0, width] × [0, height] shrunk by margin_mm on each side.
    """
    page = document.page
    min_x = margin_mm
    min_y = margin_mm
    max_x = page.width_mm - margin_mm
    max_y = page.height_mm - margin_mm

    violations: list[tuple[int, Polyline, str]] = []
    for index, path in enumerate(document.paths):
        bounds = path.bounds
        reasons: list[str] = []
        if bounds[0] < min_x:
            reasons.append(f"left edge at {bounds[0]:.2f} mm < {min_x:.2f}")
        if bounds[1] < min_y:
            reasons.append(f"top edge at {bounds[1]:.2f} mm < {min_y:.2f}")
        if bounds[2] > max_x:
            reasons.append(f"right edge at {bounds[2]:.2f} mm > {max_x:.2f}")
        if bounds[3] > max_y:
            reasons.append(f"bottom edge at {bounds[3]:.2f} mm > {max_y:.2f}")
        if reasons:
            violations.append((index, path, "; ".join(reasons)))

    return violations


def remove_zero_length(document: VectorDocument) -> VectorDocument:
    """Strip degenerate paths with effectively zero draw length."""
    paths = [p for p in document.paths if p.length_mm > 1e-6]
    return document.with_paths(paths)


def add_bounds_warnings(document: VectorDocument, *, margin_mm: float = 0.0) -> VectorDocument:
    """Detect out-of-bounds paths and add warnings to the document."""
    violations = detect_out_of_bounds(document, margin_mm=margin_mm)
    warnings = list(document.warnings)
    for index, path, reason in violations:
        warnings.append(f"Path {index} (layer={path.layer}): out of bounds — {reason}")
    return document.model_copy(update={"warnings": warnings})


def _dedupe_consecutive(points: list[Point], epsilon: float = 1e-6) -> list[Point]:
    cleaned: list[Point] = []
    for point in points:
        if not cleaned:
            cleaned.append(point)
            continue
        if abs(point[0] - cleaned[-1][0]) > epsilon or abs(point[1] - cleaned[-1][1]) > epsilon:
            cleaned.append(point)
    return cleaned


def _distance(a: Point, b: Point) -> float:
    return float(np.linalg.norm(np.array(a) - np.array(b)))
