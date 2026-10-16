// Captura guiada + prueba de vida con MediaPipe Face Landmarker (Google, Apache 2.0).
// Todo ocurre en el navegador: el video nunca sale del equipo; solo se envía la foto final.

const MEDIAPIPE_VERSION = "1.0.1";
const LOCAL_BASE = new URL("./vendor/mediapipe/", import.meta.url).href;
const CDN_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/`;
const CDN_MODEL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Umbrales calibrables. En modo técnico se ven los valores en vivo para ajustarlos.
const BLINK_CLOSED = 0.5;
const BLINK_OPEN = 0.25;
const TURN_THRESHOLD = 0.17;
const FRONTAL_THRESHOLD = 0.08;
const CENTER_TOLERANCE = 0.14;
const MIN_FACE_WIDTH = 0.3;
const MAX_FACE_WIDTH = 0.82;
const MIN_BRIGHTNESS = 50;
const HOLD_MS = 600;
// En la imagen sin espejo, cuando la persona gira hacia SU derecha la nariz se acerca al
// punto 234 y el índice de giro baja. Si en pruebas resulta al revés, cambiar a +1.
const USER_RIGHT_SIGN = -1;

const NOSE_TIP = 1;
const FACE_SIDE_A = 234;
const FACE_SIDE_B = 454;

export const STEPS = ["position", "blink", "turn", "front"];

let landmarkerPromise = null;

export function preloadLandmarker() {
  landmarkerPromise ??= createLandmarker().catch((error) => {
    landmarkerPromise = null;
    throw error;
  });
  return landmarkerPromise;
}

async function createLandmarker() {
  const { vision, wasmBase, model } = await importVision();
  const fileset = await vision.FilesetResolver.forVisionTasks(wasmBase);
  const options = (delegate) => ({
    baseOptions: { modelAssetPath: model, delegate },
    runningMode: "VIDEO",
    numFaces: 2,
    outputFaceBlendshapes: true,
  });
  try {
    return await vision.FaceLandmarker.createFromOptions(fileset, options("GPU"));
  } catch {
    return vision.FaceLandmarker.createFromOptions(fileset, options("CPU"));
  }
}

async function importVision() {
  try {
    const vision = await import(`${LOCAL_BASE}vision_bundle.mjs`);
    return { vision, wasmBase: `${LOCAL_BASE}wasm`, model: `${LOCAL_BASE}face_landmarker.task` };
  } catch {
    const vision = await import(`${CDN_BASE}vision_bundle.mjs`);
    return { vision, wasmBase: `${CDN_BASE}wasm`, model: CDN_MODEL };
  }
}

export function randomDirection() {
  return Math.random() < 0.5 ? "izquierda" : "derecha";
}

/**
 * Controla la cámara dentro de `container` (que contiene un <video>) y ejecuta la secuencia
 * centrar → parpadear → girar → volver al frente → capturar.
 */
export class FaceCheck {
  constructor(container, { onUpdate = () => {} } = {}) {
    this.container = container;
    this.video = container.querySelector("video");
    this.onUpdate = onUpdate;
    this.stream = null;
    this.frame = null;
    this.brightnessCanvas = document.createElement("canvas");
    this.brightnessCanvas.width = 32;
    this.brightnessCanvas.height = 24;
  }

  async open() {
    const [stream, landmarker] = await Promise.all([
      navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false,
      }),
      preloadLandmarker(),
    ]);
    this.stream = stream;
    this.landmarker = landmarker;
    this.video.srcObject = stream;
    await this.video.play();
  }

  close() {
    cancelAnimationFrame(this.frame);
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  run({ timeoutMs = 30000, direction = randomDirection() } = {}) {
    cancelAnimationFrame(this.frame);
    return new Promise((resolve) => {
      const session = {
        step: "position",
        direction,
        startedAt: performance.now(),
        holdSince: null,
        eyesClosed: false,
        lastVideoTime: -1,
        frameCount: 0,
        dark: false,
        measure: null,
      };
      const finish = async (passed, reason) => {
        cancelAnimationFrame(this.frame);
        const photo = await this.capture();
        resolve({ passed, reason, direction, ...photo });
      };
      const tick = () => {
        const now = performance.now();
        if (now - session.startedAt > timeoutMs) {
          finish(false, failureReason(session));
          return;
        }
        if (this.video.currentTime !== session.lastVideoTime) {
          session.lastVideoTime = this.video.currentTime;
          session.frameCount += 1;
          if (session.frameCount % 15 === 0) session.dark = this.brightness() < MIN_BRIGHTNESS;
          session.measure = this.measure(this.landmarker.detectForVideo(this.video, now));
          if (this.advance(session, now)) {
            finish(true, null);
            return;
          }
        }
        this.frame = requestAnimationFrame(tick);
      };
      this.frame = requestAnimationFrame(tick);
    });
  }

  advance(session, now) {
    const m = session.measure;
    const framing = framingHint(m, session.dark);
    let hint = null;

    if (session.step === "position" || session.step === "front") {
      const frontal = m.faces === 1 && Math.abs(m.turn) < FRONTAL_THRESHOLD;
      hint = framing ?? (frontal ? null : "Mira de frente a la cámara");
      if (hint) {
        session.holdSince = null;
      } else {
        session.holdSince ??= now;
        if (now - session.holdSince >= HOLD_MS) {
          if (session.step === "front") return true;
          session.step = "blink";
          session.holdSince = null;
        }
      }
    } else if (session.step === "blink") {
      hint = m.faces === 1 ? "Parpadea" : framing;
      if (m.blink > BLINK_CLOSED) session.eyesClosed = true;
      if (session.eyesClosed && m.blink < BLINK_OPEN) session.step = "turn";
    } else if (session.step === "turn") {
      const userTurn = m.turn * USER_RIGHT_SIGN;
      const wanted = session.direction === "derecha" ? 1 : -1;
      hint = m.faces === 1 ? `Gira la cabeza a tu ${session.direction}` : framing;
      if (m.faces === 1 && userTurn * wanted > TURN_THRESHOLD) session.step = "front";
      else if (m.faces === 1 && userTurn * wanted < -TURN_THRESHOLD) hint = "Hacia el otro lado";
    }

    this.onUpdate({
      step: session.step,
      direction: session.direction,
      hint: hint ?? stepHint(session),
      ok: !hint,
      metrics: m,
    });
    return false;
  }

  measure(result) {
    const faces = result.faceLandmarks?.length ?? 0;
    if (faces !== 1) return { faces, blink: 0, turn: 0 };
    const points = result.faceLandmarks[0];
    const view = this.viewMapping();
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    // Coordenadas como las ve la persona: recortadas por object-fit: cover y en espejo.
    const centerX = 1 - ((minX + maxX) / 2 - view.offsetX) / view.fractionX;
    const centerY = ((minY + maxY) / 2 - view.offsetY) / view.fractionY;
    const width = (maxX - minX) / view.fractionX;
    const sideA = points[FACE_SIDE_A].x;
    const sideB = points[FACE_SIDE_B].x;
    const turn = (points[NOSE_TIP].x - sideA) / (sideB - sideA) - 0.5;
    const scores = Object.fromEntries(
      (result.faceBlendshapes?.[0]?.categories ?? []).map((c) => [c.categoryName, c.score]),
    );
    const blink = Math.min(scores.eyeBlinkLeft ?? 0, scores.eyeBlinkRight ?? 0);
    return { faces, centerX, centerY, width, turn, blink };
  }

  viewMapping() {
    const videoRatio = this.video.videoWidth / this.video.videoHeight;
    const boxRatio = this.container.clientWidth / this.container.clientHeight;
    if (videoRatio > boxRatio) {
      const fractionX = boxRatio / videoRatio;
      return { fractionX, offsetX: (1 - fractionX) / 2, fractionY: 1, offsetY: 0 };
    }
    const fractionY = videoRatio / boxRatio;
    return { fractionX: 1, offsetX: 0, fractionY, offsetY: (1 - fractionY) / 2 };
  }

  brightness() {
    const ctx = this.brightnessCanvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(this.video, 0, 0, 32, 24);
    const { data } = ctx.getImageData(0, 0, 32, 24);
    let total = 0;
    for (let i = 0; i < data.length; i += 4) total += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    return total / (data.length / 4);
  }

  /** Foto del área visible (vertical, como la ve la persona) + miniatura para la demo. */
  async capture() {
    const view = this.viewMapping();
    const sw = this.video.videoWidth * view.fractionX;
    const sh = this.video.videoHeight * view.fractionY;
    const sx = this.video.videoWidth * view.offsetX;
    const sy = this.video.videoHeight * view.offsetY;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(sw);
    canvas.height = Math.round(sh);
    canvas.getContext("2d").drawImage(this.video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    return { blob, thumbnail: thumbnailOf(canvas) };
  }
}

function framingHint(m, dark) {
  if (m.faces === 0) return "No te vemos. Ubícate frente a la cámara";
  if (m.faces > 1) return "Solo debe aparecer una persona";
  if (dark) return "Busca un lugar con más luz";
  if (m.width < MIN_FACE_WIDTH) return "Acércate un poco";
  if (m.width > MAX_FACE_WIDTH) return "Aléjate un poco";
  if (Math.abs(m.centerX - 0.5) > CENTER_TOLERANCE || Math.abs(m.centerY - 0.47) > CENTER_TOLERANCE)
    return "Centra tu rostro en el óvalo";
  return null;
}

function stepHint(session) {
  return {
    position: "¡Perfecto! Quédate así",
    blink: "Parpadea",
    turn: `Gira la cabeza a tu ${session.direction}`,
    front: "Ahora mira al frente",
  }[session.step];
}

function failureReason(session) {
  if (session.step === "position") return session.measure?.faces ? "NO_FRAMING" : "NO_FACE";
  if (session.step === "blink") return "NO_BLINK";
  if (session.step === "turn") return "NO_TURN";
  return "NO_FRONT";
}

function thumbnailOf(source) {
  const width = 320;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = Math.round((source.height / source.width) * width);
  canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.8);
}
