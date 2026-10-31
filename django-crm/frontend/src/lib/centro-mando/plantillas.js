/**
 * EL CATÁLOGO DE SALAS, Y POR QUÉ LA GEOMETRÍA NO ES CONFIGURACIÓN.
 *
 * La organización de una empresa —qué departamentos tiene, cómo se llaman, en
 * qué piso están, quién se sienta— es configuración, viaja desde el motor y se
 * edita. Esto no: esto es cuánto mide una sala, dónde van los muebles y dónde
 * los escritorios.
 *
 * El corte está puesto ahí a propósito. Describir geometría isométrica no es
 * una decisión que nadie quiera tomar en un formulario: son cuarenta números
 * por sala, y equivocarse en uno no da error —los muebles se dibujan uno dentro
 * del otro y el síntoma se describe como «parpadea». Lo que una empresa quiere
 * decidir es «esta sala es un centro de operaciones» o «esta es una recepción».
 *
 * Así que la empresa ELIGE una plantilla de este catálogo, igual que
 * `AreaDeTrabajo.icono` nombra un dibujo de un catálogo que el motor no conoce.
 * El vocabulario es del producto; la elección, de la empresa.
 *
 * LOS IDENTIFICADORES DE PUESTO SON LOCALES
 * `principal`, `p1`, `p2`… se repiten en todas las plantillas, y tienen que
 * repetirse: dos departamentos con la misma plantilla tienen los mismos
 * puestos. El identificador global se compone con el de la sala
 * (`cartera:principal`), y eso lo hace `departamentos.js` — acá no hay forma de
 * saber qué sala va a usar esta plantilla.
 *
 * DE DÓNDE SALEN ESTOS NÚMEROS
 * De las seis salas que ya estaban dibujadas y verificadas en el navegador. No
 * se rediseñó ninguna: se les quitó la identidad de departamento, que era lo
 * único que las ataba a una empresa concreta. Las plantas nuevas y las que un
 * edificio de verdad necesita son trabajo de la etapa siguiente.
 */

/**
 * @typedef {{ id: string, nombre: string, principal?: boolean,
 *             gx: number, gy: number }} PuestoDePlantilla
 * @typedef {{ rotulo: string, acento: number, mundo: any, pasillo: any,
 *             cartel: any, mural: any, mobiliario: any[],
 *             puestos: PuestoDePlantilla[] }} Plantilla
 */

/**
 * Un centro de operaciones: tres pantallas de muro, armarios de equipos y un
 * panel de empalmes.
 *
 * Es la sala más grande del catálogo y la que fijó la calidad visual del resto.
 */
