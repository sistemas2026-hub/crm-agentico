/**
 * El tema claro u oscuro de la interfaz, elegido por quien la usa.
 *
 * Desde el 22/10/2026 v2.css tiene una paleta oscura ("Grafito") que nada
 * activaba: el unico interruptor vivia en AppSidebar, de v1, que no se monta.
 * Esto es ese interruptor.
 *
 * Es OPCIONAL y arranca en claro, a proposito: no sigue el tema del sistema.
 * Ninguna pantalla se vio nunca en oscuro, y quien tiene el sistema en oscuro
 * no deberia encontrarse de golpe con pantallas sin revisar. Lo prende quien
 * quiere.
 *
 * La eleccion vive en el navegador (es una comodidad de cada persona, no un
 * dato de la empresa) y se aplica antes del primer pintado desde app.html,
 * que lee la misma CLAVE. Si el navegador bloquea localStorage, queda claro y
 * no se rompe nada.
 */

export const CLAVE = 'dexter-tema';

/** @returns {'claro' | 'oscuro'} */
export function leerTema() {
  try {
    return globalThis.localStorage?.getItem(CLAVE) === 'oscuro' ? 'oscuro' : 'claro';
  } catch {
    return 'claro';
  }
}

/** @param {'claro' | 'oscuro'} tema */
export function aplicarTema(tema) {
  globalThis.document?.documentElement.classList.toggle('dark', tema === 'oscuro');
  try {
    globalThis.localStorage?.setItem(CLAVE, tema);
  } catch {
    // Sin almacenamiento el tema dura lo que dure la pagina.
  }
}

/** @returns {'claro' | 'oscuro'} el tema que quedo puesto */
export function alternarTema() {
  const siguiente = leerTema() === 'oscuro' ? 'claro' : 'oscuro';
  aplicarTema(siguiente);
  return siguiente;
}
