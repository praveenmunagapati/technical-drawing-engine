from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

import ezdxf
import fitz
from ezdxf import path as ezpath
from ezdxf import units as ezunits
from svgpathtools import CubicBezier, Line, svg2paths2

from vectordraft.model import PageSpec, Point, Polyline, VectorDocument

MM_PER_INCH = 25.4
PX_TO_MM = MM_PER_INCH / 96.0
PT_TO_MM = MM_PER_INCH / 72.0


def load_document(
    source: str | Path,
    *,
    page: PageSpec | None = None,
    curve_step_mm: float = 1.0,
) -> VectorDocument:
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return load_svg(path, page=page, curve_step_mm=curve_step_mm)
    if suffix == ".dxf":
        return load_dxf(path, page=page, curve_step_mm=curve_step_mm)
    if suffix == ".pdf":
        return load_pdf(path, page=page, curve_step_mm=curve_step_mm)
    if suffix in {".plt", ".hpgl", ".hpg"}:
        return load_hpgl(path, page=page)
    raise ValueError(f"Unsupported input format: {suffix or '<none>'}")


def load_svg(
    source: str | Path,
    *,
    page: PageSpec | None = None,
    curve_step_mm: float = 1.0,
) -> VectorDocument:
    paths, attributes, svg_attributes = svg2paths2(str(source))
    scale = _svg_scale_to_mm(svg_attributes)
    page = page or _svg_page(svg_attributes, scale) or PageSpec.preset("A1")

    polylines: list[Polyline] = []
    for path_index, svg_path in enumerate(paths):
        layer = _svg_layer(attributes[path_index], path_index)
        color = attributes[path_index].get("stroke") or attributes[path_index].get("color")
        for subpath in svg_path.continuous_subpaths():
            points = _sample_svg_path(subpath, curve_step_mm / max(scale, 1e-9), scale)
            if len(points) >= 2:
                polylines.append(
                    Polyline(
                        points=points,
                        layer=layer,
                        color=color,
                        source="svg",
                        metadata={"path_index": path_index},
                    )
                )

    return VectorDocument(paths=polylines, page=page, source_path=str(source))


def load_dxf(
    source: str | Path,
    *,
    page: PageSpec | None = None,
    curve_step_mm: float = 1.0,
) -> VectorDocument:
    drawing = ezdxf.readfile(source)
    modelspace = drawing.modelspace()
    unit_scale = _dxf_unit_scale_to_mm(drawing)
    polylines: list[Polyline] = []

    for entity in modelspace:
        if entity.dxftype() not in {
            "LINE",
            "ARC",
            "CIRCLE",
            "ELLIPSE",
            "LWPOLYLINE",
            "POLYLINE",
            "SPLINE",
        }:
            continue
        try:
            path = ezpath.make_path(entity)
            points = [
                (float(point.x) * unit_scale, float(point.y) * unit_scale)
                for point in path.flattening(distance=curve_step_mm / max(unit_scale, 1e-9))
            ]
        except Exception:
            points = _fallback_dxf_points(entity, unit_scale)
        if len(points) >= 2:
            polylines.append(
                Polyline(
                    points=points,
                    layer=entity.dxf.layer or "default",
                    color=_dxf_color(entity),
                    source="dxf",
                    metadata={"handle": entity.dxf.handle, "type": entity.dxftype()},
                )
            )

    inferred_page = page or _page_from_bounds(polylines) or PageSpec.preset("A1")
    return VectorDocument(paths=polylines, page=inferred_page, source_path=str(source))


def load_pdf(
    source: str | Path,
    *,
    page: PageSpec | None = None,
    curve_step_mm: float = 1.0,
) -> VectorDocument:
    document = fitz.open(source)
    polylines: list[Polyline] = []

    for page_index, pdf_page in enumerate(document):
        for drawing_index, drawing in enumerate(pdf_page.get_drawings()):
            color = _pdf_color(drawing.get("color"))
            layer = f"page-{page_index + 1}"
            for item_index, item in enumerate(drawing.get("items", [])):
                for points in _pdf_item_to_polylines(item, curve_step_mm):
                    if len(points) >= 2:
                        polylines.append(
                            Polyline(
                                points=points,
                                layer=layer,
                                color=color,
                                source="pdf",
                                metadata={
                                    "page": page_index + 1,
                                    "drawing": drawing_index,
                                    "item": item_index,
                                },
                            )
                        )

    if page is None and document.page_count:
        rect = document[0].rect
        page = PageSpec(width_mm=rect.width * PT_TO_MM, height_mm=rect.height * PT_TO_MM, name="PDF")
    return VectorDocument(paths=polylines, page=page or PageSpec.preset("A1"), source_path=str(source))


