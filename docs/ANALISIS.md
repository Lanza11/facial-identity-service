# Análisis: identificación facial como servicio independiente

Documento de apoyo para la reunión de viabilidad. Resume qué ofrece CompreFace, qué alternativas open source existen, si el `facial-identity-service` es viable y cómo se integraría con la app móvil `app-mobile-recaudo`.

> Estado: **prototipo de investigación**. Lo descrito como "producción" es una recomendación, no algo implementado.

---

## 1. Qué ofrece CompreFace

[CompreFace](https://github.com/exadel-inc/CompreFace) (Exadel, licencia Apache‑2.0) es un servidor de reconocimiento facial self‑hosted que se despliega con Docker.

**Componentes**

| Contenedor | Función |
|---|---|
| `compreface-api` (Java/Spring) | API REST de reconocimiento, verificación y detección |
| `compreface-admin` + `compreface-fe` (Angular + nginx) | UI de administración: usuarios, aplicaciones, servicios y API keys |
| `compreface-core` (Python) | Modelos de ML: detección de rostros y cálculo de embeddings |
| `compreface-postgres-db` | Subjects, embeddings y, opcionalmente, imágenes |

**Servicios.** Cada servicio tiene su propia `x-api-key`.
- **Recognition (1:N):** `POST /recognition/recognize` devuelve los sujetos más parecidos con su similitud (0..1).
- **Gestión de rostros:** CRUD de subjects (`/recognition/subjects`) y de ejemplos (`/recognition/faces`).
- **Verificación 1:1:** contra un ejemplo guardado (`/recognition/faces/{image_id}/verify`) o imagen contra imagen (`/verification/verify`).
- **Detección:** `/detection/detect`, con plugins de landmarks, edad, género, mascarilla y pose.
- **Embeddings:** desde la versión 1.2 acepta vectores en lugar de imágenes.

**Modelos (builds)**

| Build | Precisión LFW | Requisito | Nota |
|---|---|---|---|
| FaceNet (default) | 99.63% | CPU con AVX | El más compatible |
| **Mobilenet (ArcFace)** | 99.50% | CPU con AVX2 | El más rápido en CPU. **Es el que usa este prototipo** |
| SubCenter‑ArcFace‑r100 | 99.80% | CPU con AVX2 | El más preciso y el más lento |
| Variantes `-gpu` | — | GPU con CUDA | Para tiempo real |

Los embeddings **no son compatibles entre modelos**: si se cambia de modelo, hay que volver a registrar a todas las personas.

**Limitaciones relevantes**
1. **No tiene liveness (anti‑spoofing).** No distingue una persona real de una foto o una pantalla.
2. **Mantenimiento detenido.** La última release es la v1.2.0 y el último commit es de noviembre de 2023.
3. **Los subjects son solo un nombre.** No tienen estado (activo/inactivo), metadatos, consentimiento ni auditoría.
4. Son 5 contenedores pesados. No es serverless.
5. **Licencia de los modelos:** los pesos pre‑entrenados (FaceNet y ArcFace/InsightFace) se publicaron para **investigación no comercial**. Para este prototipo de viabilidad es válido; para producción hay que revisarlo.

## 2. Alternativas open source (para una eventual producción)

El equipo trabaja tanto en AWS como en Azure, así que se descartan los servicios propietarios de una nube (AWS Rekognition, Azure Face).

| Opción | Tipo | Licencia (código / pesos) | Liveness | Mantenimiento | Comentario |
|---|---|---|---|---|---|
| CompreFace | Servidor | Apache‑2.0 / pesos no comerciales | No | Detenido (2023) | Bueno para el PoC |
| [DeepFace](https://github.com/serengil/deepface) | Librería + REST | MIT / heredada de cada modelo | Sí (MiniFASNet) | Activo | Ideal para comparar modelos (más de 10 en una sola API) |
| [InsightFace](https://github.com/deepinsight/insightface) | Librería + servidor | MIT / **modelos solo no comerciales**; uso comercial bajo licencia paga | Sí | Muy activo | Estado del arte, pero con costo de licencia |
| [UniFace](https://github.com/yakhyo/uniface) | Librería ONNX | MIT / algunos pesos no lo son | Sí (MiniFASNet) | Activo, comunidad pequeña | Liviano; hay que auditar los pesos |
| [OpenCV Zoo YuNet + SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) | Modelos ONNX | **Apache‑2.0** | No (se combina con MiniFASNet) | OpenCV | **La opción comercialmente más limpia** y liviana (CPU) |
| Silent‑Face (MiniFASNet) | Modelo ONNX | Apache‑2.0 | Liveness pasivo | Estable | Complemento para cualquier opción |

**Recomendación para producción.** El motor quedaría así:
- **Detección:** YuNet.
- **Reconocimiento:** SFace.
- **Liveness:** MiniFASNet, más un reto activo en la app (parpadeo o giro).
- **Almacenamiento y búsqueda 1:N:** PostgreSQL con **pgvector**, que existe en ambas nubes.

Todo esto va detrás del mismo puerto `FaceEngine` que ya implementa este prototipo. Antes de decidir hay que:
- Comparar los modelos con datos reales del contexto, usando DeepFace como herramienta.
- Hacer una revisión jurídica: casi todos los pesos se entrenaron con datasets académicos, y los datos biométricos son sensibles según la Ley 1581 de 2012 (Colombia) y la LGPD (Brasil).

## 3. Viabilidad del `facial-identity-service`

**Es viable.** El prototipo lo demuestra. La fachada aporta lo que el motor no tiene:

| Responsabilidad | Cómo la cumple el prototipo |
|---|---|
| Registrar rostros asociados a usuarios | `POST /v1/subjects` y `POST /v1/subjects/{id}/enrollments`. Exige un solo rostro y como máximo N fotos por persona |
| Verificar un rostro contra un usuario (1:1) | `POST /v1/subjects/{id}/verifications`. Compara contra todas sus fotos y se queda con la mejor |
| Identificar un rostro entre varios (1:N) | `POST /v1/identifications`. Excluye inactivos y aplica el umbral |
| Eliminar o desactivar | `deactivate`/`reactivate` es lógico (en la fachada); `DELETE` es supresión total, también en el motor |
| Auditoría | Cada operación queda registrada con su resultado y el **hash** de la imagen, nunca la imagen |
| Reglas de negocio | Umbrales con zona gris (`INCONCLUSIVE`), máximo de rostros, bloqueo temporal tras varios fallos, inactivos que nunca coinciden |
| Ocultar CompreFace | El motor solo ve un UUID opaco, nunca la cédula ni el nombre. La API key y la UI del motor no se exponen |
| Normalizar respuestas | `decision` (`MATCH`/`NO_MATCH`/`INCONCLUSIVE`), `score` 0..1, `reasonCode`, y errores RFC 7807 con `slug` |
| Cambiar de motor | Puerto `FaceEngine` con dos adaptadores (`compreface` y `fake`); se elige con `FIS_ENGINE` |

**Riesgos por resolver antes de producción**
1. **Liveness.** Es el riesgo principal si la verificación se hace a distancia desde el celular.
2. **Licencias** de los modelos.
3. **Marco legal:** consentimiento previo y expreso, finalidad, derecho de supresión y retención.
4. **Calibración de umbrales** con fotos reales: gama de celulares, iluminación, etc.
5. **Mantenimiento de CompreFace.** Este riesgo se mitiga con el puerto de motor.

## 4. Integración con la app móvil (`app-mobile-recaudo`)

**Es viable, sin conflicto de arquitectura.**

- **Estado actual de la app:**
  - Flutter 3.41 con Clean Architecture (`lib/` → `modules/domain` ← `modules/infrastructure`), BLoC y get_it/injectable.
  - Tiene un cliente HTTP autenticado que ya envía `Authorization: Bearer`, `x-api-key`, `X-Correlation-Id` e `Idempotency-Key`, y traduce errores problem+json con `slug`, el mismo formato que usa este servicio.
  - Sus usuarios son **clientes**, que entran con cédula y OTP por WhatsApp. Hoy **no usa la cámara**.
- **Qué habría que añadir:**
  - Los paquetes `camera` y `google_mlkit_face_detection`, para validar en el dispositivo que hay un solo rostro, centrado y con los ojos abiertos.
  - Compresión JPEG a 1 MB o menos.
  - Los permisos `CAMERA` en Android y `NSCameraUsageDescription` en iOS.
  - Una feature `facial_verification`, con su BLoC, un contrato en `domain` y su implementación HTTP en `infrastructure`.
- **Topología recomendada:** la app no llama directamente al servicio facial. El flujo es app → backend actual (API Gateway/Lambda) → `facial-identity-service`. El backend valida el JWT y **toma el `customerId` del token**, nunca del cuerpo de la petición, para que nadie pueda verificarse "como otro". Así el mismo servicio sirve también al web administrativo.
- **Sin conexión:** no aplica; se reutiliza el `offline_banner` existente.

**Casos de uso candidatos (pendientes de decisión de negocio):** reforzar el login al cambiar de dispositivo, confirmar al titular antes de operaciones sensibles, onboarding/KYC presencial en el web administrativo.
