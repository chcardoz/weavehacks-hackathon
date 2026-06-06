from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from ..types import ProbeExecutor, ProbeResult, ProbeSpec, ProbeState, RunContext
from . import judge


def race(
    specs: list[ProbeSpec],
    executor: ProbeExecutor,
    ctx: RunContext,
    *,
    steps: int,
    on_update: Callable[[ProbeResult], None] | None = None,
) -> tuple[ProbeResult | None, list[ProbeResult]]:
    runnable = [s for s in specs if s.state == ProbeState.READY and s.branch]
    skipped = [s for s in specs if s not in runnable]

    results: list[ProbeResult] = []
    for spec in skipped:
        spec.state = ProbeState.FAILED
        result = ProbeResult(
            spec=spec, wandb_run_id=None, history=[], final_loss=None, state=ProbeState.FAILED, error="no branch"
        )
        results.append(result)
        if on_update is not None:
            on_update(result)

    if runnable:
        with ThreadPoolExecutor(max_workers=max(len(runnable), 1)) as pool:
            future_to_spec = {pool.submit(executor.execute, spec, ctx, steps=steps): spec for spec in runnable}
            for future in as_completed(future_to_spec):
                spec = future_to_spec[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    spec.state = ProbeState.FAILED
                    result = ProbeResult(
                        spec=spec,
                        wandb_run_id=None,
                        history=[],
                        final_loss=None,
                        state=ProbeState.FAILED,
                        error=str(exc),
                    )
                results.append(result)
                if on_update is not None:
                    on_update(result)

    winner = judge.pick_winner(results, ctx.loss_key)
    for result in results:
        if winner is not None and result.spec.id == winner.spec.id:
            continue
        _kill(executor, result.spec)
        if result.state == ProbeState.RUNNING:
            result.state = ProbeState.KILLED
            result.spec.state = ProbeState.KILLED
    return winner, results


def _kill(executor: ProbeExecutor, spec: ProbeSpec) -> None:
    try:
        executor.kill(spec)
    except Exception:
        pass
