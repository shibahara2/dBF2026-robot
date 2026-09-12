const STEP_MESSAGES = {
  polling_pf_ready: "AI管制PF(案内ロボット)の状態を確認しています",
  polling_r2_ready: "ドリンク準備ロボットの状態を確認しています",
  sending_load_drink: "ドリンクをセットしています",
  polling_r2_active: "ドリンクをお届け中です",
  notifying_pf_placed: "お届け完了を通知しています",
};

const formView = document.getElementById("form-view");
const progressView = document.getElementById("progress-view");
const errorView = document.getElementById("error-view");
const checkinForm = document.getElementById("checkin-form");
const guestNameInput = document.getElementById("guest-name-input");
const progressMessage = document.getElementById("progress-message");
const errorMessage = document.getElementById("error-message");
const resetButton = document.getElementById("reset-button");

function getMyGuestName() {
  return sessionStorage.getItem("myGuestName");
}

function setMyGuestName(name) {
  sessionStorage.setItem("myGuestName", name);
}

function render(snapshot) {
  formView.hidden = true;
  progressView.hidden = true;
  errorView.hidden = true;

  if (snapshot.phase === "error") {
    errorMessage.textContent = snapshot.error_message;
    errorView.hidden = false;
    return;
  }

  if (snapshot.step === "awaiting_checkin") {
    formView.hidden = false;
    return;
  }

  const stepMessage = STEP_MESSAGES[snapshot.step] || "";
  if (snapshot.guest_name === getMyGuestName()) {
    progressMessage.textContent = stepMessage;
  } else {
    progressMessage.textContent = "他の方が対応中：" + stepMessage;
  }
  progressView.hidden = false;
}

checkinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const name = guestNameInput.value.trim();
  if (!name) {
    return;
  }
  setMyGuestName(name);
  fetch("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name }),
  });
});

resetButton.addEventListener("click", () => {
  fetch("/api/reset", { method: "POST" });
});

const eventSource = new EventSource("/api/events");
eventSource.onmessage = (event) => {
  render(JSON.parse(event.data));
};
