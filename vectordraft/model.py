from __future__ import annotations

from collections import defaultdict
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from shapely.geometry import LineString

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]


PAGE_PRESETS: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
    "ARCH_D": (609.6, 914.4),
    "ARCH_E": (914.4, 1219.2),
}


class LineStyle(str, Enum):
    """CAD line styles for technical drawings."""

    CONTINUOUS = "continuous"
    DASHED = "dashed"
    DOTTED = "dotted"
    DASH_DOT = "dash_dot"
    CENTER = "center"


class PageSpec(BaseModel):
    width_mm: float
    height_mm: float
    name: str = "custom"

    @classmethod
    def preset(cls, name: str) -> "PageSpec":
        key = name.upper()
        if key not in PAGE_PRESETS:
            choices = ", ".join(PAGE_PRESETS)
            raise ValueError(f"Unknown page preset {name!r}. Choose one of: {choices}")
        width, height = PAGE_PRESETS[key]
        return cls(width_mm=width, height_mm=height, name=key)


class PenProfile(BaseModel):
    id: str = "pen-1"
    color: str = "#111111"
    nominal_width_mm: float = 0.35
    draw_feed_mm_min: float = 2400.0
    travel_feed_mm_min: float = 6000.0
    downforce_g: float | None = None
    down_dwell_ms: int = 100
    up_dwell_ms: int = 50
    max_uncapped_s: float = 300.0
    tool_type: str = "fineliner"
    preferred_media: str = "paper"


class PenLibrary(BaseModel):
    """A named collection of pen profiles for layer-to-pen mapping."""

    name: str = "default"
    pens: list[PenProfile] = Field(default_factory=list)
    layer_map: dict[str, str] = Field(
        default_factory=dict,
        description="Maps layer name to pen ID.",
    )
    color_map: dict[str, str] = Field(
        default_factory=dict,
        description="Maps hex color to pen ID.",
    )
    default_pen_id: str = "pen-1"

    def get_pen(self, pen_id: str) -> PenProfile | None:
        """Look up a pen profile by its ID."""
        for pen in self.pens:
            if pen.id == pen_id:
                return pen
        return None

    def resolve_pen(
        self,
        *,
        layer: str | None = None,
        color: str | None = None,
        width: float | None = None,
    ) -> PenProfile:
        """Resolve a pen profile from layer name, color, or nominal width."""
        # 1. Exact layer match
        if layer and layer in self.layer_map:
            pen = self.get_pen(self.layer_map[layer])
            if pen:
                return pen

        # 2. Color match
        if color and color.lower() in self.color_map:
            pen = self.get_pen(self.color_map[color.lower()])
            if pen:
                return pen

        # 3. Closest width match
        if width is not None and self.pens:
            closest = min(self.pens, key=lambda p: abs(p.nominal_width_mm - width))
            if abs(closest.nominal_width_mm - width) < 0.05:
                return closest

        # 4. Default pen
        pen = self.get_pen(self.default_pen_id)
        return pen or (self.pens[0] if self.pens else PenProfile())

    def as_dict(self) -> dict[str, PenProfile]:
        """Return pen profiles keyed by ID for G-code export compatibility."""
        return {pen.id: pen for pen in self.pens}

    @classmethod
    def load(cls, source: str | Path) -> "PenLibrary":
        return cls.model_validate_json(Path(source).read_text(encoding="utf-8"))

    def save(self, target: str | Path) -> None:
        Path(target).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def iso_default(cls) -> "PenLibrary":
        """Create a default library with standard ISO technical pen widths."""
        iso_widths = [0.13, 0.18, 0.25, 0.35, 0.50, 0.70]
        iso_colors = ["#888888", "#666666", "#444444", "#111111", "#111111", "#000000"]
        pens = [
            PenProfile(
                id=f"pen-{i + 1}",
                color=iso_colors[i],
                nominal_width_mm=w,
                draw_feed_mm_min=max(1200.0, 3000.0 - w * 2000),
                travel_feed_mm_min=6000.0,
                down_dwell_ms=int(50 + w * 100),
                up_dwell_ms=50,
            )
            for i, w in enumerate(iso_widths)
        ]
        return cls(
            name="ISO Technical Pens",
            pens=pens,
            default_pen_id="pen-4",  # 0.35 mm is the most common
        )


