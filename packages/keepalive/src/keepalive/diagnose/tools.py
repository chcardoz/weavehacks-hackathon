from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from keepalive.types import RunContext


class RunDataFetcher:
    def __init__(self, ctx: RunContext, api: Any | None = None) -> None:
        self.ctx = ctx
        self._api = api

    def _get_api(self) -> Any:
        if self._api is None:
            import wandb

            self._api = wandb.Api()
        return self._api

    def _run(self) -> Any:
        return self._get_api().run(self.ctx.run_path)

    def get_run_history(self, keys: list[str] | None = None, last_n: int = 50) -> list[dict[str, Any]]:
        run = self._run()
        rows: list[dict[str, Any]] = []
        try:
            frame = run.history(samples=max(last_n, 1), keys=keys, pandas=False)
            rows = list(frame) if frame is not None else []
        except Exception:
            try:
                rows = list(run.scan_history(keys=keys))
            except Exception:
                rows = []
        cleaned: list[dict[str, Any]] = []
        for row in rows[-last_n:]:
            numeric: dict[str, Any] = {}
            for k, v in row.items():
                if k == "_step":
                    numeric[k] = v
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    numeric[k] = v
            if numeric:
                cleaned.append(numeric)
        return cleaned

    def get_logs(self, tail: int = 100) -> str:
        try:
            run = self._run()
            with tempfile.TemporaryDirectory() as tmp:
                log_file = run.file("output.log")
                log_file.download(root=tmp, replace=True)
                text = Path(tmp, "output.log").read_text(errors="replace")
            lines = text.splitlines()
            return "\n".join(lines[-tail:])
        except Exception:
            return ""

    def get_config(self) -> dict[str, Any]:
        try:
            return dict(self._run().config)
        except Exception:
            return {}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_run_history",
            "description": "Fetch recent numeric metric rows (incl. _step) from the failing wandb run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional metric keys to restrict to (e.g. ['loss', 'grad_norm']).",
                    },
                    "last_n": {
                        "type": "integer",
                        "description": "Number of most-recent rows to return.",
                        "default": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_logs",
            "description": "Fetch the tail of the run's stdout/stderr log (output.log).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tail": {
                        "type": "integer",
                        "description": "Number of trailing log lines to return.",
                        "default": 100,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_config",
            "description": "Fetch the run's hyperparameter/config dict.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_incident_memory",
            "description": "Search long-term memory for similar past incidents and their resolutions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language description of the failure to search for.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_diagnosis",
            "description": "Submit the final diagnosis with up to 3 distinct fix hypotheses. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Plain-English explanation of what went wrong and why.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Failure category (e.g. divergence, thermal, dataloader, oom).",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence in the diagnosis, 0-1.",
                    },
                    "hypotheses": {
                        "type": "array",
                        "maxItems": 3,
                        "description": "Distinct candidate fixes; each will be implemented on its own branch.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "Short label for the fix."},
                                "rationale": {
                                    "type": "string",
                                    "description": "Why this fix should resolve the failure.",
                                },
                                "instructions": {
                                    "type": "string",
                                    "description": (
                                        "Complete standalone prompt for a Cursor cloud coding agent to "
                                        "implement this fix on a branch from the failing commit."
                                    ),
                                },
                            },
                            "required": ["title", "rationale", "instructions"],
                        },
                    },
                },
                "required": ["summary", "category", "confidence", "hypotheses"],
            },
        },
    },
]
