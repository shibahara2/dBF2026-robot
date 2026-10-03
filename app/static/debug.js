const STEPS = [
  "awaiting_checkin",
  "polling_pf_ready",
  "waiting_r2_ready",
  "starting_r2",
  "waiting_r2_placed",
  "notifying_pf_placed",
];

const ROW_BOUNDS = {
  awaiting_checkin: { y: 75, height: 30 },
  polling_pf_ready: { y: 125, height: 60 },
  waiting_r2_ready: { y: 205, height: 60 },
  starting_r2: { y: 285, height: 60 },
  waiting_r2_placed: { y: 365, height: 60 },
  notifying_pf_placed: { y: 445, height: 60 },
};

const statusPhase = document.getElementById("status-phase");
const statusStep = document.getElementById("status-step");
const statusGuest = document.getElementById("status-guest");
const debugError = document.getElementById("debug-error");
const debugErrorMessage = document.getElementById("debug-error-message");
const sequenceDiagram = document.getElementById("sequence-diagram");
const playhead = document.getElementById("playhead");
const pfStatusValue = document.getElementById("pf-status-value");
const pfStatusAt = document.getElementById("pf-status-at");
const currentTime = document.getElementById("current-time");

const ENTRY_ORDER = ["start", "select", "checkin"];
const entryAt = document.getElementById("entry-at");
const entryStarts = document.querySelectorAll(".entry-start");
const entryStages = document.querySelectorAll(".entry-stage");

const MAX_VOICE_TURNS = 20;
const voiceTurnRows = document.getElementById("voice-turn-rows");

function formatNumber(value, digits) {
  return typeof value === "number" ? value.toFixed(digits) : "-";
}

function voiceTurnRow(turn) {
  const row = document.createElement("tr");
  row.className = "voice-turn outcome-" + turn.outcome;
  [
    toSecondsTime(turn.at),
    turn.text,
    turn.outcome,
    turn.reply || "",
    formatNumber(turn.no_speech_prob, 2),
    formatNumber(turn.avg_logprob, 2),
    turn.stt_ms ?? "-",
    turn.llm_ms ?? "-",
  ].forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = String(value);
    row.append(cell);
  });
  return row;
}

function addVoiceTurn(turn) {
  voiceTurnRows.prepend(voiceTurnRow(turn));
  while (voiceTurnRows.children.length > MAX_VOICE_TURNS) {
    voiceTurnRows.lastElementChild.remove();
  }
}

fetch("/api/voice/turns")
  .then((resp) => resp.json())
  .then((data) => {
    voiceTurnRows.replaceChildren(...(data.turns || []).map(voiceTurnRow));
  })
  .catch(() => {});

function renderEntry(snapshot) {
  entryAt.textContent = toSecondsTime(snapshot.entry_at);
  // -1 when no entry is recorded, so nothing is highlighted.
  const reached = ENTRY_ORDER.indexOf(snapshot.entry_stage);
  entryStarts.forEach((el) => {
    const isSource = el.dataset.source === snapshot.entry_source;
    el.classList.toggle("active", isSource && reached === 0);
    el.classList.toggle("done", isSource && reached > 0);
  });
  entryStages.forEach((el) => {
    const index = ENTRY_ORDER.indexOf(el.dataset.stage);
    el.classList.toggle("active", index === reached);
    el.classList.toggle("done", index < reached);
  });
}

const CONNECTION_LABELS = {
  connected: "● 接続中",
  connecting: "● 接続試行中",
  disconnected: "● 未接続",
  stopped: "● 切断中（手動）",
};

