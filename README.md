# keepalive

Agents that hold you accountable — and stop waiting when you don't show up.

A pip-installable watchdog for GPU training runs: monitors wandb metrics, detects failures
(NaN loss, divergence, stalls, OOM), explains the failure, escalates over a Telegram
message + AI voice note, and — if you don't respond before the deadline — spawns parallel Cursor cloud agents
that each write a different fix on its own branch, then races those fixes as
checkpoint-resumed runs on W&B Sandboxes. The winning probe's run becomes the training.
Every agent decision is traced in W&B Weave.

```python
import keepalive

with keepalive.watchdog(run, escalate=["telegram"], timeout=120, checkpoint_dir="ckpts/"):
    train()
```

```
keepalive/
├── packages/keepalive/   # the pip-installable library
├── apps/api/             # FastAPI relay: keys, Telegram bot, voice-note pages
├── apps/dashboard/       # Next.js: API key issuance
├── docs/                 # Mintlify docs
└── infra/                # deployment runbooks
```

Built at WeaveHacks 4 (June 2026). See `TASKS.md` for build status, `infra/` for deployment.
