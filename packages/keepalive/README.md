# keepalive

Watchdog for GPU training runs. Detects failures (NaN loss, divergence, stalls, OOM),
diagnoses them with an LLM, escalates to you over SMS + AI voice note, and — if you don't
respond in time — spawns parallel Cursor cloud agents that write competing fixes, races
them as checkpoint-resumed runs on W&B Sandboxes, and promotes the winner. Fully traced
in W&B Weave.

```python
import keepalive

with keepalive.watchdog(run, escalate=["sms"], timeout=120, checkpoint_dir="ckpts/"):
    train()
```

Or supervise an unmodified script (survives hard crashes like CUDA OOM):

```
keepalive run -- python train.py --batch-size 64
```

Docs: https://docs.keepalive.club
