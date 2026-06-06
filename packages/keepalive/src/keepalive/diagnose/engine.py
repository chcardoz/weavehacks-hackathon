from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

from keepalive.config import Settings
from keepalive.diagnose.prompts import build_system_prompt
from keepalive.diagnose.tools import TOOL_SCHEMAS, RunDataFetcher
from keepalive.tracing import traced
from keepalive.types import Diagnosis, FailureEvent, FixHypothesis, Incident, new_id

_MAX_ROUNDS = 8

RecallFn = Callable[[FailureEvent], list[str]]


class _Cache:
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...


class DiagnosisEngine:
    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        recall: RecallFn | None = None,
        cache: _Cache | None = None,
    ) -> None:
        self.settings = settings
        self._injected_client = client
        self._recall = recall
        self._cache = cache

    def _client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        from openai import OpenAI

        if self.settings.use_wandb_inference:
            return OpenAI(
                base_url=self.settings.wandb_inference_base_url,
                api_key=self.settings.wandb_api_key,
            )
        return OpenAI(api_key=self.settings.openai_api_key)

    def _model(self) -> str:
        if self.settings.use_wandb_inference:
            return self.settings.wandb_inference_model
        return self.settings.diagnosis_model

    @traced
    def diagnose(self, incident: Incident, fetcher: RunDataFetcher) -> Diagnosis:
        model = self._model()
        cache_key = self._cache_key(incident)

        if self._cache is not None:
            try:
                cached = self._cache.get(cache_key)
                if cached:
                    return _diagnosis_from_dict(json.loads(cached))
            except Exception:
                pass

        memories = self._recall(incident.failure) if self._recall else []

        client = self._client()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(incident, memories)},
            {"role": "user", "content": "Diagnose this failure and submit a diagnosis."},
        ]

        diagnosis: Diagnosis | None = None
        for round_idx in range(_MAX_ROUNDS):
            force_last = round_idx == _MAX_ROUNDS - 1
            kwargs: dict[str, Any] = {"model": model, "messages": messages, "tools": TOOL_SCHEMAS}
            if force_last:
                kwargs["tool_choice"] = {
                    "type": "function",
                    "function": {"name": "submit_diagnosis"},
                }
            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                messages.append({"role": "assistant", "content": message.content or ""})
                continue

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name == "submit_diagnosis":
                    diagnosis = self._build_diagnosis(args, model)
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": "diagnosis recorded"}
                    )
                    continue

                result = self._dispatch_tool(name, args, fetcher)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            if diagnosis is not None:
                break

        if diagnosis is None:
            return Diagnosis(
                summary=incident.failure.message,
                category=str(incident.failure.kind),
                confidence=0.0,
                hypotheses=[],
            )

        if self._cache is not None:
            try:
                self._cache.set(cache_key, json.dumps(dataclasses.asdict(diagnosis), default=str))
            except Exception:
                pass

        return diagnosis

    def _dispatch_tool(self, name: str, args: dict[str, Any], fetcher: RunDataFetcher) -> Any:
        if name == "get_run_history":
            return fetcher.get_run_history(keys=args.get("keys"), last_n=args.get("last_n", 50))
        if name == "get_logs":
            return fetcher.get_logs(tail=args.get("tail", 100))
        if name == "get_config":
            return fetcher.get_config()
        if name == "search_incident_memory":
            if self._recall is None:
                return ""
            query = args.get("query", "")
            return "\n".join(self._recall(_query_event(query)))
        return f"unknown tool: {name}"

    def _build_diagnosis(self, args: dict[str, Any], model: str) -> Diagnosis:
        raw_hyps = args.get("hypotheses") or []
        hypotheses: list[FixHypothesis] = []
        for hyp in raw_hyps[: self.settings.max_probes]:
            hypotheses.append(
                FixHypothesis(
                    id=new_id("hyp"),
                    title=str(hyp.get("title", "")),
                    rationale=str(hyp.get("rationale", "")),
                    instructions=str(hyp.get("instructions", "")),
                )
            )
        confidence = float(args.get("confidence", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        return Diagnosis(
            summary=str(args.get("summary", "")),
            category=str(args.get("category", "")),
            confidence=confidence,
            hypotheses=hypotheses,
            raw={"model": model, "args": args},
        )

    def _cache_key(self, incident: Incident) -> str:
        failure = incident.failure
        metrics = ",".join(f"{k}={v}" for k, v in sorted(failure.metrics.items()))
        return f"{failure.kind}:{failure.message}|{metrics}"


def _query_event(query: str) -> FailureEvent:
    from keepalive.types import FailureKind

    return FailureEvent(kind=FailureKind.EXCEPTION, step=-1, message=query)


def _diagnosis_from_dict(data: dict[str, Any]) -> Diagnosis:
    hypotheses = [
        FixHypothesis(
            id=str(h.get("id", new_id("hyp"))),
            title=str(h.get("title", "")),
            rationale=str(h.get("rationale", "")),
            instructions=str(h.get("instructions", "")),
        )
        for h in data.get("hypotheses", [])
    ]
    return Diagnosis(
        summary=str(data.get("summary", "")),
        category=str(data.get("category", "")),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        hypotheses=hypotheses,
        raw=data.get("raw", {}) or {},
    )
