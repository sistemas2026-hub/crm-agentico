/**
 * Geometria de la PLANTA DE OFICINA: donde va cada puesto y cuanto mide.
 *
 * Es la hermana de disposicion.js -- aquella coloca los agentes en un anillo,
 * esta los coloca en una rejilla isometrica. Las dos viven fuera de los
 * componentes por el mismo motivo: son calculo con bordes (cero agentes, uno,
 * doce, un lienzo angosto) y eso se prueba; el dibujo se mira.
 *
 * LA REGLA QUE GOBIERNA TODO ESTE ARCHIVO
 * No hay una sola constante de posicion. Cuantos agentes tiene una empresa lo
 * decide la empresa (CLAUDE.md §3.3), y esa es exactamente la falla que tumbo
 * el primer centro de mando: se veia bien con seis y se rompia con ocho. La
 * rejilla, la escala y el tamano del puesto se derivan de cuantos son y del
 * lienzo que hay.
 *
 * LO QUE COSTO CADA PIEZA (medido sobre el prototipo, 24-25/09/2026)
 *  - El bounding box de la rejilla se mide con (cols-1)+(filas-1) pasos, no
 *    con (cols+filas): con esa cuenta el conjunto medido era mayor que el
 *    dibujado y quedaba descentrado, con un tercio del piso vacio abajo.
 *  - El puesto se extiende media anchura a la IZQUIERDA de su celda, asi que
 *    hay que correr la rejilla por esa saliente o la primera columna se sale
 *    del lienzo.
 *  - El ancho por caracter depende del CUERPO DE LETRA y de si el texto va en
 *    mayusculas (~0.72em) o no (~0.62em). Un factor unico para los dos
 *    recortaba "ATENCION AL CLIENTE" con sitio de sobra.
 */

/**
 * La proyeccion isometrica, con la elevacion como parametro.
 *
 * 30 grados es la isometria clasica. Subirla APLANA la escena pero separa las
 * filas en pantalla -- a 30 grados cada fila baja (x+y)*0.5, a 40 baja
 * (x+y)*0.64 -- y eso decide si el rotulo de un puesto pisa al de atras.
 * Bajarla da mas volumen y menos aire. Es un intercambio, no una mejora, y
 * por eso es un parametro y no una constante.
 *
 * @param {number} grados
 * @returns {{ ex: number, ey: number }} los dos factores de la proyeccion
 */
export function ejes(grados = 34) {
  const r = (grados * Math.PI) / 180;
  return { ex: Math.cos(r), ey: Math.sin(r) };
}

/**
 * Un punto del espacio, proyectado. `z` sube en pantalla sin mover en planta:
 * es lo que permite que un escritorio tenga volumen.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} z
 * @param {{ ex: number, ey: number }} e
 * @returns {[number, number]}
 */
export const iso = (x, y, z, e) => [(x - y) * e.ex, (x + y) * e.ey - z];

/** Un punto como "x,y", para los atributos `points` de un poligono. */
export const punto = (x, y, z, e) => iso(x, y, z, e).join(',');

/** Varios puntos seguidos, para un poligono entero. */
export const poli = (e, ...ps) => ps.map((p) => punto(p[0], p[1], p[2] || 0, e)).join(' ');

/**
 * Cuanto ocupa en pantalla una rejilla de cols x filas, puesto incluido.
 * Las esquinas estan a (cols-1) y (filas-1) pasos del origen; el +2*lado es
 * lo que el propio puesto sobresale del punto de su celda.
 */
export const extensionX = (cols, filas, paso, lado, e) =>
  (cols - 1 + (filas - 1)) * paso * e.ex + lado * e.ex * 2;
export const extensionY = (cols, filas, paso, lado, e) =>
  (cols - 1 + (filas - 1)) * paso * e.ey + lado * e.ey * 2;

/**
 * Como se reparten n puestos, y cuanto mide el conjunto.
 *
 * Se prueban TODOS los repartos posibles y gana el que mejor aprovecha esta
 * ventana. No hay un numero de columnas fijo: con uno, al cambiar el tamano
 * de la ventana las piezas se agolpaban de un lado.
 *
 * El puntaje penaliza los repartos muy alargados porque una fila de doce
 * cabe, pero deja la planta como una tira y los puestos ilegibles.
 *
 * @param {number} n
 * @param {{ ancho: number, alto: number, lado: number, separacion: number,
 *           holguraAlto?: number, elevacion?: number, escalaMaxima?: number }} caja
 */
