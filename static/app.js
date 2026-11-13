const TOKEN_KEY = "ts_auth_token";
const MODE_KEY = "ts_auth_mode";

const authSection = document.getElementById("authSection");
const authForm = document.getElementById("authForm");
const passwordInput = document.getElementById("passwordInput");
const authBtn = document.getElementById("authBtn");
const authErrorBox = document.getElementById("authErrorBox");

const appSection = document.getElementById("appSection");
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

function getAuthToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

function setAuthSession(token, mode) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(MODE_KEY, mode);
}

function clearAuthSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(MODE_KEY);
}

function showAuthGate() {
  appSection.classList.add("hidden");
  syncBtn.classList.add("hidden");
  resultsSection.classList.add("hidden");
  authSection.classList.remove("hidden");
  passwordInput.value = "";
  passwordInput.focus();
}

function showApp() {
  authSection.classList.add("hidden");
  appSection.classList.remove("hidden");
  syncBtn.classList.remove("hidden");
  phoneInput.focus();
  warmCache();
}

function showError(box, message) {
  box.textContent = message;
  box.classList.remove("hidden");
}

function hideError(box) {
  box.textContent = "";
  box.classList.add("hidden");
}

function updateInputUI() {
  const val = phoneInput.value.trim();
  digitCount.textContent = `${val.length}/10`;
  clearBtn.classList.toggle("hidden", val.length === 0);
}

passwordInput.addEventListener("input", () => hideError(authErrorBox));

phoneInput.addEventListener("input", () => {
  hideError(errorBox);
  updateInputUI();
});

clearBtn.addEventListener("click", () => {
  phoneInput.value = "";
  hideError(errorBox);
  updateInputUI();
  phoneInput.focus();
});

async function warmCache() {
  const token = getAuthToken();
  if (!token) return;
  try {
    await fetch("/api/refresh", {
      method: "POST",
      headers: { "X-Auth-Token": token },
    });
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
    } else {
      statusBadge.textContent = "Not Configured";
      statusBadge.className = "status-pill status-warn";
    }
  } catch {
    statusBadge.textContent = "Offline";
    statusBadge.className = "status-pill status-warn";
  }
}

authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError(authErrorBox);

  const password = passwordInput.value;
  if (!password) {
    showError(authErrorBox, "Please enter a password.");
    passwordInput.focus();
    return;
  }

  authBtn.disabled = true;
  authBtn.textContent = "Checking…";

  try {
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(authErrorBox, data.error || "Incorrect password.");
      passwordInput.select();
      return;
    }

    setAuthSession(data.token, data.mode);
    showApp();
  } catch {
    showError(authErrorBox, "Could not reach the server. Please try again.");
  } finally {
    authBtn.disabled = false;
    authBtn.textContent = "Unlock";
  }
});

syncBtn.addEventListener("click", async () => {
  const token = getAuthToken();
  if (!token) {
    showAuthGate();
    return;
  }

  syncBtn.disabled = true;
  syncBtn.textContent = "Syncing…";
  try {
    const res = await fetch("/api/refresh", {
      method: "POST",
      headers: { "X-Auth-Token": token },
    });
    if (res.status === 401) {
      clearAuthSession();
      showAuthGate();
      return;
    }
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
  resultsHead.innerHTML = "";
  resultsBody.innerHTML = "";

  if (data.mode === "masked") {
    tableWrapper.classList.add("hidden");
    if (data.is_duplicate) {
      verdictBanner.className = "verdict-banner verdict-duplicate";
      verdictLabel.textContent = "DUPLICATE";
      verdictDetail.textContent = data.query;
    } else {
      verdictBanner.className = "verdict-banner verdict-clear";
      verdictLabel.textContent = "NOT FOUND — GOOD TO GO";
      verdictDetail.textContent = data.query;
    }
    return;
  }

  const count = data.matches.length;

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
  hideError(errorBox);

  const token = getAuthToken();
  if (!token) {
    showAuthGate();
    return;
  }

  const raw = phoneInput.value.trim();
  if (!/^\d{10}$/.test(raw)) {
    showError(errorBox, "Please enter a valid 10-digit phone number.");
    phoneInput.focus();
    return;
  }

  searchBtn.disabled = true;
  searchBtn.textContent = "Checking…";

  try {
    const res = await fetch(`/api/search?phone=${encodeURIComponent(raw)}`, {
      headers: { "X-Auth-Token": token },
    });
    const data = await res.json();

    if (res.status === 401) {
      clearAuthSession();
      showAuthGate();
      return;
    }

    if (!res.ok) {
      showError(errorBox, data.error || "Search failed.");
      return;
    }

    renderResults(data);
  } catch {
    showError(errorBox, "Could not reach the server. Please make sure the app is running.");
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = "Check";
  }
});

updateInputUI();
checkStatus();

if (getAuthToken()) {
  showApp();
} else {
  showAuthGate();
}