def load_hpgl(source: str | Path, *, page: PageSpec | None = None) -> VectorDocument:
    text = Path(source).read_text(encoding="utf-8", errors="ignore")
    polylines: list[Polyline] = []
    current: Point = (0.0, 0.0)
    absolute = True
    pen_down = False
    selected_pen = "1"
    units_per_mm = 40.0

    for raw_command in text.replace("\n", "").split(";"):
        if not raw_command.strip():
            continue
        command = raw_command[:2].upper()
        payload = raw_command[2:].strip()
        if command == "IN":
            current = (0.0, 0.0)
            absolute = True
            pen_down = False
            selected_pen = "1"
        elif command == "SP":
            selected_pen = payload.strip() or selected_pen
        elif command == "PA":
            absolute = True
            for target in _hpgl_points(payload, current, absolute, units_per_mm):
                if pen_down:
                    polylines.append(Polyline(points=[current, target], layer=f"pen-{selected_pen}", pen=selected_pen, source="hpgl"))
                current = target
        elif command == "PR":
            absolute = False
            for target in _hpgl_points(payload, current, absolute, units_per_mm):
                if pen_down:
                    polylines.append(Polyline(points=[current, target], layer=f"pen-{selected_pen}", pen=selected_pen, source="hpgl"))
                current = target
        elif command in {"PU", "PD"}:
            pen_down = command == "PD"
            for target in _hpgl_points(payload, current, absolute, units_per_mm):
                if pen_down:
                    polylines.append(Polyline(points=[current, target], layer=f"pen-{selected_pen}", pen=selected_pen, source="hpgl"))
                current = target

    return VectorDocument(paths=polylines, page=page or _page_from_bounds(polylines) or PageSpec.preset("A1"), source_path=str(source))


def _sample_svg_path(svg_path, curve_step_user_units: float, scale: float) -> list[Point]:
    points: list[Point] = []
    for segment in svg_path:
        segment_length = max(float(segment.length(error=1e-4)), 0.0)
        steps = 1 if isinstance(segment, Line) else max(1, math.ceil(segment_length / max(curve_step_user_units, 0.1)))
        for index in range(steps + 1):
            if points and index == 0:
                continue
            point = segment.point(index / steps)
            points.append((float(point.real) * scale, float(point.imag) * scale))
    return points


def _fallback_dxf_points(entity, unit_scale: float) -> list[Point]:
    if entity.dxftype() == "LINE":
        return [
            (float(entity.dxf.start.x) * unit_scale, float(entity.dxf.start.y) * unit_scale),
            (float(entity.dxf.end.x) * unit_scale, float(entity.dxf.end.y) * unit_scale),
        ]
    return []


