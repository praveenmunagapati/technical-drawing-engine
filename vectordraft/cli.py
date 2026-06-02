from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from vectordraft.calibration import CalibrationProfile
from vectordraft.gcode import export_gcode
from vectordraft.importers import load_document
from vectordraft.model import PageSpec, PlotSettings
from vectordraft.optimizer import clean_document, estimate_travel_mm, sort_document
from vectordraft.preview import save_preview
from vectordraft.serial_stream import StreamSettings, available_ports, stream_file

app = typer.Typer(help="VectorDraft technical plotter pipeline.")
calibration_app = typer.Typer(help="Create and inspect calibration profiles.")
app.add_typer(calibration_app, name="calibration")
console = Console()


@app.command()
def inspect(
    input_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    page: Annotated[str | None, typer.Option(help="Override page preset, e.g. A1 or ARCH_D.")] = None,
    curve_step_mm: Annotated[float, typer.Option(help="Curve flattening step in millimeters.")] = 1.0,
) -> None:
    """Inspect a vector file and report plotter-relevant stats."""
    document = _load(input_file, page, curve_step_mm)
    _print_document_summary(document)


@app.command()
def preview(
    input_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output_png: Annotated[Path, typer.Argument(dir_okay=False)],
    page: Annotated[str | None, typer.Option(help="Override page preset.")] = None,
    curve_step_mm: Annotated[float, typer.Option(help="Curve flattening step in millimeters.")] = 1.0,
    simplify_mm: Annotated[float, typer.Option(help="Simplify tolerance in millimeters.")] = 0.0,
    sort_paths: Annotated[bool, typer.Option(help="Sort paths to reduce pen-up travel.")] = True,
    calibration: Annotated[Path | None, typer.Option(help="Optional calibration JSON profile.")] = None,
) -> None:
    """Render a PNG preview."""
    document = _prepare(input_file, page, curve_step_mm, simplify_mm, sort_paths)
    if calibration:
        document = CalibrationProfile.load(calibration).apply_document(document)
    save_preview(document, output_png, title=input_file.name)
    console.print(f"[green]Preview written:[/] {output_png}")


@app.command()
def export(
    input_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output_gcode: Annotated[Path, typer.Argument(dir_okay=False)],
    page: Annotated[str | None, typer.Option(help="Override page preset.")] = None,
    preview_png: Annotated[Path | None, typer.Option("--preview", help="Optional PNG preview path.")] = None,
    curve_step_mm: Annotated[float, typer.Option(help="Curve flattening step in millimeters.")] = 1.0,
    simplify_mm: Annotated[float, typer.Option(help="Simplify tolerance in millimeters.")] = 0.0,
    sort_paths: Annotated[bool, typer.Option(help="Sort paths to reduce pen-up travel.")] = True,
    origin_x_mm: Annotated[float, typer.Option(help="Machine X origin offset.")] = 0.0,
    origin_y_mm: Annotated[float, typer.Option(help="Machine Y origin offset.")] = 0.0,
    calibration: Annotated[Path | None, typer.Option(help="Optional calibration JSON profile.")] = None,
) -> None:
    """Export plotter G-code."""
    document = _prepare(input_file, page, curve_step_mm, simplify_mm, sort_paths)
    settings = PlotSettings(page=document.page, curve_step_mm=curve_step_mm, simplify_mm=simplify_mm, origin_x_mm=origin_x_mm, origin_y_mm=origin_y_mm)
    calibration_profile = CalibrationProfile.load(calibration) if calibration else CalibrationProfile.identity()
    output_gcode.write_text(export_gcode(document, settings=settings, calibration=calibration_profile), encoding="utf-8")
    console.print(f"[green]G-code written:[/] {output_gcode}")
    if preview_png:
        save_preview(calibration_profile.apply_document(document), preview_png, title=input_file.name)
        console.print(f"[green]Preview written:[/] {preview_png}")
    _print_document_summary(document)


