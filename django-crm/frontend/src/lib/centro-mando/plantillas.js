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
    { tipo: 'tablero', gy: 0.3 },
    //  Los armarios y el panel de empalmes son de ESTA plantilla. Un centro de
    //  operaciones los tiene; una sala de atención, no.
    { tipo: 'armario', gy: 3.2 },
    { tipo: 'armario', gy: 4.9 },
    { tipo: 'panel_fibra', gy: 6.7 },
    { tipo: 'luminaria', gx: 4, gy: 3 },
    { tipo: 'luminaria', gx: 9, gy: 6 },
    { tipo: 'planta', gx: 12.4, gy: 1.1 },
    { tipo: 'planta', gx: 0.9, gy: 8.9 },
    { tipo: 'planta', gx: 12.3, gy: 6.6 },
    //  La mesa de preparacion: los equipos se alistan antes de salir.
    { tipo: 'mesa', gx: 10.0, gy: 6.0 },
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
    //  La sala que atiende al publico tenia el muro casi vacio y ningun
    //  mostrador. Dos tableros -la cola y los avisos- y el mostrador por
    //  donde se atiende.
    { tipo: 'tablero', gy: 0.2 },
    { tipo: 'estanteria', gy: 3.2, largo: 2.0 },
    { tipo: 'tablero', gy: 5.5 },
    { tipo: 'mostrador', gx: 8.2, gy: 8.2, largo: 2.4 },
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
    //  LO QUE HACE QUE UN NOC SE VEA COMO UN NOC.
    //
    //  Tenía una estantería y nada más -menos equipo que la sala de
    //  expedientes- y el panel de fibra, que es la pieza más técnica del
    //  catálogo, se lo llevaba Operaciones de Campo. Mirando la sede entera no
    //  había forma de distinguir la sala de redes de una oficina cualquiera.
    { tipo: 'panel_fibra', gy: 0.4 },
    { tipo: 'tablero', gy: 2.7 },
    { tipo: 'estanteria', gy: 5.5, largo: 2.2 },
    { tipo: 'luminaria', gx: 4, gy: 3 },
    { tipo: 'luminaria', gx: 8, gy: 5 },
    //  La mesa de trabajo: en un NOC es donde se arma y se prueba un equipo
    //  antes de montarlo.
    { tipo: 'mesa', gx: 7.6, gy: 7.0 },
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
    //  Estanterías Y archivadores: finanzas y auditoría viven de expedientes
    //  guardados, y un armario cerrado dice eso mejor que otro estante.
    { tipo: 'estanteria', gy: 0.8, largo: 3.0 },
    { tipo: 'armario', gy: 4.2 },
    { tipo: 'estanteria', gy: 6.0, largo: 3.0 },
    { tipo: 'luminaria', gx: 6, gy: 3 },
    { tipo: 'luminaria', gx: 9, gy: 7 },
    { tipo: 'planta', gx: 0.6, gy: 3.0 },
    { tipo: 'planta', gx: 10.8, gy: 1.0 },
    //  La mesa de consulta, que es donde se abre un expediente.
    { tipo: 'mesa', gx: 8.6, gy: 8.4 },
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
    //  UN ÁREA DE VENTAS TIENE TABLEROS. No tenía ninguno: el muro estaba
    //  entero vacío y la sala se leía como un pasillo con sillas. Dos, porque
    //  lo que se mira en comercial son números en la pared.
    { tipo: 'tablero', gy: 0.3 },
    { tipo: 'tablero', gy: 3.2 },
    { tipo: 'estanteria', gy: 6.1, largo: 2.6 },
    { tipo: 'mampara', gx: 9, desde: 0.2, hasta: 9.8, vano: [6.6, 8.4] },
    { tipo: 'zona', gx: 1.6, gy: 5.8, ancho: 4.6, fondo: 3.4 },
    //  La mesa donde se sienta el cliente que viene a contratar.
    { tipo: 'mesa', gx: 6.6, gy: 0.9 },
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
    { tipo: 'planta', gx: 11.2, gy: 0.6 },
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
  //  AMUEBLADA, Y NO ES DECORACION.
  //
  //  Tenia cinco muebles -una zona, dos luces y dos plantas- y era la
  //  plantilla de CUATRO de los once departamentos del piloto: Administracion,
  //  Recursos Humanos, Direccion y Recepcion. Mirando la sede entera el
  //  01/11/2026 el veredicto fue «solo veo cuartos separados», y la causa
  //  estaba aca: una sala con dos escritorios y nada mas no se lee como una
  //  oficina, se lee como un cuarto.
  //
  //  Lo que se agrega NO es un puesto. Estanterias, armario, una pantalla de
  //  pared y plantas llenan la sala sin afirmar que trabaja ahi nadie mas: los
  //  escritorios siguen saliendo de lo que la empresa declara, que es la
  //  regla que no se toca.
  mobiliario: [
    { tipo: 'zona', gx: 2.0, gy: 4.6, ancho: 4.0, fondo: 2.8 },
    //  Contra el muro del fondo, que es la pared que se ve entera desde la
    //  camara y la unica que puede llevar algo alto sin tapar la sala.
    //  Los muebles de pared se colocan por `gy` a lo largo del muro: el `gx`
    //  que llevaban antes no lo mira nadie, y los tres quedaban apilados en el
    //  mismo punto del muro dibujando uno solo.
    { tipo: 'tablero', gy: 0.3 },
    { tipo: 'estanteria', gy: 3.1, largo: 1.6 },
    { tipo: 'estanteria', gy: 4.9, largo: 1.2 },
    { tipo: 'armario', gy: 6.3 },
    { tipo: 'mesa', gx: 7.4, gy: 3.2 },
    { tipo: 'luminaria', gx: 3, gy: 3 },
    { tipo: 'luminaria', gx: 7, gy: 5 },
    { tipo: 'luminaria', gx: 5, gy: 1.6 },
    { tipo: 'planta', gx: 8.6, gy: 1.6 },
    { tipo: 'planta', gx: 0.8, gy: 7.0 },
    { tipo: 'banco', gx: 8.8, gy: 5.0 },
    { tipo: 'planta', gx: 9.0, gy: 6.4 }
  ],
  puestos: [
    { id: 'principal', nombre: 'Puesto principal', principal: true, gx: 2.6, gy: 5.2 },
    { id: 'p1', nombre: 'Puesto 1', gx: 2.0, gy: 2.4 }
  ]
};

