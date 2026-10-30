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
  //  Lo que el motor sirve por agente es `rol.area`, TEXTO LIBRE, y no coincide
  //  con los identificadores de `config.areas`. `supervisor_noc` declara
  //  «Operaciones»; el área configurada se llama `operativo`. Con solo el id y
  //  el rótulo, esta sala salía VACÍA en producción — medido contra el YAML del
  //  tenant el 30/10/2026, no deducido.
  //
  //  Así que las etiquetas aceptadas son un DATO del departamento. Se declaran;
  //  no se adivinan. El día que una empresa escriba otra cosa, se agrega acá.
  areas: ['operativo', 'Operaciones', 'NOC y Redes'],
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
  id: 'atencion_cliente',
  rotulo: 'Atención al Cliente',
  direccion: 'Dirección de Servicio',
  //  «Atención al Cliente» existe en el vocabulario de los ROLES y NO tiene
  //  entrada en `config.areas`: los dos vocabularios no solo se escriben
  //  distinto, tienen miembros distintos. Por eso este departamento lleva un
  //  identificador propio.
  areas: ['Atención al Cliente', 'atencion_cliente'],
  planta: {
    //  LOS SEIS ACENTOS SE ELIGIERON MIDIENDO, NO A OJO.
    //
    //  La configuración del tenant declara un color por área —Ventas en
    //  `#d97706`, Cartera en `#7c5cd6`— y la escena NO los usa tal cual. El
    //  naranja de Ventas quedaba a 143 de distancia del rojo de alarma y la
    //  guarda lo rechazó: una sala tranquila se habría leído como una sala en
    //  alarma. Los seis están ahora a más de 160 de ese rojo y a más de 70
    //  entre sí.
    //
    //  Queda anotado porque es una divergencia deliberada con la configuración
    //  de la empresa, no un descuido: el color de un área en una lista y el
    //  color de una sala entera iluminada no pueden elegirse con el mismo
    //  criterio.
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


/**
 * Soporte Técnico. La sala del diagnóstico: poco mobiliario y mucha pantalla.
 *
 * Es la más pequeña de las seis, y es su rasgo: un equipo chico que mira
 * mediciones. Sin pasillo —se entra por el vano del muro— y con una estantería
 * de expedientes contra el lateral.
 */
const SOPORTE = {
  id: 'soporte_tecnico',
  rotulo: 'Soporte Técnico',
  direccion: 'Dirección de Servicio',
  areas: ['soporte_tecnico', 'Soporte Técnico'],
  planta: {
    acento: 0x4d9e2a,
    mundo: { ancho: 11, fondo: 8, alto: 4 },
    //  Sin pasillo: una sala chica con una franja de paso se queda sin sitio
    //  para trabajar, y el pasillo deja de significar algo.
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
      { id: 'soporte-diagnostico', nombre: 'Diagnóstico', principal: true, gx: 3.4, gy: 5.4 },
      { id: 'soporte-1', nombre: 'Soporte 1', gx: 1.6, gy: 2.4 },
      { id: 'soporte-2', nombre: 'Soporte 2', gx: 5.4, gy: 2.4 }
    ]
  }
};

/**
 * Facturación y Cartera. La sala del papel: estanterías en los dos muros y
 * NINGUNA pantalla de pared.
 *
 * Esa ausencia es la decisión que más la distingue. Un mural es una sala que
 * mira algo en vivo; acá lo que se mira son cuentas, y colgarle pantallas
 * habría sido repetir el NOC con otro color.
 */
const CARTERA = {
  id: 'cartera',
  rotulo: 'Facturación y Cartera',
  direccion: 'Dirección Financiera',
  areas: ['cartera', 'Facturación', 'Cartera'],
  planta: {
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
      { id: 'cartera-coordinacion', nombre: 'Coordinación', principal: true, gx: 4.6, gy: 6.8 },
      { id: 'cartera-1', nombre: 'Cobranza 1', gx: 3.0, gy: 3.2 },
      { id: 'cartera-2', nombre: 'Cobranza 2', gx: 6.4, gy: 3.2 },
      { id: 'cartera-3', nombre: 'Cobranza 3', gx: 9.0, gy: 5.6 }
    ]
  }
};

/**
 * Ventas. La sala que recibe gente: mostrador al frente y una espera de verdad.
 *
 * Es la única con mostrador, y es a propósito — es el departamento al que
 * alguien llega. Lo que en el NOC es un pasillo técnico, acá es una antesala.
 */
