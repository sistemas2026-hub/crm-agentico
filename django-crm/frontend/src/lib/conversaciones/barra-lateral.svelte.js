/**
 * Si la barra lateral del CRM está recogida.
 *
 * POR QUÉ ES UN MÓDULO Y NO UNA PROP
 * ----------------------------------
 * La barra la dibuja `(app)/+layout.svelte` y el botón que la recoge vive en
 * la barra de consola de la Bandeja, que es un layout hijo. Pasar el estado
 * hacia arriba no se puede, y subir el botón al layout padre lo pondría en
 * todas las rutas del CRM, donde no tiene sentido.
 *
 * SE RECUERDA ENTRE VISITAS. Quien trabaja la Bandeja a pantalla completa lo
 * hace todo el turno: pedirle que la recoja cada vez que entra sería una
 * decisión que ya tomó, olvidada a propósito. `localStorage` alcanza -- es
 * una preferencia de esta persona en esta máquina, no un dato del sistema.
 *
 * ARRANCA VISIBLE. La barra es la única navegación que alguien que entra por
 * primera vez reconoce; esconderla por defecto es dejar a alguien sin saber
 * cómo salir. Se recoge cuando lo pide, y recién entonces se recuerda.
 */
const CLAVE = 'dexter:bandeja:barra-recogida';

function leer() {
  try {
    return localStorage.getItem(CLAVE) === '1';
  } catch {
    // Ventana privada, almacenamiento bloqueado. Sin preferencia guardada se
    // muestra la barra, que es el estado seguro.
    return false;
  }
}

/* `$state` en un módulo `.svelte.js`: una sola instancia para toda la
   aplicación, que es justo lo que hace falta acá -- el botón y la barra
   tienen que estar mirando el mismo valor. */
export const barra = $state({ recogida: false, leida: false });

/** Se llama una vez, del lado del navegador: en el servidor no hay
    `localStorage` y leerlo ahí rompería el renderizado. */
export function recordarPreferencia() {
  if (barra.leida) return;
  barra.recogida = leer();
  barra.leida = true;
}

export function alternar() {
  barra.recogida = !barra.recogida;
  try {
    localStorage.setItem(CLAVE, barra.recogida ? '1' : '0');
  } catch {
    // Si no se puede guardar, el cambio vale para esta sesión igual.
  }
}