/**
 * UNA SALA MAS GRANDE, GENERADA. NO COPIADA.
 *
 * Que una empresa pueda decidir cuantos puestos tiene un departamento exigia
 * una de dos cosas: un numero de capacidad -que puede contradecir al dibujo, y
 * entonces o el numero miente o el dibujo miente- o mas salas en el catalogo.
 * Se eligio lo segundo, y se GENERAN: escribir a mano tres tamanos de seis
 * salas son dieciocho geometrias de cuarenta numeros cada una, y equivocarse en
 * uno no da error, da una silla dentro de una pared.
 *
 * CRECEN A LO ANCHO, Y ESO NO ES ESTETICA. La separacion entre pisos del
 * edificio salio de invertir la proyeccion isometrica: un puesto a altura `z`
 * de un nivel queda tapado por el nivel de arriba cuando
 *
 *     (ALTURA_DE_PISO - z) * 0.8125  <=  fondo de la sala - gy del puesto
 *
 * `gx` NO aparece en esa condicion. Crecer en FONDO empeora los dos lados de la
 * desigualdad a la vez -mas fondo y, si la fila nueva va mas atras, menos gy- y
 * los escritorios del nuevo tamano se esconderian bajo el piso de arriba sin un
 * error que lo explique: la escena los seguiria animando donde nadie los ve.
 * Crecer en ANCHO es gratis. Por eso la fila se estira y la sala se ensancha.
 *
 * QUE SE CORRE Y QUE NO. Lo que esta en la mitad derecha se aleja; lo que esta
 * en la izquierda se queda, y la fila nueva llena el hueco. El cartel se
 * reubica proporcional -es el nombre de la sala y tiene que seguir centrado-, y
 * un mueble que ATRAVIESA la sala -un ducto- se estira hasta el muro nuevo.
 *
 * @param {Plantilla} base
 * @param {number} extra cuantos puestos de mas
 * @returns {Plantilla}
 */
