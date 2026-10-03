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
python run_mocks.py   # starts the PF mock on :5002 and the Themis WebSocket mock on :9002
                      # (R2 /realtime and video /zed2i share the port, like the real robot)
python run.py          # starts this app on :5100
```

Then open `http://localhost:5100/` in a browser: search a reservation to check in
and watch the check-in -> guide-robot-ready -> drink-load -> drink-delivered
progress update live via SSE. While one guest's cycle is in progress,
anyone else who opens the page sees a waiting message instead of the form.

For a full manual walkthrough (check-in, watching SSE progress, forcing error
paths, resetting), see
`docs/superpowers/plans/manual-e2e-check.md`.

GPU環境では、上記のモックとFlaskアプリに加えて、音声IFを別プロセスで
明示的に起動できます。GPUなし環境ではこのコマンドを実行しないでください。

## 音声IF (voice_ui) の起動 (GPU環境のみ)

マイク・スピーカーが接続された端末で、音声によるチェックイン開始
（「チェックイン」を含む発話でキオスクを検索画面にし、入力方法を案内する）を
行う場合は、上記のFlaskアプリ起動に加えて以下を別ターミナルで起動します。
進行状況は読み上げず、エラーのみ読み上げます:

```
python -m voice_ui.main
```

VOICEVOXエンジン（`http://127.0.0.1:50021`）が別途起動している必要がある。
話者はspeaker 29（dimosと同じ）。案内文は起動時に合成しておくため、起動に
数十秒かかる。
設定可能な環境変数は`voice_ui/config.py`を参照。詳細は
`docs/superpowers/specs/2026-09-13-voice-ui-design.md`を参照。

### 音声対話（フロント雑談）

「チェックイン」を含む発話はすぐにキオスクを検索画面にする。それ以外の
発話は LLM（既定はローカルの llama-server、`DIALOGUE_LLM_URL`）が判定し、
チェックインの意図なら同じく検索画面へ、フロントへの質問・雑談なら
返事を読み上げ、宛てでない会話には黙る。ホテルの事実は
`data/hotel_info.md`（デモ用の架空ホテル）に基づいて答える。
`DIALOGUE_ENABLED=0` でキーワードだけの動作に戻る。会話は `/debug` の
「音声対話ログ」で確認できる。判定精度は `python -m tools.dialogue_eval`
で評価できる。

雑談の返事はその場で合成するため、VOICEVOX（CPU版）は性能コアに固定して
起動することを推奨する（GB10 の例）:

```
docker run -d --name voicevox -p 127.0.0.1:50021:50021 --cpuset-cpus=5-9,15-19 \
  voicevox/voicevox_engine:cpu-ubuntu22.04-latest \
  gosu user /opt/voicevox_engine/run --host 0.0.0.0 --cpu_num_threads 10
```

固定しないと1文の合成が2〜9秒ぶれることを計測で確認している。

LLM（Qwen3.6-35B-A3B）は llama.cpp の公式イメージで起動する。音声対話
（`DIALOGUE_LLM_URL`）と `vlm_server`（`VLM_BACKEND_URL`）の両方が
`http://localhost:8080/v1` を使う。初回は GGUF（約22GB）と mmproj を
`~/.cache/huggingface` にダウンロードする:

```
docker run -d --name llm --restart unless-stopped --gpus all \
  --user "$(id -u):$(id -g)" -e HF_HOME=/hf -v "$HOME/.cache/huggingface:/hf" \
  -p 8080:8080 ghcr.io/ggml-org/llama.cpp:server-cuda13 \
  -hf unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M --alias qwen3.6-35b-a3b \
  --host 0.0.0.0 --port 8080 -ngl 999 -c 32768 --jinja --reasoning off
```

`curl localhost:8080/health` が `{"status":"ok"}` を返せば準備完了。
展示PCなど別マシンから使う場合は、`DIALOGUE_LLM_URL=http://<このPCのIP>:8080/v1`
とする。認証はないので、信頼できないネットワークに出す場合は `--api-key` を
付けて `DIALOGUE_LLM_API_KEY` / `VLM_BACKEND_API_KEY` に同じ値を入れる。

## 展示PCで音声IFだけ動かす（サーバーと分離）

ゲストの前に置く展示PC（サーバーと同じ DGX Spark）で音声IFとキオスク画面を
動かし、Flaskアプリ（:5100）とLLM（:8080）はサーバーに残す構成。通信は
すべて展示PCからサーバーへ向かう（サーバー側の IP は例として
`192.168.11.16`）。

