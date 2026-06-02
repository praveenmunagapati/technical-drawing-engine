from __future__ import annotations

from datetime import datetime, timezone

from vectordraft.calibration import CalibrationProfile
from vectordraft.model import PenLibrary, PenProfile, PlotSettings, Polyline, VectorDocument
from vectordraft.optimizer import estimate_travel_mm


def export_gcode(
    document: VectorDocument,
    *,
    settings: PlotSettings | None = None,
    pen_profiles: dict[str, PenProfile] | None = None,
    pen_library: PenLibrary | None = None,
    calibration: CalibrationProfile | None = None,
) -> str:
    settings = settings or PlotSettings(page=document.page)
    calibration = calibration or CalibrationProfile.identity()

    # Build effective pen lookup: pen_library takes priority over raw dict
    effective_profiles = pen_profiles or {}
    if pen_library:
        effective_profiles = {**pen_library.as_dict(), **effective_profiles}

    est_time = estimate_plot_time(document, pen_profiles=effective_profiles, calibration=calibration)
    est_min, est_sec = divmod(int(est_time), 60)

    lines: list[str] = [
        "; VectorDraft G-code",
        f"; Generated: {datetime.now(timezone.utc).isoformat()}",
        f"; Source: {document.source_path or 'unknown'}",
        f"; Page: {document.page.name} {document.page.width_mm:.3f} x {document.page.height_mm:.3f} mm",
        f"; Calibration: {calibration.name}",
        f"; Draw length: {document.total_draw_length_mm:.3f} mm",
        f"; Travel estimate: {estimate_travel_mm(document.paths):.3f} mm",
        f"; Estimated plot time: {est_min}m {est_sec}s",
        "G21 ; millimeters",
        "G90 ; absolute positioning",
        settings.pen_up_command,
    ]

    active_pen: str | None = None
    pen_changes = 0
    for index, path in enumerate(document.paths, start=1):
        pen_id = path.pen or path.layer or "pen-1"
        profile = _resolve_profile(pen_id, path, effective_profiles, pen_library)
        resolved_id = profile.id
        if active_pen != resolved_id:
            lines.append(settings.pen_up_command)
            if active_pen is not None:
                # Pen change required
                pen_changes += 1
                lines.append(f"M0 ; CHANGE TO PEN {resolved_id}")
            lines.append(
                f"; PEN {resolved_id} layer={path.layer} width={profile.nominal_width_mm:.3f} color={profile.color}"
            )
            active_pen = resolved_id
        lines.extend(_path_to_gcode(path, settings=settings, profile=profile, calibration=calibration, index=index))

    lines.extend([
        settings.pen_up_command,
        "G0 X0.000 Y0.000",
        f"; Pen changes: {pen_changes}",
        "M2 ; end",
    ])
    return "\n".join(lines) + "\n"


def estimate_plot_time(
    document: VectorDocument,
    *,
    pen_profiles: dict[str, PenProfile] | None = None,
    pen_library: PenLibrary | None = None,
    calibration: CalibrationProfile | None = None,
    pen_change_time_s: float = 15.0,
) -> float:
    """Estimate total plot time in seconds from feed rates, dwell, and pen changes."""
    pen_profiles = pen_profiles or {}
    if pen_library:
        pen_profiles = {**pen_library.as_dict(), **pen_profiles}

    total_s = 0.0
    active_pen: str | None = None

    for path in document.paths:
        pen_id = path.pen or path.layer or "pen-1"
        profile = pen_profiles.get(pen_id, PenProfile(id=pen_id))

        # Pen change time
        if active_pen is not None and active_pen != pen_id:
            total_s += pen_change_time_s
        active_pen = pen_id

        # Travel to start (pen up)
        # Simplified: just use path length / travel feed
        travel_feed = profile.travel_feed_mm_min
        if travel_feed > 0:
            total_s += 0.0  # Approximation; exact travel depends on previous position

        # Draw time
        draw_feed = profile.draw_feed_mm_min
        if draw_feed > 0:
            total_s += (path.length_mm / draw_feed) * 60.0

        # Pen up/down dwell
        total_s += (profile.down_dwell_ms + profile.up_dwell_ms) / 1000.0

    # Add estimated travel time (pen-up movement)
    travel_mm = estimate_travel_mm(document.paths)
    default_travel_feed = 6000.0
    if pen_profiles:
        default_travel_feed = max(p.travel_feed_mm_min for p in pen_profiles.values())
    if default_travel_feed > 0:
        total_s += (travel_mm / default_travel_feed) * 60.0

    return total_s


def _resolve_profile(
    pen_id: str,
    path: Polyline,
    profiles: dict[str, PenProfile],
    library: PenLibrary | None,
) -> PenProfile:
    """Resolve the best pen profile for a path."""
    if pen_id in profiles:
        return profiles[pen_id]
    if library:
        return library.resolve_pen(layer=path.layer, color=path.color)
    return PenProfile(id=pen_id, color=path.color or "#111111")


def _path_to_gcode(
    path: Polyline,
    *,
    settings: PlotSettings,
    profile: PenProfile,
    calibration: CalibrationProfile,
    index: int,
) -> list[str]:
    start = _machine_point(path.start, settings, calibration)
    commands = [
        f"; PATH {index} layer={path.layer} points={len(path.points)} length={path.length_mm:.3f}",
        f"G0 X{start[0]:.3f} Y{start[1]:.3f} F{profile.travel_feed_mm_min:.0f}",
        settings.pen_down_command,
    ]
    if profile.down_dwell_ms > 0:
        commands.append(f"G4 P{profile.down_dwell_ms / 1000:.3f}")
    for point in path.points[1:]:
        x, y = _machine_point(point, settings, calibration)
        commands.append(f"G1 X{x:.3f} Y{y:.3f} F{profile.draw_feed_mm_min:.0f}")
    commands.append(settings.pen_up_command)
    if profile.up_dwell_ms > 0:
        commands.append(f"G4 P{profile.up_dwell_ms / 1000:.3f}")
    return commands


def _machine_point(point: tuple[float, float], settings: PlotSettings, calibration: CalibrationProfile) -> tuple[float, float]:
    x, y = calibration.apply_point(point)
    return x + settings.origin_x_mm, y + settings.origin_y_mm
