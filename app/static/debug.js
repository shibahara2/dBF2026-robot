const STEPS = [
  "awaiting_checkin",
  "polling_pf_ready",
  "polling_r2_ready",
  "sending_load_drink",
  "polling_r2_active",
  "notifying_pf_placed",
];

const ROW_BOUNDS = {
  awaiting_checkin: { y: 75, height: 30 },
  polling_pf_ready: { y: 125, height: 60 },
  polling_r2_ready: { y: 205, height: 60 },
  sending_load_drink: { y: 285, height: 60 },
  polling_r2_active: { y: 365, height: 60 },
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
const r2StatusValue = document.getElementById("r2-status-value");
const r2StatusAt = document.getElementById("r2-status-at");
const currentTime = document.getElementById("current-time");

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
  statusPhase.textContent = snapshot.phase;
  statusStep.textContent = snapshot.step;
  statusGuest.textContent = snapshot.guest_name || "-";

  pfStatusValue.textContent = snapshot.pf_status || "-";
  pfStatusAt.textContent = toSecondsTime(snapshot.pf_status_at);
  r2StatusValue.textContent = snapshot.r2_status || "-";
  r2StatusAt.textContent = toSecondsTime(snapshot.r2_status_at);

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
  render(JSON.parse(event.data));
};

function tickClock() {
  currentTime.textContent = toSecondsTime(new Date().toISOString());
}

tickClock();
setInterval(tickClock, 1000);