function ampliar(base, extra) {
  const secundarios = base.puestos.filter((p) => !p.principal);

  //  La fila mas larga es la que se estira. Una sala puede tener los puestos
  //  repartidos -expedientes tiene dos atras y uno al costado-, y estirar la
  //  del costado dejaria la sala creciendo en diagonal.
  const filas = new Map();
  for (const p of secundarios) {
    if (!filas.has(p.gy)) filas.set(p.gy, []);
    filas.get(p.gy).push(p);
  }
  const fila = [...filas.values()]
    .sort((a, b) => b.length - a.length || a[0].gy - b[0].gy)[0]
    .slice()
    .sort((a, b) => a.gx - b.gx);

  //  La separacion sale de la sala misma, no de una constante: cada plantilla
  //  tiene su escala y un numero fijo apretaria unas y desparramaria otras.
  const sep = fila.length > 1 ? Number((fila[1].gx - fila[0].gx).toFixed(2)) : 3.2;

  //  CUANTO BAJA UNA FILA NUEVA. Sale de la sala, igual que `sep`: si ya tiene
  //  dos filas, la distancia entre ellas; si no, lo que ocupa un escritorio con
  //  su silla y el paso de atras.
  const gys = [...filas.keys()].sort((x, y) => x - y);
  const paso = gys.length > 1
    ? Number(Math.abs(gys[1] - gys[0]).toFixed(2))
    : 3.2;

  //  UNA SALA NO SE ESTIRA SIN LIMITE, SE LLENA EN FILAS.
  //
  //  La primera version metia TODOS los puestos nuevos en la misma fila. Con
  //  los tamanos chicos no se notaba, pero el dia que una empresa declare
  //  veinte agentes en un departamento, `tecnica_21` mediria 78 celdas de
  //  ancho: eso no es una oficina, es un pasillo con escritorios. Y en una
  //  planta unica -donde todos los departamentos comparten el plano- una sala
  //  asi se come el edificio entero.
  //
  //  Seis es el maximo que se estira la fila existente; a partir de ahi se
  //  abren filas nuevas hacia el frente y la sala crece en fondo.
  const MAX_EXTRA_POR_FILA = 6;
  const enLaFilaLarga = Math.min(extra, MAX_EXTRA_POR_FILA);
  const porFila = fila.length + enLaFilaLarga;
  const alFondo = Math.max(0, extra - enLaFilaLarga);
  const filasNuevas = Math.ceil(alFondo / porFila);

  const delta = Number((enLaFilaLarga * sep).toFixed(2));
  const mitad = base.mundo.ancho / 2;
  const ancho = Number((base.mundo.ancho + delta).toFixed(2));
  const correr = (gx) => (gx > mitad ? Number((gx + delta).toFixed(2)) : gx);

  //  LA FILA QUE SE ESTIRA NO SE CORRE. Correrla ademas de estirarla pone el
  //  ultimo escritorio viejo exactamente encima del ultimo nuevo -- `p3` y `p6`
  //  en el mismo punto, que dibuja uno solo y muestra la oficina con menos
  //  gente de la que tiene. Lo cazo la guarda de solapamiento al generar
  //  `operaciones_7` por primera vez; sin ella habria entrado derecho.
  const enLaFila = new Set(fila.map((p) => p.id));

  //  Los nombres siguen el patron de la sala: «Atencion 1, 2, 3» sigue en 4, y
  //  una fila sin numero cae en «Puesto N». Inventar un vocabulario propio
  //  haria que la cuarta silla se llamara distinto que las tres de al lado.
  const ultimo = fila[fila.length - 1];
  const raiz = String(ultimo.nombre ?? '').replace(/\s*\d+\s*$/, '').trim() || 'Puesto';
  const desde = secundarios.length;

  const nuevos = [];
  const lamparas = [];
  for (let k = 1; k <= extra; k++) {
    let gx, gy;
    if (k <= enLaFilaLarga) {
      //  Los primeros estiran la fila que ya estaba.
      gx = Number((ultimo.gx + k * sep).toFixed(2));
      gy = ultimo.gy;
    } else {
      //  Y el resto abre filas nuevas por delante, alineadas con la primera
      //  columna: asi los escritorios quedan en rejilla y no escalonados.
      const i = k - enLaFilaLarga - 1;
      gx = Number((fila[0].gx + (i % porFila) * sep).toFixed(2));
      gy = Number((ultimo.gy + (Math.floor(i / porFila) + 1) * paso).toFixed(2));
    }
    nuevos.push({ id: `p${desde + k}`, nombre: `${raiz} ${desde + k}`, gx, gy });
    //  Una luminaria cada dos puestos nuevos: sin esto la mitad agregada queda
    //  a oscuras y parece un deposito, no una oficina.
    if (k % 2 === 1) lamparas.push({ tipo: 'luminaria', gx: Math.round(gx), gy: Math.round(gy + 0.6) });
  }

  const mueble = (m) => {
    //  Un mueble CON `gx` esta puesto en un punto: se corre. Sus `desde`/`hasta`
    //  son el otro eje -una mampara va de gy a gy- y tocarlos la rotaria.
    if (typeof m.gx === 'number') return { ...m, gx: correr(m.gx) };
    //  Sin `gx`, un `desde`/`hasta` recorre la sala a lo ancho: se estira.
    if (typeof m.hasta === 'number') return { ...m, hasta: correr(m.hasta) };
    return { ...m };
  };

  //  LA MITAD AGREGADA NO PUEDE QUEDAR VACIA. Estirar la fila y correr lo de
  //  la derecha deja en medio una franja de suelo pelado del ancho de los
  //  puestos nuevos: en el navegador se lee como un deposito, no como una
  //  oficina. Asi que lo que se repite a lo largo de una oficina se repite:
  //  estanterias y plantas. Lo UNICO -un dispensador, un mostrador, un rack-
  //  no, porque dos dispensadores en una sala no son mas sala.
  //
  //  SE CALCULAN CONTRA LAS POSICIONES FINALES Y NO CONTRA LAS DE LA BASE.
  //  Con las de la base, una copia caia exactamente encima del mueble original
  //  ya corrido -- `operaciones_7` tenia 11 puntos distintos para 13 muebles,
  //  y dos muebles en el mismo punto dibujan uno solo. Lo cazo la guarda de
  //  solapamiento; a ojo no se habria visto nunca.
  const REPETIBLES = new Set(['estanteria', 'planta']);
  const finales = base.mobiliario.map(mueble);
  const ocupados = finales
    .filter((m) => typeof m.gx === 'number')
    .map((m) => ({ tipo: m.tipo, gx: m.gx, gy: m.gy }));
  const copias = [];
  for (const m of finales) {
    if (!REPETIBLES.has(m.tipo) || typeof m.gx !== 'number') continue;
    for (let k = 1; k <= Math.ceil(extra / 3); k++) {
      const gx = Number((m.gx + k * sep * 3).toFixed(2));
      if (gx > ancho - 0.6) continue;
      const choca = ocupados.some(
        (o) => o.tipo === m.tipo && Math.abs(o.gx - gx) < 1 && o.gy === m.gy);
      if (choca) continue;
      //  Y NO ENCIMA DE UN PUESTO NUEVO. La copia se calculaba contra los
      //  muebles y no contra las sillas que acababa de abrir la ampliacion:
      //  en `expedientes_7` una planta quedaba a una unidad del escritorio
      //  `p4`, tapando a quien trabaja ahi, que es el unico elemento de la
      //  sala que no es decoracion. Lo cazo la guarda de solapes del suelo; a
      //  ojo no se habria visto, porque solo pasa en los tamanos generados.
      const sobrePuesto = nuevos.some(
        (q) => Math.hypot(q.gx - gx, q.gy - (m.gy ?? 0)) < 1.7);
      if (sobrePuesto) continue;
      ocupados.push({ tipo: m.tipo, gx, gy: m.gy });
      copias.push({ ...m, gx });
    }
  }

  return {
    ...base,
    rotulo: `${base.rotulo} · ${base.puestos.length + extra} puestos`,
    //  El fondo crece con las filas nuevas; el ancho, solo con lo que se
    //  estiro la fila larga.
    mundo: {
      ...base.mundo,
      ancho,
      fondo: Number((base.mundo.fondo + filasNuevas * paso).toFixed(2))
    },
    pasillo: base.pasillo
      ? { desde: correr(base.pasillo.desde), hasta: correr(base.pasillo.hasta) }
      : null,
    //  Proporcional y no `correr`: el cartel nombra la sala y tiene que quedar
    //  centrado, no pegado a la pared que no se movio.
    cartel: { ...base.cartel, gx: Number((base.cartel.gx * ancho / base.mundo.ancho).toFixed(2)) },
    mural: base.mural
      ? { ...base.mural, paneles: base.mural.paneles.map((p) => ({ ...p, gx: correr(p.gx) })) }
      : base.mural,
    mobiliario: [...finales, ...copias, ...lamparas],
    puestos: [
      ...base.puestos.map((p) => (enLaFila.has(p.id) ? { ...p } : { ...p, gx: correr(p.gx) })),
      ...nuevos
    ]
  };
}