const r2Panel = document.getElementById("r2-panel");
const r2Connection = document.getElementById("r2-connection");
const r2ConnectionAt = document.getElementById("r2-connection-at");
const r2ToggleConnection = document.getElementById("r2-toggle-connection");
const r2Status = document.getElementById("r2-status");
const r2StatusAt = document.getElementById("r2-status-at");
const r2Failure = document.getElementById("r2-failure");
const r2UnderMode = document.getElementById("r2-under-mode");
const r2UnderModeAt = document.getElementById("r2-under-mode-at");
const r2LastReply = document.getElementById("r2-last-reply");
const r2Confirm = document.getElementById("r2-confirm");
const r2ConfirmMessage = document.getElementById("r2-confirm-message");
const r2Result = document.getElementById("r2-result");
const r2Hint = document.getElementById("r2-hint");

// Each button: the API action, an optional body, an optional confirmation,
// and when it may be pressed (mirrors R2Controller; the server re-checks).
const R2_BUTTONS = {
  "r2-stop": {
    action: "stop",
    confirm: "R2 を止めます（その場で立ち止まり、status は failed になります）。",
    hint: "R2 に接続しているときだけ",
    enabled: (s) => s.connection === "connected",
  },
  "r2-resend": {
    action: "resend",
    hint: "開始の失敗で failed、かつ under_mode が _m1 のときだけ",
    enabled: (s) =>
      s.status === "failed" &&
      ["start_no_reply", "start_rejected", "start_disconnected"].includes(s.failure) &&
      typeof s.under_mode === "string" &&
      s.under_mode.split("_m")[1] === "1" &&
      s.connection === "connected",
  },
  "r2-mark-returning": {
    action: "mark",
    body: { status: "returning" },
    confirm: "置き終わったものとして AI管制PF に drink/placed を送り、temi が出発します。",
    hint: "status が loading のときだけ",
    enabled: (s) => s.status === "loading",
  },
  "r2-mark-completed": {
    action: "mark",
    body: { status: "completed" },
    hint: "status が returning のときだけ",
    enabled: (s) => s.status === "returning",
  },
  "r2-mark-failed": {
    action: "mark",
    body: { status: "failed" },
    hint: "status が loading / returning のときだけ",
    enabled: (s) => s.status === "loading" || s.status === "returning",
  },
  "r2-reset": {
    action: "reset",
    confirm: "R2 が A にいることを確認しましたか？ status を completed に戻します。",
    hint: "status が failed のときだけ",
    enabled: (s) => s.status === "failed",
  },
};

let r2Snapshot = null;
let pendingR2Action = null;

function postR2(action, body) {
  r2Result.textContent = "送信中…";
  fetch("/api/debug/r2/" + action, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  })
    .then((resp) => resp.json().then((data) => ({ ok: resp.ok, data })))
    .then(({ ok, data }) => {
      r2Result.textContent = ok ? "完了" : data.message || "受け付けられませんでした";
      if (ok) {
        renderR2(data);
      }
    })
    .catch(() => {
      r2Result.textContent = "送信に失敗しました";
    });
}

Object.entries(R2_BUTTONS).forEach(([id, spec]) => {
  document.getElementById(id).addEventListener("click", () => {
    if (!spec.confirm) {
      postR2(spec.action, spec.body);
      return;
    }
    pendingR2Action = spec;
    r2ConfirmMessage.textContent = spec.confirm;
    r2Confirm.hidden = false;
  });
});

document.getElementById("r2-confirm-yes").addEventListener("click", () => {
  r2Confirm.hidden = true;
  if (pendingR2Action) {
    postR2(pendingR2Action.action, pendingR2Action.body);
    pendingR2Action = null;
  }
});

document.getElementById("r2-confirm-no").addEventListener("click", () => {
  r2Confirm.hidden = true;
  pendingR2Action = null;
});

r2ToggleConnection.addEventListener("click", () => {
  const live = r2Snapshot && ["connected", "connecting", "disconnected"].includes(r2Snapshot.connection);
  postR2(live ? "disconnect" : "connect");
});

document.getElementById("state-machine-reset").addEventListener("click", () => {
  fetch("/api/reset", { method: "POST" }).catch(() => {});
});