const OPERACIONES = {
  rotulo: 'Centro de operaciones',
  acento: 0x4f46e5,
  mundo: { ancho: 14, fondo: 10, alto: 4 },
  pasillo: { desde: 11, hasta: 14 },
  cartel: { gx: 7.4 },
  mural: {
    paneles: [
      { gx: 2.6, ancho: 3.0 },
      { gx: 5.9, ancho: 3.0 },
      { gx: 9.2, ancho: 3.0 }
    ]
  },
  mobiliario: [
    { tipo: 'mampara', gx: 11, desde: 0.2, hasta: 9.8, vano: [4.6, 6.4] },
    { tipo: 'zona', gx: 4.2, gy: 6.2, ancho: 4.4, fondo: 3.4 },
    { tipo: 'ducto', gy: 5.3, desde: 1.0, hasta: 10.6 },
    { tipo: 'tablero', gy: 7.0 },
    //  Los armarios y el panel de empalmes son de ESTA plantilla. Un centro de
    //  operaciones los tiene; una sala de atención, no.
    { tipo: 'armario', gy: 2.4 },
    { tipo: 'armario', gy: 4.2 },
    { tipo: 'panel_fibra', gy: 6.3 },
    { tipo: 'luminaria', gx: 4, gy: 3 },
    { tipo: 'luminaria', gx: 9, gy: 6 },
    { tipo: 'planta', gx: 12.4, gy: 1.1 },
    { tipo: 'planta', gx: 0.9, gy: 8.9 },
    { tipo: 'planta', gx: 12.3, gy: 6.6 },
    { tipo: 'banco', gx: 11.3, gy: 8.2 },
    { tipo: 'dispensador', gx: 13.0, gy: 4.6 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Supervisión', principal: true, gx: 4.8, gy: 7.4 },
    { id: 'p1', nombre: 'Monitoreo 1', gx: 1.5, gy: 3.4 },
    { id: 'p2', nombre: 'Monitoreo 2', gx: 4.5, gy: 3.4 },
    { id: 'p3', nombre: 'Monitoreo 3', gx: 7.5, gy: 3.4 }
  ]
};

/**
 * Una sala a la que llega gente: dos pantallas de muro y una espera con bancos
 * junto al paso.
 *
 * Lo que la distingue de un centro de operaciones no es el color: no tiene
 * armarios de equipos ni panel de empalmes, y el muro lleva dos pantallas en
 * vez de tres porque acá lo que se mira es una cola, no una red.
 */
const ATENCION = {
  rotulo: 'Sala de atención',
  acento: 0x0ea5a4,
  mundo: { ancho: 13, fondo: 9, alto: 4 },
  pasillo: { desde: 10, hasta: 13 },
  cartel: { gx: 5.2 },
  mural: {
    paneles: [
      { gx: 2.4, ancho: 3.2 },
      { gx: 6.0, ancho: 3.2 }
    ]
  },
  mobiliario: [
    { tipo: 'mampara', gx: 10, desde: 0.2, hasta: 8.8, vano: [3.8, 5.6] },
    { tipo: 'zona', gx: 2.0, gy: 5.6, ancho: 5.0, fondo: 3.0 },
    { tipo: 'ducto', gy: 4.6, desde: 1.0, hasta: 9.6 },
    { tipo: 'tablero', gy: 5.5 },
    { tipo: 'luminaria', gx: 4, gy: 3 },
    { tipo: 'luminaria', gx: 8, gy: 6 },
    { tipo: 'banco', gx: 10.4, gy: 1.2 },
    { tipo: 'banco', gx: 10.4, gy: 6.4 },
    { tipo: 'planta', gx: 11.6, gy: 3.4 },
    { tipo: 'planta', gx: 0.8, gy: 7.8 },
    { tipo: 'planta', gx: 11.5, gy: 8.0 },
    { tipo: 'dispensador', gx: 12.0, gy: 4.6 }
  ],
  puestos: [
    //  Corrido a la izquierda respecto de la fila de atrás: con los dos
    //  alineados, sus placas se montaban una sobre otra y la de delante tapaba
    //  el nombre de la de atrás. En isometría dos puestos con el mismo `gx`
    //  caen en la misma columna de pantalla aunque estén a tres celdas.
    { id: 'principal', nombre: 'Coordinación', principal: true, gx: 2.2, gy: 6.4 },
    { id: 'p1', nombre: 'Atención 1', gx: 1.2, gy: 3.0 },
    { id: 'p2', nombre: 'Atención 2', gx: 4.2, gy: 3.0 },
    { id: 'p3', nombre: 'Atención 3', gx: 7.2, gy: 3.0 }
  ]
};

/**
 * Una sala técnica: poco mobiliario y mucha pantalla.
 *
 * Es la más pequeña del catálogo y es su rasgo —un equipo chico que mira
 * mediciones—. Sin pasillo: una sala chica con una franja de paso se queda sin
 * sitio para trabajar, y el pasillo deja de significar algo.
 */
const TECNICA = {
  rotulo: 'Sala técnica',
  acento: 0x4d9e2a,
  mundo: { ancho: 11, fondo: 8, alto: 4 },
  pasillo: null,
  cartel: { gx: 5.0 },
  mural: { paneles: [{ gx: 3.0, ancho: 4.4 }] },
  mobiliario: [
    { tipo: 'zona', gx: 2.4, gy: 4.6, ancho: 4.6, fondo: 2.8 },
    { tipo: 'ducto', gy: 3.8, desde: 1.0, hasta: 9.8 },
    { tipo: 'estanteria', gy: 4.4, largo: 3.0 },
    { tipo: 'luminaria', gx: 4, gy: 3 },
    { tipo: 'luminaria', gx: 8, gy: 5 },
    { tipo: 'planta', gx: 9.6, gy: 1.0 },
    { tipo: 'planta', gx: 0.8, gy: 7.0 },
    { tipo: 'dispensador', gx: 9.9, gy: 6.4 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Coordinación', principal: true, gx: 3.4, gy: 5.4 },
    { id: 'p1', nombre: 'Puesto 1', gx: 1.6, gy: 2.4 },
    { id: 'p2', nombre: 'Puesto 2', gx: 5.4, gy: 2.4 }
  ]
};

/**
 * Una sala de expedientes: estanterías en los dos muros y NINGUNA pantalla de
 * pared.
 *
 * Esa ausencia es la decisión que más la distingue. Un mural es una sala que
 * mira algo en vivo; acá lo que se mira son cuentas y papeles, y colgarle
 * pantallas habría sido repetir el centro de operaciones con otro color.
 */
const EXPEDIENTES = {
  rotulo: 'Sala de expedientes',
  acento: 0xa855f7,
  mundo: { ancho: 12, fondo: 10, alto: 4 },
  pasillo: { desde: 0, hasta: 2 },
  cartel: { gx: 6.0 },
  mural: null,
  mobiliario: [
    { tipo: 'mampara', gx: 2, desde: 0.2, hasta: 9.8, vano: [4.0, 5.8] },
    { tipo: 'zona', gx: 4.0, gy: 6.0, ancho: 5.0, fondo: 3.4 },
    { tipo: 'estanteria', gy: 1.0, largo: 3.6 },
    { tipo: 'estanteria', gy: 5.2, largo: 3.6 },
    { tipo: 'luminaria', gx: 6, gy: 3 },
    { tipo: 'luminaria', gx: 9, gy: 7 },
    { tipo: 'planta', gx: 0.6, gy: 3.0 },
    { tipo: 'planta', gx: 10.8, gy: 1.0 },
    { tipo: 'banco', gx: 0.4, gy: 7.6 },
    { tipo: 'dispensador', gx: 11.0, gy: 8.4 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Coordinación', principal: true, gx: 4.6, gy: 6.8 },
    { id: 'p1', nombre: 'Gestión 1', gx: 3.0, gy: 3.2 },
    { id: 'p2', nombre: 'Gestión 2', gx: 6.4, gy: 3.2 },
    { id: 'p3', nombre: 'Gestión 3', gx: 9.0, gy: 5.6 }
  ]
};

/**
 * Una sala comercial: mostrador al frente y una antesala de verdad.
 *
 * Es la única con mostrador, y es a propósito: es la sala a la que alguien
 * llega a cerrar algo. Lo que en un centro de operaciones es un pasillo
 * técnico, acá es una espera.
 */
const COMERCIAL = {
  rotulo: 'Sala comercial',
  acento: 0xb8860b,
  mundo: { ancho: 13, fondo: 10, alto: 4 },
  pasillo: { desde: 9, hasta: 13 },
  cartel: { gx: 4.4 },
  mural: { paneles: [{ gx: 2.2, ancho: 2.6 }, { gx: 5.2, ancho: 2.6 }] },
  mobiliario: [
    { tipo: 'mostrador', gx: 6.6, gy: 7.4, largo: 2.6 },
    { tipo: 'mampara', gx: 9, desde: 0.2, hasta: 9.8, vano: [6.6, 8.4] },
    { tipo: 'zona', gx: 1.6, gy: 5.8, ancho: 4.6, fondo: 3.4 },
    { tipo: 'banco', gx: 9.4, gy: 2.0 },
    { tipo: 'banco', gx: 9.4, gy: 5.0 },
    { tipo: 'banco', gx: 11.6, gy: 3.4 },
    { tipo: 'luminaria', gx: 4, gy: 3 },
    { tipo: 'luminaria', gx: 7, gy: 7 },
    { tipo: 'planta', gx: 11.8, gy: 0.8 },
    { tipo: 'planta', gx: 0.8, gy: 9.0 },
    { tipo: 'planta', gx: 10.4, gy: 8.6 },
    { tipo: 'dispensador', gx: 12.0, gy: 6.2 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Cierre', principal: true, gx: 2.2, gy: 6.6 },
    { id: 'p1', nombre: 'Asesoría 1', gx: 1.4, gy: 2.6 },
    { id: 'p2', nombre: 'Asesoría 2', gx: 4.6, gy: 2.6 },
    { id: 'p3', nombre: 'Asesoría 3', gx: 6.6, gy: 4.4 }
  ]
};

/**
 * Una sala de reuniones: mesa en medio y pocos escritorios.
 *
 * Es la más vacía del catálogo y no por descuido — una sala donde se reúne
 * gente tiene menos puestos y más sitio libre. Llenarla de escritorios la
 * habría hecho igual a las demás.
 */
const REUNIONES = {
  rotulo: 'Sala de reuniones',
  acento: 0x2563eb,
  mundo: { ancho: 12, fondo: 9, alto: 4 },
  pasillo: null,
  cartel: { gx: 5.6 },
  mural: null,
  mobiliario: [
    { tipo: 'mesa', gx: 7.6, gy: 4.2 },
    { tipo: 'zona', gx: 1.6, gy: 5.4, ancho: 4.0, fondo: 2.8 },
    { tipo: 'estanteria', gy: 2.0, largo: 4.0 },
    { tipo: 'tablero', gy: 6.4 },
    { tipo: 'luminaria', gx: 3, gy: 3 },
    { tipo: 'luminaria', gx: 8, gy: 4 },
    { tipo: 'planta', gx: 10.6, gy: 0.9 },
    { tipo: 'planta', gx: 0.8, gy: 8.0 },
    { tipo: 'planta', gx: 10.4, gy: 7.6 },
    { tipo: 'banco', gx: 9.6, gy: 1.4 },
    { tipo: 'dispensador', gx: 11.0, gy: 5.6 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Dirección', principal: true, gx: 2.0, gy: 6.0 },
    { id: 'p1', nombre: 'Gestión', gx: 2.2, gy: 2.4 }
  ]
};

/**
 * La sala de cuando la configuración pide una plantilla que no existe.
 *
 * NO es un valor por defecto cómodo: es la alternativa menos mala a dos cosas
 * peores. Dejar el departamento sin dibujar abriría un hueco en el edificio que
 * nadie puede explicar, y caer en silencio a otra plantilla afirmaría que esa
 * sala es un centro de operaciones cuando nadie lo dijo.
 *
 * Es deliberadamente sosa —sin mural, sin mostrador, sin estanterías— para que
 * se vea que falta algo, y quien la usa queda marcado con `plantillaFaltante`
 * para que la ficha pueda decir qué pidió la configuración.
 */
const GENERICA = {
  rotulo: 'Sala sin plantilla',
  acento: 0x64748b,
  mundo: { ancho: 10, fondo: 8, alto: 4 },
  pasillo: null,
  cartel: { gx: 4.6 },
  mural: null,
  mobiliario: [
    { tipo: 'zona', gx: 2.0, gy: 4.6, ancho: 4.0, fondo: 2.8 },
    { tipo: 'luminaria', gx: 3, gy: 3 },
    { tipo: 'luminaria', gx: 7, gy: 5 },
    { tipo: 'planta', gx: 8.6, gy: 1.0 },
    { tipo: 'planta', gx: 0.8, gy: 7.0 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Puesto principal', principal: true, gx: 2.6, gy: 5.2 },
    { id: 'p1', nombre: 'Puesto 1', gx: 2.0, gy: 2.4 }
  ]
};

/** @type {Record<string, Plantilla>} */
export const PLANTILLAS = {
  operaciones: OPERACIONES,
  atencion: ATENCION,
  tecnica: TECNICA,
  expedientes: EXPEDIENTES,
  comercial: COMERCIAL,
  reuniones: REUNIONES,
  generica: GENERICA
};

/** El nombre que se usa cuando la configuración pide una que no está. */
export const PLANTILLA_DE_RESERVA = 'generica';

/**
 * La plantilla que pide un nombre, y si hubo que caer en la de reserva.
 *
 * Devuelve las DOS cosas en vez de solo la plantilla: quien dibuja necesita la
 * geometría, y quien explica necesita saber que esto no es lo que se pidió.
 *
 * @param {string} nombre
 */
export function plantillaDe(nombre) {
  const clave = String(nombre ?? '');
  const hay = Object.prototype.hasOwnProperty.call(PLANTILLAS, clave);
  return {
    plantilla: hay ? PLANTILLAS[clave] : PLANTILLAS[PLANTILLA_DE_RESERVA],
    faltante: hay ? null : clave
  };
}