@app.command()
def demo(output_dir: Annotated[Path, typer.Argument(file_okay=False)]) -> None:
    """Create a small SVG demo drawing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    demo_path = output_dir / "demo_house.svg"
    demo_path.write_text(_demo_svg(), encoding="utf-8")
    console.print(f"[green]Demo SVG written:[/] {demo_path}")


@app.command()
def ports() -> None:
    """List detected serial ports."""
    ports = available_ports()
    if not ports:
        console.print("[yellow]No serial ports detected.[/]")
        return
    for port in ports:
        console.print(port)


@app.command()
def stream(
    gcode_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    port: Annotated[str, typer.Argument(help="Serial port, e.g. COM3 or /dev/ttyUSB0.")],
    baudrate: Annotated[int, typer.Option(help="Controller baudrate.")] = 115200,
    timeout_s: Annotated[float, typer.Option(help="Serial read timeout in seconds.")] = 2.0,
    reset_after_open_s: Annotated[float, typer.Option(help="Delay after opening/resetting controller.")] = 2.0,
    soft_reset: Annotated[bool, typer.Option(help="Send GRBL soft reset before streaming.")] = True,
    dry_run: Annotated[bool, typer.Option(help="Print acknowledged command count without opening the port.")] = False,
) -> None:
    """Stream G-code to a GRBL/FluidNC-style controller."""
    settings = StreamSettings(
        baudrate=baudrate,
        timeout_s=timeout_s,
        reset_after_open_s=reset_after_open_s,
        send_soft_reset=soft_reset,
    )
    result = stream_file(gcode_file, port=port, settings=settings, dry_run=dry_run, progress=_stream_progress)
    if result.errors:
        console.print(f"[red]Stopped after {result.commands_sent} commands:[/] {result.errors[0]}")
        raise typer.Exit(code=1)
    mode = "dry-run " if result.dry_run else ""
    console.print(f"[green]{mode}Stream complete:[/] {result.commands_sent} commands")


@calibration_app.command("create")
def calibration_create(
    output_json: Annotated[Path, typer.Argument(dir_okay=False)],
    name: Annotated[str, typer.Option(help="Profile name.")] = "machine-calibration",
    scale_x: Annotated[float, typer.Option(help="X scale multiplier.")] = 1.0,
    scale_y: Annotated[float, typer.Option(help="Y scale multiplier.")] = 1.0,
    rotation_deg: Annotated[float, typer.Option(help="Rotation correction in degrees.")] = 0.0,
    skew_x_deg: Annotated[float, typer.Option(help="X shear angle in degrees.")] = 0.0,
    skew_y_deg: Annotated[float, typer.Option(help="Y shear angle in degrees.")] = 0.0,
    offset_x_mm: Annotated[float, typer.Option(help="Machine X offset in millimeters.")] = 0.0,
    offset_y_mm: Annotated[float, typer.Option(help="Machine Y offset in millimeters.")] = 0.0,
) -> None:
    """Create a calibration JSON profile from affine components."""
    profile = CalibrationProfile.from_components(
        name=name,
        scale_x=scale_x,
        scale_y=scale_y,
        rotation_deg=rotation_deg,
        skew_x_deg=skew_x_deg,
        skew_y_deg=skew_y_deg,
        offset_x_mm=offset_x_mm,
        offset_y_mm=offset_y_mm,
    )
    profile.save(output_json)
    console.print(f"[green]Calibration written:[/] {output_json}")


@calibration_app.command("inspect")
def calibration_inspect(profile_json: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Inspect a calibration JSON profile."""
    profile = CalibrationProfile.load(profile_json)
    table = Table(title=f"Calibration: {profile.name}")
    table.add_column("Row")
    table.add_column("Values")
    for index, row in enumerate(profile.matrix, start=1):
        table.add_row(str(index), ", ".join(f"{value:.8f}" for value in row))
    console.print(table)


def _load(input_file: Path, page_name: str | None, curve_step_mm: float):
    page = PageSpec.preset(page_name) if page_name else None
    return load_document(input_file, page=page, curve_step_mm=curve_step_mm)


def _prepare(input_file: Path, page_name: str | None, curve_step_mm: float, simplify_mm: float, sort_paths: bool):
    document = _load(input_file, page_name, curve_step_mm)
    document = clean_document(document, simplify_mm=simplify_mm)
    if sort_paths:
        document = sort_document(document)
    return document


def _print_document_summary(document) -> None:
    table = Table(title="VectorDraft document")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Source", document.source_path or "unknown")
    table.add_row("Page", f"{document.page.name} {document.page.width_mm:.2f} x {document.page.height_mm:.2f} mm")
    table.add_row("Paths", str(len(document.paths)))
    table.add_row("Layers", ", ".join(document.layers) or "-")
    table.add_row("Draw length", f"{document.total_draw_length_mm:.2f} mm")
    table.add_row("Travel estimate", f"{estimate_travel_mm(document.paths):.2f} mm")
    table.add_row("Bounds", _format_bounds(document.bounds))
    console.print(table)


def _stream_progress(index: int, command: str, response: str) -> None:
    if index <= 5 or index % 100 == 0 or response.lower().startswith("error"):
        console.print(f"{index:>5} {command} -> {response}")


def _format_bounds(bounds) -> str:
    if not bounds:
        return "-"
    minx, miny, maxx, maxy = bounds
    return f"{minx:.2f}, {miny:.2f} -> {maxx:.2f}, {maxy:.2f} mm"


def _demo_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">
  <g id="walls" stroke="#111111" fill="none" stroke-width="0.35">
    <path class="walls" stroke="#111111" d="M 30 210 L 30 110 L 105 55 L 180 110 L 180 210 Z"/>
    <path class="walls" stroke="#111111" d="M 60 210 L 60 145 L 100 145 L 100 210"/>
    <path class="walls" stroke="#111111" d="M 125 155 L 165 155 L 165 185 L 125 185 Z"/>
    <path class="walls" stroke="#111111" d="M 30 110 L 180 110"/>
  </g>
  <g id="dimensions" stroke="#0b5cad" fill="none" stroke-width="0.18">
    <path class="dimensions" stroke="#0b5cad" d="M 30 230 L 180 230 M 30 225 L 30 235 M 180 225 L 180 235"/>
    <path class="dimensions" stroke="#0b5cad" d="M 190 210 L 190 55 M 185 210 L 195 210 M 185 55 L 195 55"/>
  </g>
</svg>
"""
