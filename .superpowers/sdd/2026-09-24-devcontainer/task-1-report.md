# Task 1 report: Split core and voice dependencies

## Implementation

- Created `requirements-core.txt` with the existing Flask, requests, pytest, responses, and python-dotenv pins.
- Created `requirements-voice-gpu.txt` with the existing Whisper, Silero VAD, CUDA torch/torchaudio wheel URLs, sounddevice, and numpy pins.
- Added a comment to the voice file stating that it must be installed after the core file.
- Changed `requirements.txt` to include both split files with pip/uv-compatible `-r` entries, preserving the complete existing install set.

## Validation

The brief's package-content validation passed using `python3`.

An additional inventory check confirmed that the aggregate split contains exactly the same pinned requirement lines as the original `requirements.txt`; `git diff --check` also passed.

The exact commands requested by the brief could not run because this shell has no `python` or `pytest` executable on `PATH`:

- `python - ...`: `command not found: python`
- `pytest -q`: `command not found: pytest`

The equivalent content validation using `python3` passed. The repository `.venv` was then used for the test suite:

```text
./.venv/bin/python -m pytest -q
ERROR collecting tests/test_voice_ui_main.py
ModuleNotFoundError: No module named 'sounddevice'
1 error during collection
```

The test suite could not complete because the existing `.venv` is missing the already-pinned `sounddevice==0.4.7` dependency. No source tests or application files were changed.

## Files changed

- `requirements-core.txt`
- `requirements-voice-gpu.txt`
- `requirements.txt`
