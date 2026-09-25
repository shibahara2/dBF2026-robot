# GPUデフォルト／no-GPU音声環境 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GPU環境をデフォルトとして音声IFを利用可能にし、GPUなし環境ではコア依存だけをインストールして音声IFを起動しない構成にする。

**Architecture:** `requirements.txt` をGPU向けの既定入口として維持し、共通依存を `requirements-core.txt`、GPU音声依存を `requirements-voice-gpu.txt` に分離する。`requirements-no-gpu.txt` は共通依存だけを参照し、音声プロセスはどの構成でも自動起動せず、GPU環境で明示的に `python -m voice_ui.main` を実行する。

**Tech Stack:** Python 3.12、uv/pip requirements files、pytest、Flask、openai-whisper、Silero VAD、CUDA版torch/torchaudio。

**Spec:** `docs/superpowers/specs/2026-09-25-gpu-optional-voice-environment-design.md`

## Global Constraints

- GPU構成をデフォルトとする。
- GPUなし構成は `requirements-no-gpu.txt` で明示する。
- GPUなし構成では音声IFをインストールしない。CPU版Whisperへのフォールバックは実装しない。
- 音声IFは本体プロセスに組み込まず、`python -m voice_ui.main` で別プロセスとして明示的に起動する。
- `WHISPER_DEVICE` の既定値は `cuda`、`WHISPER_FP16` の既定値は有効のままにする。
- Docker/ComposeによるGPU切り替えは今回の対象外とする。

## Review Focus

- `requirements-no-gpu.txt` に音声依存やtorchが混入しないことを、ファイル内容の検証で固定する。
- `requirements.txt` がGPU環境の既定入口であり、coreとvoice-gpuの両方を含むことを、ファイル内容の検証で固定する。
- GPUなしの起動手順が音声プロセスを起動しないことを、READMEの手順確認で固定する。
- GPUありの起動手順がFlask本体と音声プロセスを別々に起動することを、READMEの手順確認で固定する。
- GPUなし向けテストコマンドが音声依存のテストを除外しつつコアテストを実行することを、README記載コマンドの実行で固定する。

## File Map

- Create: `requirements-no-gpu.txt` — 共通依存だけを導入するGPUなし環境の入口。
- Modify: `requirements.txt` — GPU構成のデフォルト入口であることを明示し、既存のcore/voice-gpu参照を維持する。
- Modify: `README.md` — GPU/GPUなしのインストール、起動、テスト手順を記載する。
- No change: `requirements-core.txt` — 共通依存の内容は変更しない。
- No change: `requirements-voice-gpu.txt` — GPU音声依存の内容は変更しない。
- No change: `voice_ui/config.py` — `cuda`/`fp16`の既定値は現状を維持する。
- No change: `run.py`, `voice_ui/main.py` — 本体と音声IFを別プロセスで起動する現状を維持する。

### Task 1: Dependency entry points

**Files:**
- Create: `requirements-no-gpu.txt`
- Modify: `requirements.txt`
- Test: shell-level file-content and dependency-resolution checks

**Interfaces:**
- Produces: `requirements-no-gpu.txt` that includes only `-r requirements-core.txt`.
- Produces: `requirements.txt` that includes `-r requirements-core.txt` and `-r requirements-voice-gpu.txt`.

- [ ] **Step 1: Write the no-GPU requirements entry point**

Create `requirements-no-gpu.txt` with exactly:

```text
-r requirements-core.txt
```

- [ ] **Step 2: Clarify the default GPU entry point**

Keep the existing includes in `requirements.txt` and add a short comment stating that this file is the default GPU environment and that `requirements-no-gpu.txt` is the alternative. Do not duplicate package pins in either entry point.

- [ ] **Step 3: Verify dependency boundaries**

Run:

```bash
rg -n "requirements-(core|voice-gpu|no-gpu)|torch|torchaudio|openai-whisper|silero-vad|sounddevice" requirements*.txt
```

Expected:

- `requirements-no-gpu.txt` contains only the core include.
- `requirements.txt` contains both core and voice-gpu includes.
- GPU/audio package pins appear only in `requirements-voice-gpu.txt`.

- [ ] **Step 4: Verify both requirement graphs resolve**

Run in disposable environments or with dry-run support:

```bash
uv pip install --dry-run -r requirements-no-gpu.txt
uv pip install --dry-run -r requirements.txt
```

