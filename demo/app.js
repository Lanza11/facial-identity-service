// Demo del servicio de identificación facial: tres escenarios del negocio + modo técnico.
// Solo consume la API pública /v1; toda decisión (umbrales, bloqueos, reglas) es del backend.

import { api, ApiError, getApiKey, onApiCall, setApiKey } from "./api.js";
import { FaceCheck, STEPS, preloadLandmarker } from "./liveness.js";
import { getPhoto, removePhoto, savePhoto } from "./photos.js";

const view = document.querySelector("#view");
const TECH_STORAGE = "fis-demo-tech";
let leaveView = () => {};
let preferredSubjectId = null;

const API_MESSAGES = {
  NO_FACE: ["No vemos un rostro en la foto", "Prueba con más luz, mirando de frente a la cámara."],
  MULTIPLE_FACES: ["Aparece más de una persona", "Asegúrate de que solo haya una persona frente a la cámara."],
  SUBJECT_INACTIVE: ["Este cliente está desactivado", "Reactívalo para poder usar su rostro."],
  SUBJECT_LOCKED: [
    "Bloqueado por seguridad",
    "Hubo varios intentos fallidos seguidos. El cliente podrá intentarlo de nuevo en unos minutos.",
  ],
  MAX_ENROLLMENTS: ["Ya tiene suficientes fotos", "Este cliente alcanzó el máximo de fotos registradas."],
  NO_ENROLLMENTS: ["Aún no tiene su rostro registrado", "Regístralo primero en el escenario Nuevo cliente."],
  CONSENT_REQUIRED: ["Falta la autorización", "El cliente debe autorizar el uso de su rostro antes de registrarlo."],
  SUBJECT_ALREADY_EXISTS: ["Ese cliente ya existe", "Ya hay un cliente registrado con esa identificación."],
  ENGINE_UNAVAILABLE: [
    "El reconocimiento no está disponible",
    "Revisa que el servicio y CompreFace estén encendidos (docker compose up -d).",
  ],
  UNAUTHORIZED: ["Clave de acceso inválida", "Revisa la API key en el modo técnico."],
};

const LIVENESS_MESSAGES = {
  NO_FACE: "No logramos ver un rostro a tiempo.",
  NO_FRAMING: "No logramos centrar el rostro a tiempo.",
  NO_BLINK: "No detectamos un parpadeo.",
  NO_TURN: "No detectamos el giro de cabeza.",
  NO_FRONT: "No volviste a mirar al frente a tiempo.",
};

const AUDIT_LABELS = {
  SUBJECT_CREATED: "Cliente creado",
  CONSENT_GRANTED: "Autorización registrada",
  FACE_ENROLLED: "Rostro registrado",
  FACE_VERIFIED: "Verificación",
  FACE_IDENTIFIED: "Identificación",
  SUBJECT_DEACTIVATED: "Cliente desactivado",
  SUBJECT_REACTIVATED: "Cliente reactivado",
  SUBJECT_DELETED: "Cliente eliminado",
};

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const percent = (score) => Math.round((score ?? 0) * 100);
const firstName = (name) => String(name ?? "").trim().split(/\s+/)[0];
const brandMark = `<svg class="brand-mark" viewBox="0 0 40 40" aria-hidden="true"><ellipse cx="20" cy="20" rx="13" ry="16" fill="none" stroke="currentColor" stroke-width="3.2"/><path d="M13.5 23.5c3.6 3.4 9.4 3.4 13 0" fill="none" stroke="var(--mango)" stroke-width="3.2" stroke-linecap="round"/><circle cx="15.5" cy="16.5" r="2" fill="currentColor"/><circle cx="24.5" cy="16.5" r="2" fill="currentColor"/></svg>`;

function describeError(error) {
  if (error instanceof ApiError) {
    const [title, text] = API_MESSAGES[error.slug] ?? ["Algo salió mal", error.body.detail ?? error.message];
    return { title, text };
  }
  if (error?.name === "NotAllowedError") {
    return { title: "Sin permiso para la cámara", text: "Autoriza el uso de la cámara en el navegador e inténtalo de nuevo." };
  }
  if (error?.name === "NotFoundError") {
    return { title: "No encontramos una cámara", text: "Conecta una cámara o, en modo técnico, usa una foto." };
  }
  return {
    title: "No pudimos preparar la cámara",
    text: "Revisa la conexión o descarga la prueba de vida con scripts/fetch_mediapipe.py.",
  };
}

