/**
 * A dónde volver después de iniciar sesión o elegir organización.
 *
 * POR QUÉ EXISTE
 * Quien abre un link profundo sin sesión — el expediente de una solicitud
 * desde un ticket del ISP, cualquier enlace compartido — era rebotado a
 * `/login`, de ahí a `/org`, y al elegir organización terminaba en `/`. El
 * destino se perdía en el camino y la persona quedaba mirando la pantalla de
 * inicio sin saber por qué. Reportado el 09/09/2026 con el expediente, pero
 * le pasaba a cualquier enlace.
 *
 * POR QUÉ NO SE ACEPTA CUALQUIER VALOR
 * El destino viaja en la URL, así que lo escribe quien arme el enlace. Sin
 * filtro, `?redirect=https://otro-sitio` convierte el login en un trampolín:
 * la persona ve el dominio del CRM, entra, y sale despedida a un sitio ajeno
 * que puede imitar esta misma pantalla y pedirle la clave otra vez. Es un
 * *open redirect*, y es la razón por la que esto es una función y no un
 * `?? '/'` escrito en tres lugares.
 *
 * Sólo pasa una ruta relativa de este mismo sitio. Se rechaza:
 *   - lo que no empieza con `/`   (`https://…`, `javascript:…`)
 *   - `//otro-sitio`              (relativa al protocolo, sale igual)
 *   - `/\otro-sitio`              (algunos navegadores la tratan como `//`)
 *   - `/login`, `/org`            (volver ahí es un bucle, no un destino)
 */

const SIN_SENTIDO = ['/login', '/logout', '/org', '/bounce'];

/**
 * @param {string | null | undefined} valor
 * @param {string} [porDefecto]
 * @returns {string}
 */
export function destinoSeguro(valor, porDefecto = '/') {
  if (!valor || typeof valor !== 'string') return porDefecto;
  if (!valor.startsWith('/')) return porDefecto;
  if (valor.startsWith('//') || valor.startsWith('/\\')) return porDefecto;

  const camino = valor.split('?')[0].split('#')[0];
  if (SIN_SENTIDO.some((r) => camino === r || camino.startsWith(r + '/'))) {
    return porDefecto;
  }
  return valor;
}

/**
 * `?redirect=<destino>` para colgar de `/login` o `/org`, o cadena vacía si
 * no hay a dónde volver. Devolver la cadena vacía y no `'?redirect='` importa:
 * un parámetro vacío en la URL se ve como un error de la aplicación.
 *
 * @param {string | null | undefined} destino
 * @returns {string}
 */
export function comoParametro(destino) {
  const limpio = destinoSeguro(destino, '');
  return limpio ? `?redirect=${encodeURIComponent(limpio)}` : '';
}
