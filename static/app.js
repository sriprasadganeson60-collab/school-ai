const categories = ["attendance", "performance", "discipline", "event"];
let cachedData = {};
let attendanceChart;
let performanceChart;

const listEl = document.getElementById("recordList");
const latestEl = document.getElementById("latestRecord");
const categoryFilter = document.getElementById("categoryFilter");
const searchInput = document.getElementById("searchInput");
const aiResponseEl = document.getElementById("aiResponse");
const voiceSelect = document.getElementById("voiceSelect");

function saveLocal() {
  localStorage.setItem("schoolDashboardCache", JSON.stringify(cachedData));
}

function loadLocal() {
  const raw = localStorage.getItem("schoolDashboardCache");
  if (!raw) return;
  try {
    cachedData = JSON.parse(raw);
    render();
  } catch (e) {
    console.warn("Cache parse failed", e);
  }
}

async function fetchCategory(category) {
  const res = await fetch(`/display/${category}`);
  if (!res.ok) throw new Error(`Failed ${category}`);
  return await res.json();
}

async function refreshData() {
  for (const cat of categories) {
    try {
      cachedData[cat] = await fetchCategory(cat);
    } catch (e) {
      console.warn(e.message);
    }
  }
  saveLocal();
  render();
  scheduleEventNotifications();
}

function flattenRecords() {
  const flat = [];
  for (const cat of categories) {
    for (const item of cachedData[cat] || []) {
      flat.push({ ...item, _category: cat });
    }
  }
  return flat.sort((a, b) => `${b.date}-${b.id}`.localeCompare(`${a.date}-${a.id}`));
}

function render() {
  const filter = categoryFilter.value;
  const term = searchInput.value.toLowerCase().trim();
  const records = flattenRecords().filter((r) => {
    if (filter !== "all" && r._category !== filter) return false;
    if (!term) return true;
    const hay = [r.name, r.event_name, r.subject, r.case_desc, r.description].join(" ").toLowerCase();
    return hay.includes(term);
  });

  listEl.innerHTML = "";
  records.forEach((r) => {
    const li = document.createElement("li");
    li.className = "list-group-item";
    li.textContent = `[${r._category}] ${JSON.stringify(r)}`;
    listEl.appendChild(li);
  });

  latestEl.textContent = records.length ? JSON.stringify(records[0], null, 2) : "No matching records.";
  renderCharts();
}

function renderCharts() {
  const attendanceMap = {};
  (cachedData.attendance || []).forEach((r) => {
    attendanceMap[r.name] = (attendanceMap[r.name] || 0) + 1;
  });

  const perfMap = {};
  (cachedData.performance || []).forEach((r) => {
    if (!perfMap[r.name]) perfMap[r.name] = { total: 0, count: 0 };
    perfMap[r.name].total += Number(r.marks || 0);
    perfMap[r.name].count += 1;
  });

  if (attendanceChart) attendanceChart.destroy();
  attendanceChart = new Chart(document.getElementById("attendanceChart"), {
    type: "bar",
    data: {
      labels: Object.keys(attendanceMap),
      datasets: [{ label: "Attendance", data: Object.values(attendanceMap) }],
    },
  });

  if (performanceChart) performanceChart.destroy();
  performanceChart = new Chart(document.getElementById("performanceChart"), {
    type: "bar",
    data: {
      labels: Object.keys(perfMap),
      datasets: [
        {
          label: "Avg Marks",
          data: Object.values(perfMap).map((v) => (v.count ? (v.total / v.count).toFixed(2) : 0)),
        },
      ],
    },
  });
}

async function askAI() {
  const question = document.getElementById("questionInput").value.trim();
  if (!question) return;

  const res = await fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const data = await res.json();
  aiResponseEl.textContent = JSON.stringify(data.response, null, 2);

  if (data.tts_audio_base64) {
    const audio = new Audio(`data:${data.tts_mime};base64,${data.tts_audio_base64}`);
    audio.play().catch(console.warn);
  } else {
    speakBrowser(data.response?.message || "Done");
  }

  await refreshData();
}

function speakBrowser(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  const selected = speechSynthesis.getVoices().find((v) => v.name === voiceSelect.value);
  if (selected) u.voice = selected;
  u.pitch = Number(document.getElementById("pitchInput").value || 1);
  u.rate = Number(document.getElementById("rateInput").value || 1);
  speechSynthesis.speak(u);
}

function populateVoices() {
  const voices = speechSynthesis.getVoices();
  voiceSelect.innerHTML = voices.map((v) => `<option>${v.name}</option>`).join("");
}

function scheduleEventNotifications() {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const now = new Date();
  (cachedData.event || []).forEach((e) => {
    const d = new Date(e.date);
    const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24));
    if (diffDays >= 0 && diffDays <= 2) {
      new Notification("Upcoming School Event", { body: `${e.event_name} on ${e.date}` });
    }
  });
}

async function manualAdd() {
  const category = document.getElementById("manualCategory").value;
  let payload;
  try {
    payload = JSON.parse(document.getElementById("manualJson").value);
  } catch {
    alert("Invalid JSON");
    return;
  }

  const res = await fetch(`/add/${category}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  aiResponseEl.textContent = JSON.stringify(data, null, 2);
  await refreshData();
}

document.getElementById("refreshBtn").addEventListener("click", refreshData);
document.getElementById("askBtn").addEventListener("click", askAI);
document.getElementById("manualAddBtn").addEventListener("click", manualAdd);
document.getElementById("notifyBtn").addEventListener("click", async () => {
  if (!("Notification" in window)) return alert("Notifications unsupported");
  await Notification.requestPermission();
  scheduleEventNotifications();
});
categoryFilter.addEventListener("change", render);
searchInput.addEventListener("input", render);

window.speechSynthesis.onvoiceschanged = populateVoices;
populateVoices();
loadLocal();
refreshData();
