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

/* ── EL RESUMEN DE LA ESCALADA ────────────────────────────────────────────
   Misma mecánica y mismo motivo que la barra, así que vive acá en vez de
   duplicar el patrón: es una preferencia de esta persona en esta máquina, se
   recuerda entre conversaciones, y se lee del navegador sin romper el
   renderizado del servidor.

   Arranca ABIERTO, al revés que un panel opcional cualquiera: la primera vez
   que se abre una conversación escalada, por qué llegó ahí es exactamente lo
   que hay que leer. Se recoge cuando alguien ya no lo necesita -- y ahí sí se
   recuerda, porque quien trabaja un turno entero abre decenas y volver a
   cerrarlo en cada una es la fricción que se quiere evitar.

   `valor` y no una propiedad suelta: leerlo desde un `$derived` de un
   componente exige que el acceso pase por el objeto reactivo. */
const CLAVE_RESUMEN = 'dexter:bandeja:resumen-recogido';

export const resumenRecogido = $state({
  valor: false,
  leida: false,

  recordar() {
    if (this.leida) return;
    try {
      /* RECOGIDO POR DEFECTO desde el 22/09/2026. Medido sobre la columna
         real: desplegado ocupa 143px de 702, y al hilo le quedaban 124 --
         el 18% de la pantalla para lo que la pantalla ES.

         Lo que cambió y habilita el cambio: la línea del título ahora
         muestra el MOTIVO de la escalada. Antes recoger escondía la
         respuesta y por eso arrancaba abierto; ahora recogido sigue
         contestando "por qué llegó acá" en 28px en vez de 143.

         La preferencia de cada uno manda igual: sólo cambia qué pasa
         cuando todavía no eligió. */
      const guardado = localStorage.getItem(CLAVE_RESUMEN);
      this.valor = guardado === null ? true : guardado === '1';
    } catch {
      this.valor = false;
    }
    this.leida = true;
  },

  alternar() {
    this.valor = !this.valor;
    try {
      localStorage.setItem(CLAVE_RESUMEN, this.valor ? '1' : '0');
    } catch {
      // Sin almacenamiento el cambio vale para esta sesión igual.
    }
  }
});