function errorBox(error) {
  const { title, text } = describeError(error);
  return `<div class="error-box" role="alert"><strong>${esc(title)}</strong><span>${esc(text)}</span></div>`;
}

function narrationMarkup(steps) {
  return `<ol>${steps
    .map(([title, text]) => `<li><div><strong>${esc(title)}</strong>${esc(text)}</div></li>`)
    .join("")}</ol>`;
}

function setNarration(index) {
  view.querySelectorAll(".narration li").forEach((li, i) => {
    li.classList.toggle("done", i < index);
    li.classList.toggle("active", i === index);
  });
}

function scenarioLayout({ number, title, lead, steps, device }) {
  return `
    <a class="back" href="#inicio">← Volver a los escenarios</a>
    <header class="scenario-head">
      <div class="eyebrow">Escenario ${number} de 3</div>
      <h1>${title}</h1>
      <p class="lead">${lead}</p>
    </header>
    <div class="stage">
      <aside class="narration" aria-label="Qué está pasando">
        <div class="eyebrow">Qué está pasando</div>
        ${narrationMarkup(steps)}
      </aside>
      <div class="device">${device}</div>
    </div>`;
}

const STEP_LABELS = { position: "Te vemos", blink: "Parpadeo", turn: "Giro", front: "Listo" };

function cameraMarkup() {
  return `
    <div class="cam" data-state="idle">
      <video playsinline muted></video>
      <div class="cam-oval"></div>
      <div class="cam-loading">Preparando la cámara…</div>
      <div class="cam-hint" aria-live="polite"></div>
      <ul class="cam-steps">${STEPS.map((s) => `<li data-step="${s}">${STEP_LABELS[s]}</li>`).join("")}</ul>
      <pre class="cam-debug tech-only"></pre>
    </div>
    <div class="actions tech-only">
      <label class="btn quiet small">Usar una foto (sin prueba de vida)
        <input type="file" accept="image/*" hidden data-photo-input>
      </label>
    </div>`;
}

function paintCamera(cam, update) {
  cam.dataset.state = update.ok ? "good" : "guiding";
  cam.querySelector(".cam-hint").textContent = update.hint ?? "";
  const current = STEPS.indexOf(update.step);
  cam.querySelectorAll(".cam-steps li").forEach((li, i) => {
    li.classList.toggle("done", i < current);
    li.classList.toggle("active", i === current);
    if (li.dataset.step === "turn") li.textContent = `Giro a la ${update.direction}`;
  });
  const m = update.metrics ?? {};
  cam.querySelector(".cam-debug").textContent = [
    `rostros  ${m.faces ?? 0}`,
    `parpadeo ${(m.blink ?? 0).toFixed(2)}`,
    `giro     ${(m.turn ?? 0).toFixed(2)}`,
    `ancho    ${(m.width ?? 0).toFixed(2)}`,
    `centro   ${(m.centerX ?? 0).toFixed(2)}, ${(m.centerY ?? 0).toFixed(2)}`,
  ].join("\n");
}

/**
 * Muestra la cámara en `host`, ejecuta la prueba de vida y devuelve
 * { passed, reason, blob, thumbnail, liveness }. Lanza error si la cámara no está disponible.
 */
function captureWithLiveness(host, { timeoutMs = 30000 } = {}) {
  host.innerHTML = cameraMarkup();
  const cam = host.querySelector(".cam");
  cam.scrollIntoView({ behavior: "smooth", block: "center" });
  const check = new FaceCheck(cam, { onUpdate: (update) => paintCamera(cam, update) });
  let settled = false;

  return new Promise((resolve, reject) => {
    const done = (result) => {
      if (settled) return;
      settled = true;
      check.close();
      resolve(result);
    };
    const previousLeave = leaveView;
    leaveView = () => {
      settled = true;
      check.close();
      previousLeave();
    };
    host.querySelector("[data-photo-input]").addEventListener("change", async (event) => {
      const file = event.target.files[0];
      if (file) done({ passed: true, reason: null, blob: file, thumbnail: await fileThumbnail(file), liveness: "NOT_PERFORMED" });
    });
    check
      .open()
      .then(async () => {
        cam.querySelector(".cam-loading").hidden = true;
        const result = await check.run({ timeoutMs });
        cam.dataset.state = result.passed ? "good" : "failed";
        done({ ...result, liveness: result.passed ? "PASSED" : "FAILED" });
      })
      .catch((error) => {
        if (settled) return;
        check.close();
        if (document.body.classList.contains("tech")) {
          // En modo técnico se puede seguir con una foto subida (sin prueba de vida).
          const { title, text } = describeError(error);
          cam.querySelector(".cam-loading").textContent = `${title}. ${text} Puedes usar una foto.`;
          return;
        }
        settled = true;
        reject(error);
      });
  });
}

