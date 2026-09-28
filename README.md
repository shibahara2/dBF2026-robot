# 分散ロボ基盤 (Distributed Robot Platform)

Flask backend that orchestrates a check-in -> guide-robot-ready -> drink-load
-> drink-delivered cycle against the AI管制PF (guide robot control plane) and
R2/Themis (drink-serving robot) systems, exposing progress over SSE. A
self-service venue kiosk UI (`GET /`) lets a guest check in and watch that
progress in a browser.

## Install

GPU環境をデフォルトとしています。音声IFを利用するGPU環境では
`requirements.txt` を使い、GPUがない環境では `requirements-no-gpu.txt` を
使ってください。no-GPU構成では音声IFをインストール・起動しません。

Using [uv](https://docs.astral.sh/uv/):

GPUあり（デフォルト）:

```
uv venv .venv
uv pip install -r requirements.txt --python .venv/bin/python
source .venv/bin/activate
```

GPUなし:

```
uv venv .venv
uv pip install -r requirements-no-gpu.txt --python .venv/bin/python
source .venv/bin/activate
```

Or with plain pip:

```
pip install -r requirements.txt
```

GPUなしでplain pipを使う場合は `pip install -r requirements-no-gpu.txt` を
実行してください。

## Codex

Run Codex from the host repository with approvals disabled while retaining the
workspace-write sandbox:

```bash
codex -c approval_policy=never -c sandbox_mode=workspace-write
```

Authenticate once with `codex login`. The workspace-write sandbox limits writes
to the current project directory; avoid `danger-full-access` on the host.

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

GPU環境では、上記のモックとFlaskアプリに加えて、音声IFを別プロセスで
明示的に起動できます。GPUなし環境ではこのコマンドを実行しないでください。

## 音声IF (voice_ui) の起動 (GPU環境のみ)

マイク・スピーカーが接続された端末で、名前の音声チェックインと進行状況の
読み上げを行う場合は、上記のFlaskアプリ起動に加えて以下を別ターミナルで
起動します:

```
python -m voice_ui.main
```

VOICEVOXエンジン（`http://127.0.0.1:50021`）が別途起動している必要がある。
設定可能な環境変数は`voice_ui/config.py`を参照。詳細は
`docs/superpowers/specs/2026-09-13-voice-ui-design.md`を参照。

## Test

GPU環境（`requirements.txt`）では、コア機能と音声IFを含む全テストを実行します:

```
pytest -q
```

GPUなし環境（`requirements-no-gpu.txt`）では、GPU・音声ハードウェア依存の
テストを除外してコア機能を実行します:

```
pytest -q \
  --ignore=tests/test_voice_ui_main.py \
  --ignore=tests/test_voice_ui_tts.py \
  --ignore=tests/test_voice_ui_vad_segmenter.py \
  --ignore=tests/test_voice_ui_stt_transcriber.py \
  --ignore=tests/test_integration_mocks.py
```

これらの除外はコア機能の縮退ではなく、GPU・音声デバイス・音声専用依存を
必要とするテストを実行環境に合わせて除外するためのものです。

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

## Themis WebSocket image client

The external VLM server can connect as a WebSocket client to the existing
Themis `gamepad-server`; this repository does not subscribe to ROS topics.
Configure the endpoint without hard-coding a robot address:

```
export THEMIS_WS_URL="ws://<themis-main-pc>:9002/zed2i"
```

The physical endpoint can be checked before VLM integration with:

```
python tools/check_themis_video.py "$THEMIS_WS_URL" --duration 10
```

The probe reports binary message sizes and arrival intervals. The server is
expected to deliver frames at up to 2 Hz. The payload is kept raw until the
Themis-specific binary header is verified on the physical robot.
To capture one frame for decoder analysis, add
`--save-first-frame themis-frame.bin`.

When the external VLM detects that someone is speaking to Themis, it can call
`POST /api/visual/start`. This only moves the single kiosk browser to the
existing search screen; it does not start check-in or submit a name. The user
then enters their name, reservation number, or phone number and continues
through the existing reservation flow.

For local end-to-end testing, run the existing Flask app, the VLM mock, and
the Themis WebSocket mock in separate terminals.

The WebSocket mock repeatedly sends the repository's `person.png` as a PNG
image at the configured interval (0.5 seconds by default).
The VLM mock checks for PNG or JPEG image bytes, then returns the fixed
`VLM_MOCK_DECISION` value; it does not inspect the scene.

Set `THEMIS_VLM_MODE=mock` in `.env` (the example file uses this mode), then:

```
VLM_MOCK_DECISION=true .venv/bin/python -m mocks.vlm_mock
.venv/bin/python -m mocks.themis_video_mock
.venv/bin/python tools/run_themis_vlm.py
```

The runner logs video health every 30 seconds, including connection attempts,
received frames, processing errors, and time since the last frame. It warns
when disconnected or when no frame has arrived for 10 seconds.

### VLM API server

`vlm_server` is the real replacement for the VLM mock. It keeps the same
contract (`POST /analyze` with `{"image_base64": ...}`) and returns
`{"speaking_to_themis": bool, "answer": "yes"|"no", "latency_ms": int}`.
The yes/no prompt lives on the server (`vlm_server/prompt.py`); any `prompt`
sent by a client is ignored. Images are downscaled to `VLM_MAX_IMAGE_SIDE`
and sent to an OpenAI-compatible multimodal backend with a JSON schema that
forces a `yes`/`no` answer. `GET /health` checks the backend.

The default backend is the Qwen3.6-35B-A3B pod (`one-box-rag-chat` service).
Set `VLM_BACKEND_URL` in `.env`, then:

```
.venv/bin/python -m vlm_server
.venv/bin/python -m tools.vlm_client --health
.venv/bin/python -m tools.vlm_client person.png other.jpg
```

`tools.vlm_client` prints one `path<TAB>yes|no<TAB>latency` line per image
and exits non-zero if any request fails. `VLM_API_KEY`, when set, must be sent
as `Authorization: Bearer ...` (the pipeline and CLI do this automatically).

To measure the prompt against labeled images, run `tools.vlm_eval` while the
server is up. Images live in `tests/fixtures/vlm/yes/` and
`tests/fixtures/vlm/no/`; the directory name is the expected answer, so new
cases (for example real Themis frames) are added by dropping files there.

```
.venv/bin/python -m tools.vlm_eval
.venv/bin/python -m tools.vlm_eval --dataset path/to/frames --min-accuracy 0.9
```

It prints `OK`/`NG` per image plus accuracy, false positives, false negatives,
and average latency, and exits non-zero on request errors or when accuracy is
below `--min-accuracy`. The bundled fixtures are all derived from
`person.png`; people who are near the robot but not addressing it are not yet
covered.

For the robot and external VLM, set `THEMIS_VLM_MODE=real` and configure
`THEMIS_WS_URL`, `VLM_ENDPOINT`, and optionally `VLM_API_KEY` in `.env`.
Real robot frames are currently forwarded as raw WebSocket payloads. The
Themis-specific image header must be decoded before a production VLM can
reliably analyze them; capture a sample with `--save-first-frame` to verify
the format first.

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
