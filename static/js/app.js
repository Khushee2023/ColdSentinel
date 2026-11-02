const $ = (id) => document.getElementById(id);

let chart = null;
let selected = null;
let lastSnapshot = "";

// escape text before putting it into HTML
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

function renderUnits(units) {
  if (!units.length) {
    $("units").innerHTML = '<p class="unit-meta">No data yet. Run the replay script.</p>';
    return;
  }
  $("units").innerHTML = units
    .map((u) => {
      const eta =
        u.status === "alert" && u.eta_min != null ? ` · ~${u.eta_min} min to 8°C` : "";
      return `
        <div class="unit status-${esc(u.status)}">
          <div class="unit-top">
            <span class="unit-name">Unit ${esc(u.unit_id)}</span>
            <span class="badge ${esc(u.status)}">${esc(u.status)}</span>
          </div>
          <div class="unit-temp">${Number(u.temp_c).toFixed(1)}°C</div>
          <div class="unit-meta">score ${Number(u.score).toFixed(2)} · ${esc(u.timestamp)}${eta}</div>
        </div>`;
    })
    .join("");
}

function renderAlerts(alerts) {
  $("alerts").innerHTML = alerts.length
    ? alerts
        .map(
          (a) => `
        <li class="alert-item sev-${esc(a.severity)}">
          <div class="alert-head">
            <strong>Unit ${esc(a.unit_id)} · ${esc((a.severity || "").toUpperCase())}</strong>
            <span>${esc(a.timestamp)}</span>
          </div>
          <p class="alert-msg">${esc(a.message)}</p>
        </li>`
        )
        .join("")
    : '<li class="empty">No alerts.</li>';
}

function syncSelect(units) {
  const sel = $("unit-select");
  const ids = units.map((u) => u.unit_id);
  if (sel.options.length !== ids.length) {
    sel.innerHTML = ids.map((id) => `<option value="${esc(id)}">Unit ${esc(id)}</option>`).join("");
  }
  if (!selected && ids.length) selected = ids[0];
  if (selected) sel.value = selected;
}

function initChart() {
  if (typeof Chart === "undefined") return; // CDN blocked / offline
  chart = new Chart($("chart"), {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Temperature (°C)", data: [], borderColor: "#2563eb", yAxisID: "yT", tension: 0.25, pointRadius: 0 },
        { label: "Failure limit (8°C)", data: [], borderColor: "#d93636", borderDash: [6, 4], yAxisID: "yT", pointRadius: 0 },
        { label: "Anomaly score", data: [], borderColor: "#d98b00", yAxisID: "yS", tension: 0.25, pointRadius: 0 },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        yT: { position: "left", title: { display: true, text: "°C" } },
        yS: { position: "right", min: 0.3, max: 0.8, title: { display: true, text: "score" }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function renderChart(hist) {
  if (!chart) return;
  chart.data.labels = hist.map((h) => h.timestamp);
  chart.data.datasets[0].data = hist.map((h) => h.temp_c);
  chart.data.datasets[1].data = hist.map(() => 8);
  chart.data.datasets[2].data = hist.map((h) => h.score);
  chart.update("none");
}

async function refresh() {
  const live = $("live");
  try {
    const [units, alerts] = await Promise.all([getJSON("/api/status"), getJSON("/api/alerts")]);
    renderUnits(units);
    renderAlerts(alerts);
    syncSelect(units);

    if (selected) {
      renderChart(await getJSON(`/api/history/${encodeURIComponent(selected)}`));
    }

    const snapshot = JSON.stringify(units.map((u) => u.id));
    const changed = snapshot !== lastSnapshot;
    live.textContent = changed ? "live" : "idle";
    live.classList.toggle("on", changed);
    lastSnapshot = snapshot;
  } catch (e) {
    live.textContent = "offline";
    live.classList.remove("on");
    console.error(e);
  }
}

$("unit-select").addEventListener("change", (e) => {
  selected = e.target.value;
  refresh();
});

initChart();
refresh();
setInterval(refresh, 1000);