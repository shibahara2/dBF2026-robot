const STEP_MESSAGES = {
  polling_pf_ready: "AI管制PF(案内ロボット)の状態を確認しています",
  polling_r2_ready: "ドリンク準備ロボットの状態を確認しています",
  sending_load_drink: "ドリンクをセットしています",
  polling_r2_active: "ドリンクを積み込み中です",
  notifying_pf_placed: "積み込み完了をAI管制PFに通知しています",
};

const formView = document.getElementById("form-view");
const progressView = document.getElementById("progress-view");
const errorView = document.getElementById("error-view");
const progressMessage = document.getElementById("progress-message");
const errorMessage = document.getElementById("error-message");
const resetButton = document.getElementById("reset-button");

const stages = {
  start: document.getElementById("stage-start"),
  search: document.getElementById("stage-search"),
  select: document.getElementById("stage-select"),
  confirm: document.getElementById("stage-confirm"),
};
const startButton = document.getElementById("start-button");
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchError = document.getElementById("search-error");
const candidateList = document.getElementById("candidate-list");
const reservationDetail = document.getElementById("reservation-detail");
const confirmButton = document.getElementById("confirm-button");
const confirmError = document.getElementById("confirm-error");

let selectedReservation = null;
let lastStep = null;

function getMyGuestName() {
  return sessionStorage.getItem("myGuestName");
}

function setMyGuestName(name) {
  sessionStorage.setItem("myGuestName", name);
}

function showStage(name) {
  Object.keys(stages).forEach((key) => {
    stages[key].hidden = key !== name;
  });
  searchError.textContent = "";
  confirmError.textContent = "";
  if (name === "search") {
    searchInput.focus();
    searchInput.select();
  }
}

function resetFlow() {
  selectedReservation = null;
  candidateList.replaceChildren();
  reservationDetail.replaceChildren();
  showStage("start");
}

function formatStay(reservation) {
  return `${reservation.check_in_date} 〜 ${reservation.check_out_date} (${reservation.nights}泊)`;
}

function renderDetail(reservation) {
  const rows = [
    ["予約番号", reservation.reservation_number],
    ["お名前", reservation.guest_name + " 様"],
    ["ご宿泊", formatStay(reservation)],
    ["人数", `${reservation.guests}名`],
    ["プラン", reservation.plan],
    ["お部屋", reservation.room_number],
    ["電話番号", reservation.phone_masked],
  ];
  reservationDetail.replaceChildren();
  rows.forEach(([label, value]) => {
    if (!value) {
      return;
    }
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    reservationDetail.append(dt, dd);
  });
}

function selectReservation(reservation) {
  selectedReservation = reservation;
  renderDetail(reservation);
  showStage("confirm");
}

function renderCandidates(reservations) {
  candidateList.replaceChildren();
  reservations.forEach((reservation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "candidate";
    const name = document.createElement("strong");
    name.textContent = `${reservation.guest_name} 様`;
    const detail = document.createElement("span");
    detail.textContent = `${reservation.reservation_number} / ${formatStay(reservation)}`;
    button.append(name, detail);
    button.addEventListener("click", () => selectReservation(reservation));
    const item = document.createElement("li");
    item.append(button);
    candidateList.append(item);
  });
  showStage("select");
}

function searchReservations(query) {
  searchError.textContent = "";
  return fetch("/api/reservations/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query }),
  })
    .then((resp) => resp.json().then((data) => ({ ok: resp.ok, data: data })))
    .then(({ ok, data }) => {
      if (!ok) {
        searchError.textContent = "検索できませんでした。入力内容をご確認ください。";
        return;
      }
      const reservations = data.reservations || [];
      if (reservations.length === 0) {
        searchError.textContent =
          "ご予約が見つかりませんでした。別の情報でお試しください。";
        return;
      }
      if (reservations.length === 1) {
        selectReservation(reservations[0]);
        return;
      }
      renderCandidates(reservations);
    })
    .catch(() => {
      searchError.textContent = "通信に失敗しました。もう一度お試しください。";
    });
}

const CONFIRM_ERRORS = {
  404: "ご予約が見つかりませんでした。もう一度検索してください。",
  409: "現在ほかの方が対応中か、すでにチェックイン済みです。",
};

function confirmCheckin() {
  if (!selectedReservation) {
    return;
  }
  confirmError.textContent = "";
  confirmButton.disabled = true;
  fetch("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reservation_id: selectedReservation.reservation_id }),
  })
    .then((resp) => {
      if (resp.ok) {
        setMyGuestName(selectedReservation.guest_name);
        return;
      }
      confirmError.textContent =
        CONFIRM_ERRORS[resp.status] || "チェックインに失敗しました。";
    })
    .catch(() => {
      confirmError.textContent = "通信に失敗しました。もう一度お試しください。";
    })
    .finally(() => {
      confirmButton.disabled = false;
    });
}

function render(snapshot) {
  formView.hidden = true;
  progressView.hidden = true;
  errorView.hidden = true;

  if (snapshot.phase === "error") {
    errorMessage.textContent = snapshot.error_message;
    errorView.hidden = false;
    lastStep = snapshot.step;
    return;
  }

  if (snapshot.step === "awaiting_checkin") {
    // A finished (or reset) cycle puts the kiosk back to the start screen.
    if (lastStep !== "awaiting_checkin") {
      resetFlow();
    }
    formView.hidden = false;
    lastStep = snapshot.step;
    return;
  }

  const stepMessage = STEP_MESSAGES[snapshot.step] || "";
  if (snapshot.guest_name === getMyGuestName()) {
    progressMessage.textContent = stepMessage;
  } else {
    progressMessage.textContent = "他の方が対応中：" + stepMessage;
  }
  progressView.hidden = false;
  lastStep = snapshot.step;
}

startButton.addEventListener("click", () => showStage("search"));

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  if (!query) {
    return;
  }
  searchReservations(query);
});

confirmButton.addEventListener("click", confirmCheckin);

document.querySelectorAll(".back-button").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.target === "start") {
      resetFlow();
    } else {
      showStage(button.dataset.target);
    }
  });
});

resetButton.addEventListener("click", () => {
  fetch("/api/reset", { method: "POST" }).catch(() => {});
});

const eventSource = new EventSource("/api/events");
eventSource.onmessage = (event) => {
  render(JSON.parse(event.data));
};
