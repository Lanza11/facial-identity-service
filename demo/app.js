// Consumidor de ejemplo del facial-identity-service: simula lo que haría la app móvil o el
// web administrativo. Solo usa la API pública /v1 (nunca CompreFace directamente).

const $ = (selector) => document.querySelector(selector);
const state = { image: null, subjects: [] };

const DECISION_LABEL = {
  MATCH: ["Coincide", "badge-ok"],
  NO_MATCH: ["No coincide", "badge-bad"],
  INCONCLUSIVE: ["No concluyente", "badge-warn"],
};
const ACTION_LABEL = {
  SUBJECT_CREATED: "Persona creada",
  FACE_ENROLLED: "Rostro registrado",
  FACE_VERIFIED: "Verificación 1:1",
  FACE_IDENTIFIED: "Identificación 1:N",
  SUBJECT_DEACTIVATED: "Desactivada",
  SUBJECT_REACTIVATED: "Reactivada",
  SUBJECT_DELETED: "Eliminada",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "x-api-key": $("#api-key").value, ...(options.headers || {}) },
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) throw { status: response.status, body };
  return body;
}

function imageForm() {
  if (!state.image) throw { body: { slug: "SIN_FOTO", title: "Primero captura o sube una foto" } };
  const form = new FormData();
  form.append("image", state.image, "captura.jpg");
  return form;
}

function showResult(html, json) {
  $("#result").hidden = false;
  $("#result-summary").innerHTML = html;
  $("#result-json").textContent = JSON.stringify(json, null, 2);
}

function showError(error) {
  const body = error.body || { title: String(error) };
  showResult(
    `<div class="verdict"><span class="badge badge-bad">${escapeHtml(body.slug || "ERROR")}</span>
     <span>${escapeHtml(body.title || "")}</span></div>
     ${body.detail && body.detail !== body.title ? `<p class="muted">${escapeHtml(body.detail)}</p>` : ""}`,
    body,
  );
}

function decisionHtml(decision, score, extra = "") {
  const [label, css] = DECISION_LABEL[decision] || [decision, "badge-muted"];
  const scoreHtml = score === undefined ? "" :
    `<span class="muted">similitud ${(score * 100).toFixed(1)}%</span>
     </div><div class="score-bar"><span style="width:${Math.round(score * 100)}%"></span>`;
  return `<div class="verdict"><span class="badge ${css}">${label}</span>${extra}${scoreHtml}</div>`;
}

async function run(action) {
  try {
    await action();
  } catch (error) {
    showError(error);
  }
  await Promise.all([loadSubjects(), loadAudit()]);
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 960, facingMode: "user" },
    });
    $("#video").srcObject = stream;
    $("#btn-capture").disabled = false;
    $("#btn-camera").textContent = "Cámara encendida";
    $("#btn-camera").disabled = true;
  } catch (error) {
    showError({ body: { slug: "CAMARA", title: "No se pudo acceder a la cámara", detail: String(error) } });
  }
}

function capture() {
  const video = $("#video");
  const canvas = $("#canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  canvas.toBlob(setImage, "image/jpeg", 0.9);
}

function setImage(blob) {
  state.image = blob;
  const img = $("#snapshot");
  img.src = URL.createObjectURL(blob);
  img.hidden = false;
  $("#snapshot-empty").hidden = true;
}

async function createSubject(event) {
  event.preventDefault();
  const form = event.target;
  await run(async () => {
    const subject = await api("/v1/subjects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        externalId: form.externalId.value.trim(),
        displayName: form.displayName.value.trim(),
      }),
    });
    form.reset();
    showResult(
      `<div class="verdict"><span class="badge badge-ok">Persona creada</span>
       <span>${escapeHtml(subject.displayName)}</span></div>
       <p class="muted">Ahora registra su rostro con la foto capturada.</p>`,
      subject,
    );
    state.selected = subject.subjectId;
  });
}

const enroll = () => run(async () => {
  const subjectId = $("#enroll-subject").value;
  const result = await api(`/v1/subjects/${subjectId}/enrollments`, { method: "POST", body: imageForm() });
  const name = subjectName(subjectId);
  showResult(
    `<div class="verdict"><span class="badge badge-ok">Rostro registrado</span><span>${escapeHtml(name)}</span></div>`,
    result,
  );
});

const verify = () => run(async () => {
  const subjectId = $("#verify-subject").value;
  const result = await api(`/v1/subjects/${subjectId}/verifications`, { method: "POST", body: imageForm() });
  showResult(
    decisionHtml(result.decision, result.score, `<span>¿Es ${escapeHtml(subjectName(subjectId))}?</span>`),
    result,
  );
});

const identify = () => run(async () => {
  const result = await api("/v1/identifications", { method: "POST", body: imageForm() });
  const best = result.candidates[0];
  const who = best ? `<span>${escapeHtml(best.displayName)} <span class="muted">(${escapeHtml(best.externalId)})</span></span>` :
    `<span class="muted">Ninguna persona registrada coincide</span>`;
  showResult(decisionHtml(result.decision, best?.score, who), result);
});

