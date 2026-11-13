/**
 * Cómo se lee en pantalla una clave de motivo, etiqueta o caso.
 *
 * Las claves son identificadores (`frustracion_detectada`) y la Bandeja las
 * mostraba con el guion bajo cambiado por un espacio, en CINCO copias de la
 * misma línea: «frustracion detectada», «informacion a confirmar»,
 * «facturacion», sin tildes (29/10/2026). Las palabras son de cada empresa,
 * así que el texto sale de su configuración (`conversaciones.rotulos`, se
 * edita en /settings/bandeja) y viaja con la cola.
 *
 * Una clave sin rótulo se sigue mostrando como antes: agregar un motivo nuevo
 * nunca deja una fila sin texto.
 *
 * @param {string | null | undefined} clave
 * @param {Record<string, string> | null | undefined} rotulos
 * @returns {string}
 */
export function rotuloDe(clave, rotulos) {
  if (!clave) return '';
  const propio = rotulos?.[clave];
  if (typeof propio === 'string' && propio.trim()) return propio.trim();
  return String(clave).replaceAll('_', ' ');
}
