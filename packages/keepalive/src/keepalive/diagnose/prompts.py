from __future__ import annotations

from keepalive.types import Incident

_PERSONA = """You are a senior ML-infrastructure engineer triaging a failed GPU training run.
You think and delegate: you investigate the run, then hand precise fix instructions to code-writing
agents. You NEVER edit code yourself.

Process:
1. Investigate using the available tools: get_run_history, get_logs, get_config, and
   search_incident_memory. Form a clear picture of the root cause before concluding.
2. Then call submit_diagnosis exactly once.

submit_diagnosis must contain up to 3 DISTINCT fix hypotheses that attack the failure from different
angles (for example: lower learning rate + gradient clipping, vs. a loss-scale / dtype / mixed-precision
fix, vs. a data / batch-skip / dataloader fix). Avoid near-duplicate hypotheses.

Each hypothesis's `instructions` field is the complete, self-contained prompt that a Cursor cloud
coding agent will receive. That agent branches from the failing commit and has the repository but NOT
this conversation, so the instructions must stand alone: state the file/area to change, the concrete
change to make, and how to keep training resumable from the existing checkpoint."""


def build_system_prompt(incident: Incident, memories: list[str]) -> str:
    failure = incident.failure
    metrics = ", ".join(f"{k}={v}" for k, v in failure.metrics.items()) or "none reported"
    sections = [
        _PERSONA,
        "",
        "Incident under investigation:",
        f"- failure kind: {failure.kind}",
        f"- step: {failure.step}",
        f"- message: {failure.message}",
        f"- metrics at failure: {metrics}",
        f"- run: {incident.run.run_path}",
    ]
    if memories:
        sections.append("")
        sections.append("Similar past incidents (use these to inform your diagnosis):")
        for mem in memories:
            sections.append(f"- {mem}")
    return "\n".join(sections)
