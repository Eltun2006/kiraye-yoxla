/* KirayəYoxla frontend — plain JS, no build step. Talks to the FastAPI backend on the same origin. */
const app = document.getElementById("app");

const RISK = {
  high: { label: "Yüksək risk", short: "Yüksək", color: "var(--high)" },
  medium: { label: "Orta risk", short: "Orta", color: "var(--med)" },
  low: { label: "Aşağı risk", short: "Aşağı", color: "var(--low)" },
};
const CATEGORY = {
  deposit: "Depozit", payment: "Ödəniş", price_change: "Qiymət dəyişikliyi", penalty: "Cərimə",
  termination: "Müqavilənin ləğvi", access_privacy: "Mənzilə giriş", repairs: "Təmir",
  utilities: "Kommunal", usage_rules: "İstifadə qaydaları", general: "Ümumi",
};
const DECISION = { accepted: "✓ Qəbul edildi", edited: "✎ Redaktə edildi", rejected: "Rədd edildi" };
const STEPS = [
  { key: "queued", label: "Sənəd qəbul edildi" },
  { key: "parsing", label: "Mətn oxunur və bəndlərə bölünür" },
  { key: "analyzing", label: "Hər bənd risk baxımından analiz edilir" },
  { key: "done", label: "Nəticə hazırlanır" },
];
const ACCEPT = [".pdf", ".docx", ".txt"];
const MAX_MB = 5;

/* ---------- helpers ---------- */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MONTHS = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avq", "sen", "okt", "noy", "dek"];
const fmtDate = (iso) => {
  const d = new Date(iso), p = (n) => String(n).padStart(2, "0");
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// "My analyses" live in this browser: the server deliberately has no endpoint listing everyone's
// contracts, and an analysis link (unguessable id) is the only way to open it.
const SAVED_KEY = "kiraye.analyses";
const saved = {
  ids() { try { return JSON.parse(localStorage.getItem(SAVED_KEY)) || []; } catch { return []; } },
  set(ids) { try { localStorage.setItem(SAVED_KEY, JSON.stringify(ids.slice(0, 50))); } catch { /* private mode */ } },
  add(id) { this.set([id, ...this.ids().filter((x) => x !== id)]); },
  remove(id) { this.set(this.ids().filter((x) => x !== id)); },
};

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("Serverə qoşulmaq olmadı. Backend işləyirmi?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not json */ }
    throw new Error(typeof detail === "string" ? detail : "Sorğu alınmadı.");
  }
  return res;
}

let toastTimer;
function toast(msg, kind = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 2800);
}

