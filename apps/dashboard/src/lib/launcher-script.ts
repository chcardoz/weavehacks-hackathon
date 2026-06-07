// The Python driver that runs INSIDE a Vercel Sandbox (python3.13) and uses the
// W&B Sandbox SDK to launch the actual training run in a W&B Sandbox.
//
// IMPORTANT: every value the launcher needs is read from ENV VARS at runtime —
// nothing is string-interpolated into this template, so secrets never appear in
// the source or in process listings of the launch command itself. The Vercel
// sandbox passes them via `runCommand({ env })`.
//
// LAUNCH_* env contract (set by the trainingLaunch workflow):
//   LAUNCH_REPO          owner/name
//   LAUNCH_SHA           commit sha to check out
//   LAUNCH_TRAIN_CMD     project.trainCommand
//   LAUNCH_GITHUB_TOKEN  x-access-token for the clone
//   LAUNCH_WANDB_KEY     user's W&B API key (also auths the wandb sandbox client)
//   LAUNCH_KEEPALIVE_KEY project.trainingApiKey
//   LAUNCH_KEEPALIVE_URL public dashboard base URL (BETTER_AUTH_URL)
//
// W&B Sandboxes are a public-preview product: the SDK surface may drift, so the
// launcher is defensive and prints a single machine-parseable line on success
// (`WANDB_SANDBOX_ID=<id>`) or failure (`LAUNCH_ERROR=<msg>`).
export const LAUNCHER_SCRIPT = String.raw`import os
import sys

try:
    from wandb.sandbox import Sandbox, NetworkOptions

    repo = os.environ["LAUNCH_REPO"]            # owner/name
    sha = os.environ["LAUNCH_SHA"]
    train_cmd = os.environ["LAUNCH_TRAIN_CMD"]
    gh = os.environ["LAUNCH_GITHUB_TOKEN"]

    script = f"""
set -e
git clone https://x-access-token:{gh}@github.com/{repo}.git /work && cd /work
git checkout {sha}
pip install -r requirements.txt || pip install wandb keepalive-club
{train_cmd}
"""

    sb = Sandbox.run(
        "bash",
        "-c",
        script,
        container_image="python:3.11",
        network=NetworkOptions(egress_mode="internet"),
        environment_variables={
            "WANDB_API_KEY": os.environ["LAUNCH_WANDB_KEY"],
            "KEEPALIVE_API_KEY": os.environ["LAUNCH_KEEPALIVE_KEY"],
            "KEEPALIVE_API_URL": os.environ["LAUNCH_KEEPALIVE_URL"],
        },
        max_lifetime_seconds=3600,
    )
    # The W&B sandbox's main command IS the training script; it keeps running
    # after this driver exits. Do NOT wait_until_complete.
    print(f"WANDB_SANDBOX_ID={sb.id}")
except Exception as exc:  # noqa: BLE001 - preview product, surface anything
    print(f"LAUNCH_ERROR={exc}")
    sys.exit(1)
`