export function rejillaPlanta(n, caja) {
  const {
    ancho, alto, lado, separacion,
    holguraAlto = 0, elevacion = 34, escalaMaxima = 1.7
  } = caja;
  const e = ejes(elevacion);
  if (n <= 0) return { celdas: [], escala: 1, ancho: 0, alto: 0, cols: 0, filas: 0, ejes: e };

  const paso = lado + separacion;
  // Lo que sobresale del rombo por arriba y por abajo (el rotulo del puesto),
  // en lados de puesto. Entra en el calculo de la escala: si no, la primera
  // fila cabe segun la cuenta y se corta en la pantalla.
  const extra = holguraAlto * lado;

  let mejor = null;
  for (let cols = 1; cols <= n; cols++) {
    const filas = Math.ceil(n / cols);
    const w = extensionX(cols, filas, paso, lado, e);
    const h = extensionY(cols, filas, paso, lado, e) + extra;
    const escala = Math.min(ancho / w, alto / h, escalaMaxima);
    const desbalance = Math.max(cols, filas) / Math.min(cols, filas);
    const puntaje = escala / Math.pow(desbalance, 0.35);
    if (!mejor || puntaje > mejor.puntaje) mejor = { cols, filas, escala, puntaje };
  }

  const { cols, filas, escala } = mejor;
  const celdas = [];
  for (let i = 0; i < n; i++) {
    const c = i % cols;
    const f = Math.floor(i / cols);
    const [x, y] = iso(c * paso, f * paso, 0, e);
    celdas.push({ indice: i, col: c, fila: f, x, y });
  }
  // El puesto se extiende media anchura a la izquierda de su celda, y minX se
  // calcula sobre el PUNTO de la celda, no sobre el dibujo: sin esta
  // correccion la columna de la izquierda se sale del lienzo.
  const minX = Math.min(...celdas.map((c) => c.x));
  const saliente = lado * e.ex;
  for (const c of celdas) c.x += saliente - minX;

  return {
    celdas, escala, cols, filas, ejes: e,
    ancho: extensionX(cols, filas, paso, lado, e),
    alto: extensionY(cols, filas, paso, lado, e)
  };
}

/**
 * En isometrica, los puestos de dos filas seguidas se solapan en pantalla, asi
 * que lo que esta mas ADELANTE tiene que dibujarse despues o los tabiques del
 * de atras tapan el escritorio del de adelante.
 *
 * @param {{col: number, fila: number}[]} celdas
 * @returns {number[]} los indices, en el orden en que hay que pintarlos
 */
export function ordenDePintado(celdas) {
  return celdas
    .map((c, i) => ({ i, p: c.col + c.fila }))
    .sort((a, b) => a.p - b.p || a.i - b.i)
    .map((x) => x.i);
}

/* ------------------------------------------------------------------ zonas */

/**
 * Las tres zonas de la oficina. Salen de datos que el tenant YA declara
 * --`orientado_a` por rol y `rol_de_entrada` en la configuracion-- y no son
 * una invencion del tablero: son la estructura real del asistente.
 */
export const ZONAS = {
  recepcion: { rotulo: 'RECEPCIÓN', color: '#C8A2E8', orden: 0 },
  cliente: { rotulo: 'ATIENDE AL CLIENTE', color: '#8FD3B8', orden: 1 },
  interno: { rotulo: 'TRASTIENDA', color: '#A8C0DE', orden: 2 }
};

/**
 * A que zona pertenece un agente.
 *
 * `entrada` puede ser null y entonces NADIE es recepcion: el tenant no lo
 * declara y no se adivina. Deducirlo del "primer rol orientado al cliente" es
 * el error que el 07/09/2026 hizo que un suscriptor sin internet terminara
 * hablando con el agente comercial -- Rapilink tiene cuatro de esos y el
 * orden lo decidia un diccionario.
 *
 * @param {{nombre: string, orientado_a?: string}} agente
 * @param {string|null} entrada
 */
export function zonaDe(agente, entrada) {
  if (entrada && agente.nombre === entrada) return 'recepcion';
  return agente.orientado_a === 'cliente_final' ? 'cliente' : 'interno';
}

/* --------------------------------------------------------- identidad visual */

/**
 * Color propio de cada agente. Identifica al puesto y NO dice nada del
 * estado: ese va en la silla, la pantalla del monitor y el borde del piso.
 *
 * Son dos lecturas que conviene que no se pisen: el color del agente es
 * siempre el mismo y por eso sirve para reconocerlo; el del estado cambia
 * cada pocos minutos y por eso sirve para alarmar.
 *
 * Tonos medios, ninguno cerca de los cuatro de estado (rojo, violeta, cian y
 * ambar), para que una pared no se confunda con una alarma.
 */
export const COLORES_AGENTE = [
  '#C2703E', '#3E7F6B', '#8A5FA8', '#B0455E', '#4A6FA5', '#7E8B3A',
  '#A8622F', '#2F7C8E', '#9B4E88', '#5C6E8C', '#C08A2E', '#5E8C4A'
];