//  Cuantos puestos de mas tiene cada tamano. Dos y no cinco: el catalogo se
//  elige de una lista desplegable, y veinte opciones no son mas libertad que
//  seis -- son veinte lineas para leer antes de elegir.
//
//  Y SE QUEDA EN DOS, aunque el 01/11/2026 se decidiera que una empresa crea
//  mas agentes a medida que crece. Ampliar la lista rompia dos cosas a la vez:
//  este catalogo lo comparte el motor Python -que no se toca- y las variantes
//  de aca NO crecen hacia el fondo a proposito. Lo que se agrego en su lugar
//  es `plantillaPara()`, que DERIVA el tamano de cuantos agentes declara el
//  departamento sin inventar nombres nuevos de configuracion.
const TAMANOS = [3, 6];

/**
 * El catalogo con sus tamanos.
 *
 * La clave es `<base>_<total de puestos>`, que es lo que se guarda en la
 * configuracion de la empresa: `tecnica_6` dice sola que sala es y de que
 * tamano, y el dia que alguien lea el documento crudo no tiene que buscar una
 * tabla para entenderlo.
 */
function conTamanos(catalogo) {
  const salida = {};
  for (const [nombre, base] of Object.entries(catalogo)) {
    salida[nombre] = base;
    //  La generica no se amplia: es la sala a la que se cae cuando la
    //  plantilla pedida no existe, y ofrecer tamanos de una sala de reserva
    //  seria ofrecer elegir el error.
    if (nombre === 'generica') continue;
    for (const extra of TAMANOS) {
      salida[`${nombre}_${base.puestos.length + extra}`] = ampliar(base, extra);
    }
  }
  return salida;
}

