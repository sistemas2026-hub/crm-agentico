/**
 * LOS DEPARTAMENTOS DE LA EMPRESA VIRTUAL, Y SU PLANTA.
 *
 * Reemplaza a `noc.js`, que decía dentro de sí mismo que iba a desaparecer en
 * cuanto hubiera un segundo departamento. Ya lo hay, y desapareció.
 *
 * QUÉ CAMBIÓ, Y POR QUÉ IMPORTA MÁS QUE LA SALA NUEVA
 * La geometría de la oficina era código: la escena tenía escrito un mundo de
 * 14 × 10, un pasillo en una franja fija y una lista de muebles con sus
 * coordenadas. Servía para UNA sala. Ahora la escena recibe la planta como
 * dato, sabe dibujar TIPOS de mueble y no sabe qué departamento está
 * construyendo.
 *
 * La prueba de que eso valía la pena es que el segundo departamento no toca una
 * línea de `escena/`: es este archivo y nada más.
 *
 * DÓNDE VIVE ESTO DE VERDAD
 * Acá sigue siendo código, y no es el sitio definitivo. Lo que varía por
 * empresa —cuántos departamentos tiene, cuántos puestos, dónde— es
 * configuración, y la regla de esta casa es que dar de alta un ISP sea una fila
 * en una tabla y un archivo en una carpeta.
 *
 * Lo que SÍ está resuelto es la forma: una planta ya es un documento de datos
 * que se puede guardar y editar. Moverlo a `tenant_config` es cambiar de dónde
 * se lee, no rediseñarlo. Mientras tanto esto es la semilla, igual que
 * `tenants/<slug>.config.yaml` lo es de la configuración.
 *
 * LOS IDENTIFICADORES NO SE RENOMBRAN
 * `operativo` y `soporte_tecnico` son los que ya existen en la configuración y
 * en los datos. «NOC y Redes» y «Atención al Cliente» son cómo se llaman en la
 * organización. Renombrar el identificador daría un rótulo bonito y perdería la
 * continuidad de todo lo registrado con el nombre viejo.
 */

/**
 * @typedef {{ id: string, rotulo: string, direccion: string,
 *             planta: any }} Departamento
 */

/** El NOC. La primera sala, y la que fijó la calidad visual. */
const NOC = {
  id: 'operativo',
  rotulo: 'NOC y Redes',
  direccion: 'Dirección de Operaciones',
  planta: {
    //  Índigo: el color de la acción del producto. La primera sala se queda
    //  con él porque es la que fijó la identidad visual.
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
      // Los armarios y el panel de empalmes son de ESTA sala. Un centro de
      // operaciones de red los tiene; una sala de atención, no.
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
      { id: 'noc-supervision', nombre: 'Supervisión', principal: true, gx: 4.8, gy: 7.4 },
      { id: 'noc-monitoreo-1', nombre: 'Monitoreo 1', gx: 1.5, gy: 3.4 },
      { id: 'noc-monitoreo-2', nombre: 'Monitoreo 2', gx: 4.5, gy: 3.4 },
      { id: 'noc-monitoreo-3', nombre: 'Monitoreo 3', gx: 7.5, gy: 3.4 }
    ]
  }
};

/**
 * Atención al Cliente. La segunda sala, y la que prueba que el motor sirve.
 *
 * NO es el NOC con otro rótulo, y eso es deliberado: si las dos salas se vieran
 * iguales, la oficina virtual no estaría representando a la empresa, estaría
 * repitiendo un fondo. Lo que la distingue es lo que una sala de atención
 * tiene y un centro de operaciones no —una espera con bancos junto al paso— y
 * lo que no tiene: ni armarios de equipos ni panel de empalmes. El muro lleva
 * dos pantallas en vez de tres, porque acá lo que se mira es una cola, no una
 * red.
 */
