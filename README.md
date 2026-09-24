# 分散ロボ基盤 (Distributed Robot Platform)

Flask backend that orchestrates a check-in -> guide-robot-ready -> drink-load
-> drink-delivered cycle against the AI管制PF (guide robot control plane) and
R2/Themis (drink-serving robot) systems, exposing progress over SSE. A
self-service venue kiosk UI (`GET /`) lets a guest check in and watch that
progress in a browser.

## Docker / Compose development environment

### Prerequisites

Install Docker Engine (or Docker Desktop) with the Docker Compose plugin. The
default stack also starts the GPU-backed `voice-ui` service, so it requires an
ARM64/aarch64 Linux host with an NVIDIA GPU, a compatible NVIDIA driver, and
the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
The voice image and its pinned CUDA PyTorch wheels target `linux/arm64`; x86
hosts should use the no-GPU override below.

On a machine without GPU support, or on an x86 host, use the no-GPU override
below. It removes `voice-ui`; voice input and spoken status updates are
unavailable in that mode, while the Flask app and mock robot services remain
available.

### Start the stack

The default command builds and starts the complete stack, including the
GPU-backed voice service:

```bash
docker compose up --build
```

For a host without an NVIDIA GPU, build and start the app, mocks, and
development container without the voice service:

```bash
docker compose -f compose.yaml -f compose.no-gpu.yaml up --build
```

The kiosk is available at `http://localhost:5000/`. Stop either stack with
`Ctrl-C` (or run the same Compose command with `down`).

### Development container

Start an interactive shell in the repository-mounted development container:

```bash
docker compose run --rm devcontainer bash
```

Run Codex or the Python test suite without first opening a shell:

```bash
docker compose run --rm devcontainer codex
docker compose run --rm devcontainer pytest -q
```

For no-GPU hosts, prepend the same override files to `run` commands, for
example `docker compose -f compose.yaml -f compose.no-gpu.yaml run --rm
devcontainer pytest -q`.

### Runtime credentials

Inject credentials at runtime through your shell environment or a local
`.env` file (which is ignored by Git). `OPENAI_API_KEY` is passed to the
development container for Codex API authentication; alternatively, run
`docker compose run --rm devcontainer codex login` to use Codex login. Set
`PF_API_KEY` for the app's AI管制PF requests:

```bash
export OPENAI_API_KEY="<openai-api-key>"
export PF_API_KEY="<pf-api-key>"
docker compose up --build
```

Never copy secrets into Dockerfiles, image layers, or committed files. Pass
them only at runtime as environment variables or through an uncommitted
`.env` file.

## Install

Using [uv](https://docs.astral.sh/uv/):

```
uv venv .venv
uv pip install -r requirements.txt --python .venv/bin/python
source .venv/bin/activate
```

Or with plain pip:

```
pip install -r requirements.txt
```

## Run (mock mode)

Mock servers stand in for the real AI管制PF/R2/Themis systems during
development:

```
python run_mocks.py   # starts the R2 mock on :5001 and the PF mock on :5002
python run.py          # starts this app on :5000
```

Then open `http://localhost:5000/` in a browser: enter a name to check in
and watch the check-in -> guide-robot-ready -> drink-load -> drink-delivered
progress update live via SSE. While one guest's cycle is in progress,
anyone else who opens the page sees a waiting message instead of the form.

For a full manual walkthrough (check-in, watching SSE progress, forcing error
paths, resetting), see
`docs/superpowers/plans/manual-e2e-check.md`.

## 音声IF (voice_ui) の起動 (任意)

マイク・スピーカーが接続された端末で、名前の音声チェックインと進行状況の
読み上げを行いたい場合は、上記のFlaskアプリ起動に加えて以下も起動する:

```
python -m voice_ui.main
```

VOICEVOXエンジン（`http://127.0.0.1:50021`）が別途起動している必要がある。
設定可能な環境変数は`voice_ui/config.py`を参照。詳細は
`docs/superpowers/specs/2026-09-13-voice-ui-design.md`を参照。

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `R2_BASE_URL` | `http://localhost:5001` | Base URL of the R2/Themis drink-serving robot system |
| `PF_BASE_URL` | `http://localhost:5002` | Base URL of the AI管制PF (guide robot control plane) |
| `PF_API_KEY` | unset | `X-API-Key` sent to the AI管制PF; the local mock accepts any non-empty value |
| `PF_PROXY_URL` | unset | Optional proxy URL used for PF requests |
| `POLL_INTERVAL_SECONDS` | `2` | Seconds between status polls while waiting on R2/PF |
| `HTTP_TIMEOUT_SECONDS` | `5` | Per-request HTTP timeout for calls to R2/PF |
| `DRINK_TYPE` | `water` | `drink_type` sent in R2's load-drink command |
| `TARGET_ROBOT_ID` | `temi` | `target_robot_id` sent in R2's load-drink command |
| `R2_MOCK_RETURNING_SECONDS` | `3` | (mock only) seconds the R2 mock spends in `returning` |
| `R2_MOCK_FORCE_FAILURE` | unset | (mock only) `422`, `500`, or `failed` to force that R2 mock response |
| `PF_MOCK_INITIALIZING_SECONDS` | `0` | (mock only) seconds the PF mock reports `Initializing` before `Ready` |
| `PF_MOCK_ACCEPTED` | `true` | (mock only) set to `false` to make the PF mock reject `drink/placed` |
| `PF_MOCK_FORCE_FAILURE` | unset | (mock only) `422` or `500` to force that PF mock response from `guide-robot/status` |

The local PF mock requires a non-empty `X-API-Key`, but does not validate its
value.

## Switching to the real systems

Cutting over from the mocks to the real AI管制PF/R2/Themis systems requires
no code changes — point `R2_BASE_URL` and `PF_BASE_URL` at their real URLs and
set the PF API key in the runtime environment:

```
export PF_BASE_URL="https://reception.robility-system-stg.com"
export PF_API_KEY="<the-provided-api-key>"
python run.py
```

Alternatively, copy `.env.example` to `.env`, fill in `PF_API_KEY`, and run
`python run.py`. The `.env` file is ignored by Git.

If the host network requires an explicit HTTPS proxy, also set
`PF_PROXY_URL` to the proxy URL including its port. Leave it empty when no
explicit proxy is required. Do not put the API key in source code or commit
it to the repository.