def _pdf_item_to_polylines(item, curve_step_mm: float) -> Iterable[list[Point]]:
    code = item[0]
    if code == "l":
        p1, p2 = item[1], item[2]
        yield [(p1.x * PT_TO_MM, p1.y * PT_TO_MM), (p2.x * PT_TO_MM, p2.y * PT_TO_MM)]
    elif code == "c":
        p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
        curve = CubicBezier(
            complex(p1.x * PT_TO_MM, p1.y * PT_TO_MM),
            complex(p2.x * PT_TO_MM, p2.y * PT_TO_MM),
            complex(p3.x * PT_TO_MM, p3.y * PT_TO_MM),
            complex(p4.x * PT_TO_MM, p4.y * PT_TO_MM),
        )
        yield _sample_complex_curve(curve, curve_step_mm)
    elif code == "qu":
        quad = item[1]
        points = [quad.ul, quad.ur, quad.lr, quad.ll, quad.ul]
        yield [(point.x * PT_TO_MM, point.y * PT_TO_MM) for point in points]
    elif code == "re":
        rect = item[1]
        x0, y0 = rect.x0 * PT_TO_MM, rect.y0 * PT_TO_MM
        x1, y1 = rect.x1 * PT_TO_MM, rect.y1 * PT_TO_MM
        yield [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _sample_complex_curve(curve, curve_step_mm: float) -> list[Point]:
    length = max(float(curve.length(error=1e-4)), 0.0)
    steps = max(1, math.ceil(length / max(curve_step_mm, 0.1)))
    points: list[Point] = []
    for index in range(steps + 1):
        point = curve.point(index / steps)
        points.append((float(point.real), float(point.imag)))
    return points


def _svg_layer(attributes: dict[str, str], path_index: int) -> str:
    return (
        attributes.get("data-layer")
        or attributes.get("inkscape:label")
        or attributes.get("class")
        or attributes.get("id")
        or f"path-{path_index + 1}"
    )


def _svg_scale_to_mm(svg_attributes: dict[str, str]) -> float:
    view_box = svg_attributes.get("viewBox") or svg_attributes.get("viewbox")
    width_attr = svg_attributes.get("width")
    if view_box and width_attr:
        values = [float(value) for value in re.split(r"[,\s]+", view_box.strip()) if value]
        if len(values) == 4 and values[2]:
            width_mm = _length_to_mm(width_attr)
            if width_mm:
                return width_mm / values[2]
    return _length_unit_to_mm(width_attr) if width_attr else PX_TO_MM


def _svg_page(svg_attributes: dict[str, str], scale: float) -> PageSpec | None:
    view_box = svg_attributes.get("viewBox") or svg_attributes.get("viewbox")
    width = _length_to_mm(svg_attributes.get("width", ""))
    height = _length_to_mm(svg_attributes.get("height", ""))
    if width and height:
        return PageSpec(width_mm=width, height_mm=height, name="SVG")
    if view_box:
        values = [float(value) for value in re.split(r"[,\s]+", view_box.strip()) if value]
        if len(values) == 4:
            return PageSpec(width_mm=values[2] * scale, height_mm=values[3] * scale, name="SVG")
    return None


def _length_to_mm(value: str) -> float | None:
    match = re.match(r"^\s*([0-9.+-]+)\s*([a-zA-Z]*)\s*$", value or "")
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower() or "px"
    if unit == "mm":
        return amount
    if unit == "cm":
        return amount * 10.0
    if unit in {"in", "inch"}:
        return amount * MM_PER_INCH
    if unit == "pt":
        return amount * PT_TO_MM
    if unit == "px":
        return amount * PX_TO_MM
    return amount


def _length_unit_to_mm(value: str | None) -> float:
    match = re.match(r"^\s*[0-9.+-]+\s*([a-zA-Z]*)\s*$", value or "")
    unit = (match.group(1).lower() if match else "") or "px"
    if unit == "mm":
        return 1.0
    if unit == "cm":
        return 10.0
    if unit in {"in", "inch"}:
        return MM_PER_INCH
    if unit == "pt":
        return PT_TO_MM
    return PX_TO_MM


def _dxf_unit_scale_to_mm(drawing) -> float:
    unit_code = getattr(drawing, "units", None) or drawing.header.get("$INSUNITS", 0)
    unit_name = (ezunits.decode(unit_code) or "unitless").lower()
    return {
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "in": MM_PER_INCH,
        "ft": MM_PER_INCH * 12.0,
    }.get(unit_name, 1.0)


def _dxf_color(entity) -> str | None:
    try:
        if entity.rgb:
            r, g, b = entity.rgb
            return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None
    return None


def _pdf_color(color) -> str | None:
    if not color:
        return None
    r, g, b = [max(0, min(255, round(channel * 255))) for channel in color[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"


def _hpgl_points(payload: str, current: Point, absolute: bool, units_per_mm: float) -> list[Point]:
    numbers = [float(number) for number in re.findall(r"[-+]?\d*\.?\d+", payload)]
    points: list[Point] = []
    x0, y0 = current
    for index in range(0, len(numbers) - 1, 2):
        x = numbers[index] / units_per_mm
        y = numbers[index + 1] / units_per_mm
        if not absolute:
            x += x0
            y += y0
        points.append((x, y))
        x0, y0 = x, y
    return points


def _page_from_bounds(paths: list[Polyline]) -> PageSpec | None:
    if not paths:
        return None
    minx = min(path.bounds[0] for path in paths)
    miny = min(path.bounds[1] for path in paths)
    maxx = max(path.bounds[2] for path in paths)
    maxy = max(path.bounds[3] for path in paths)
    return PageSpec(width_mm=maxx - minx, height_mm=maxy - miny, name="inferred")