const ATENCION = {
  id: 'soporte_tecnico',
  rotulo: 'Atención al Cliente',
  direccion: 'Dirección de Servicio',
  planta: {
    //  Verde azulado. Distinto del NOC de un vistazo y a la misma distancia
    //  del rojo de un fallo, que es lo que no puede cambiar de sala en sala.
    acento: 0x1f7a6b,
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
      // La espera: dos bancos junto al paso. Es lo que hace que la sala se lea
      // como un sitio al que llega gente.
      { tipo: 'banco', gx: 10.4, gy: 1.2 },
      { tipo: 'banco', gx: 10.4, gy: 6.4 },
      { tipo: 'planta', gx: 11.6, gy: 3.4 },
      { tipo: 'planta', gx: 0.8, gy: 7.8 },
      { tipo: 'planta', gx: 11.5, gy: 8.0 },
      { tipo: 'dispensador', gx: 12.0, gy: 4.6 }
    ],
    puestos: [
      // Corrido a la izquierda respecto de la fila de atrás: con los dos
      // alineados, sus placas se montaban una sobre otra y la de delante
      // tapaba el nombre de la de atrás. En isometría dos puestos con el
      // mismo `gx` caen en la misma columna de pantalla aunque estén a tres
      // celdas de distancia.
      { id: 'atencion-coordinacion', nombre: 'Coordinación', principal: true, gx: 2.2, gy: 6.4 },
      { id: 'atencion-1', nombre: 'Atención 1', gx: 1.2, gy: 3.0 },
      { id: 'atencion-2', nombre: 'Atención 2', gx: 4.2, gy: 3.0 },
      { id: 'atencion-3', nombre: 'Atención 3', gx: 7.2, gy: 3.0 }
    ]
  }
};

/** Los departamentos que la oficina virtual sabe mostrar hoy. */
export const DEPARTAMENTOS = [NOC, ATENCION];

/** @param {string} id */
export function departamentoPorId(id) {
  return DEPARTAMENTOS.find((d) => d.id === id) ?? DEPARTAMENTOS[0];
}

/**
 * Compara rótulos de área sin acentos, mayúsculas ni separadores.
 *
 * Hace falta porque **hay dos vocabularios de área y no coinciden**: la
 * configuración declara identificadores (`operativo`, `soporte_tecnico`) y el
 * campo `area` de cada rol es texto libre. Lo encontró el inventario de la Fase
 * 0 y sigue abierto.
 *
 * Lo que NO hace es adivinar: no acepta parecidos ni sinónimos. Aceptar
 * «operaciones» como `operativo` serviría hoy y el día que una empresa tenga
 * las dos cosas sentaría al agente equivocado en el puesto, sin un error que lo
 * explique.
 */
function normalizar(texto) {
  return String(texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/**
 * Los agentes de un departamento, en orden estable.
 *
 * Un orden estable es lo que hace que la sala se vea igual en dos cargas
 * seguidas. Y no muta el arreglo que recibe: `sort` lo haría, y el resto de la
 * pantalla vería los agentes en otro orden sin motivo.
 *
 * @param {any[]} agentes el inventario tal como lo sirve el motor
 * @param {Departamento} depto
 */
export function agentesDe(agentes, depto) {
  const lista = Array.isArray(agentes) ? agentes : [];
  const buscadas = new Set([normalizar(depto.id), normalizar(depto.rotulo)]);
  return [...lista]
    .filter((a) => a && buscadas.has(normalizar(a.area)))
    .sort((a, b) => String(a.nombre).localeCompare(String(b.nombre)))
    .map((a) => ({
      nombre: String(a.nombre),
      rotulo: a.cargo || String(a.nombre),
      area: depto.id
    }));
}

/**
 * La planta lista para dibujar: geometría del departamento + quién la ocupa.
 *
 * Los agentes se sientan en orden, el primero en el puesto principal. Un puesto
 * sin agente se dibuja VACÍO y lo dice: inventarle un ocupante para que la
 * escena no se vea sosa es la clase de afirmación que esta pantalla no puede
 * permitirse.
 *
 * @param {Departamento} depto
 * @param {any[]} agentes inventario del motor
 */
export function plantaDe(depto, agentes) {
  const suyos = agentesDe(agentes, depto);
  const puestos = depto.planta.puestos.map((p, i) => {
    const agente = suyos[i] ?? null;
    return {
      ...p,
      agente: agente?.nombre ?? null,
      //  Ocupado: el cargo del agente. Libre: el nombre del PUESTO, que lo
      //  pone la planta. Un «Puesto 3» genérico no le dice a nadie para qué
      //  está ese escritorio, y el nombre del sitio sobrevive a quien lo ocupa.
      nombre: agente?.rotulo || p.nombre || (p.principal ? 'Puesto principal' : `Puesto ${i}`),
      area: agente ? depto.rotulo : 'puesto libre'
    };
  });
  return {
    ...depto.planta,
    cartel: { ...depto.planta.cartel, rotulo: depto.rotulo },
    puestos
  };
}