function formatReply(snapshot) {
  if (!snapshot.last_reply) {
    return "-";
  }
  const seconds =
    typeof snapshot.last_reply_seconds === "number"
      ? `（受信まで ${snapshot.last_reply_seconds.toFixed(1)} 秒）`
      : "";
  return `${JSON.stringify(snapshot.last_reply)} ${toSecondsTime(snapshot.last_reply_at)}${seconds}`;
}

function renderR2(snapshot) {
  r2Snapshot = snapshot;
  r2Panel.className = "r2-connection-" + snapshot.connection;
  r2Connection.textContent = CONNECTION_LABELS[snapshot.connection] || snapshot.connection;
  r2ConnectionAt.textContent = toSecondsTime(snapshot.connection_at);
  r2ToggleConnection.textContent = snapshot.connection === "stopped" ? "接続" : "切断";
  r2Status.textContent = snapshot.starting ? `${snapshot.status}（開始中）` : snapshot.status;
  r2StatusAt.textContent = toSecondsTime(snapshot.status_at);
  r2Failure.textContent = snapshot.failure
    ? `${snapshot.failure_message}（${snapshot.failure}）`
    : "-";
  r2UnderMode.textContent = snapshot.under_mode || "-";
  r2UnderModeAt.textContent = toSecondsTime(snapshot.under_mode_at);
  r2LastReply.textContent = formatReply(snapshot);
  Object.entries(R2_BUTTONS).forEach(([id, spec]) => {
    const button = document.getElementById(id);
    if (id === "r2-stop") {
      // STOP can be pressed during a start; only check its enabled rule.
      button.disabled = !spec.enabled(snapshot);
    } else {
      // Other buttons are disabled while starting.
      button.disabled = snapshot.starting || !spec.enabled(snapshot);
    }
    button.title = button.disabled ? spec.hint : "";
  });
  r2Hint.textContent = Object.entries(R2_BUTTONS)
    .filter(([id]) => document.getElementById(id).disabled)
    .map(([id, spec]) => `${document.getElementById(id).textContent}: ${spec.hint}`)
    .join(" / ");
}

fetch("/api/debug/r2")
  .then((resp) => resp.json())
  .then(renderR2)
  .catch(() => {});

function toSecondsTime(isoString) {
  if (!isoString) {
    return "-";
  }
  return new Date(isoString).toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function render(snapshot) {
  renderEntry(snapshot);

  statusPhase.textContent = snapshot.phase;
  statusStep.textContent = snapshot.step;
  statusGuest.textContent = snapshot.guest_name || "-";

  pfStatusValue.textContent = snapshot.pf_status || "-";
  pfStatusAt.textContent = toSecondsTime(snapshot.pf_status_at);

  STEPS.forEach((step) => {
    const el = document.getElementById("arrow-" + step);
    if (el) {
      el.classList.remove("active");
    }
  });

  const activeArrow = document.getElementById("arrow-" + snapshot.step);
  if (activeArrow) {
    activeArrow.classList.add("active");
  }

  const bounds = ROW_BOUNDS[snapshot.step];
  if (bounds) {
    playhead.setAttribute("y", bounds.y);
    playhead.setAttribute("height", bounds.height);
  }

  if (snapshot.phase === "error") {
    sequenceDiagram.classList.add("error");
    debugErrorMessage.textContent = snapshot.error_message;
    debugError.hidden = false;
    return;
  }

  sequenceDiagram.classList.remove("error");
  debugError.hidden = true;
}

const eventSource = new EventSource("/api/events");
eventSource.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  // Typed events (e.g. ui_action) are not state snapshots.
  if (payload.type) {
    if (payload.type === "voice_turn") {
      addVoiceTurn(payload);
    }
    if (payload.type === "r2_state") {
      renderR2(payload);
    }
    return;
  }
  render(payload);
};

function tickClock() {
  currentTime.textContent = toSecondsTime(new Date().toISOString());
}

tickClock();
setInterval(tickClock, 1000);