class MachineProfile(BaseModel):
    """Physical machine configuration."""

    name: str = "VectorDraft X1"
    workspace_width_mm: float = 841.0
    workspace_height_mm: float = 594.0
    steps_per_mm_x: float = 80.0
    steps_per_mm_y: float = 80.0
    max_feed_mm_min: float = 10000.0
    soft_limit_x_mm: float = 860.0
    soft_limit_y_mm: float = 610.0
    pen_station_slots: int = 6
    pen_change_time_s: float = 15.0
    firmware: str = "grblHAL"
    firmware_version: str = "1.0"

    @classmethod
    def load(cls, source: str | Path) -> "MachineProfile":
        return cls.model_validate_json(Path(source).read_text(encoding="utf-8"))

    def save(self, target: str | Path) -> None:
        Path(target).write_text(self.model_dump_json(indent=2), encoding="utf-8")


class PlotSettings(BaseModel):
    page: PageSpec = Field(default_factory=lambda: PageSpec.preset("A1"))
    margin_mm: float = 5.0
    curve_step_mm: float = 1.0
    simplify_mm: float = 0.0
    origin_x_mm: float = 0.0
    origin_y_mm: float = 0.0
    pen_up_command: str = "M5"
    pen_down_command: str = "M3 S1000"


class Polyline(BaseModel):
    points: list[Point]
    layer: str = "default"
    pen: str | None = None
    color: str | None = None
    line_style: LineStyle = LineStyle.CONTINUOUS
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("points")
    @classmethod
    def validate_points(cls, points: list[Point]) -> list[Point]:
        if len(points) < 2:
            raise ValueError("A polyline needs at least two points.")
        cleaned: list[Point] = []
        for x, y in points:
            if not isfinite(x) or not isfinite(y):
                continue
            point = (float(x), float(y))
            if not cleaned or cleaned[-1] != point:
                cleaned.append(point)
        if len(cleaned) < 2:
            raise ValueError("A polyline needs at least two finite, distinct points.")
        return cleaned

    @property
    def start(self) -> Point:
        return self.points[0]

    @property
    def end(self) -> Point:
        return self.points[-1]

    @property
    def length_mm(self) -> float:
        return float(LineString(self.points).length)

    @property
    def bounds(self) -> Bounds:
        minx, miny, maxx, maxy = LineString(self.points).bounds
        return float(minx), float(miny), float(maxx), float(maxy)

    def reversed(self) -> "Polyline":
        return self.model_copy(update={"points": list(reversed(self.points))})

    def with_points(self, points: list[Point]) -> "Polyline":
        return self.model_copy(update={"points": points})


class VectorDocument(BaseModel):
    paths: list[Polyline] = Field(default_factory=list)
    page: PageSpec = Field(default_factory=lambda: PageSpec.preset("A1"))
    source_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.paths

    @property
    def layers(self) -> list[str]:
        return sorted({path.layer for path in self.paths})

    @property
    def total_draw_length_mm(self) -> float:
        return sum(path.length_mm for path in self.paths)

    @property
    def bounds(self) -> Bounds | None:
        if not self.paths:
            return None
        path_bounds = [path.bounds for path in self.paths]
        return (
            min(bounds[0] for bounds in path_bounds),
            min(bounds[1] for bounds in path_bounds),
            max(bounds[2] for bounds in path_bounds),
            max(bounds[3] for bounds in path_bounds),
        )

    def grouped_by_pen(self) -> dict[str, list[Polyline]]:
        groups: dict[str, list[Polyline]] = defaultdict(list)
        for path in self.paths:
            groups[path.pen or path.layer or "pen-1"].append(path)
        return dict(groups)

    def with_paths(self, paths: list[Polyline]) -> "VectorDocument":
        return self.model_copy(update={"paths": paths})


class JobPackage(BaseModel):
    """Everything needed to reproduce a plot job."""

    id: str = ""
    source_filename: str = ""
    document: VectorDocument = Field(default_factory=VectorDocument)
    pen_assignments: dict[str, str] = Field(
        default_factory=dict,
        description="Maps layer name to pen ID.",
    )
    calibration_name: str = "identity"
    estimated_duration_s: float = 0.0
    pen_changes: int = 0
    machine_name: str = "VectorDraft X1"
    firmware_version: str = ""
    status: str = "uploaded"
    created_at: str = ""