/** @type {Record<string, Plantilla>} */
export const PLANTILLAS = conTamanos({
  operaciones: OPERACIONES,
  atencion: ATENCION,
  tecnica: TECNICA,
  expedientes: EXPEDIENTES,
  comercial: COMERCIAL,
  reuniones: REUNIONES,
  generica: GENERICA
});

/** El nombre que se usa cuando la configuración pide una que no está. */
export const PLANTILLA_DE_RESERVA = 'generica';

/**
 * La plantilla que le hace falta a un departamento con `cuantos` agentes.
 *
 * POR QUE NO ALCANZA CON LA QUE DECLARA LA CONFIGURACION
 * -----------------------------------------------------
 * El 01/11/2026 se fijo una regla de producto: **una empresa crea mas agentes
 * a medida que crece.** Medido contra lo que habia ese dia, diez agentes en un
 * departamento con plantilla `atencion` dejaban SIETE sin silla, y veinte no
 * entraban ni en `atencion_10`, la variante mayor del catalogo. Los agentes no
 * desaparecian en silencio -`ocupacionesSinSilla()` los nombra- pero la
 * oficina no crecia sola: habia que editar el YAML a mano cada vez. Eso es
 * exactamente lo que CLAUDE.md §3.3 prohibe.
 *
 * Asi que el tamano deja de elegirse y pasa a DERIVARSE. La configuracion
 * sigue declarando QUE clase de sala es -`atencion`, `tecnica`- y cuantos
 * agentes tiene; de ahi sale cuanta sala hace falta.
 *
 * TRES COSAS QUE ESTA FUNCION NO HACE, y cada una tiene su motivo:
 *
 * 1. **No achica.** Si la configuracion pide `atencion_10` y hoy hay dos
 *    agentes, la sala sigue siendo de diez: la empresa pidio ese tamano y una
 *    oficina que se encoge cuando alguien se va es una oficina que se mueve
 *    sola.
 * 2. **No inventa nombres de configuracion.** El catalogo con sus `_7` y `_10`
 *    lo comparte el motor Python, que no se toca. Las salas mas grandes se
 *    construyen al vuelo y no se registran: no son una opcion que elegir, son
 *    el resultado de un dato.
 * 3. **No cambia la clase de sala.** Un departamento tecnico con veinte
 *    agentes sigue siendo tecnico, con su acento y su mobiliario.
 *
 * Y UNA ADVERTENCIA QUE IMPORTA: las salas que esta funcion construye por
 * encima del catalogo **crecen hacia el fondo**, y eso solo es correcto en una
 * planta unica. En el edificio apilado de `edificio.js`, mas fondo es un
 * escritorio detras de la losa de arriba -la desigualdad esta escrita en ese
 * archivo-. La decision del 01/11/2026 de poner todos los departamentos en una
 * sola planta es la que lo habilita.
 *
 * @param {string} nombre el que declara la configuracion
 * @param {number} cuantos cuantos agentes tiene declarados el departamento
 */
