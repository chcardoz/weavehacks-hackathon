from __future__ import annotations

from typing import Any

from keepalive.diagnose.tools import RunDataFetcher
from keepalive.types import RunContext


def make_ctx() -> RunContext:
    return RunContext(
        run_id="run123",
        project="proj",
        entity="team",
        run_url="https://wandb.ai/team/proj/run123",
        commit_sha="abc",
        repo_url="https://github.com/x/y",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
    )


class FakeRunObj:
    def __init__(
        self,
        history_rows: list[dict[str, Any]] | None = None,
        config: dict[str, Any] | None = None,
        file_raises: bool = True,
    ) -> None:
        self._history_rows = history_rows or []
        self.config = config or {}
        self._file_raises = file_raises

    def history(self, samples: int, keys: Any = None, pandas: bool = False) -> list[dict[str, Any]]:
        return self._history_rows

    def file(self, name: str) -> Any:
        if self._file_raises:
            raise RuntimeError("no such file")
        raise RuntimeError("unexpected")


class FakeApi:
    def __init__(self, run_obj: Any) -> None:
        self._run_obj = run_obj
        self.run_call_count = 0

    def run(self, path: str) -> Any:
        self.run_call_count += 1
        return self._run_obj


def test_get_run_history_filters_non_numeric_keeps_step_and_last_n() -> None:
    rows = [
        {"_step": 1, "loss": 1.0, "name": "ignore-me", "ok": True},
        {"_step": 2, "loss": 0.5, "grad": 3, "flag": False},
        {"_step": 3, "loss": 0.25},
    ]
    api = FakeApi(FakeRunObj(history_rows=rows))
    fetcher = RunDataFetcher(make_ctx(), api=api)

    out = fetcher.get_run_history(last_n=2)

    assert len(out) == 2  # last_n applied
    # Strings filtered out; bools filtered out; _step kept; ints/floats kept.
    assert out[0] == {"_step": 2, "loss": 0.5, "grad": 3}
    assert out[1] == {"_step": 3, "loss": 0.25}
    assert "name" not in out[0]
    assert "flag" not in out[0]


def test_get_config_returns_dict() -> None:
    api = FakeApi(FakeRunObj(config={"lr": 0.1, "batch": 32}))
    fetcher = RunDataFetcher(make_ctx(), api=api)

    cfg = fetcher.get_config()

    assert cfg == {"lr": 0.1, "batch": 32}
    assert isinstance(cfg, dict)


def test_get_logs_returns_empty_on_download_failure() -> None:
    api = FakeApi(FakeRunObj(file_raises=True))
    fetcher = RunDataFetcher(make_ctx(), api=api)

    assert fetcher.get_logs() == ""


def test_run_refetched_per_call() -> None:
    api = FakeApi(FakeRunObj(history_rows=[{"_step": 1, "loss": 1.0}], config={"a": 1}))
    fetcher = RunDataFetcher(make_ctx(), api=api)

    fetcher.get_run_history()
    fetcher.get_config()

    assert api.run_call_count == 2  # re-fetched each method call
