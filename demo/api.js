// Cliente de la API /v1 del servicio. Es lo mismo que haría la app móvil o el web administrativo.

const API_KEY_STORAGE = "fis-demo-api-key";
const listeners = new Set();

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.title ?? `Error ${status}`);
    this.status = status;
    this.body = body ?? {};
    this.slug = this.body.slug ?? "ERROR";
  }
}

export function getApiKey() {
  try {
    return localStorage.getItem(API_KEY_STORAGE) || "demo-key";
  } catch {
    return "demo-key";
  }
}

export function setApiKey(value) {
  try {
    localStorage.setItem(API_KEY_STORAGE, value);
  } catch {
    /* sin almacenamiento local se usa la key por defecto */
  }
}

/** Avisa de cada llamada (método, ruta, estado, respuesta) para el panel del modo técnico. */
export function onApiCall(listener) {
  listeners.add(listener);
}

async function request(method, path, { json, form } = {}) {
  const headers = { "x-api-key": getApiKey() };
  let body;
  if (json) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  const response = await fetch(path, { method, headers, body });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  listeners.forEach((listener) => listener({ method, path, status: response.status, payload }));
  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

function imageForm(blob, liveness) {
  const form = new FormData();
  form.append("image", blob, "captura.jpg");
  if (liveness) form.append("liveness", liveness);
  return form;
}

export const api = {
  health: () => fetch("/health").then((r) => r.json()),
  listSubjects: () => request("GET", "/v1/subjects"),
  createSubject: (externalId, displayName) =>
    request("POST", "/v1/subjects", { json: { externalId, displayName } }),
  recordConsent: (subjectId, channel) =>
    request("POST", `/v1/subjects/${subjectId}/consents`, {
      json: { textVersion: "biometria-v1", channel },
    }),
  enroll: (subjectId, blob, liveness) =>
    request("POST", `/v1/subjects/${subjectId}/enrollments`, { form: imageForm(blob, liveness) }),
  verify: (subjectId, blob, liveness) =>
    request("POST", `/v1/subjects/${subjectId}/verifications`, { form: imageForm(blob, liveness) }),
  identify: (blob, liveness) => request("POST", "/v1/identifications", { form: imageForm(blob, liveness) }),
  deactivate: (subjectId) => request("POST", `/v1/subjects/${subjectId}/deactivate`),
  reactivate: (subjectId) => request("POST", `/v1/subjects/${subjectId}/reactivate`),
  remove: (subjectId) => request("DELETE", `/v1/subjects/${subjectId}`),
  audit: (limit = 60) => request("GET", `/v1/audit?limit=${limit}`),
};