function fileThumbnail(file) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 320;
      canvas.height = Math.round((image.height / image.width) * 320);
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(image.src);
      resolve(canvas.toDataURL("image/jpeg", 0.8));
    };
    image.src = URL.createObjectURL(file);
  });
}

function compareMarkup(registered, current, score, tone) {
  const photo = (src, caption) =>
    `<figure>${src ? `<img src="${src}" alt="${esc(caption)}">` : `<div class="no-photo">Foto no disponible en este equipo</div>`}<figcaption>${esc(caption)}</figcaption></figure>`;
  const ring =
    score === null
      ? `<div></div>`
      : `<div class="score-ring ${tone}" style="--value:${percent(score)}" role="img" aria-label="Similitud ${percent(score)}%"><span>${percent(score)}%</span></div>`;
  return `<div class="compare">${photo(registered, "Foto registrada")}${ring}${photo(current, "Foto de ahora")}</div>`;
}

function verdictMarkup(kind, title, text) {
  const icon = { ok: "✓", bad: "✕", warn: "?" }[kind];
  return `<div class="verdict ${kind}"><div class="verdict-icon" aria-hidden="true">${icon}</div><h3>${title}</h3><p>${text}</p></div>`;
}

/** Si la persona no parpadeó o no giró, lo más probable es una foto o una pantalla. */
function livenessFailureMarkup(reason) {
  const detail = esc(LIVENESS_MESSAGES[reason] ?? "No completamos la prueba de vida.");
  if (reason === "NO_BLINK" || reason === "NO_TURN") {
    return verdictMarkup("bad", "No detectamos a una persona real", `${detail} Por seguridad no damos acceso.`);
  }
  return verdictMarkup("warn", "Intentémoslo otra vez", detail);
}

const toneOf = (decision) => ({ MATCH: "ok", NO_MATCH: "bad", INCONCLUSIVE: "warn" })[decision] ?? "warn";

async function verifiableSubjects() {
  const subjects = await api.listSubjects();
  return subjects.filter((s) => s.status === "ACTIVE" && s.enrollments > 0);
}

function subjectOptions(subjects) {
  const selected = subjects.some((s) => s.subjectId === preferredSubjectId) ? preferredSubjectId : subjects[0]?.subjectId;
  return subjects
    .map((s) => `<option value="${s.subjectId}" ${s.subjectId === selected ? "selected" : ""}>${esc(s.displayName)}</option>`)
    .join("");
}

function noSubjectsMarkup() {
  return `<div class="panel"><p>Primero registra al menos un cliente con su rostro.</p>
    <div class="actions"><a class="btn" href="#nuevo-cliente">Ir a Nuevo cliente</a></div></div>`;
}

function renderHome() {
  view.innerHTML = `
    <section class="hero">
      <div class="eyebrow">Demostración</div>
      <h1>Tu rostro confirma que eres tú</h1>
      <p class="lead">Registramos el rostro del cliente una sola vez. Desde ahí, en segundos y con una foto, sabemos si quien está al otro lado es realmente quien dice ser.</p>
    </section>
    <section class="scenario-grid" aria-label="Escenarios">
      ${scenarioCard("nuevo-cliente", "Nuevo cliente", "Asesor en sede · al firmar el crédito", "El cliente autoriza el uso de su rostro y lo registramos en segundos.")}
      ${scenarioCard("titular", "¿Es realmente quien dice ser?", "Al ingresar al sistema · app o web", "Antes de dar acceso, su rostro confirma que quien entra es esa persona.")}
      ${scenarioCard("quien-es", "¿Quién es este cliente?", "Asesor en sede · cliente sin documento", "Lo reconocemos entre todos los clientes registrados.")}
    </section>
    <aside class="privacy-note">
      <p><strong>Las fotos no se guardan.</strong> El servicio conserva solo una huella numérica del rostro, y únicamente con la autorización del cliente. El cliente puede pedir que se elimine cuando quiera.</p>
    </aside>`;
}

