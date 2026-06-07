# keepalive

A thin client watchdog for GPU training runs. It detects hard failures (NaN loss,
divergence, stalls, OOM), reports your metrics and events to
[the keepalive dashboard](https://weavehacks-hackathon-dashboard.vercel.app), and gets out of the way. The server scores
your run against a plain-English monitoring prompt, and when something goes wrong it
diagnoses the failure and opens fix PRs on your repo — fully traced in W&B Weave.

## Quickstart

```bash
pip install keepalive-club   # installs as `keepalive-club`, imports as `keepalive`
keepalive login              # prompts for your ka_live_ key, stores ~/.config/keepalive/config.json
```

Wrap your training loop:

```python
import keepalive

with keepalive.watchdog(
    run,                                   # your wandb run
    prompt="Flag if val/loss diverges from train/loss or grad_norm spikes.",
    threshold=0.6,
    max_agents=3,
    checkpoint_dir="ckpts/",               # informational
    demo_mode=False,
):
    train()
```

The watchdog hooks `run.log()`, batches metrics/events to
`POST {api_url}/api/v1/events`, and emits `incident.detected` on a hard failure —
then keeps going. The server handles diagnosis, fixing, and PRs.

Or supervise an unmodified script (survives hard crashes like CUDA OOM):

```bash
keepalive run -- python train.py --batch-size 64
```

## Configuration

| Setting | Env var | Default |
| ------- | ------- | ------- |
| API key | `KEEPALIVE_API_KEY` | — (or `keepalive login`) |
| API URL | `KEEPALIVE_API_URL` | `https://weavehacks-hackathon-dashboard.vercel.app` |
| Demo mode | `KEEPALIVE_DEMO` | off |

Precedence is explicit kwargs > environment variables > `~/.config/keepalive/config.json`.

Docs: https://weavehacks-hackathon-dashboard.vercel.app/docs
