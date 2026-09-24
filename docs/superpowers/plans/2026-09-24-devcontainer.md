# Devcontainer and Compose Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two selectable Docker Compose environments, GPU/all-included and no-GPU, each with a Codex-enabled `devcontainer` service.

**Architecture:** `compose.gpu.yaml` and `compose.no-gpu.yaml` are independent selectable stacks. Core Python dependencies remain separate from GPU-only voice dependencies. The GPU `devcontainer` uses the voice image; the no-GPU `devcontainer` uses the core image. Both contain Codex CLI and use a container-local `CODEX_HOME` with bypass settings.

**Tech Stack:** Docker Compose, Python 3.12, NVIDIA Container Toolkit, CUDA 13.0, Node.js 22, Codex CLI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-devcontainer-design.md`

## Global Constraints

- GPU command is `docker compose -f compose.gpu.yaml up` and is all-included.
- No-GPU command is `docker compose -f compose.no-gpu.yaml up`.
- The logical development service is named `devcontainer`.
- Voice dependencies are not installed in the core image.
- Secrets stay outside images and source control.

---

### Task 1: Split core and voice dependencies

**Files:**
- Create: `requirements-core.txt`
- Create: `requirements-voice-gpu.txt`
- Modify: `requirements.txt`

**Interfaces:**
- `requirements-core.txt` is the install input for Flask/mock/devcontainer base images.
- `requirements-voice-gpu.txt` extends the core set with Whisper, Silero VAD, CUDA torch/torchaudio, sounddevice, and numpy.
- `requirements.txt` remains a backward-compatible aggregate for existing local installs.

- [ ] **Step 1: Write the dependency split**

Move the current non-audio packages into `requirements-core.txt`; put the current voice packages and CUDA wheel URLs in `requirements-voice-gpu.txt` with a comment that it must be installed after the core file.

- [ ] **Step 2: Validate package contents**

Run:

```bash
python - <<'PY'
from pathlib import Path
core = Path('requirements-core.txt').read_text()
voice = Path('requirements-voice-gpu.txt').read_text()
assert 'openai-whisper' not in core
assert 'torch @' not in core
assert 'openai-whisper' in voice
assert 'torch @' in voice
PY
```

Expected: command exits successfully.

- [ ] **Step 3: Keep the aggregate install path valid**

Make `requirements.txt` contain the complete existing install set or clearly include both split files in a way supported by pip/uv; do not change pinned versions.

- [ ] **Step 4: Run the existing tests**

Run: `pytest -q`

Expected: all existing tests pass.

### Task 2: Add core and GPU Docker images

**Files:**
- Create: `docker/core.Dockerfile`
- Create: `docker/voice-gpu.Dockerfile`
- Create: `docker/devcontainer.Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- `docker/core.Dockerfile` produces a Python 3.12 core runtime with `requirements-core.txt` installed.
- `docker/voice-gpu.Dockerfile` produces the CUDA aarch64 voice runtime with both split requirements installed.
- `docker/devcontainer.Dockerfile` produces a development image with Python tooling, Node.js, Codex CLI, and `/workspace` as the working directory.

- [ ] **Step 1: Create the core Dockerfile**

Use a Python 3.12 slim base, install only required OS packages, copy `requirements-core.txt`, install it, then copy the application. Keep the default command overridable by Compose.

- [ ] **Step 2: Create the CUDA voice Dockerfile**

Use the CUDA 13.0 aarch64 runtime/devel base compatible with the pinned torch wheels, install Python 3.12/runtime prerequisites, install core plus voice requirements, and set the default command to `python -m voice_ui.main`.

- [ ] **Step 3: Create the devcontainer Dockerfile**

Start from the core image, install Node.js 22 and `@openai/codex`, set `CODEX_HOME=/opt/codex-home`, create `/workspace`, and set `WORKDIR /workspace`. Do not copy credentials or host configuration into the image.