function scenarioCard(hash, title, who, text) {
  return `<a class="scenario-card" href="#${hash}">
    <h2>${title}</h2><span class="who">${who}</span><p>${text}</p><span class="go">Empezar →</span></a>`;
}

function renderEnroll() {
  view.innerHTML = scenarioLayout({
    number: 1,
    title: "Nuevo cliente",
    lead: "Al firmar el crédito, el asesor registra el rostro del cliente. Solo se hace una vez.",
    steps: [
      ["Datos del cliente", "El asesor busca o crea al cliente en el sistema."],
      ["Autorización", "El cliente acepta el uso de su rostro. Queda registrado, como pide la Ley 1581."],
      ["Prueba de vida", "Parpadea y gira la cabeza: así sabemos que es una persona real."],
      ["Listo", "Desde ahora su rostro sirve para confirmar su identidad."],
    ],
    device: `<div class="panel" id="enroll-panel"></div>`,
  });
  const panel = view.querySelector("#enroll-panel");
  const head = (step) => `<div class="panel-head"><span class="who">Pantalla del asesor</span><span class="badge">Paso ${step} de 4</span></div>`;

  const showData = (error) => {
    setNarration(0);
    panel.innerHTML = `${head(1)}
      <h2>¿A quién vamos a registrar?</h2>
      <form class="form-grid" id="subject-form">
        <label class="field" for="f-name">Nombre completo<input id="f-name" name="name" required autocomplete="off" placeholder="Ana Pérez"></label>
        <label class="field" for="f-id">Identificación del cliente<input id="f-id" name="externalId" required autocomplete="off" placeholder="CL-1001"></label>
        <div class="actions"><button class="btn" type="submit">Continuar</button></div>
      </form>
      ${error ? errorBox(error) : ""}`;
    panel.querySelector("#subject-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target;
      form.querySelector("button").disabled = true;
      try {
        const subject = await api.createSubject(form.externalId.value.trim(), form.name.value.trim());
        showConsent(subject);
      } catch (error) {
        showData(error);
      }
    });
    panel.querySelector("#f-name").focus();
  };

  const showConsent = (subject, error) => {
    setNarration(1);
    panel.innerHTML = `${head(2)}
      <h2>${esc(firstName(subject.displayName))}, ¿nos autorizas?</h2>
      <div class="consent-box">
        <p>Autorizo a Motos del Caribe a guardar una representación numérica de mi rostro (no la foto) para confirmar mi identidad en sus canales. Puedo pedir que se elimine en cualquier momento.</p>
        <label class="check" for="consent-check"><input id="consent-check" type="checkbox"> Sí, autorizo el uso de mi rostro</label>
      </div>
      <div class="actions"><button class="btn" id="consent-btn" disabled>Registrar autorización</button></div>
      ${error ? errorBox(error) : ""}`;
    const check = panel.querySelector("#consent-check");
    const button = panel.querySelector("#consent-btn");
    check.addEventListener("change", () => (button.disabled = !check.checked));
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api.recordConsent(subject.subjectId, "sede");
        showCapture(subject);
      } catch (error) {
        showConsent(subject, error);
      }
    });
  };

  const showCapture = async (subject) => {
    setNarration(2);
    panel.innerHTML = `${head(3)}
      <h2>Mira a la cámara, ${esc(firstName(subject.displayName))}</h2>
      <div id="cam-host"></div>`;
    try {
      const capture = await captureWithLiveness(panel.querySelector("#cam-host"));
      if (!capture.passed) {
        showCaptureFailed(subject, capture);
        return;
      }
      await api.enroll(subject.subjectId, capture.blob, capture.liveness);
      savePhoto(subject.subjectId, capture.thumbnail);
      showDone(subject, capture);
    } catch (error) {
      showRetry(subject, error);
    }
  };

  const showRetry = (subject, error) => {
    panel.innerHTML = `${head(3)}${errorBox(error)}
      <div class="actions"><button class="btn" id="retry">Intentar de nuevo</button></div>`;
    panel.querySelector("#retry").addEventListener("click", () => showCapture(subject));
  };

  const showCaptureFailed = (subject, capture) => {
    panel.innerHTML = `${head(3)}
      ${verdictMarkup("warn", "Intentémoslo otra vez", esc(LIVENESS_MESSAGES[capture.reason] ?? "No completamos la prueba de vida."))}
      <div class="actions"><button class="btn" id="retry">Intentar de nuevo</button></div>`;
    panel.querySelector("#retry").addEventListener("click", () => showCapture(subject));
  };

  const showDone = (subject, capture) => {
    setNarration(4);
    preferredSubjectId = subject.subjectId;
    panel.innerHTML = `${head(4)}
      <div class="result">
        ${verdictMarkup("ok", `¡Listo! ${esc(firstName(subject.displayName))} ya tiene su rostro registrado`, "Desde ahora su rostro sirve para confirmar su identidad.")}
        <div class="compare" style="grid-template-columns:1fr;max-width:180px"><figure><img src="${capture.thumbnail}" alt="Foto registrada"><figcaption>Foto registrada (solo en este equipo)</figcaption></figure></div>
        <div class="actions"><a class="btn" href="#titular">Probar: ¿es el titular?</a><button class="btn ghost" id="another">Registrar otro cliente</button></div>
      </div>`;
    panel.querySelector("#another").addEventListener("click", () => showData());
  };

  showData();
}

