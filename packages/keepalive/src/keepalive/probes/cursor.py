from __future__ import annotations

import contextlib
import time
from typing import Any

from ..config import Settings
from ..types import FixHypothesis, ProbeSpec, ProbeState, RunContext, new_id

_TERMINAL_OK = {"finished", "completed", "done", "succeeded", "success"}
_TERMINAL_FAIL = {"failed", "error", "errored", "expired", "cancelled", "canceled", "aborted"}


class IntegrationNotConnectedError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "Cursor cannot access this repository. Connect it at cursor.com Dashboard "
                "→ Integrations → GitHub (grant the training repo read-write access), then retry."
            )
        )


def _looks_unconnected(status: int, body: str) -> bool:
    if status in (403, 404):
        return True
    lowered = body.lower()
    return status >= 400 and ("not connected" in lowered or "integration" in lowered or "repository" in lowered)


def _extract_branch(payload: dict[str, Any]) -> str | None:
    git = payload.get("git")
    if isinstance(git, dict):
        branches = git.get("branches")
        if isinstance(branches, list) and branches:
            first = branches[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for key in ("branch", "name"):
                    if first.get(key):
                        return str(first[key])
    target = payload.get("target")
    if isinstance(target, dict) and target.get("branchName"):
        return str(target["branchName"])
    if payload.get("branchName"):
        return str(payload["branchName"])
    return None


def _extract_status(payload: dict[str, Any]) -> str:
    for key in ("status", "state"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


class CursorClient:
    def __init__(self, settings: Settings, http: Any | None = None) -> None:
        self._settings = settings
        self._base = f"{settings.cursor_api_url.rstrip('/')}/v1"
        self._sdk: Any | None = None
        self._sdk_kind: str | None = None
        if http is not None:
            self._http = http
            self._owns_http = False
        else:
            self._http = self._build_http()
            self._owns_http = True
        self._load_sdk()

    def _build_http(self) -> Any:
        import httpx

        return httpx.Client(
            base_url=self._base,
            headers={"Authorization": f"Bearer {self._settings.cursor_api_key}"},
            timeout=30.0,
        )

    def _load_sdk(self) -> None:
        try:
            import cursor_sdk  # pyright: ignore[reportMissingImports]

            self._sdk = cursor_sdk
            self._sdk_kind = "cursor_sdk"
            return
        except ImportError:
            pass
        try:
            import cursor_agent_sdk  # pyright: ignore[reportMissingImports]

            self._sdk = cursor_agent_sdk
            self._sdk_kind = "cursor_agent_sdk"
            return
        except ImportError:
            self._sdk = None
            self._sdk_kind = None

    def _build_prompt(self, hypothesis: FixHypothesis, ctx: RunContext) -> str:
        return (
            f"Fix hypothesis: {hypothesis.title}\n\n"
            f"Rationale: {hypothesis.rationale}\n\n"
            f"Instructions: {hypothesis.instructions}\n\n"
            "Constraints:\n"
            f"- Branch from the failing commit {ctx.commit_sha}.\n"
            "- Keep the diff minimal and targeted to this single hypothesis.\n"
            "- Do not touch training data or dataset files.\n"
            "- Commit your change and push the branch."
        )

    def spawn_probe(self, hypothesis: FixHypothesis, ctx: RunContext, incident_id: str) -> ProbeSpec:
        spec = ProbeSpec(id=new_id("probe"), incident_id=incident_id, hypothesis=hypothesis)
        prompt = self._build_prompt(hypothesis, ctx)
        body: dict[str, Any] = {
            "prompt": {"text": prompt},
            "repos": [{"url": ctx.repo_url, "startingRef": ctx.commit_sha}],
            "autoCreatePR": False,
        }
        spec.agent_id = self._create_agent(body, ctx)
        spec.state = ProbeState.WRITING
        return spec

    def _create_agent(self, body: dict[str, Any], ctx: RunContext) -> str | None:
        if self._sdk is not None:
            try:
                return self._sdk_create_agent(body)
            except AttributeError:
                pass
        return self._rest_create_agent(body, ctx)

    def _sdk_create_agent(self, body: dict[str, Any]) -> str | None:
        client_factory = getattr(self._sdk, "Cursor", None) or getattr(self._sdk, "Client", None)
        if client_factory is None:
            raise AttributeError("no SDK client factory")
        client = client_factory(api_key=self._settings.cursor_api_key)
        agents = getattr(client, "agents", None)
        creator = getattr(agents, "create", None) if agents is not None else getattr(client, "create_agent", None)
        if creator is None:
            raise AttributeError("no SDK agent creator")
        result = creator(**body)
        return self._parse_agent_id(result)

    @staticmethod
    def _parse_agent_id(result: Any) -> str | None:
        if isinstance(result, dict):
            agent = result.get("agent")
            if isinstance(agent, dict) and agent.get("id"):
                return str(agent["id"])
            value = result.get("id") or result.get("agentId")
            return str(value) if value else None
        for attr in ("id", "agentId", "agent_id"):
            value = getattr(result, attr, None)
            if value:
                return str(value)
        return None

    def _rest_create_agent(self, body: dict[str, Any], ctx: RunContext) -> str | None:
        resp = self._http.post("/agents", json=body)
        if resp.status_code >= 400:
            text = resp.text or ""
            if _looks_unconnected(resp.status_code, text) or ctx.repo_url in text:
                raise IntegrationNotConnectedError()
            resp.raise_for_status()
        payload = resp.json()
        return self._parse_agent_id(payload)

    def wait_for_branch(
        self,
        spec: ProbeSpec,
        timeout_s: float | None = None,
        poll_s: float = 5.0,
        sleep_fn: Any = time.sleep,
    ) -> ProbeSpec:
        if spec.agent_id is None:
            spec.state = ProbeState.FAILED
            return spec
        budget = timeout_s if timeout_s is not None else self._settings.probe_branch_timeout_s
        deadline = time.monotonic() + budget
        while True:
            payload = self._get_agent(spec.agent_id)
            status = _extract_status(payload).lower()
            branch = _extract_branch(payload)
            if status in _TERMINAL_FAIL:
                spec.state = ProbeState.FAILED
                return spec
            if branch:
                spec.branch = branch
                spec.state = ProbeState.READY
                return spec
            if status in _TERMINAL_OK:
                spec.state = ProbeState.FAILED
                return spec
            if time.monotonic() >= deadline:
                spec.state = ProbeState.FAILED
                return spec
            sleep_fn(poll_s)

    def _get_agent(self, agent_id: str) -> dict[str, Any]:
        if self._sdk is not None:
            try:
                payload = self._sdk_get_agent(agent_id)
                if payload is not None:
                    return payload
            except AttributeError:
                pass
        resp = self._http.get(f"/agents/{agent_id}")
        resp.raise_for_status()
        return resp.json()

    def _sdk_get_agent(self, agent_id: str) -> dict[str, Any] | None:
        client_factory = getattr(self._sdk, "Cursor", None) or getattr(self._sdk, "Client", None)
        if client_factory is None:
            raise AttributeError("no SDK client factory")
        client = client_factory(api_key=self._settings.cursor_api_key)
        agents = getattr(client, "agents", None)
        getter = getattr(agents, "get", None) if agents is not None else getattr(client, "get_agent", None)
        if getter is None:
            raise AttributeError("no SDK agent getter")
        result = getter(agent_id)
        if isinstance(result, dict):
            return result
        return getattr(result, "__dict__", None)

    def cancel(self, spec: ProbeSpec) -> None:
        if spec.agent_id is not None:
            try:
                resp = self._http.post(f"/agents/{spec.agent_id}/cancel")
                if resp.status_code >= 400:
                    self._http.delete(f"/agents/{spec.agent_id}")
            except Exception:
                with contextlib.suppress(Exception):
                    self._http.delete(f"/agents/{spec.agent_id}")
        spec.state = ProbeState.KILLED