Expected: both commands parse their requirement graphs successfully; the GPU command resolves the voice requirements and the no-GPU command does not request them.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-no-gpu.txt
git commit -m "build: add explicit no-GPU dependency profile"
```

### Task 2: Document environment selection and startup

**Files:**
- Modify: `README.md`
- Test: manual command review and startup smoke test

**Interfaces:**
- Consumes: the dependency entry points from Task 1.
- Produces: copyable GPU and no-GPU setup instructions with explicit process boundaries.

- [ ] **Step 1: Add the environment selection section**

Document the two install commands:

```bash
# GPUあり（デフォルト）
uv venv .venv
uv pip install -r requirements.txt --python .venv/bin/python

# GPUなし
uv venv .venv
uv pip install -r requirements-no-gpu.txt --python .venv/bin/python
```

State that the GPU profile is the default and that the no-GPU profile does not install or support the voice UI.

- [ ] **Step 2: Document separate startup commands**

For GPU environments, document `python run_mocks.py`, `python run.py`, and `python -m voice_ui.main` as separate processes. For no-GPU environments, document only the Flask app and mock processes; do not include the voice command in that path.

- [ ] **Step 3: Document the test commands**

Keep the full test command for GPU environments and add the explicit no-GPU command that excludes:

```text
tests/test_voice_ui_main.py
tests/test_voice_ui_tts.py
tests/test_voice_ui_vad_segmenter.py
tests/test_voice_ui_stt_transcriber.py
tests/test_integration_mocks.py
```

Explain that the exclusions are dependency/hardware-specific, not product behavior exclusions for the core app.

- [ ] **Step 4: Verify the documented commands against the repository**

Check that every referenced file and command exists, and run the no-GPU core command in the current environment when its dependencies are available:

```bash
.venv/bin/pytest -q \
  --ignore=tests/test_voice_ui_main.py \
  --ignore=tests/test_voice_ui_tts.py \
  --ignore=tests/test_voice_ui_vad_segmenter.py \
  --ignore=tests/test_voice_ui_stt_transcriber.py \
  --ignore=tests/test_integration_mocks.py
```

Expected: collection does not import the excluded hardware/GPU modules; any remaining failure is reported with its exact cause.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document GPU and no-GPU workflows"
```

### Task 3: End-to-end verification and handoff

**Files:**
- Test: repository test commands and mock startup
- Modify: none unless verification exposes a documentation mismatch

**Interfaces:**
- Consumes: dependency profiles and README workflows from Tasks 1–2.
- Produces: verified evidence that core startup works without voice dependencies and that the GPU profile remains the full path.

- [x] **Step 1: Run the core test suite using the no-GPU command**

Run the documented no-GPU pytest command. Record the pass count and any environment-specific skips or failures.

- [x] **Step 2: Run the mock/app smoke test**

Start the mock servers and Flask app using the no-GPU dependency profile, then verify:

```bash
curl -fsS http://localhost:5000/
curl -fsS http://localhost:5000/api/events --max-time 2
```

Expected: the kiosk page responds successfully and the SSE endpoint opens without importing or starting `voice_ui`.

- [x] **Step 3: Verify the GPU voice entry point is documented, not auto-started**

Confirm `run.py` and `run_mocks.py` do not import `voice_ui`, and confirm the README requires the explicit `python -m voice_ui.main` command only for the GPU workflow.

- [x] **Step 4: Run the full GPU test command where GPU dependencies are installed**

Run:

```bash
.venv/bin/pytest -q
```

Expected: the full suite collects, including voice tests. If the current machine lacks the GPU/audio dependency set, mark this verification as environment-blocked rather than changing the product design.

- [ ] **Step 5: Commit any verification-only documentation corrections**

Only if Task 3 finds a concrete mismatch, update the affected documentation and commit it with:

```bash
git add README.md
git commit -m "docs: correct environment verification instructions"
```

#### Verification record (2026-09-25)

- No-GPU core test command: **128 passed**.
- Mock server and Flask app smoke test: **completed**; kiosk page and SSE endpoint confirmed.
- `run.py` / `run_mocks.py` do not auto-start `voice_ui`; GPU voice UI remains an explicit separate process.
- Full GPU test suite: **environment-dependent and not run in this no-GPU verification session**. Run `pytest -q` in the GPU environment before production cutover.