function phoneMarkup(content) {
  return `<div class="phone"><div class="phone-screen">
      <div class="app-bar">${brandMark}<span>Ingreso</span></div>
      <div class="app-body center" id="app-body">${content}</div>
    </div></div>`;
}

function appHome(subject) {
  return `
    <div class="greeting">Hola, ${esc(firstName(subject.displayName))}</div>
    <div class="app-card"><small>Para ingresar al sistema</small><span>Confirma que eres tú con tu rostro. Sin contraseñas.</span></div>
    <button class="btn mango" id="login">Ingresar con mi rostro</button>`;
}

async function renderPhoneScenario(config) {
  view.innerHTML = scenarioLayout({
    number: config.number,
    title: config.title,
    lead: config.lead,
    steps: config.steps,
    device: `<div class="who-select" id="who"></div><div id="phone-host"></div><p class="device-caption">${config.caption}</p>`,
  });
  let subjects;
  try {
    subjects = await verifiableSubjects();
  } catch (error) {
    view.querySelector("#phone-host").innerHTML = errorBox(error);
    return;
  }
  if (!subjects.length) {
    view.querySelector("#phone-host").innerHTML = noSubjectsMarkup();
    return;
  }
  view.querySelector("#who").innerHTML = `<label for="who-select">${config.whoLabel}</label><select id="who-select">${subjectOptions(subjects)}</select>`;
  const select = view.querySelector("#who-select");
  const start = () => {
    const subject = subjects.find((s) => s.subjectId === select.value);
    preferredSubjectId = subject.subjectId;
    showAppHome(subject);
  };
  const showAppHome = (subject) => {
    leaveView();
    setNarration(0);
    view.querySelector("#phone-host").innerHTML = phoneMarkup(appHome(subject));
    view.querySelector("#login").addEventListener("click", () => config.onStart(subject, body(), () => showAppHome(subject)));
  };
  const body = () => view.querySelector("#app-body");
  select.addEventListener("change", start);
  start();
}

function renderVerify() {
  renderPhoneScenario({
    number: 2,
    title: "¿Es realmente quien dice ser?",
    lead: "Al ingresar al sistema, el rostro confirma que quien entra es realmente esa persona. Sirve igual para la app o para el web administrativo.",
    whoLabel: "Persona que intenta ingresar:",
    caption: "Simulación de la pantalla de ingreso.",
    steps: [
      ["La persona quiere ingresar", "Abre el sistema y elige entrar con su rostro."],
      ["El sistema pide confirmar su identidad", "Una sola foto, sin contraseñas."],
      ["Prueba de vida", "Parpadea y gira la cabeza: una foto no puede hacerlo."],
      ["Comparación", "Se compara con el rostro que registró."],
    ],
    onStart: (subject, body, restart) => verifyFlow(subject, body, restart),
  });
}

