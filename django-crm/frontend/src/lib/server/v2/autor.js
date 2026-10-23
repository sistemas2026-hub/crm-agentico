/**
 * Quién escribe, para todo lo que una persona le manda al motor: texto, nota,
 * adjunto o plantilla.
 *
 * Server-only, y a propósito un solo lugar. El autor sale de la SESIÓN
 * autenticada (locals.user), nunca del cuerpo que arma el navegador: un
 * mensaje firmado por quien dice el cliente HTTP no prueba nada. El motor
 * rechaza con 400 un mensaje de persona sin nombre o sin id
 * (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D2 y X13).
 *
 * 'autor' es el nombre --lo que firma la copia al ticket y lo que ve el
 * modelo--, con el email como respaldo si el perfil no tiene nombre.
 * 'autor_usuario_id' es el User.id de Django (uuid), el mismo 'user_id' del JWT.
 *
 * @param {any} locals
 * @returns {{ autor: string, autor_usuario_id: string }}
 */
export function autorDeSesion(locals) {
  const u = locals?.user ?? {};
  return {
    autor: (u.name || u.email || '').trim(),
    autor_usuario_id: u.id ?? ''
  };
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * La clave de idempotencia de un mensaje. La genera la pantalla UNA vez por
 * mensaje compuesto y la reutiliza al reintentar: así un reintento no crea
 * otra fila. Si no llega o no tiene forma de uuid, se genera acá -- ese envío
 * queda protegido contra un doble POST del proxy, pero no contra un reintento
 * desde la pantalla, que tiene que mandar la suya.
 *
 * @param {unknown} valor
 * @returns {string}
 */
export function claveIdempotencia(valor) {
  return typeof valor === 'string' && UUID.test(valor) ? valor : crypto.randomUUID();
}