function subjectAction(subjectId, action) {
  if (action === "delete" && !confirm("¿Eliminar la persona y todos sus rostros? (supresión total)")) return;
  run(async () => {
    const result = action === "delete"
      ? await api(`/v1/subjects/${subjectId}`, { method: "DELETE" })
      : await api(`/v1/subjects/${subjectId}/${action}`, { method: "POST" });
    const label = { delete: "Eliminada", deactivate: "Desactivada", reactivate: "Reactivada" }[action];
    showResult(`<div class="verdict"><span class="badge badge-muted">${label}</span></div>`, result ?? { deleted: subjectId });
  });
}

function subjectName(subjectId) {
  return state.subjects.find((s) => s.subjectId === subjectId)?.displayName ?? subjectId;
}

async function loadSubjects() {
  try {
    state.subjects = await api("/v1/subjects");
  } catch {
    state.subjects = [];
  }
  renderSubjectSelects();
  renderSubjectsTable();
}

function renderSubjectSelects() {
  document.querySelectorAll(".subject-select").forEach((select) => {
    const previous = state.selected || select.value;
    select.innerHTML = state.subjects.length
      ? state.subjects.map((s) =>
          `<option value="${s.subjectId}">${escapeHtml(s.displayName)} · ${escapeHtml(s.externalId)}` +
          `${s.status === "INACTIVE" ? " (inactiva)" : ""} · ${s.enrollments} rostro(s)</option>`).join("")
      : `<option value="">— crea una persona primero —</option>`;
    if (state.subjects.some((s) => s.subjectId === previous)) select.value = previous;
  });
  state.selected = null;
}

function renderSubjectsTable() {
  $("#subjects-body").innerHTML = state.subjects.map((s) => {
    const active = s.status === "ACTIVE";
    const locked = s.lockedUntil && new Date(s.lockedUntil) > new Date();
    return `<tr>
      <td>${escapeHtml(s.displayName)}</td>
      <td>${escapeHtml(s.externalId)}</td>
      <td><span class="badge ${active ? "badge-ok" : "badge-muted"}">${active ? "Activa" : "Inactiva"}</span>
          ${locked ? '<span class="badge badge-warn">Bloqueada</span>' : ""}</td>
      <td>${s.enrollments}</td>
      <td>${s.failedAttempts}</td>
      <td class="actions-cell">
        <button class="small secondary" data-id="${s.subjectId}" data-action="${active ? "deactivate" : "reactivate"}">
          ${active ? "Desactivar" : "Reactivar"}</button>
        <button class="small danger" data-id="${s.subjectId}" data-action="delete">Eliminar</button>
      </td></tr>`;
  }).join("") || `<tr><td colspan="6" class="muted">Sin personas registradas.</td></tr>`;
}

async function loadAudit() {
  let events = [];
  try {
    events = await api("/v1/audit?limit=50");
  } catch {
    /* sin API key válida no hay auditoría que mostrar */
  }
  $("#audit-body").innerHTML = events.map((e) => {
    const ok = ["OK", "MATCH"].includes(e.outcome);
    const warn = e.outcome === "INCONCLUSIVE";
    return `<tr>
      <td>${new Date(e.occurredAt).toLocaleTimeString()}</td>
      <td>${ACTION_LABEL[e.action] || e.action}</td>
      <td><span class="badge ${ok ? "badge-ok" : warn ? "badge-warn" : "badge-bad"}">${escapeHtml(e.outcome)}</span></td>
      <td>${escapeHtml(e.subjectId ? subjectName(e.subjectId) : "—")}</td>
      <td class="hash">${escapeHtml(e.detail)} ${e.imageSha256 ? `img:${e.imageSha256.slice(0, 10)}…` : ""}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="5" class="muted">Sin eventos.</td></tr>`;
}

async function loadHealth() {
  try {
    const health = await fetch("/health").then((r) => r.json());
    const badge = $("#engine-badge");
    badge.textContent = `motor: ${health.engine} · ${health.engineStatus}`;
    badge.className = `badge ${health.engineStatus === "UP" ? "badge-ok" : "badge-bad"}`;
  } catch {
    $("#engine-badge").textContent = "servicio no disponible";
  }
}

function selectTab(tab) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.dataset.panel !== tab));
  $("#result").hidden = true;
}

$("#btn-camera").addEventListener("click", startCamera);
$("#btn-capture").addEventListener("click", capture);
$("#file-input").addEventListener("change", (e) => e.target.files[0] && setImage(e.target.files[0]));
$("#form-subject").addEventListener("submit", createSubject);
$("#btn-enroll").addEventListener("click", enroll);
$("#btn-verify").addEventListener("click", verify);
$("#btn-identify").addEventListener("click", identify);
$("#subjects-body").addEventListener("click", (e) => {
  const button = e.target.closest("button[data-action]");
  if (button) subjectAction(button.dataset.id, button.dataset.action);
});
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
$("#api-key").addEventListener("change", () => Promise.all([loadSubjects(), loadAudit()]));

loadHealth();
loadSubjects().then(loadAudit);