async function verifyFlow(subject, body, restart) {
  setNarration(1);
  body.classList.remove("center");
  body.innerHTML = `<div class="greeting" style="font-size:1.25rem">Mira a la cámara para ingresar</div><div id="cam-host"></div>`;
  let capture;
  try {
    setNarration(2);
    capture = await captureWithLiveness(body.querySelector("#cam-host"), { timeoutMs: 20000 });
  } catch (error) {
    body.innerHTML = `${errorBox(error)}<button class="btn" id="again">Volver</button>`;
    body.querySelector("#again").addEventListener("click", restart);
    return;
  }
  body.classList.add("center");
  if (!capture.passed) {
    body.innerHTML = `<div class="result">${livenessFailureMarkup(capture.reason)}
      <button class="btn" id="again">Intentar de nuevo</button></div>`;
    body.querySelector("#again").addEventListener("click", () => verifyFlow(subject, body, restart));
    return;
  }
  setNarration(3);
  body.innerHTML = `<div class="spinner" role="status" aria-label="Comparando"></div><p>Comparando…</p>`;
  try {
    const result = await api.verify(subject.subjectId, capture.blob, capture.liveness);
    const name = esc(firstName(subject.displayName));
    const copy = {
      MATCH: [`¡Eres tú, ${name}!`, "Acceso concedido."],
      NO_MATCH: [`No pudimos confirmar que eres ${name}`, "Por seguridad no damos acceso."],
      INCONCLUSIVE: ["No estamos seguros", "Probemos otra vez, con mejor luz y mirando de frente."],
    }[result.decision];
    const tone = toneOf(result.decision);
    setNarration(4);
    body.innerHTML = `<div class="result">
      ${compareMarkup(getPhoto(subject.subjectId), capture.thumbnail, result.score, tone)}
      ${verdictMarkup(tone, copy[0], copy[1])}
      <div class="actions">${result.decision === "MATCH" ? `<button class="btn" id="again">Entrar</button>` : `<button class="btn" id="retry">Intentar de nuevo</button>`}</div>
    </div>`;
    body.querySelector("#again")?.addEventListener("click", restart);
    body.querySelector("#retry")?.addEventListener("click", () => verifyFlow(subject, body, restart));
  } catch (error) {
    body.innerHTML = `${errorBox(error)}<button class="btn" id="again">Volver</button>`;
    body.querySelector("#again").addEventListener("click", restart);
  }
}

function renderIdentify() {
  view.innerHTML = scenarioLayout({
    number: 3,
    title: "¿Quién es este cliente?",
    lead: "Llega un cliente a la sede sin su documento. Con su rostro lo encontramos entre todos los clientes registrados.",
    steps: [
      ["Llega un cliente sin documento", "El asesor no sabe quién es."],
      ["Prueba de vida", "El cliente parpadea y gira la cabeza frente a la cámara."],
      ["Búsqueda", "Se compara con todos los clientes activos registrados."],
      ["Resultado", "El asesor ve quién es, o que no está registrado."],
    ],
    device: `<div class="panel" id="identify-panel"></div>`,
  });
  const panel = view.querySelector("#identify-panel");
  const head = `<div class="panel-head"><span class="who">Pantalla del asesor</span></div>`;

  const showStart = () => {
    setNarration(0);
    panel.innerHTML = `${head}<h2>Identificar a un cliente</h2>
      <p class="lead" style="font-size:1rem">Pídele al cliente que mire a la cámara. No necesitas saber su nombre.</p>
      <div class="actions"><button class="btn" id="start">Empezar</button></div>`;
    panel.querySelector("#start").addEventListener("click", showCapture);
  };

  const showCapture = async () => {
    setNarration(1);
    panel.innerHTML = `${head}<h2>Mira a la cámara</h2><div id="cam-host"></div>`;
    let capture;
    try {
      capture = await captureWithLiveness(panel.querySelector("#cam-host"));
    } catch (error) {
      panel.innerHTML = `${head}${errorBox(error)}<div class="actions"><button class="btn" id="again">Intentar de nuevo</button></div>`;
      panel.querySelector("#again").addEventListener("click", showCapture);
      return;
    }
    if (!capture.passed) {
      panel.innerHTML = `${head}${verdictMarkup("warn", "Intentémoslo otra vez", esc(LIVENESS_MESSAGES[capture.reason] ?? ""))}
        <div class="actions"><button class="btn" id="again">Intentar de nuevo</button></div>`;
      panel.querySelector("#again").addEventListener("click", showCapture);
      return;
    }
    setNarration(2);
    panel.innerHTML = `${head}<div class="result"><div class="spinner" role="status" aria-label="Buscando"></div><p>Buscando entre los clientes…</p></div>`;
    try {
      showResult(await api.identify(capture.blob, capture.liveness), capture);
    } catch (error) {
      panel.innerHTML = `${head}${errorBox(error)}<div class="actions"><button class="btn" id="again">Intentar de nuevo</button></div>`;
      panel.querySelector("#again").addEventListener("click", showCapture);
    }
  };

  const showResult = (result, capture) => {
    setNarration(4);
    const best = result.candidates[0];
    const tone = best ? toneOf(result.decision) : "bad";
    const verdict = best
      ? result.decision === "MATCH"
        ? verdictMarkup("ok", `Es ${esc(best.displayName)}`, `Identificación del cliente: ${esc(best.externalId)}`)
        : verdictMarkup("warn", `Podría ser ${esc(best.displayName)}`, "La similitud no es suficiente. Pide un documento para confirmar.")
      : verdictMarkup("bad", "No encontramos a esta persona", "No está entre los clientes registrados.");
    panel.innerHTML = `${head}<div class="result">
      ${compareMarkup(best ? getPhoto(best.subjectId) : null, capture.thumbnail, best ? best.score : null, tone)}
      ${verdict}
      <div class="actions"><button class="btn" id="again">Identificar a otra persona</button>${best ? "" : `<a class="btn ghost" href="#nuevo-cliente">Registrarlo como nuevo cliente</a>`}</div>
    </div>`;
    panel.querySelector("#again").addEventListener("click", showCapture);
  };

  showStart();
}

