from __future__ import annotations

import math
from typing import Any

from ..types import MetricSnapshot, ProbeResult, ProbeState


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    return None


def fetch_probe_metrics(
    run_path: str,
    api: Any | None = None,
    loss_key: str = "loss",
) -> tuple[float | None, list[MetricSnapshot]]:
    if api is None:
        import wandb

        api = wandb.Api()
    run = api.run(run_path)
    history: list[MetricSnapshot] = []
    last_finite_loss: float | None = None
    for row in run.scan_history():
        if not isinstance(row, dict):
            continue
        step_raw = row.get("_step")
        step = int(step_raw) if isinstance(step_raw, (int, float)) else len(history)
        metrics: dict[str, float] = {}
        for key, raw in row.items():
            if key.startswith("_"):
                continue
            coerced = _coerce_float(raw)
            if coerced is not None:
                metrics[key] = coerced
        if metrics:
            history.append(MetricSnapshot(step=step, metrics=metrics))
            if loss_key in metrics:
                last_finite_loss = metrics[loss_key]
    summary_loss = _coerce_float(run.summary.get(loss_key)) if hasattr(run, "summary") else None
    final_loss = summary_loss if summary_loss is not None else last_finite_loss
    return final_loss, history


def find_probe_run(api: Any, entity: str, project: str, group: str, name: str) -> str | None:
    try:
        runs = api.runs(f"{entity}/{project}", filters={"group": group, "displayName": name})
        for run in runs:
            return str(run.id)
    except Exception:
        return None
    return None


def pick_winner(results: list[ProbeResult], loss_key: str = "loss") -> ProbeResult | None:
    candidates = [
        r for r in results if r.state == ProbeState.FINISHED and r.final_loss is not None and math.isfinite(r.final_loss)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: r.final_loss)  # type: ignore[arg-type, return-value]


def summarize(results: list[ProbeResult]) -> str:
    lines: list[str] = []
    for r in results:
        loss = "n/a" if r.final_loss is None else f"{r.final_loss:.4f}"
        lines.append(f"{r.spec.id} [{r.state}] branch={r.spec.branch} final_loss={loss}")
    return "\n".join(lines)
