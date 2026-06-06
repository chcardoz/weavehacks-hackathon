from __future__ import annotations

import types as _types
from typing import Any

from keepalive.config import Settings
from keepalive.escalate.voice import VoiceNoteBuilder
from keepalive.types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    Incident,
    RunContext,
)


def make_incident(with_diagnosis: bool = True) -> Incident:
    run = RunContext(
        run_id="run123",
        project="proj",
        entity="team",
        run_url="https://wandb.ai/team/proj/run123",
        commit_sha="abc",
        repo_url="https://github.com/x/y",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
    )
    failure = FailureEvent(kind=FailureKind.NAN_LOSS, step=400, message="loss NaN")
    inc = Incident(id="inc_1", run=run, failure=failure)
    if with_diagnosis:
        inc.diagnosis = Diagnosis(
            summary="learning rate spiked the gradients",
            category="divergence",
            confidence=0.7,
            hypotheses=[],
        )
    return inc


def test_script_for_content_and_format() -> None:
    settings = Settings(escalation_timeout_s=30.0)
    builder = VoiceNoteBuilder(settings)
    script = builder.script_for(make_incident())

    assert "400" in script  # step
    assert "nan_loss" in script  # failure wording (kind)
    # reply options
    lower = script.lower()
    assert "one" in lower and "two" in lower and "three" in lower
    assert "roll back" in lower
    # no markdown
    assert "**" not in script
    assert "#" not in script
    # short enough to read aloud quickly
    assert len(script.split()) < 120


def test_script_for_uses_deadline_when_present() -> None:
    settings = Settings(escalation_timeout_s=999.0)
    builder = VoiceNoteBuilder(settings)
    inc = make_incident()
    inc.deadline_ts = inc.created_at + 20  # 20s remaining
    script = builder.script_for(inc)

    assert "20 seconds" in script


def test_synthesize_with_content_bytes() -> None:
    class FakeResponse:
        content = b"mp3-audio-bytes"

    class FakeClient:
        def __init__(self) -> None:
            self.audio = _types.SimpleNamespace(speech=_types.SimpleNamespace(create=self._create))

        def _create(self, **kwargs: Any) -> Any:
            return FakeResponse()

    builder = VoiceNoteBuilder(Settings(), client=FakeClient())
    out = builder.synthesize("hello")
    assert out == b"mp3-audio-bytes"


def test_synthesize_with_read_method() -> None:
    class FakeResponse:
        content = None  # no usable .content

        def read(self) -> bytes:
            return b"read-bytes"

    class FakeClient:
        def __init__(self) -> None:
            self.audio = _types.SimpleNamespace(speech=_types.SimpleNamespace(create=self._create))

        def _create(self, **kwargs: Any) -> Any:
            return FakeResponse()

    builder = VoiceNoteBuilder(Settings(), client=FakeClient())
    out = builder.synthesize("hello")
    assert out == b"read-bytes"