function openModal(title, html) {
  const m = document.getElementById("modal");
  m.querySelector("#modal-title").textContent = title;
  m.querySelector(".modal-body").innerHTML = html;
  m.hidden = false;
  return m;
}
function closeModal() { document.getElementById("modal").hidden = true; }
document.getElementById("modal").addEventListener("click", (e) => {
  if (e.target.id === "modal" || e.target.closest("[data-close]")) closeModal();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function setNav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
}

/* ---------- router ---------- */
let routeToken = 0; // cancels polling when the user navigates away
async function route() {
  const token = ++routeToken;
  const hash = location.hash || "#/";
  closeModal();
  window.scrollTo(0, 0);
  const m = hash.match(/^#\/a\/([\w-]+)/);
  if (m) { setNav(""); return showAnalysis(m[1], token); }
  if (hash.startsWith("#/history")) { setNav("history"); return showHistory(); }
  setNav("home");
  return showHome();
}
window.addEventListener("hashchange", route);

/* =========================================================
   HOME / UPLOAD
   ========================================================= */
const ICON_UPLOAD = `<svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

async function showHome() {
  const state = { tab: "file", file: null, text: "", sample: null };

  app.innerHTML = `
  <section class="hero fade-in">
    <div class="hero-copy">
      <span class="badge-soft">🏠 Kirayəçilər üçün AI köməkçi</span>
      <h1>İmzalamazdan əvvəl <em>riskli bəndləri</em> görün.</h1>
      <p class="lead">Kirayə müqaviləsini yükləyin — KirayəYoxla hər bəndi yoxlayır, riskləri sadə dillə izah edir və ev sahibinə təqdim edə biləcəyiniz ədalətli alternativ mətn təklif edir.</p>
      <ul class="features">
        <li><span class="fi">🔍</span><div><b>Bənd-bənd analiz</b><span>Depozit, cərimə, ləğv, mənzilə giriş — hər şey ayrıca qiymətləndirilir.</span></div></li>
        <li><span class="fi">✍️</span><div><b>Qərar sizindir</b><span>Təklifləri qəbul edin, rədd edin və ya öz variantınızı yazın.</span></div></li>
        <li><span class="fi">📨</span><div><b>Hazır danışıq mesajı</b><span>Qəbul etdiyiniz dəyişikliklərdən ev sahibinə nəzakətli mesaj.</span></div></li>
      </ul>
      <div class="preview-strip" aria-hidden="true">
        <div class="preview-line high"><span>5. Depozit heç bir halda Kirayəçiyə qaytarılmır.</span><span class="pill high">Yüksək</span></div>
        <div class="preview-line medium"><span>6. Hər gecikmə günü üçün 10% cərimə...</span><span class="pill medium">Orta</span></div>
        <div class="preview-line low"><span>13. Müqavilə iki nüsxədə tərtib edilir.</span><span class="pill low">Aşağı</span></div>
      </div>
    </div>

    <div class="card upload-card">
      <div class="tabs" role="tablist">
        <button class="tab active" data-tab="file" role="tab">📄 Fayl</button>
        <button class="tab" data-tab="text" role="tab">📋 Mətn</button>
        <button class="tab" data-tab="sample" role="tab">🧪 Nümunə</button>
      </div>

      <div class="panel" data-panel="file">
        <label class="dropzone" id="dz">
          <input type="file" id="file" accept="${ACCEPT.join(",")}" hidden>
          <span class="dz-icon">${ICON_UPLOAD}</span>
          <b>Faylı bura sürükləyin</b>
          <span class="muted">və ya kompüterdən seçmək üçün klikləyin</span>
          <small class="muted">PDF, DOCX, TXT · maks. ${MAX_MB} MB</small>
        </label>
        <div id="file-chip"></div>
      </div>

      <div class="panel" data-panel="text" hidden>
        <textarea class="input" id="text" placeholder="1. Ev sahibi ... mənzili Kirayəçiyə istifadəyə verir.&#10;2. Müqavilənin müddəti ...&#10;3. ..."></textarea>
        <div class="counter"><span id="count">0</span> / 40 000 simvol</div>
      </div>

      <div class="panel" data-panel="sample" hidden>
        <div class="samples" id="samples"><p class="muted">Yüklənir...</p></div>
      </div>

      <div class="upload-foot">
        <small id="hint">Başlamaq üçün fayl seçin.</small>
        <button class="btn btn-primary btn-lg" id="go" disabled>Analizə başla →</button>
      </div>
    </div>
  </section>`;

  const $ = (s) => app.querySelector(s);
  const go = $("#go"), hint = $("#hint");

  function refresh() {
    const ready = (state.tab === "file" && state.file) || (state.tab === "text" && state.text.trim().length >= 50) || (state.tab === "sample" && state.sample);
    go.disabled = !ready;
    hint.textContent = {
      file: state.file ? "Hazırdır — analizə başlaya bilərsiniz." : "Başlamaq üçün fayl seçin.",
      text: state.text.trim().length >= 50 ? "Hazırdır — analizə başlaya bilərsiniz." : "Ən azı 50 simvol yapışdırın.",
      sample: state.sample ? "Synthetic nümunə seçildi." : "Nümunə müqavilə seçin.",
    }[state.tab];
  }

  app.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    state.tab = t.dataset.tab;
    app.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    app.querySelectorAll("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== state.tab));
    refresh();
  }));

  // file + drag & drop
  const dz = $("#dz"), input = $("#file");
  function pickFile(f) {
    if (!f) return;
    const ext = "." + f.name.split(".").pop().toLowerCase();
    if (!ACCEPT.includes(ext)) return toast("Yalnız PDF, DOCX və TXT faylları qəbul olunur.", "error");
    if (f.size > MAX_MB * 1024 * 1024) return toast(`Fayl ${MAX_MB} MB-dan böyükdür.`, "error");
    state.file = f;
    $("#file-chip").innerHTML = `
      <div class="file-chip fade-in">
        <span class="ext">${esc(ext.slice(1))}</span>
        <span class="name">${esc(f.name)}</span>
        <span class="muted">${(f.size / 1024).toFixed(0)} KB</span>
        <button class="icon-btn" id="rm" aria-label="Faylı sil">✕</button>
      </div>`;
    $("#rm").onclick = () => { state.file = null; input.value = ""; $("#file-chip").innerHTML = ""; refresh(); };
    refresh();
  }
  input.addEventListener("change", () => pickFile(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => pickFile(e.dataTransfer.files[0]));

  // text
  $("#text").addEventListener("input", (e) => {
    state.text = e.target.value;
    $("#count").textContent = state.text.length.toLocaleString("az-AZ");
    refresh();
  });

  // samples
  try {
    const samples = await (await api("/samples")).json();
    $("#samples").innerHTML = samples.length ? samples.map((s) => `
      <button class="sample" data-name="${esc(s.name)}">
        <span class="ext">${esc(s.format)}</span>
        <span class="meta"><b>${esc(s.title)}</b><small>${esc(s.name)} · ${s.clauses} bənd</small></span>
        <span class="tag-synth">SYNTHETIC</span>
      </button>`).join("") : `<p class="muted">Nümunə tapılmadı.</p>`;
    app.querySelectorAll(".sample").forEach((b) => b.addEventListener("click", () => {
      state.sample = b.dataset.name;
      app.querySelectorAll(".sample").forEach((x) => x.classList.toggle("active", x === b));
      refresh();
    }));
  } catch (e) {
    $("#samples").innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }

  go.addEventListener("click", async () => {
    go.disabled = true;
    go.textContent = "Göndərilir...";
    try {
      const fd = new FormData();
      if (state.tab === "file") fd.append("file", state.file);
      else if (state.tab === "text") fd.append("text", state.text);
      else {
        const blob = await (await api(`/samples/${encodeURIComponent(state.sample)}`)).blob();
        fd.append("file", blob, state.sample);
      }
      const a = await (await api("/analyses", { method: "POST", body: fd })).json();
      saved.add(a.id);
      location.hash = `#/a/${a.id}`;
    } catch (e) {
      toast(e.message, "error");
      go.textContent = "Analizə başla →";
      refresh();
    }
  });
}

