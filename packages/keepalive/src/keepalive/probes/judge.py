from __future__ import annotations

import math
import time
from collections.abc import Callable
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


def _default_api_factory() -> Any:
    import wandb

    return wandb.Api()


def collect_probe_metrics(
    entity: str,
    project: str,
    group: str,
    name: str,
    loss_key: str = "loss",
    *,
    poll_interval_s: float = 10.0,
    timeout_s: float = 120.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    api_factory: Callable[[], Any] = _default_api_factory,
) -> tuple[str | None, float | None, list[MetricSnapshot]]:
    """Find a probe run and its metrics, retrying while W&B history ingestion catches up.

    The public API lags seconds to minutes behind a finished run, and the Run object
    caches — so each attempt builds a fresh Api(). Returns as soon as the run is found
    AND a final loss is available; on timeout returns the best partial result.
    """
    deadline = time.monotonic() + timeout_s
    run_id: str | None = None
    final_loss: float | None = None
    history: list[MetricSnapshot] = []
    while True:
        try:
            api = api_factory()
            run_id = find_probe_run(api, entity, project, group, name) or run_id
            if run_id is not None:
                final_loss, history = fetch_probe_metrics(f"{entity}/{project}/{run_id}", api=api, loss_key=loss_key)
        except Exception:
            pass
        if run_id is not None and final_loss is not None:
            return run_id, final_loss, history
        if time.monotonic() >= deadline:
            return run_id, final_loss, history
        sleep_fn(poll_interval_s)


def pick_winner(results: list[ProbeResult], loss_key: str = "loss") -> ProbeResult | None:
    candidates = [
        r
        for r in results
        if r.state == ProbeState.FINISHED and r.final_loss is not None and math.isfinite(r.final_loss)
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
