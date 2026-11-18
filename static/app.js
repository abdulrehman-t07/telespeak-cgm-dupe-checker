const phoneInput = document.getElementById("phoneInput");
const digitCount = document.getElementById("digitCount");
const clearBtn = document.getElementById("clearBtn");
const searchForm = document.getElementById("searchForm");
const searchBtn = document.getElementById("searchBtn");
const syncBtn = document.getElementById("syncBtn");
const errorBox = document.getElementById("errorBox");

const statusBadge = document.getElementById("statusBadge");
const resultsSection = document.getElementById("resultsSection");
const verdictBanner = document.getElementById("verdictBanner");
const verdictLabel = document.getElementById("verdictLabel");
const verdictDetail = document.getElementById("verdictDetail");

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function hideError() {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function updateInputUI() {
  const val = phoneInput.value.trim();
  digitCount.textContent = `${val.length}/10`;
  clearBtn.classList.toggle("hidden", val.length === 0);
}

phoneInput.addEventListener("input", () => {
  hideError();
  updateInputUI();
});

clearBtn.addEventListener("click", () => {
  phoneInput.value = "";
  hideError();
  updateInputUI();
  phoneInput.focus();
});

async function warmCache() {
  try {
    await fetch("/api/refresh", { method: "POST" });
  } catch {
    // Non-fatal; search will still fetch on demand
  }
}

async function checkStatus() {
  statusBadge.textContent = "Checking…";
  statusBadge.className = "status-pill status-loading";

  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (data.configured) {
      statusBadge.textContent = "Ready";
      statusBadge.className = "status-pill status-ok";
      warmCache();
    } else {
      statusBadge.textContent = "Unavailable";
      statusBadge.className = "status-pill status-warn";
    }
  } catch {
    statusBadge.textContent = "Offline";
    statusBadge.className = "status-pill status-warn";
  }
}

syncBtn.addEventListener("click", async () => {
  syncBtn.disabled = true;
  syncBtn.textContent = "Syncing…";
  try {
    const res = await fetch("/api/refresh", { method: "POST" });
    if (res.ok) {
      syncBtn.textContent = "✓ Synced";
      setTimeout(() => {
        syncBtn.textContent = "↻ Sync";
      }, 1400);
    } else {
      syncBtn.textContent = "↻ Sync";
    }
  } catch {
    syncBtn.textContent = "↻ Sync";
  } finally {
    syncBtn.disabled = false;
  }
});

function renderResult(data) {
  resultsSection.classList.remove("hidden");
  if (data.is_duplicate) {
    verdictBanner.className = "verdict-banner verdict-duplicate";
    verdictLabel.textContent = "DUPLICATE";
    verdictDetail.textContent = data.query;
  } else {
    verdictBanner.className = "verdict-banner verdict-clear";
    verdictLabel.textContent = "NOT FOUND — GOOD TO GO";
    verdictDetail.textContent = data.query;
  }
}

searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();

  const raw = phoneInput.value.trim();
  if (!/^\d{10}$/.test(raw)) {
    showError("Please enter a valid 10-digit phone number.");
    phoneInput.focus();
    return;
  }

  searchBtn.disabled = true;
  searchBtn.textContent = "Checking…";

  try {
    const res = await fetch(`/api/search?phone=${encodeURIComponent(raw)}`);
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Something went wrong. Please try again later.");
      return;
    }

    renderResult(data);
  } catch {
    showError("Unable to reach the server. Please try again later.");
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = "Check";
  }
});

updateInputUI();
checkStatus();
