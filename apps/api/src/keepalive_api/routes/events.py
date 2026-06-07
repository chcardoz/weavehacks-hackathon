from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_pg_pool
from keepalive_api.models import EventIn, EventsRequest, ProjectMeta

if TYPE_CHECKING:
    import asyncpg

    # pool.acquire() yields a PoolConnectionProxy, not a bare Connection; accept either.
    PgConn = asyncpg.Connection | asyncpg.pool.PoolConnectionProxy
else:
    PgConn = Any

logger = logging.getLogger("keepalive_api.events")

router = APIRouter()

_MAX_EVENTS = 100
_LOSS_HISTORY_CAP = 60

_INSERT_EVENT = """
    INSERT INTO event (project_id, incident_id, agent_id, source, level, type, message, data, created_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
"""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_ts(ts: str | None) -> datetime:
    """Parse an ISO ts (accepting a trailing Z) into a naive UTC datetime; default now()."""
    if not ts:
        return _now()
    try:
        cleaned = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return _now()
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _parse_deadline(value: Any) -> datetime | None:
    """Accept deadline as epoch seconds (int/float) or an ISO string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC).replace(tzinfo=None)
    if isinstance(value, str):
        return _parse_ts(value)
    return None


async def _upsert_project(
    conn: PgConn,
    project_id: str,
    meta: ProjectMeta | None,
    apikey_id: str,
    *,
    status: str | None = None,
    when: datetime,
) -> None:
    meta = meta or ProjectMeta()
    await conn.execute(
        """
        INSERT INTO project (
            id, name, repo, wandb_run_id, wandb_url, commit_sha, demo_mode,
            status, apikey_id, last_event_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
        ON CONFLICT (id) DO UPDATE SET
            name = COALESCE(EXCLUDED.name, project.name),
            repo = COALESCE(EXCLUDED.repo, project.repo),
            wandb_run_id = COALESCE(EXCLUDED.wandb_run_id, project.wandb_run_id),
            wandb_url = COALESCE(EXCLUDED.wandb_url, project.wandb_url),
            commit_sha = COALESCE(EXCLUDED.commit_sha, project.commit_sha),
            demo_mode = COALESCE(EXCLUDED.demo_mode, project.demo_mode),
            status = COALESCE(EXCLUDED.status, project.status),
            apikey_id = EXCLUDED.apikey_id,
            last_event_at = EXCLUDED.last_event_at,
            updated_at = EXCLUDED.updated_at
        """,
        project_id,
        meta.name,
        meta.repo,
        meta.wandb_run_id,
        meta.wandb_url,
        meta.commit_sha,
        meta.demo_mode,
        status,
        apikey_id,
        when,
    )


async def _set_project_status(conn: PgConn, project_id: str, status: str, when: datetime) -> None:
    await conn.execute(
        "UPDATE project SET status = $2, updated_at = $3 WHERE id = $1",
        project_id,
        status,
        when,
    )


def _append_loss_history(history: Any, step: Any, loss: Any) -> str:
    points: list[dict[str, Any]] = list(history) if isinstance(history, list) else []
    point: dict[str, Any] = {}
    if step is not None:
        point["step"] = step
    if loss is not None:
        point["loss"] = loss
    if point:
        points.append(point)
    return json.dumps(points[-_LOSS_HISTORY_CAP:])


async def _apply_state_effect(
    conn: PgConn,
    ev: EventIn,
    apikey_id: str,
    when: datetime,
) -> None:
    """Apply the contract's state effect for a recognized event type. Unknown types: no-op."""
    t = ev.type
    data = ev.data
    pid = ev.project_id

    if t == "run.started":
        await _upsert_project(conn, pid, ev.project, apikey_id, status="training", when=when)
        return

    if t == "run.heartbeat":
        # Append to loss_history (capped) and refresh current_step/latest_loss/last_event_at.
        row = await conn.fetchrow("SELECT loss_history FROM project WHERE id = $1", pid)
        history = row["loss_history"] if row is not None else None
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except ValueError:
                history = None
        new_history = _append_loss_history(history, data.get("step"), data.get("loss"))
        await conn.execute(
            """
            UPDATE project
            SET current_step = COALESCE($2, current_step),
                latest_loss = COALESCE($3, latest_loss),
                loss_history = $4::jsonb,
                last_event_at = $5,
                updated_at = $5
            WHERE id = $1
            """,
            pid,
            data.get("step"),
            data.get("loss"),
            new_history,
            when,
        )
        return

    if t == "run.stopped":
        await _set_project_status(conn, pid, "stopped", when)
        return

    if t == "incident.detected":
        incident_id = ev.incident_id
        if incident_id is None:
            logger.warning("incident.detected without incident_id for project %s", pid)
            return
        await conn.execute(
            """
            INSERT INTO incident (id, project_id, kind, step, status)
            VALUES ($1, $2, $3, $4, 'detected')
            ON CONFLICT (id) DO UPDATE SET
                kind = COALESCE(EXCLUDED.kind, incident.kind),
                step = COALESCE(EXCLUDED.step, incident.step),
                status = 'detected'
            """,
            incident_id,
            pid,
            data.get("kind"),
            data.get("step"),
        )
        await _set_project_status(conn, pid, "incident", when)
        return

    if t == "incident.diagnosed":
        if ev.incident_id is None:
            return
        await conn.execute(
            "UPDATE incident SET diagnosis = $2, status = 'diagnosing' WHERE id = $1",
            ev.incident_id,
            data.get("diagnosis"),
        )
        return

    if t == "incident.escalated":
        if ev.incident_id is None:
            return
        deadline = _parse_deadline(data.get("deadline_ts"))
        await conn.execute(
            """
            UPDATE incident
            SET status = 'awaiting_human',
                deadline_at = COALESCE($2, deadline_at),
                weave_url = COALESCE($3, weave_url)
            WHERE id = $1
            """,
            ev.incident_id,
            deadline,
            data.get("weave_url"),
        )
        await _set_project_status(conn, pid, "awaiting_human", when)
        return

    if t == "incident.human_reply":
        if ev.incident_id is None:
            return
        await conn.execute(
            "UPDATE incident SET human_reply = $2 WHERE id = $1",
            ev.incident_id,
            data.get("reply"),
        )
        return

    if t == "incident.deadline_expired":
        if ev.incident_id is None:
            return
        await conn.execute("UPDATE incident SET status = 'racing' WHERE id = $1", ev.incident_id)
        await _set_project_status(conn, pid, "racing", when)
        return

    if t == "agent.spawned":
        if ev.agent_id is None:
            logger.warning("agent.spawned without agent_id for project %s", pid)
            return
        await conn.execute(
            """
            INSERT INTO agent (id, incident_id, project_id, hypothesis, cursor_agent_id, state)
            VALUES ($1, $2, $3, $4, $5, 'spawned')
            ON CONFLICT (id) DO UPDATE SET
                incident_id = COALESCE(EXCLUDED.incident_id, agent.incident_id),
                project_id = COALESCE(EXCLUDED.project_id, agent.project_id),
                hypothesis = COALESCE(EXCLUDED.hypothesis, agent.hypothesis),
                cursor_agent_id = COALESCE(EXCLUDED.cursor_agent_id, agent.cursor_agent_id),
                state = 'spawned'
            """,
            ev.agent_id,
            ev.incident_id,
            pid,
            data.get("hypothesis"),
            data.get("cursor_agent_id"),
        )
        return

    if t == "agent.status":
        if ev.agent_id is None:
            return
        await conn.execute(
            """
            UPDATE agent
            SET state = COALESCE($2, state),
                branch = COALESCE($3, branch),
                cursor_agent_id = COALESCE($4, cursor_agent_id),
                wandb_run_id = COALESCE($5, wandb_run_id),
                error = COALESCE($6, error)
            WHERE id = $1
            """,
            ev.agent_id,
            data.get("state"),
            data.get("branch"),
            data.get("cursor_agent_id"),
            data.get("wandb_run_id"),
            data.get("error"),
        )
        return

    if t == "agent.metrics":
        if ev.agent_id is None:
            return
        row = await conn.fetchrow("SELECT loss_history FROM agent WHERE id = $1", ev.agent_id)
        history = row["loss_history"] if row is not None else None
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except ValueError:
                history = None
        new_history = _append_loss_history(history, data.get("step"), data.get("loss"))
        await conn.execute(
            """
            UPDATE agent
            SET loss_history = $2::jsonb,
                final_loss = COALESCE($3, final_loss)
            WHERE id = $1
            """,
            ev.agent_id,
            new_history,
            data.get("final_loss"),
        )
        return

    if t == "incident.promoted":
        if ev.incident_id is None:
            return
        winner = data.get("winner_agent_id")
        await conn.execute(
            """
            UPDATE incident
            SET winner_agent_id = $2, status = 'resolved', resolved_at = $3
            WHERE id = $1
            """,
            ev.incident_id,
            winner,
            when,
        )
        await _set_project_status(conn, pid, "recovered", when)
        if winner is not None:
            await conn.execute(
                "UPDATE agent SET state = 'winner', final_loss = COALESCE($2, final_loss) WHERE id = $1",
                winner,
                data.get("final_loss"),
            )
        return

    if t == "incident.stopped":
        if ev.incident_id is not None:
            await conn.execute("UPDATE incident SET status = 'stopped' WHERE id = $1", ev.incident_id)
        await _set_project_status(conn, pid, "stopped", when)
        return

    # unknown / "log": event row only, no state effect.


@router.post("/v1/events")
async def ingest_events(
    req: EventsRequest,
    request: Request,
    apikey_id: str = Depends(require_api_key),
) -> dict[str, int]:
    if len(req.events) > _MAX_EVENTS:
        raise HTTPException(status_code=422, detail=f"too many events: max {_MAX_EVENTS} per batch")

    pool = get_pg_pool(request)
    if pool is None:
        logger.warning("no pg pool configured; dropping %d events", len(req.events))
        return {"accepted": 0}

    accepted = 0
    project_ids: list[str] = []
    async with pool.acquire() as conn:
        for ev in req.events:
            when = _parse_ts(ev.ts)
            # 1) ALWAYS insert the event row.
            try:
                await conn.execute(
                    _INSERT_EVENT,
                    ev.project_id,
                    ev.incident_id,
                    ev.agent_id,
                    ev.source,
                    ev.level,
                    ev.type,
                    ev.message,
                    json.dumps(ev.data),
                    when,
                )
                accepted += 1
            except Exception:
                logger.warning("event insert failed for project %s type %s", ev.project_id, ev.type, exc_info=True)

            if ev.project_id not in project_ids:
                project_ids.append(ev.project_id)

            # 2) Apply the state effect; isolate failures so the event row still lands.
            try:
                await _apply_state_effect(conn, ev, apikey_id, when)
            except Exception:
                logger.warning("state effect failed for project %s type %s", ev.project_id, ev.type, exc_info=True)

        # 3) Always bump last_event_at for every distinct project in the batch.
        when = _now()
        for pid in project_ids:
            try:
                await conn.execute(
                    "UPDATE project SET last_event_at = $2, updated_at = $2 WHERE id = $1",
                    pid,
                    when,
                )
            except Exception:
                logger.warning("last_event_at bump failed for project %s", pid, exc_info=True)

    return {"accepted": accepted}
