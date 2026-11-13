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
const tableWrapper = document.getElementById("tableWrapper");
const resultsHead = document.getElementById("resultsHead");
const resultsBody = document.getElementById("resultsBody");

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
      statusBadge.textContent = "Not Configured";
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

function renderResults(data) {
  resultsSection.classList.remove("hidden");
  const count = data.matches.length;

  resultsHead.innerHTML = "";
  resultsBody.innerHTML = "";

  if (count === 0) {
    verdictBanner.className = "verdict-banner verdict-clear";
    verdictLabel.textContent = "NOT FOUND — GOOD TO GO";
    verdictDetail.textContent = data.query;
    tableWrapper.classList.add("hidden");
    return;
  }

  verdictBanner.className = "verdict-banner verdict-duplicate";
  verdictLabel.textContent = "DUPLICATE";
  verdictDetail.textContent =
    count === 1
      ? `1 matching row for ${data.query}`
      : `${count} matching rows for ${data.query}`;

  tableWrapper.classList.remove("hidden");

  const headerRow = document.createElement("tr");
  const rowNumTh = document.createElement("th");
  rowNumTh.textContent = "Row #";
  headerRow.appendChild(rowNumTh);

  data.headers.forEach((header) => {
    const th = document.createElement("th");
    th.textContent = header || "(Blank)";
    headerRow.appendChild(th);
  });
  resultsHead.appendChild(headerRow);

  data.matches.forEach((match) => {
    const tr = document.createElement("tr");

    const rowNumTd = document.createElement("td");
    rowNumTd.className = "cell-row-num";
    rowNumTd.textContent = match.row_number;
    tr.appendChild(rowNumTd);

    const matchedSet = new Set(match.matched_indices);
    match.values.forEach((val, idx) => {
      const td = document.createElement("td");
      td.textContent = val;
      if (matchedSet.has(idx)) {
        td.className = "cell-matched";
      }
      tr.appendChild(td);
    });

    resultsBody.appendChild(tr);
  });
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
      showError(data.error || "Search failed.");
      return;
    }

    renderResults(data);
  } catch {
    showError("Could not reach the server. Please make sure the app is running.");
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = "Check";
  }
});

updateInputUI();
checkStatus();
