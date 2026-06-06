# W&B Sandboxes — the default probe executor

`SandboxExecutor` runs each probe on W&B Sandboxes: Kata microVMs, CPU-only serverless,
arbitrary Python/pip/git, authed with your W&B API key. This is the demo path — tiny model
probes run on W&B's own brand-new public-preview product.

## Install + import

```bash
pip install "wandb[sandbox]"
```

```python
from wandb.sandbox import Sandbox
```

Auth is your **W&B API key** (`WANDB_API_KEY`) — same key as metrics.

## Status + limits

- **Public preview.** The serverless path is **CPU-only**.
- Time limits and default CPU/RAM are **undocumented** → smoke-test hour one (below).
- **Free tier confirmed in person by W&B staff.** If you hit quota at the event, find a W&B
  rep and ask for a bump.

## Hour-one smoke test

Confirm a sandbox can pip-install torch and run a few hundred steps before you depend on
it. API surface (per current docs — built on the CoreWeave Sandbox library):
`Sandbox.run()` is a context manager that boots a microVM and auto-stops it;
`sandbox.exec([...])` returns a Process future — call `.result()` to block and read
`stdout`/`stderr`. Multiple sandboxes sharing config = a `Session`.

```python
import time
from wandb.sandbox import Sandbox

TRAIN = r"""
import torch
x = torch.randn(64, 64)
w = torch.randn(64, 64, requires_grad=True)
opt = torch.optim.SGD([w], lr=1e-3)
for step in range(300):
    loss = (x @ w).pow(2).mean()
    opt.zero_grad(); loss.backward(); opt.step()
    if step % 50 == 0:
        print(f"step {step} loss {loss.item():.4f}")
print("SMOKE_OK")
"""

t0 = time.time()
with Sandbox.run() as sandbox:
    print(sandbox.exec(["pip", "install", "--quiet", "torch"]).result().stdout)
    out = sandbox.exec(["python", "-c", TRAIN]).result()
    print(out.stdout, out.stderr)
print(f"wall-clock: {time.time() - t0:.0f}s")
```

You're looking for `SMOKE_OK` and a sane wall-clock (time the torch install — it dominates).
Also confirm `git clone` works (internet is on by default) and check the file read/write
API for injecting checkpoints into the VM. CPU/RAM/time limits are undocumented — whatever
this smoke test survives is your budget; align `SandboxExecutor` to what it confirms.

## If sandboxes misbehave

Fall back to `LocalExecutor` (git worktree + subprocess on your own box). Same race logic,
runs locally. CoreWeave GPU sandboxes / Modal are the roadmap executors.

## Probe run grouping

Each probe is a **separate** W&B run, grouped under the parent:
`group="watchdog-{run_id}"`, `job_type="probe"`, name = probe spec id. The probe race shows
up live on the W&B dashboard — that's the demo visual; we don't build our own charts. Never
co-write `_step` to the trainer's own run.