**サーバー側**: モックとFlaskアプリ（`run_mocks.py` / `run.py`）とLLMを起動する。
`python -m voice_ui.main` は**起動しない**。両方で動かすと音声での開始が
二重に届き、`/debug` の音声対話ログも混ざる。

**展示PC側**:

```
# 1. 取得とインストール（DGX Spark なので requirements.txt のままでよい）
git clone git@github.com:shibahara2/dBF2026-robot.git && cd dBF2026-robot
uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python

# 2. VOICEVOX（上の「音声IF」と同じコマンド）
docker run -d --name voicevox -p 127.0.0.1:50021:50021 --cpuset-cpus=5-9,15-19 \
  voicevox/voicevox_engine:cpu-ubuntu22.04-latest \
  gosu user /opt/voicevox_engine/run --host 0.0.0.0 --cpu_num_threads 10

# 3. サーバーに届くか確認
curl http://192.168.11.16:5100/               # キオスク画面
curl http://192.168.11.16:8080/health         # LLM: {"status":"ok"}
curl -N http://192.168.11.16:5100/api/events  # 15秒ごとに ": keepalive" が届く

# 4. 起動
FLASK_BASE_URL=http://192.168.11.16:5100 \
DIALOGUE_LLM_URL=http://192.168.11.16:8080/v1 \
.venv/bin/python -m voice_ui.main
```

その後、展示PCのブラウザで `http://192.168.11.16:5100/` を開く。

- voice_ui は `.env` を読まないので、接続先は上のように環境変数で渡す。
- マイクとスピーカーは OS の既定デバイスが使われる。サウンド設定か
  `pactl set-default-source` / `pactl set-default-sink` で使う機器を既定にする。
- 初回起動時に Whisper の `large-v3`（約3GB）を `~/.cache/whisper` に
  ダウンロードするので、会場に出る前に一度起動しておく。
- `/api/events` は無通信が15秒続くとキープアライブのコメントを送り、
  voice_ui は45秒何も届かなければ再接続する。途中に NAT や VPN があっても
  接続が止まったままにならない。

## R2 (THEMIS) への接続

R2 は、ロボットの gamepad-server（`ws://192.168.0.11:9002/realtime`）に WebSocket で
つないで、このアプリ（Flask）が直接操作する。送るものと受け取ったものの解釈は、
ロボットのベンダーの操作パネル UI-DRP と同じ（詳細は
`docs/superpowers/specs/2026-10-03-r2-websocket-design.md`）。UI-DRP は使わない。
UI-DRP と同時に R2 につながないこと。

R2 には、ロボットの AP「THEMIS_5G」につながっている展示PC（spark-60c9）からしか
届かない。spark-60c9 で 9002 番を転送し、サーバー（spark-3a50）からは
`R2_WS_URL=ws://10.17.4.171:9002/realtime` でつなぐ。ロボット側の設定は変えない。

**spark-60c9 での設定**（sudo が必要。`<有線IF>` は 10.17.4.171 を持つインターフェース名）：

```
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A PREROUTING -i <有線IF> -s 10.17.2.171 -p tcp --dport 9002 \
  -j DNAT --to-destination 192.168.0.11:9002
sudo iptables -t nat -A POSTROUTING -o wlP9s9 -d 192.168.0.11 -p tcp --dport 9002 -j MASQUERADE
sudo iptables -A FORWARD -s 10.17.2.171 -d 192.168.0.11 -p tcp --dport 9002 -j ACCEPT
sudo iptables -A FORWARD -s 192.168.0.11 -d 10.17.2.171 -m state --state ESTABLISHED,RELATED -j ACCEPT
```

- ufw が有効なので、ufw の FORWARD ポリシーで止まらないか確かめる。
- 再起動後も残すには、`net.ipv4.ip_forward=1` を `/etc/sysctl.d/` に書き、iptables の
  ルールを `iptables-persistent`（`netfilter-persistent save`）で保存する。
- ロボットの電源が切れると Wi-Fi が Robotbank に切り替わる。THEMIS_5G を優先して
  自動でつなぎ直すよう NetworkManager の優先度を設定する。
- 映像（`THEMIS_WS_URL`）も同じ 9002 番なので、`ws://10.17.4.171:9002/zed2i` で届く。
- `/realtime` には認証がなく、ロボットの停止や関節の操作も受け付ける。転送する相手を
  spark-3a50 だけに絞っておくこと。

