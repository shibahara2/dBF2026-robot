# Themis WebSocket Image Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 外部VLMサーバーからThemisの既存WebSocket画像配信へ接続し、再接続可能な2Hz画像受信クライアントを追加する。

**Architecture:** Themis側のROS/Zenoh実装は変更しない。外部側にWebSocket transport clientを追加し、受信したThemis独自バイナリフレームを画像デコード層へ渡す。実機で未確定なフレームヘッダの詳細はtransportから分離し、接続試験はraw payloadで先行できるようにする。

**Tech Stack:** Python 3, `websocket-client`, pytest, existing Flask configuration conventions.

**Spec:** User requirements in this conversation: connect externally as a WebSocket client to the existing Themis `gamepad-server` endpoint, avoid ROS/Zenoh exposure, and receive the camera stream at up to 2Hz.

## Global Constraints

- Themis側のコード、ROS graph、Zenoh設定は変更しない。
- The client must not assume exact 2Hz; it processes frames when received and tolerates missing frames.
- The WebSocket URL and camera path must be configurable; no robot IP is hard-coded.
- The exact 20-byte frame header is not assumed until verified against the physical robot.
- Existing Flask app startup must remain unaffected unless the client is explicitly started.

## Review Focus

- Connection drops during operation: reconnect with bounded delay and stop cleanly.
- Binary payloads and text/error messages: ignore or report non-frame messages without crashing.
- Unknown Themis frame header: preserve raw payload and keep the decoder replaceable.
- Slow VLM callbacks: avoid unbounded memory growth by processing one frame at a time.
- Configuration errors: fail clearly when the URL is absent or malformed.

### Task 1: WebSocket transport client

**Files:**
- Create: `themis_video/__init__.py`
- Create: `themis_video/client.py`
- Modify: `requirements-core.txt`
- Test: `tests/test_themis_video_client.py`

**Interfaces:**
- Produces `ThemisVideoClient(url, on_frame, reconnect_delay=..., connect_timeout=...)`.
- `start()` launches a background receive loop; `stop()` requests clean shutdown.
- `on_frame(payload: bytes)` receives each binary WebSocket message as-is.

- [x] **Step 1: Write failing tests** for binary callback delivery, clean stop, reconnect after a connection failure, and ignoring text messages.
- [x] **Step 2: Run the focused test and verify failure because the module is absent.
- [x] **Step 3: Add the minimal `websocket-client` dependency and implement the client with an injectable WebSocket factory for tests.
- [x] **Step 4: Run the focused tests and verify they pass.
- [x] **Step 5: Run the existing test suite; one pre-existing app-factory timing test remains failing.

### Task 2: Configurable frame decoding boundary

**Files:**
- Create: `themis_video/frames.py`
- Modify: `themis_video/__init__.py`
- Test: `tests/test_themis_video_frames.py`

**Interfaces:**
- Produces `RawThemisFrame(payload: bytes)` for unverified payloads.
- Produces a decoder protocol/function boundary that can later convert the verified Themis header plus image bytes into `DecodedImage(data, mime_type, timestamp)`.

- [x] **Step 1: Write failing tests** proving raw payloads are preserved and malformed/empty payloads are rejected with clear errors.
- [x] **Step 2: Run the focused tests and verify failure.
- [x] **Step 3: Implement the raw frame value object and decoder boundary without guessing header offsets.
- [x] **Step 4: Run focused tests; the existing suite result is recorded under Task 1.

### Task 3: Runtime configuration and external VLM handoff

**Files:**
- Modify: `app/config.py`
- Create: `themis_video/settings.py`
- Modify: `README.md`
- Test: `tests/test_themis_video_settings.py`

**Interfaces:**
- Reads `THEMIS_WS_URL`, defaulting to unset rather than a hard-coded robot address.
- Reads `THEMIS_WS_RECONNECT_DELAY_SECONDS` and `THEMIS_WS_CONNECT_TIMEOUT_SECONDS` with safe defaults.
- Does not start a client automatically from `create_app()` until an explicit integration point is selected.

- [x] **Step 1: Write failing tests** for unset URL, valid URL, and invalid numeric settings.
- [x] **Step 2: Run focused tests and verify failure.
- [x] **Step 3: Implement settings parsing and document the external-client startup example.
- [x] **Step 4: Run focused tests; the existing suite result is recorded under Task 1.

### Task 4: Hardware verification adapter

**Files:**
- Create: `tools/check_themis_video.py`
- Test: `tests/test_check_themis_video.py`

**Interfaces:**
- Connects to a supplied WebSocket URL, prints message sizes and arrival intervals, and optionally saves raw binary payloads.
- Does not decode or upload images; it is for the user’s physical Themis verification.

- [x] **Step 1: Write failing tests** for URL selection and interval reporting from a fake client.
- [x] **Step 2: Implement the command-line adapter.
- [x] **Step 3: Run tests and document the physical checks: port 9002, `/zed2i`, `/zedxm`, and observed message cadence.

### Task 5: Visual start UI trigger

**Files:**
- Create: `app/routes/visual.py`
- Create: `app/visual_trigger.py`
- Modify: `app/__init__.py`
- Modify: `app/config.py`
- Modify: `app/static/app.js`
- Modify: `app/templates/index.html`
- Test: `tests/test_routes_visual.py`

**Interfaces:**
- Consumes: a yes decision from the future VLM orchestrator via `POST /api/visual/start`.
- Produces: an SSE data payload `{\"type\":\"ui_action\",\"action\":\"start_checkin\"}` for the single kiosk browser.

- [x] Accept the visual trigger only while the state machine is awaiting check-in.
- [x] Rate-limit repeated yes signals with `VISUAL_START_COOLDOWN_SECONDS`.
- [x] Transition the browser to the existing search stage without calling `/api/checkin`.
- [x] Keep the search field empty so the user enters their own identity.