/* =========================================================
   ANALYSIS: progress -> result | failure
   ========================================================= */
async function showAnalysis(id, token) {
  let a;
  while (true) {
    try {
      a = await (await api(`/analyses/${id}`)).json();
    } catch (e) {
      return renderFailure({ filename: "Analiz", error: e.message });
    }
    if (token !== routeToken) return; // user navigated away
    if (a.status === "done") return renderResult(a);
    if (a.status === "failed") return renderFailure(a);
    renderProgress(a);
    await sleep(1500);
  }
}

function renderProgress(a) {
  const current = STEPS.findIndex((s) => s.key === a.status);
  app.innerHTML = `
  <div class="progress-wrap fade-in">
    <div class="spinner"></div>
    <h2>Müqavilə yoxlanılır</h2>
    <p class="muted">${esc(a.filename)} · adətən 30–60 saniyə çəkir</p>
    <ol class="steps">
      ${STEPS.map((s, i) => `
        <li class="step ${i < current ? "done" : i === current ? "current" : ""}">
          <span class="dot">${i < current ? "✓" : i === current ? "" : i + 1}</span>${s.label}
        </li>`).join("")}
    </ol>
  </div>`;
}

function renderFailure(a) {
  app.innerHTML = `
  <div class="card state-card fade-in">
    <div class="ico">⚠️</div>
    <h2>Analiz alınmadı</h2>
    <p class="err">${esc(a.error || "Naməlum xəta")}</p>
    <ul>
      <li>Skan edilmiş PDF-dirsə, mətni “Mətn” bölməsinə əl ilə yapışdırın.</li>
      <li>Faylın PDF, DOCX və ya TXT olduğunu yoxlayın.</li>
      <li>Xidmət xətasıdırsa, bir neçə dəqiqə sonra yenidən cəhd edin.</li>
    </ul>
    <a class="btn btn-primary" href="#/">Yenidən yüklə</a>
  </div>`;
}

