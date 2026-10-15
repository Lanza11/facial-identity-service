// Miniaturas para la comparación lado a lado. Viven SOLO en este navegador (localStorage):
// el servicio nunca guarda imágenes. Es un recurso visual de la demo, no parte del producto.

const PREFIX = "fis-demo-photo:";

export function savePhoto(subjectId, dataUrl) {
  try {
    localStorage.setItem(PREFIX + subjectId, dataUrl);
  } catch {
    /* sin almacenamiento la comparación muestra un marcador en lugar de la foto */
  }
}

export function getPhoto(subjectId) {
  try {
    return localStorage.getItem(PREFIX + subjectId);
  } catch {
    return null;
  }
}

export function removePhoto(subjectId) {
  try {
    localStorage.removeItem(PREFIX + subjectId);
  } catch {
    /* nada que borrar */
  }
}