/**
 * Una semilla estable a partir del nombre. Estable importa: la pantalla se
 * repinta cada 12 segundos, y con azar le cambiaria el color y la cara a la
 * gente delante de quien esta mirando.
 *
 * @param {string} nombre
 */
export function semillaDe(nombre) {
  let s = 0;
  for (const c of String(nombre)) s = (s * 31 + c.charCodeAt(0)) >>> 0;
  return s;
}

/** Elige de una lista con la semilla, desplazando bits para no correlacionar. */
export const tomaDe = (semilla, desplazamiento, lista) =>
  lista[(semilla >>> desplazamiento) % lista.length];

/** Aclara (f>0) u oscurece (f<0) un hex. Para las dos caras de un tabique. */
export function tono(hex, f) {
  const n = parseInt(String(hex).slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) =>
    Math.max(0, Math.min(255, Math.round(f > 0 ? v + (255 - v) * f : v * (1 + f))))
  );
  return '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
}

/* ------------------------------------------------------------------ texto */

/**
 * El cuerpo de letra al que un texto entra ENTERO en un ancho dado.
 *
 * Recortar el nombre de un agente es lo peor que puede hacer su rotulo:
 * "SOPORTE TE..." y "ATENCION A..." no identifican a nadie, que es lo unico
 * para lo que el rotulo existe. Los nombres de area los pone cada empresa y
 * pueden medir cualquier cosa, asi que el ancho no se puede fijar de
 * antemano: se ajusta la letra. El minimo existe para que un nombre absurdo
 * no la vuelva ilegible; ahi si se recorta, pero recien ahi.
 *
 * @param {string} texto
 * @param {number} ancho
 * @param {number} maximo
 * @param {number} minimo
 * @param {number} [porLetra] 0.72 en MAYUSCULAS, 0.62 en minusculas
 */
export function cuerpoQueCabe(texto, ancho, maximo, minimo, porLetra = 0.72) {
  const n = Math.max(1, String(texto).length);
  return Math.max(minimo, Math.min(maximo, ancho / (n * porLetra)));
}

/**
 * Recorta con puntos suspensivos, como ultimo recurso.
 *
 * La tolerancia de 1e-6 no es cosmetica y la encontro una prueba de render:
 * cuando `cuerpoQueCabe` devuelve el cuerpo EXACTO para que un texto entre,
 * rehacer aqui la misma division da 14,999... en vez de 15, el floor se queda
 * en 14 y el nombre se recorta teniendo sitio. Se veia como "SOPORTE
 * TECNI..." en un cartel donde "SOPORTE TECNICO" cabia entero.
 */
export function recortar(texto, ancho, cuerpo, porLetra = 0.72) {
  const s = String(texto);
  const max = Math.floor(ancho / (cuerpo * porLetra) + 1e-6);
  return s.length > max ? s.slice(0, Math.max(1, max - 1)) + '…' : s;
}

/* ------------------------------------------------------- lo que cambio */

/**
 * Que cambio entre dos panoramas, por agente.
 *
 * Es el insumo de TODA la animacion de esta pantalla, y su forma responde a
 * como llegan los datos: sondeo cada 12 s (lib/centro-mando/eventos.js). No
 * hay tiempo real que animar -- lo que llega es una foto. Lo unico honesto
 * que se puede animar es la DIFERENCIA entre dos fotos, y eso es lo que esto
 * calcula.
 *
 * Se devuelve tambien `cargaPrevia` para que la cifra pueda contar de un
 * numero al otro: ver el recorrido dice algo que el numero final no dice.
 *
 * @param {any[]} antes
 * @param {any[]} ahora
 * @returns {Record<string, {estadoPrevio: string|null, cargaPrevia: number|null,
 *   entroEnAlarma: boolean, empezoAEsperar: boolean, esNuevo: boolean}>}
 */
export function cambios(antes, ahora) {
  const previo = new Map((antes || []).map((a) => [a.nombre, a]));
  /** @type {Record<string, any>} */
  const salida = {};
  const ALARMA = new Set(['error', 'waiting_approval']);
  for (const a of ahora || []) {
    const p = previo.get(a.nombre);
    const esperaAhora = (a.esperando_humano || 0) + (a.esperando_aprobacion || 0) > 0;
    const esperaAntes = p ? (p.esperando_humano || 0) + (p.esperando_aprobacion || 0) > 0 : false;
    salida[a.nombre] = {
      estadoPrevio: p ? p.estado : null,
      cargaPrevia: p ? (p.conversaciones || 0) : null,
      // Entrar en alarma es un cambio; SEGUIR en alarma no lo es. Un destello
      // que se repite cada 12 segundos deja de avisar y pasa a ser ruido.
      entroEnAlarma: !!p && ALARMA.has(a.estado) && !ALARMA.has(p.estado),
      empezoAEsperar: !!p && esperaAhora && !esperaAntes,
      esNuevo: !p
    };
  }
  return salida;
}