const VENTAS = {
  id: 'ventas',
  rotulo: 'Ventas',
  direccion: 'Dirección Comercial',
  areas: ['ventas', 'Ventas'],
  planta: {
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
      { id: 'ventas-cierre', nombre: 'Cierre', principal: true, gx: 2.2, gy: 6.6 },
      { id: 'ventas-1', nombre: 'Asesoría 1', gx: 1.4, gy: 2.6 },
      { id: 'ventas-2', nombre: 'Asesoría 2', gx: 4.6, gy: 2.6 },
      { id: 'ventas-3', nombre: 'Asesoría 3', gx: 6.6, gy: 4.4 }
    ]
  }
};

/**
 * Administración. La sala de las decisiones: mesa de reunión en medio y un
 * único puesto.
 *
 * Es la más vacía de las seis y no por descuido — un departamento donde se
 * reúne gente tiene menos escritorios y más sitio libre. Llenarla de puestos
 * habría sido hacerla igual a las demás.
 */
const ADMINISTRACION = {
  id: 'administracion',
  rotulo: 'Administración',
  direccion: 'Dirección General',
  areas: ['administracion', 'Administración'],
  planta: {
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
      { id: 'admin-direccion', nombre: 'Dirección', principal: true, gx: 2.0, gy: 6.0 },
      { id: 'admin-1', nombre: 'Gestión', gx: 2.2, gy: 2.4 }
    ]
  }
};

/** Los departamentos que la oficina virtual sabe mostrar hoy. */
export const DEPARTAMENTOS = [NOC, ATENCION, SOPORTE, CARTERA, VENTAS, ADMINISTRACION];

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
  //  Las etiquetas que este departamento acepta. Si no las declara, se cae a
  //  su identificador y su rótulo — que es lo que había antes y lo que dejaba
  //  al NOC vacío en producción.
  const declaradas = depto.areas ?? [depto.id, depto.rotulo];
  const buscadas = new Set(declaradas.map(normalizar));
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

/**
 * LA PLANTA DE LA EMPRESA ENTERA: las seis salas a la vez.
 *
 * Hasta acá la oficina virtual se miraba de una sala en una. Juntas son otra
 * cosa — se ve la empresa, no un departamento— y es lo que da sentido al
 * nombre.
 *
 * EL REPARTO DEJA PASILLO ENTRE SALAS, Y NO ES ESTÉTICO. La escena ordena las
 * salas por la profundidad de su origen y dentro de cada una por la suya: eso
 * es correcto mientras dos salas no se solapen en la rejilla. Si se tocaran,
 * habría que intercalar sus objetos uno a uno, y eso la escena no lo hace. El
 * hueco es lo que mantiene cierta la simplificación.
 *
 * El reparto se calcula, no se escribe a mano: las salas no miden lo mismo, y
 * una rejilla con coordenadas fijas se descuadra en cuanto alguien cambie el
 * tamaño de una.
 *
 * @param {any[]} agentes inventario del motor
 * @param {number} columnas cuántas salas por fila
 */
export function plantaDeLaEmpresa(agentes, columnas = 3) {
  //  Cinco celdas, no tres. Con tres los muros de una sala se metían dentro de
  //  la vecina: en isometría un muro de cuatro unidades de alto se proyecta
  //  más de cien píxeles hacia arriba, y eso invade la sala de atrás aunque en
  //  planta no se toquen. El hueco se mide contra la ALTURA, no contra el
  //  suelo.
  const SEPARACION = 5;
  //  Cada columna es tan ancha como su sala más ancha, y cada fila tan honda
  //  como su sala más honda. Así ninguna invade a su vecina por mucho que
  //  crezca.
  const anchoDeColumna = [];
  const fondoDeFila = [];
  DEPARTAMENTOS.forEach((d, i) => {
    const c = i % columnas;
    const f = Math.floor(i / columnas);
    anchoDeColumna[c] = Math.max(anchoDeColumna[c] ?? 0, d.planta.mundo.ancho);
    fondoDeFila[f] = Math.max(fondoDeFila[f] ?? 0, d.planta.mundo.fondo);
  });

  const desplazamientoX = [];
  const desplazamientoY = [];
  let acumulado = 0;
  anchoDeColumna.forEach((w, c) => {
    desplazamientoX[c] = acumulado;
    acumulado += w + SEPARACION;
  });
  acumulado = 0;
  fondoDeFila.forEach((h, f) => {
    desplazamientoY[f] = acumulado;
    acumulado += h + SEPARACION;
  });

  return DEPARTAMENTOS.map((d, i) => ({
    ...plantaDe(d, agentes),
    origen: {
      gx: desplazamientoX[i % columnas],
      gy: desplazamientoY[Math.floor(i / columnas)]
    }
  }));
}