export function plantillaPara(nombre, cuantos) {
  const { plantilla, faltante } = plantillaDe(nombre);
  const hacenFalta = Number.isFinite(cuantos) ? Math.max(0, Math.trunc(cuantos)) : 0;
  const tiene = plantilla.puestos.length;
  if (hacenFalta <= tiene) return { plantilla, faltante, derivada: false };

  //  LA DE RESERVA NO SE AMPLIA CUANDO ES RESERVA, y SI cuando la eligieron.
  //
  //  Las dos cosas son la misma sala y hay que distinguirlas, porque `faltante`
  //  dice cual de las dos paso. Si la configuracion pidio una plantilla que no
  //  existe, agrandar la sala en la que se cayo seria agrandar el error -y el
  //  aviso de `faltante` ya viaja-. Pero `generica` tambien se declara a
  //  proposito: en la empresa del piloto la usan Administracion, Recursos
  //  Humanos, Direccion y Recepcion. Esos departamentos tienen el mismo derecho
  //  a crecer que cualquier otro, y no darselo dejaria sin crecer justo a los
  //  que mas probable es que empiecen chicos.
  if (faltante !== null) return { plantilla, faltante, derivada: false };

  //  Se amplia desde la BASE y no desde la variante declarada: ampliar dos
  //  veces estiraria la fila ya estirada y dejaria los puestos nuevos sobre
  //  los viejos. `ampliar` cuenta desde la base y eso es lo que espera.
  const base = PLANTILLAS[String(nombre ?? '').replace(/_\d+$/, '')] ?? plantilla;
  return {
    plantilla: ampliar(base, hacenFalta - base.puestos.length),
    faltante,
    derivada: true
  };
}

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
