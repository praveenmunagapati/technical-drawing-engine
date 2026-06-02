from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from vectordraft.model import VectorDocument


def save_preview(document: VectorDocument, output: str | Path, *, title: str | None = None) -> None:
    width_in = max(6.0, min(14.0, document.page.width_mm / 80.0))
    height_in = max(6.0, min(14.0, document.page.height_mm / 80.0))
    fig, ax = plt.subplots(figsize=(width_in, height_in))

    for path in document.paths:
        xs = [point[0] for point in path.points]
        ys = [point[1] for point in path.points]
        ax.plot(xs, ys, linewidth=max(path.metadata.get("preview_width", 0.4), 0.2), color=path.color or "#111111")

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(0, document.page.width_mm)
    ax.set_ylim(document.page.height_mm, 0)
    ax.set_xlabel("X mm")
    ax.set_ylabel("Y mm")
    ax.grid(True, linewidth=0.2, color="#dddddd")
    ax.set_title(title or "VectorDraft preview")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)