**確認**：spark-3a50 で `.venv/bin/python -c "import websocket; websocket.create_connection('ws://10.17.4.171:9002/realtime', timeout=5).close(); print('ok')"`

**運用上の注意**

- R2 の status（`completed` / `loading` / `returning` / `failed`）はこのアプリの中に
  しかない。**R2 の動作中に Flask を再起動しない**（再起動すると `completed` に戻る）。
- `/debug` の R2 パネルで、接続状態、status、`under_mode`、開始の返事を確認できる。
  - STOP：UI-DRP の停止の手順（ナビゲーションを抜けて一連の動作を止める操作）を送り、
    `failed` にする。ロボットがその結果どういう状態になるかは現地で確かめること。
    R2 を手で A に戻してから「R2 を初期状態に戻す」→「ステートマシンをリセット」。
  - 開始の返事が来なかったとき：R2 が A にいる（`under_mode` が `_m1`）なら
    「開始を再送」で続きから進める。
- R2 が未接続のあいだ、チェックインは `waiting_r2_ready`（R2 の待機確認）で待ち続ける。
  エラーにはならず、ステートマシンのリセットでも抜けられない。R2 につながると先へ進む。
- `/debug` の R2 操作と `/api/checkin` には認証がない。spark-3a50 の 5100/tcp は ufw で
  キオスクPCと展示PCだけに絞ること。

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
| `R2_WS_URL` | `ws://127.0.0.1:9002/realtime` | R2's gamepad-server `/realtime` (on site: spark-60c9's forwarded port) |
| `R2_START_REPLY_TIMEOUT_SECONDS` | `15` | Seconds to wait for R2's reply to `play_navigation5` before failing |
| `R2_WS_RECONNECT_DELAY_SECONDS` | `1` | Seconds before reconnecting to R2 |
| `R2_WS_CONNECT_TIMEOUT_SECONDS` | `5` | Timeout of the WebSocket handshake with R2 |
| `R2_MOCK_STEP_SECONDS` | `3` | (mock only) seconds per `under_mode` step of the `/realtime` mock |
| `R2_MOCK_START_REPLY` | `success` | (mock only) `success`, `fail`, or `none` as the reply to `play_navigation5` |
| `PF_BASE_URL` | `http://localhost:5002` | Base URL of the AI管制PF (guide robot control plane) |
| `PF_API_KEY` | unset | `X-API-Key` sent to the AI管制PF; the local mock accepts any non-empty value |
| `PF_PROXY_URL` | unset | Optional proxy URL used for PF requests |
| `POLL_INTERVAL_SECONDS` | `2` | Seconds between status polls while waiting on PF |
| `HTTP_TIMEOUT_SECONDS` | `5` | Per-request HTTP timeout for calls to PF |
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

### Check-in entries

Check-in always follows the kiosk sequence: start → reservation select →
check-in. The kiosk's start button, the VLM (`POST /api/visual/start`) and
voice (`POST /api/voice/start`) only differ in how "start" is detected; all of
them open the kiosk search screen, and the guest searches, selects and confirms
on screen. `POST /api/checkin` requires `reservation_id`.

Visual and voice starts return 409 while a cycle runs or while someone is using
the kiosk (an entry at start/select). An entry idle for `ENTRY_IDLE_SECONDS`
(default 60) no longer blocks them.

`voice_ui` calls `/api/voice/start` when a confident utterance contains one of
`VOICE_START_KEYWORDS` (comma separated, default `チェックイン`), then reads out
the on-screen input guidance.

`/debug` shows the current entry and stage live.

For local end-to-end testing, run the existing Flask app, `run_mocks.py` (which serves the Themis WebSocket mock on :9002), and the VLM mock in separate terminals.

The WebSocket mock repeatedly sends the repository's `person.png` as a PNG
image at the configured interval (0.5 seconds by default).
The VLM mock checks for PNG or JPEG image bytes, then returns the fixed
`VLM_MOCK_DECISION` value; it does not inspect the scene.

Set `THEMIS_VLM_MODE=mock` in `.env` (the example file uses this mode), then:

```
VLM_MOCK_DECISION=true .venv/bin/python -m mocks.vlm_mock
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

The default backend is the local llama-server container (see "LLM" above).
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
no code changes — point `R2_WS_URL` (see "R2 (THEMIS) への接続") and `PF_BASE_URL` at their real URLs and
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
