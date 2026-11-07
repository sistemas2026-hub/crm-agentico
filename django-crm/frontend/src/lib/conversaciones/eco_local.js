/**
 * El eco de lo que ESTA pestaña acaba de enviar.
 *
 * Al apretar Enviar la pantalla dibuja la burbuja enseguida, sin id. La fila
 * de verdad llega después, por el sondeo. Si las dos no se reconocen, el hilo
 * muestra el mensaje dos veces, y quien atiende lo lee como que al cliente le
 * llegó doble (visto en producción el 29/10/2026).
 *
 * POR QUÉ LA CLAVE Y NO EL TEXTO
 * ------------------------------
 * Antes se reconocían por rol + texto dentro de 15 segundos. Desde que el
 * envío espera a que WhatsApp confirme, la fila puede llegar más tarde que
 * eso, y la copia se sumaba igual. La burbuja ya viaja con su
 * `clave_idempotencia` y el motor la devuelve tal cual: esa es la identidad
 * del envío, y no vence. Rol + texto queda solo para las burbujas que no
 * tienen clave.
 *
 * Y AL RECONOCERLA, SE ACTUALIZA
 * ------------------------------
 * Saltearse el eco no alcanza: la burbuja local se quedaba sin id, sin autor
 * y sin estado de entrega hasta recargar. Ahora toma lo que sabe la base. Lo
 * único que conserva es lo que la base no tiene: el aviso de que no salió.
 */

const VENTANA_SIN_CLAVE_MS = 15000;

/**
 * Suma `m` al hilo, o lo funde con la burbuja local que lo envió.
 *
 * @param {any[]} mensajes  el hilo; se modifica en el lugar
 * @param {any} m           un mensaje tal como lo trae el sondeo
 * @param {number} ahora    epoch ms
 * @returns {'ignorado'|'repetido'|'reconciliado'|'nuevo'}
 */
export function incorporarMensaje(mensajes, m, ahora) {
  if (!m?.id) return 'ignorado';
  if (mensajes.some((loc) => loc.id === m.id)) return 'repetido';

  const i = mensajes.findIndex((loc) => {
    if (loc.id) return false;
    if (loc.clave_idempotencia) return loc.clave_idempotencia === m.clave_idempotencia;
    return (
      loc.rol === m.rol &&
      loc.contenido === m.contenido &&
      ahora - new Date(loc.creado_en).getTime() < VENTANA_SIN_CLAVE_MS
    );
  });
  if (i < 0) {
    mensajes.push(m);
    return 'nuevo';
  }
  const local = mensajes[i];
  mensajes[i] = { ...local, ...m, sinEntregar: local.sinEntregar ?? null };
  return 'reconciliado';
}
