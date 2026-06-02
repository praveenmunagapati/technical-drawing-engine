from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, field_validator

from vectordraft.model import Point, Polyline, VectorDocument


class CalibrationProfile(BaseModel):
    """Affine machine calibration from drawing coordinates to machine coordinates."""

    name: str = "identity"
    matrix: list[list[float]] = Field(default_factory=lambda: _identity_matrix().tolist())
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("matrix")
    @classmethod
    def validate_matrix(cls, matrix: list[list[float]]) -> list[list[float]]:
        if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
            raise ValueError("Calibration matrix must be 3x3.")
        return [[float(value) for value in row] for row in matrix]

    @classmethod
    def identity(cls, *, name: str = "identity") -> "CalibrationProfile":
        return cls(name=name)

    @classmethod
    def from_components(
        cls,
        *,
        name: str = "component-calibration",
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        rotation_deg: float = 0.0,
        skew_x_deg: float = 0.0,
        skew_y_deg: float = 0.0,
        offset_x_mm: float = 0.0,
        offset_y_mm: float = 0.0,
    ) -> "CalibrationProfile":
        scale = np.array(
            [
                [scale_x, 0.0, 0.0],
                [0.0, scale_y, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        rotation = _rotation_matrix(rotation_deg)
        skew = np.array(
            [
                [1.0, math.tan(math.radians(skew_x_deg)), 0.0],
                [math.tan(math.radians(skew_y_deg)), 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        offset = np.array(
            [
                [1.0, 0.0, offset_x_mm],
                [0.0, 1.0, offset_y_mm],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        matrix = offset @ skew @ rotation @ scale
        return cls(
            name=name,
            matrix=matrix.tolist(),
            metadata={
                "scale_x": scale_x,
                "scale_y": scale_y,
                "rotation_deg": rotation_deg,
                "skew_x_deg": skew_x_deg,
                "skew_y_deg": skew_y_deg,
                "offset_x_mm": offset_x_mm,
                "offset_y_mm": offset_y_mm,
            },
        )

    @classmethod
    def load(cls, source: str | Path) -> "CalibrationProfile":
        return cls.model_validate_json(Path(source).read_text(encoding="utf-8"))

    def save(self, target: str | Path) -> None:
        Path(target).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def apply_point(self, point: Point) -> Point:
        vector = np.array([point[0], point[1], 1.0], dtype=float)
        result = np.array(self.matrix, dtype=float) @ vector
        return float(result[0]), float(result[1])

    def apply_path(self, path: Polyline) -> Polyline:
        return path.with_points([self.apply_point(point) for point in path.points])

    def apply_document(self, document: VectorDocument) -> VectorDocument:
        return document.with_paths([self.apply_path(path) for path in document.paths])


def _identity_matrix() -> np.ndarray:
    return np.eye(3, dtype=float)


def _rotation_matrix(rotation_deg: float) -> np.ndarray:
    radians = math.radians(rotation_deg)
    c = math.cos(radians)
    s = math.sin(radians)
    return np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