function renderResult(a) {
  const state = {
    filter: "all",
    selected: (a.clauses.find((c) => c.risk === "high") || a.clauses.find((c) => c.risk === "medium") || {}).id ?? null,
    editing: false,
  };
  const byId = (id) => a.clauses.find((c) => c.id === id);
  const laws = Object.fromEntries((a.laws || []).map((l) => [l.id, l]));
  // Highlight the points the explanation talks about ("688.2-yə əsasən" -> lines starting with "688.2.").
  const lawText = (art, c) => {
    const cited = [...`${c.explanation} ${c.suggestion || ""}`.matchAll(new RegExp(`\\b${art.id}\\.\\d+(?:\\.\\d+)*`, "g"))].map((m) => m[0]);
    return art.text.split("\n").map((line) => {
      const hit = cited.some((p) => line.startsWith(p + "."));
      return hit ? `<mark>${esc(line)}</mark>` : esc(line);
    }).join("\n");
  };
  const risky = () => a.clauses.filter((c) => c.risk !== "low");
  const counts = () => Object.fromEntries(Object.keys(RISK).map((r) => [r, a.clauses.filter((c) => c.risk === r).length]));

  app.innerHTML = `
  <div class="fade-in">
    <div class="result-head">
      <div>
        <span class="eyebrow">Analiz</span>
        <h1>${esc(a.filename)}</h1>
        <div class="meta">
          <span>🗓 ${fmtDate(a.created_at)}</span>
          <span>📑 ${a.clauses.length} bənd</span>
        </div>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" id="del" title="Müqaviləni serverdən sil">🗑 Sil</button>
        <a class="btn" href="#/">+ Yeni analiz</a>
      </div>
    </div>
    <div class="result-grid">
      <section class="card doc">
        <div class="doc-toolbar">
          <div class="chips" id="chips"></div>
          <span class="muted" style="font-size:13px">Bəndə klikləyin →</span>
        </div>
        <div class="doc-body">
          ${a.preamble ? `<div class="preamble">${esc(a.preamble)}</div>` : ""}
          <div id="clauses"></div>
        </div>
      </section>
      <aside class="side">
        <div class="card card-pad" id="summary"></div>
        <div class="card card-pad detail" id="detail"></div>
        <div class="card card-pad" id="export"></div>
      </aside>
    </div>
  </div>`;

  const $ = (s) => app.querySelector(s);

  function renderChips() {
    const c = counts();
    const items = [["all", "Hamısı", a.clauses.length, null], ...Object.entries(RISK).map(([k, v]) => [k, v.short, c[k], v.color])];
    $("#chips").innerHTML = items.map(([k, label, n, color]) => `
      <button class="chip ${state.filter === k ? "active" : ""}" data-f="${k}">
        ${color ? `<span class="sw" style="background:${color}"></span>` : ""}${label} <span class="n">${n}</span>
      </button>`).join("");
    app.querySelectorAll(".chip").forEach((b) => (b.onclick = () => { state.filter = b.dataset.f; renderChips(); renderClauses(); }));
  }

  function renderClauses() {
    $("#clauses").innerHTML = a.clauses.map((c) => {
      const dim = state.filter !== "all" && c.risk !== state.filter;
      const proposal = c.decision === "edited" ? c.user_text : c.decision === "accepted" ? c.suggestion : null;
      return `
      <article class="clause ${c.risk} ${c.id === state.selected ? "selected" : ""} ${dim ? "dim" : ""}" data-id="${c.id}" tabindex="0">
        <span class="num">${c.idx}.</span>
        <p><span class="hl">${esc(c.text)}</span>${(c.law_refs || []).map((r) => ` <span class="lawtag" title="Mülki Məcəllə, maddə ${esc(r)}">§ ${esc(r)}</span>`).join("")}</p>
        ${c.risk === "low" ? "" : `<span class="state ${c.decision}">${DECISION[c.decision] || `<span class="pill ${c.risk}">${RISK[c.risk].short}</span>`}</span>`}
        ${proposal ? `<div class="rewrite">${esc(proposal)}</div>` : ""}
      </article>`;
    }).join("");
    app.querySelectorAll(".clause").forEach((el) => {
      const pick = () => {
        state.selected = Number(el.dataset.id);
        state.editing = false;
        renderClauses(); renderDetail();
        if (window.innerWidth <= 980) $("#detail").scrollIntoView({ behavior: "smooth", block: "start" });
      };
      el.onclick = pick;
      el.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
    });
  }

  function renderSummary() {
    const c = counts(), total = a.clauses.length || 1;
    const r = risky(), reviewed = r.filter((x) => x.decision !== "pending").length;
    const verdict = c.high >= 3 ? ["Diqqətli olun", "Bir neçə ciddi risk var — imzalamazdan əvvəl danışın.", "var(--high)"]
      : c.high > 0 ? ["Danışıq tələb edir", "Ən azı bir ciddi bənd dəyişdirilməlidir.", "var(--med)"]
      : c.medium > 0 ? ["Əsasən normaldır", "Bir neçə bəndi dəqiqləşdirmək faydalı olar.", "var(--med)"]
      : ["Ciddi risk tapılmadı", "Bu hüquqi zəmanət deyil.", "var(--low)"];
    $("#summary").innerHTML = `
      <span class="eyebrow">Ümumi qiymət</span>
      <div class="score" style="margin-top:12px">
        <div class="ring" style="--p:${Math.round((r.length / total) * 100)};--ring-color:${verdict[2]}">
          <div><b>${r.length}</b><small>riskli</small></div>
        </div>
        <div class="verdict"><b>${verdict[0]}</b><span>${verdict[1]}</span></div>
      </div>
      <div class="bar">${Object.entries(RISK).map(([k, v]) => c[k] ? `<i style="width:${(c[k] / total) * 100}%;background:${v.color}"></i>` : "").join("")}</div>
      <div class="legend">${Object.entries(RISK).map(([k, v]) => `<span><i class="sw" style="background:${v.color}"></i>${v.short}: <b>${c[k]}</b></span>`).join("")}</div>
      ${a.summary ? `<p class="summary-text">${esc(a.summary)}</p>` : ""}
      ${r.length ? `<div class="review">Baxılıb: <b>${reviewed}</b> / ${r.length} riskli bənd<div class="track"><i style="width:${(reviewed / r.length) * 100}%"></i></div></div>`
        : `<div class="notice">✅ Riskli bənd tapılmadı. Vacib müqavilələrdə yenə də mütəxəssislə məsləhətləşin.</div>`}`;
  }

  function renderDetail() {
    const c = byId(state.selected);
    if (!c) {
      $("#detail").innerHTML = `<div class="empty-detail"><div class="big">👈</div>Ətraflı izah üçün soldan bəndə klikləyin.</div>`;
      return;
    }
    const r = risky(), pos = r.findIndex((x) => x.id === c.id);
    const proposal = c.decision === "edited" ? c.user_text : c.suggestion;
    $("#detail").innerHTML = `
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="pill ${c.risk}">● ${RISK[c.risk]?.label ?? "—"}</span>
        <span class="pill neutral">${esc(CATEGORY[c.category] || c.category || "")}</span>
      </div>
      <h3>Bənd ${c.idx}</h3>
      <div class="section">
        <div class="label">Niyə ${c.risk === "low" ? "normaldır" : "risklidir"}</div>
        <p>${esc(c.explanation)}</p>
      </div>
      ${(c.law_refs || []).filter((r) => laws[r]).length ? `
        <div class="section">
          <div class="label">Qanun · Mülki Məcəllə</div>
          ${c.law_refs.filter((r) => laws[r]).map((r, i) => `
            <details class="law" ${i === 0 ? "open" : ""}>
              <summary><span class="art">§ ${esc(r)}</span><span>${esc(laws[r].title)}</span></summary>
              <div class="law-text">${lawText(laws[r], c)}</div>
              <a class="law-link" href="${esc(laws[r].source_url)}" target="_blank" rel="noopener">e-qanun.az-da rəsmi mətn ↗</a>
            </details>`).join("")}
          <p class="law-note">Maddələr avtomatik seçilib. Mətn rəsmidir, amma bu hüquqi məsləhət deyil.</p>
        </div>` : ""}
      <div class="section">
        <div class="label">Hazırkı mətn</div>
        <div class="orig ${proposal && c.risk !== "low" ? "" : "keep"}">${esc(c.text)}</div>
      </div>
      ${c.risk === "low" ? "" : state.editing ? `
        <div class="section">
          <div class="label">Öz variantınız</div>
          <textarea class="input" id="edit">${esc(c.user_text || c.suggestion || c.text)}</textarea>
          <div class="actions" style="grid-template-columns:1fr 1fr">
            <button class="btn" id="cancel">Ləğv et</button>
            <button class="btn btn-primary" id="save">Yadda saxla</button>
          </div>
        </div>` : `
        ${proposal ? `<div class="section"><div class="label">${c.decision === "edited" ? "Sizin variant" : "Təklif olunan mətn"}</div><div class="proposal">${esc(proposal)}</div></div>` : ""}
        <div class="actions">
          <button class="btn sm ${c.decision === "accepted" ? "btn-accept" : ""}" id="accept" ${c.suggestion ? "" : "disabled"}>✓ Qəbul</button>
          <button class="btn sm ${c.decision === "edited" ? "btn-accept" : ""}" id="editbtn">✎ Redaktə</button>
          <button class="btn sm btn-reject" id="reject">✕ Rədd</button>
        </div>`}
      ${r.length > 1 && pos >= 0 ? `
        <div class="nav-row">
          <button class="btn btn-ghost sm" id="prev" ${pos === 0 ? "disabled" : ""}>← Əvvəlki</button>
          <span class="muted" style="font-size:13px;align-self:center">${pos + 1} / ${r.length}</span>
          <button class="btn btn-ghost sm" id="next" ${pos === r.length - 1 ? "disabled" : ""}>Növbəti →</button>
        </div>` : ""}`;

    app.querySelectorAll(".law-text").forEach((box) => {
      const m = box.querySelector("mark");
      if (m) box.scrollTop = m.offsetTop - 8; // .law-text is position:relative, so offsetTop is inside the box
    });
    const on = (id, fn) => { const el = $("#" + id); if (el) el.onclick = fn; };
    on("accept", () => decide(c, "accepted"));
    on("reject", () => decide(c, "rejected"));
    on("editbtn", () => { state.editing = true; renderDetail(); $("#edit").focus(); });
    on("cancel", () => { state.editing = false; renderDetail(); });
    on("save", () => decide(c, "edited", $("#edit").value));
    on("prev", () => { state.selected = r[pos - 1].id; state.editing = false; renderClauses(); renderDetail(); });
    on("next", () => { state.selected = r[pos + 1].id; state.editing = false; renderClauses(); renderDetail(); });
  }

  async function decide(c, decision, userText) {
    if (decision === "edited" && !userText?.trim()) return toast("Mətn boş ola bilməz.", "error");
    try {
      const updated = await (await api(`/analyses/${a.id}/clauses/${c.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, user_text: userText ?? null }),
      })).json();
      Object.assign(c, updated);
      state.editing = false;
      // jump to the next clause that still needs a decision
      const next = risky().find((x) => x.decision === "pending");
      if (decision !== "rejected" && next) state.selected = next.id;
      renderClauses(); renderSummary(); renderDetail();
      toast(decision === "rejected" ? "Bənd olduğu kimi saxlanıldı" : "Yadda saxlanıldı ✓");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function renderExport() {
    $("#export").innerHTML = `
      <span class="eyebrow">Nəticə</span>
      <div class="export" style="margin-top:12px">
        <button class="btn btn-primary" id="msg">📨 Danışıq mesajını göstər</button>
        <a class="btn" href="/analyses/${a.id}/report.md" download="kiraye_analiz_${a.id}.md">⬇️ Hesabatı yüklə (.md)</a>
      </div>
      <div class="cost-row">
        <span>${a.latency_ms ? `⏱ ${(a.latency_ms / 1000).toFixed(0)} san` : ""}</span>
        <span>${a.cost_usd != null ? `💲 ${a.cost_usd.toFixed(3)} USD` : ""}</span>
      </div>`;
    $("#msg").onclick = async () => {
      try {
        const text = await (await api(`/analyses/${a.id}/message`)).text();
        const m = openModal("Ev sahibinə mesaj", `
          <div class="message-box">${esc(text)}</div>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="btn" data-close>Bağla</button>
            <button class="btn btn-primary" id="copy">📋 Kopyala</button>
          </div>`);
        m.querySelector("#copy").onclick = async () => {
          try { await navigator.clipboard.writeText(text); toast("Mesaj kopyalandı ✓"); }
          catch { toast("Kopyalamaq olmadı — mətni əl ilə seçin.", "error"); }
        };
      } catch (e) {
        toast(e.message, "error");
      }
    };
  }

  $("#del").onclick = () => {
    const m = openModal("Analizi silmək?", `
      <p>Müqavilənin mətni, analiz və bütün qərarlarınız serverdən birdəfəlik silinəcək.</p>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
        <button class="btn" data-close>Ləğv et</button>
        <button class="btn btn-reject" id="confirm-del">🗑 Sil</button>
      </div>`);
    m.querySelector("#confirm-del").onclick = async () => {
      try {
        await api(`/analyses/${a.id}`, { method: "DELETE" });
        saved.remove(a.id);
        toast("Analiz silindi");
        location.hash = "#/history";
      } catch (e) {
        toast(e.message, "error");
      }
    };
  };

  renderChips(); renderClauses(); renderSummary(); renderDetail(); renderExport();
}

/* =========================================================
   HISTORY
   ========================================================= */
async function showHistory() {
  app.innerHTML = `
  <div class="fade-in">
    <div class="page-head">
      <div><span class="eyebrow">Tarixçə</span><h1>Əvvəlki analizlər</h1></div>
      <a class="btn btn-primary" href="#/">+ Yeni analiz</a>
    </div>
    <div id="list"><p class="muted">Yüklənir...</p></div>
  </div>`;
  const list = app.querySelector("#list");
  try {
    const ids = saved.ids();
    const rows = ids.length ? await (await api(`/analyses?ids=${ids.map(encodeURIComponent).join(",")}`)).json() : [];
    saved.set(ids.filter((id) => rows.some((r) => r.id === id))); // forget deleted / expired ones
    if (!rows.length) {
      list.innerHTML = `<div class="card empty"><div class="big">🗂️</div><p>Bu brauzerdə hələ analiz yoxdur.</p><p style="margin-top:14px"><a class="btn btn-primary" href="#/">İlk müqaviləni yoxla</a></p></div>`;
      return;
    }
    const pill = { done: ["low", "Hazır"], failed: ["high", "Xəta"] };
    list.innerHTML = `<div class="hist-grid">${rows.map((r) => {
      const [cls, label] = pill[r.status] || ["medium", "Gedir..."];
      return `
      <a class="card hist" href="#/a/${r.id}">
        <div class="top"><b>📄 ${esc(r.filename)}</b><span class="pill ${cls}">${label}</span></div>
        <p>${esc(r.summary || r.error || "Analiz davam edir...")}</p>
        <small>${fmtDate(r.created_at)}</small>
      </a>`;
    }).join("")}</div>`;
  } catch (e) {
    list.innerHTML = `<div class="card empty"><div class="big">⚠️</div><p>${esc(e.message)}</p></div>`;
  }
}

route();