- [ ] **Step 4: Add `.dockerignore`**

Exclude `.git`, `.venv`, `__pycache__`, test caches, `.env`, and local Codex state.

- [ ] **Step 5: Validate Dockerfile parsing**

Run: `docker compose config` after Task 3 is complete.

Expected: valid merged Compose configuration.

### Task 3: Define selectable Compose stacks

**Files:**
- Create: `compose.gpu.yaml`
- Create: `compose.no-gpu.yaml`
- Create: `docker/codex-config.toml`

**Interfaces:**
- GPU services: `app`, `mocks`, `voice-ui`, `devcontainer`; no-GPU services: `app`, `mocks`, `devcontainer`.
- `voice-ui` requests NVIDIA GPU access and depends on the application/mocks as appropriate.
- `devcontainer` mounts the repository at `/workspace` and a named volume at `/opt/codex-home`.

- [ ] **Step 1: Define the core services**

Expose app port 5000, mock ports 5001 and 5002, set mock URLs for the app, and add healthchecks or stable startup dependencies where they are supported by the existing entrypoints.

- [ ] **Step 2: Define the GPU voice service**

Build from `docker/voice-gpu.Dockerfile`, request one NVIDIA GPU with `capabilities: [gpu]`, pass `VOICEVOX_URL`/existing voice configuration through environment variables, and keep host audio device access explicit.

- [ ] **Step 3: Define the devcontainer service**

Build the GPU variant from `docker/devcontainer-gpu.Dockerfile` and the no-GPU variant from `docker/devcontainer.Dockerfile`; mount the project and `docker/codex-config.toml` into the container-local Codex home, pass through only runtime credentials needed by Codex, and use an interactive long-running command.

- [ ] **Step 4: Add Codex bypass configuration**

Set:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

Keep this file outside `.codex/` in the repository so it cannot alter host Codex behavior when the user works on the host.

### Task 4: Add independent no-GPU Compose stack

**Files:**
- Modify: `compose.no-gpu.yaml`

**Interfaces:**
- The no-GPU configuration must define `app`, `mocks`, and `devcontainer` service names.
- The no-GPU configuration must not require NVIDIA runtime/device reservations.
- The no-GPU configuration must omit `voice-ui`.

- [ ] **Step 1: Override the development image**

Point `devcontainer` at the core-based development image or remove GPU-specific build/runtime settings while preserving the repository mount and Codex configuration.

- [ ] **Step 2: Disable voice service**

Define the no-GPU services directly so its command does not depend on merge tags or a GPU Compose file.

- [ ] **Step 3: Validate both merged configurations**

Run:

```bash
docker compose -f compose.gpu.yaml config
docker compose -f compose.no-gpu.yaml config
```

Expected: the first contains GPU voice configuration; the second contains no `voice-ui` service and no NVIDIA device reservation.

### Task 5: Document operation and verify

**Files:**
- Modify: `README.md`
- Modify: `.gitignore` if required by local Codex/Compose state

**Interfaces:**
- README commands are the user-facing contract for default, no-GPU, shell, tests, and Codex use.

- [ ] **Step 1: Document prerequisites**

Document Docker Compose, NVIDIA Container Toolkit for the GPU stack, and the fact that no-GPU mode excludes voice services.

- [ ] **Step 2: Document startup commands**

Add:

```bash
docker compose -f compose.gpu.yaml up --build
docker compose -f compose.no-gpu.yaml up --build
docker compose run --rm devcontainer codex
docker compose run --rm devcontainer pytest -q
```

- [ ] **Step 3: Document credentials**

Explain runtime injection for `OPENAI_API_KEY`/Codex login and `PF_API_KEY`; state that secrets must not be copied into Dockerfiles, images, or committed files.

- [ ] **Step 4: Run verification**

Run `pytest -q`, both `docker compose ... config` commands, and build the available images. Record any unavailable GPU build limitation without claiming a successful GPU runtime test.
