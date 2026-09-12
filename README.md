# 分散ロボ基盤 (Distributed Robot Platform)

Flask backend that orchestrates a check-in -> guide-robot-ready -> drink-load
-> drink-delivered cycle against the AI管制PF (guide robot control plane) and
R2/Themis (drink-serving robot) systems, exposing progress over SSE. A
self-service venue kiosk UI (`GET /`) lets a guest check in and watch that
progress in a browser.

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

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `R2_BASE_URL` | `http://localhost:5001` | Base URL of the R2/Themis drink-serving robot system |
| `PF_BASE_URL` | `http://localhost:5002` | Base URL of the AI管制PF (guide robot control plane) |
| `POLL_INTERVAL_SECONDS` | `2` | Seconds between status polls while waiting on R2/PF |
| `HTTP_TIMEOUT_SECONDS` | `5` | Per-request HTTP timeout for calls to R2/PF |
| `DRINK_TYPE` | `water` | `drink_type` sent in R2's load-drink command |
| `TARGET_ROBOT_ID` | `temi` | `target_robot_id` sent in R2's load-drink command |
| `R2_MOCK_LOADING_SECONDS` | `3` | (mock only) seconds the R2 mock spends in `loading` |
| `R2_MOCK_RETURNING_SECONDS` | `3` | (mock only) seconds the R2 mock spends in `returning` |
| `R2_MOCK_FORCE_FAILURE` | unset | (mock only) `422`, `500`, or `failed` to force that R2 mock response |
| `PF_MOCK_INITIALIZING_SECONDS` | `0` | (mock only) seconds the PF mock reports `Initializing` before `Ready` |
| `PF_MOCK_ACCEPTED` | `true` | (mock only) set to `false` to make the PF mock reject `drink/placed` |
| `PF_MOCK_FORCE_FAILURE` | unset | (mock only) `422` or `500` to force that PF mock response from `guide-robot/status` |

## Switching to the real systems

Cutting over from the mocks to the real AI管制PF/R2/Themis systems requires
no code changes — just point `R2_BASE_URL` and `PF_BASE_URL` at their real
URLs.
