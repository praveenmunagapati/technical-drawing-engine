"""Generate SVG preview strings from VectorDocument for in-browser rendering."""

from __future__ import annotations

from xml.sax.saxutils import escape

from vectordraft.model import PenLibrary, PenProfile, VectorDocument


def render_svg(
    document: VectorDocument,
    *,
    pen_library: PenLibrary | None = None,
    show_page_border: bool = True,
    background: str = "#ffffff",
) -> str:
    """Return a standalone SVG string for a VectorDocument."""
    w = document.page.width_mm
    h = document.page.height_mm

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w:.3f} {h:.3f}" '
        f'width="100%" height="100%" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="background:{background}">',
    ]

    if show_page_border:
        parts.append(
            f'  <rect x="0" y="0" width="{w:.3f}" height="{h:.3f}" '
            f'fill="none" stroke="#cccccc" stroke-width="0.5" stroke-dasharray="4,2"/>'
        )

    # Group paths by layer for layer visibility toggles
    layers: dict[str, list[int]] = {}
    for i, path in enumerate(document.paths):
        layers.setdefault(path.layer, []).append(i)

    for layer_name, indices in layers.items():
        safe_id = escape(layer_name.replace(" ", "_").replace("/", "_"))
        parts.append(f'  <g id="layer-{safe_id}" data-layer="{escape(layer_name)}">')

        for idx in indices:
            path = document.paths[idx]
            profile = _resolve(path, pen_library)
            color = path.color or profile.color
            width = profile.nominal_width_mm

            points_str = " ".join(f"{x:.3f},{y:.3f}" for x, y in path.points)
            parts.append(
                f'    <polyline points="{points_str}" '
                f'fill="none" stroke="{color}" stroke-width="{max(width, 0.15):.3f}" '
                f'stroke-linecap="round" stroke-linejoin="round" '
                f'data-layer="{escape(layer_name)}" data-index="{idx}"/>'
            )

        parts.append("  </g>")

    parts.append("</svg>")
    return "\n".join(parts)


def _resolve(path, pen_library: PenLibrary | None) -> PenProfile:
    if pen_library:
        return pen_library.resolve_pen(layer=path.layer, color=path.color)
    return PenProfile(color=path.color or "#111111")