async function renderSubjects() {
  view.innerHTML = `<header class="scenario-head"><div class="eyebrow">Modo técnico</div><h1>Personas registradas</h1>
    <p class="lead">Desactivar es reversible. Eliminar borra a la persona y su rostro también en el motor.</p></header>
    <div id="subjects"><div class="spinner"></div></div>`;
  const host = view.querySelector("#subjects");
  let subjects;
  try {
    subjects = await api.listSubjects();
  } catch (error) {
    host.innerHTML = errorBox(error);
    return;
  }
  if (!subjects.length) {
    host.innerHTML = `<div class="table-wrap"><p class="empty">Aún no hay personas registradas.</p></div>`;
    return;
  }
  host.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Foto</th><th>Nombre</th><th>Identificación</th><th>Estado</th><th>Autorización</th><th>Rostros</th><th>Fallos</th><th></th></tr></thead>
    <tbody>${subjects.map(subjectRow).join("")}</tbody></table></div>`;
  host.querySelector("tbody").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const { id, action } = button.dataset;
    if (action === "remove" && !window.confirm("¿Eliminar a esta persona y su rostro? No se puede deshacer.")) return;
    button.disabled = true;
    try {
      await api[action](id);
      if (action === "remove") removePhoto(id);
      renderSubjects();
    } catch (error) {
      host.insertAdjacentHTML("afterbegin", errorBox(error));
    }
  });
}

function subjectRow(s) {
  const active = s.status === "ACTIVE";
  const locked = s.lockedUntil && new Date(s.lockedUntil) > new Date();
  const photo = getPhoto(s.subjectId);
  return `<tr>
    <td>${photo ? `<img class="thumb" src="${photo}" alt="">` : `<span class="thumb"></span>`}</td>
    <td>${esc(s.displayName)}</td>
    <td class="mono">${esc(s.externalId)}</td>
    <td><span class="badge ${active ? "ok" : ""}">${active ? "Activa" : "Inactiva"}</span> ${locked ? `<span class="badge bad">Bloqueada</span>` : ""}</td>
    <td>${s.consentedAt ? new Date(s.consentedAt).toLocaleString() : `<span class="badge bad">Pendiente</span>`}</td>
    <td>${s.enrollments}</td>
    <td>${s.failedAttempts}</td>
    <td><div class="actions">
      <button class="btn small ghost" data-id="${s.subjectId}" data-action="${active ? "deactivate" : "reactivate"}">${active ? "Desactivar" : "Reactivar"}</button>
      <button class="btn small danger" data-id="${s.subjectId}" data-action="remove">Eliminar</button>
    </div></td></tr>`;
}

async function renderAudit() {
  view.innerHTML = `<header class="scenario-head"><div class="eyebrow">Modo técnico</div><h1>Auditoría</h1>
    <p class="lead">Cada operación queda registrada con su resultado y la prueba de vida. De la imagen solo se guarda su huella SHA-256.</p></header>
    <div id="audit"><div class="spinner"></div></div>`;
  const host = view.querySelector("#audit");
  try {
    const [events, subjects] = await Promise.all([api.audit(), api.listSubjects()]);
    const names = Object.fromEntries(subjects.map((s) => [s.subjectId, s.displayName]));
    host.innerHTML = events.length
      ? `<div class="table-wrap"><table><thead><tr><th>Hora</th><th>Acción</th><th>Resultado</th><th>Persona</th><th>Detalle</th><th>Imagen</th></tr></thead>
        <tbody>${events.map((e) => auditRow(e, names)).join("")}</tbody></table></div>`
      : `<div class="table-wrap"><p class="empty">Sin eventos todavía.</p></div>`;
  } catch (error) {
    host.innerHTML = errorBox(error);
  }
}

function auditRow(e, names) {
  const good = ["OK", "MATCH"].includes(e.outcome);
  const warn = e.outcome === "INCONCLUSIVE";
  const detail = e.detail
    .replace("liveness=PASSED", "prueba de vida superada")
    .replace("liveness=FAILED", "prueba de vida fallida")
    .replace("liveness=NOT_PERFORMED", "sin prueba de vida");
  return `<tr>
    <td class="mono">${new Date(e.occurredAt).toLocaleTimeString()}</td>
    <td>${AUDIT_LABELS[e.action] ?? esc(e.action)}</td>
    <td><span class="badge ${good ? "ok" : warn ? "" : "bad"}">${esc(e.outcome)}</span></td>
    <td>${esc(e.subjectId ? names[e.subjectId] ?? "(eliminada)" : "—")}</td>
    <td>${esc(detail)}</td>
    <td class="mono">${e.imageSha256 ? `${e.imageSha256.slice(0, 10)}…` : ""}</td></tr>`;
}

const ROUTES = {
  inicio: renderHome,
  "nuevo-cliente": renderEnroll,
  titular: renderVerify,
  "quien-es": renderIdentify,
  personas: renderSubjects,
  auditoria: renderAudit,
};

function route() {
  leaveView();
  leaveView = () => {};
  const name = location.hash.slice(1) || "inicio";
  (ROUTES[name] ?? renderHome)();
  const current = ["personas", "auditoria"].includes(name) ? name : "inicio";
  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.dataset.nav === current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  window.scrollTo({ top: 0 });
  view.focus({ preventScroll: true });
}

function setupTechMode() {
  const toggle = document.querySelector("#tech-toggle");
  let enabled = false;
  try {
    enabled = localStorage.getItem(TECH_STORAGE) === "1";
  } catch {
    /* por defecto, modo presentación */
  }
  const apply = () => document.body.classList.toggle("tech", toggle.checked);
  toggle.checked = enabled;
  apply();
  toggle.addEventListener("change", () => {
    apply();
    try {
      localStorage.setItem(TECH_STORAGE, toggle.checked ? "1" : "0");
    } catch {
      /* preferencia solo para esta sesión */
    }
  });

  const keyInput = document.querySelector("#api-key");
  keyInput.value = getApiKey();
  keyInput.addEventListener("change", () => setApiKey(keyInput.value.trim()));

  const calls = [];
  onApiCall((call) => {
    calls.unshift(call);
    calls.length = Math.min(calls.length, 8);
    document.querySelector("#calls-count").textContent = calls.length;
    document.querySelector("#calls-list").innerHTML = calls
      .map((c) => `<li><span class="mono">${esc(c.method)} ${esc(c.path)} → ${c.status}</span><pre>${esc(JSON.stringify(c.payload, null, 2))}</pre></li>`)
      .join("");
  });

  api
    .health()
    .then((health) => {
      const badge = document.querySelector("#engine-badge");
      badge.textContent = `motor: ${health.engine} · ${health.engineStatus}`;
      badge.classList.add(health.engineStatus === "UP" ? "ok" : "bad");
    })
    .catch(() => (document.querySelector("#engine-badge").textContent = "servicio caído"));
}

setupTechMode();
window.addEventListener("hashchange", route);
route();
// Precarga el modelo mientras se presenta la portada, para que la cámara arranque rápido.
preloadLandmarker().catch(() => {});
