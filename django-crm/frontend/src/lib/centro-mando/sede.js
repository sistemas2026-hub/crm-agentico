/**
 * LA SEDE: todos los departamentos en una planta, lista para dibujar.
 *
 * Es la composición que se decidió el 01/11/2026 mirando la referencia: una
 * planta abierta con plaza al frente, los departamentos alrededor, y la
 * navegación por traslado —uno se acerca al departamento— en vez de por
 * cambio de piso.
 *
 * QUÉ SE GANA, Y NO ES SOLO ESTÉTICO
 * ----------------------------------
 * Sin pisos apilados **no hay nada encima de nada**, y con eso desaparece toda
 * la aritmética que costó la semana: la desigualdad de oclusión de
 * `edificio.js`, la altura de piso mínima, la cubierta que escondía nueve
 * puestos, los 38 de separación que habrían hecho una torre de 114. Ninguna de
 * esas cosas es un problema resuelto acá: es un problema que deja de existir.
 *
 * El precio es que se pierde la jerarquía de los pisos —P1 Administración, P2
 * Operación, P3 Tecnología—. Sigue en el dato: cada sala conserva su `piso`, y
 * el día que haga falta se puede leer como zona dentro del mismo plano sin
 * tocar la geometría.
 *
 * Devuelve el MISMO contrato que `edificioDe`: `plantas`, `niveles` y `mundo`.
 * La escena no tiene por qué saber qué composición está dibujando, y mientras
 * no lo sepa se puede comparar una contra otra con los mismos personajes, la
 * misma ficha y las mismas pruebas.
 */

import { plantaDe } from './departamentos.js';
import { ENTRADA, PASILLO, repartirAnillo } from './anillo.js';
import { mobiliarioDeEntrada, mobiliarioDePatio } from './patio.js';
//  EL MISMO BULTO QUE USA LA REJILLA. Si la puerta se decidiera con unos
//  numeros y el paso se midiera con otros, habria puertas que la rejilla
//  considera tapiadas y el dibujo muestra abiertas — la contradiccion que
//  `navegacion.js` existe para no tener.
import { BULTO } from './navegacion.js';

/** Lo que sube un muro de sala. */
export const ALTURA_DE_MURO = 4;

/**
 * La sede de una empresa en una sola planta.
 *
 * @param {any[]} salas las salas de la empresa, ya compuestas
 * @param {any[]} agentes el inventario del motor
 * @param {{ soloSala?: string|null }} [opciones]
 */
export function sedeDe(salas, agentes, opciones = {}) {
  const lista = Array.isArray(salas) ? salas.filter(Boolean) : [];
  if (lista.length === 0) {
    return { plantas: [], niveles: [], mundo: { ancho: 0, fondo: 0, alto: 0 } };
  }

  const { puestas, pasillos, huella, patio, entrada } = repartirAnillo(lista);
  const soloSala = opciones.soloSala ?? null;
  const plantas = [];

  //  TODO LO QUE ES CIRCULACIÓN, junto: por acá se entra a las salas y por acá
  //  cruzan las figuras de ambiente.
  const circulacion = [...pasillos, patio, entrada].filter(Boolean);

  //  LOS VANOS QUE DAN AL PATIO, para que no se le pongan muebles delante.
  //  Se llena al colocar las salas y se usa al amueblar el patio, mas abajo.
  const vanosAlPatio = [];
  //  Y los que dan a la franja de ENTRADA, que es otra pieza de circulacion
  //  con su propio mobiliario. Olvidarla costo la puerta de una sala.
  const vanosALaEntrada = [];

  /**
   * El vano de la puerta lateral de una sala, si hay circulación a su
   * izquierda.
   *
   * SE DECIDE POR GEOMETRÍA Y NO POR BANDA. Hoy son las salas de la manzana
   * derecha las que tienen el pasillo contra el muro, pero eso es consecuencia
   * de cómo reparte `anillo.js`, no una ley. Preguntarle al plano —¿hay algo
   * por donde se pase pegado a mi muro izquierdo?— sigue siendo cierto el día
   * que el reparto cambie.
   *
   * A un cuarto del fondo y de 1,8 de ancho, los mismos números que
   * `edificio.js`: centrada queda detrás del puesto principal en casi todas
   * las plantillas, y una puerta tapada por una silla no se lee como puerta.
   */
  /** ¿Hay circulación pegada a este lado de la sala? */
  const daACirculacion = (p, lado) => circulacion.some((c) => {
    if (lado === 'izquierda') {
      return Math.abs(c.x + c.ancho - p.x) < 0.01
        && c.y < p.y + p.fondo && p.y < c.y + c.fondo;
    }
    if (lado === 'derecha') {
      return Math.abs(c.x - (p.x + p.ancho)) < 0.01
        && c.y < p.y + p.fondo && p.y < c.y + c.fondo;
    }
    if (lado === 'frente') {
      return Math.abs(c.y - (p.y + p.fondo)) < 0.01
        && c.x < p.x + p.ancho && p.x < c.x + c.ancho;
    }
    return Math.abs(c.y + c.fondo - p.y) < 0.01
      && c.x < p.x + p.ancho && p.x < c.x + c.ancho;
  });

  /** ¿Hay otra sala pegada a este lado? */
  const salaPegada = (p, lado) => puestas.some((q) => {
    if (q === p) return false;
    if (lado === 'derecha') {
      return Math.abs(q.x - (p.x + p.ancho)) < 0.01
        && q.y < p.y + p.fondo && p.y < q.y + q.fondo;
    }
    return Math.abs(q.y - (p.y + p.fondo)) < 0.01
      && q.x < p.x + p.ancho && p.x < q.x + q.ancho;
  });

  /** Lo que mide un vano de puerta. Una persona pasa; dos no. */
  const ANCHO_DE_VANO = 1.8;

  /**
   * El vano de una puerta en un lado de la sala, corrido al hueco que haya.
   *
   * ARRANCÓ EN «UN CUARTO DEL LADO», copiado de `edificio.js`, y la guarda de
   * `sede.test.js` lo tumbó: en la plantilla de atención el puesto «Atención
   * 1» queda a 1,2 del muro justo donde caía el vano. Una puerta tapada por
   * una silla no se lee como puerta, y encima deja a ese puesto sin salida.
   *
   * Así que el vano se busca, igual que el ancla de los rótulos: se recorre el
   * lado y se elige el tramo más lejano de cualquier puesto pegado a ese muro.
   * No se mueve el escritorio —los puestos salen de lo que declara la
   * empresa— sino la puerta, que es lo que este archivo sí decide.
   *
   * @param largo cuánto mide ese lado, en celdas
   * @param estorbos posición a lo largo del lado de lo que no se puede tapar
   */
  const vanoDe = (largo, estorbos = []) => {
    const margen = 0.6;
    const util = largo - margen * 2 - ANCHO_DE_VANO;
    if (util <= 0) return [margen, largo - margen];

    //  CUANTO SE METE EL VANO EN CADA CLASE DE ESTORBO, por separado.
    //
    //  No se suman con un peso: son cosas distintas y se ordenan, no se
    //  promedian. Un vano DETRAS DE UN ESCRITORIO deja ese puesto sin salida
    //  -lo midio la guarda de navegacion, con un puesto aislado- asi que eso
    //  es una condicion dura. Un vano debajo de un tablero solo lo hace
    //  invisible: malo, pero menos. Se elige el que no pise ningun puesto y,
    //  entre esos, el que menos quede tapado.
    const invasion = (desde, clase) => {
      const hasta = desde + ANCHO_DE_VANO;
      let total = 0;
      for (const e of estorbos) {
        if ((e.clase ?? 'puesto') !== clase) continue;
        total += Math.max(0, Math.min(hasta, e.hasta) - Math.max(desde, e.desde));
      }
      return total;
    };
    //  Y lo lejos que queda del más cercano, para desempatar entre libres.
    const holgura = (desde) => {
      const centro = desde + ANCHO_DE_VANO / 2;
      if (estorbos.length === 0) return Infinity;
      return Math.min(...estorbos.map(
        (e) => Math.abs(centro - (e.desde + e.hasta) / 2)));
    };

    /** Comparacion lexicografica: el primer campo que difiera decide. */
    const antesQue = (a, b) => {
      for (let k = 0; k < a.length; k++) {
        if (a[k] < b[k] - 0.001) return true;
        if (a[k] > b[k] + 0.001) return false;
      }
      return false;
    };

    //  Cuarenta y un posiciones: un vano mide 1,8 y los lados miden entre 8 y
    //  14, asi que el paso queda en un cuarto de celda.
    const candidatos = [];
    for (let i = 0; i <= 40; i++) candidatos.push(margen + (i / 40) * util);

    //  LOS PUESTOS SON UN FILTRO DURO, no un termino a minimizar. Una puerta
    //  detras de un escritorio deja ese puesto SIN SALIDA -lo midio la guarda
    //  de navegacion, con un puesto aislado-, y eso no se compensa con que la
    //  puerta se vea mejor. Solo si ninguna posicion los evita se afloja.
    const libres = candidatos.filter(
      (d) => invasion(d, 'puesto') + invasion(d, 'bulto') < 0.001);
    const donde = libres.length > 0 ? libres : candidatos;

    let mejor = donde[0];
    let mejorClave = null;
    for (const desde of donde) {
      //  Entre los que no pisan un puesto: el que menos quede tapado por un
      //  mueble de pared y, a igualdad, el mas despejado.
      const clave = [invasion(desde, 'pared'), -holgura(desde)];
      if (mejorClave === null || antesQue(clave, mejorClave)) {
        mejorClave = clave;
        mejor = desde;
      }
    }
    return [Number(mejor.toFixed(2)), Number((mejor + ANCHO_DE_VANO).toFixed(2))];
  };

  /**
   * Los puestos que están lo bastante cerca de un muro como para estorbar su
   * puerta, proyectados sobre ese muro.
   *
   * @param planta la sala ya compuesta
   * @param lado cuál de los cuatro
   */
  /**
   * Cuánto ocupa a lo largo de SU muro cada mueble de pared.
   *
   * Leído del dibujo, no supuesto: un tablero ocupa 2,74 y arranca medio paso
   * antes de su `gy`; el panel de empalmes, 2,1; el armario, 1,5; la
   * estantería, la biblioteca, la pizarra y la videoconferencia, su `largo`.
   * Con números inventados, el vano esquivaría estorbos que no existen y se
   * quedaría encima de los que sí.
   *
   * `null` es un mueble que NO va en el muro: no estorba a una puerta.
   */
  /**
   * POR DÓNDE NO PUEDE IR LA PUERTA DE ESE LADO.
   *
   * Dos clases de estorbo, y la segunda faltaba:
   *
   * - Un PUESTO pegado al muro. Una puerta detrás de una silla no se lee como
   *   puerta y deja a ese puesto sin salida.
   * - Un MUEBLE DE PARED encima del vano. Se dibuja después del muro, así que
   *   lo tapa: la puerta existe, se dibuja, se pasa por ella — y no se ve.
   *
   * Lo segundo costó seis de las once puertas. Medido el 02/11/2026 buscando
   * por qué «las entradas del lado derecho no se distinguen»: en Finanzas, el
   * tablero de recaudo caía justo encima de su vano, y lo mismo en Campo,
   * Atención, Recursos Humanos, Dirección y Recepción. Las seis son las que
   * tienen su puerta en el muro lateral, que es el que lleva mobiliario.
   *
   * @returns {{desde: number, hasta: number}[]} tramos ocupados del lado
   */
  const estorbosDe = (planta, lado) => {
    const CERCA = 2.2;
    const m = planta.mundo;
    const tramos = [];

    //  Los puestos pegados a ese muro, con el bulto de su escritorio.
    for (const q of planta.puestos ?? []) {
      const cerca = lado === 'izquierda' ? (q.gx ?? 0) < CERCA
        : lado === 'derecha' ? m.ancho - (q.gx ?? 0) < CERCA
          : m.fondo - (q.gy ?? 0) < CERCA;
      if (!cerca) continue;
      const centro = lado === 'frente' ? (q.gx ?? 0) : (q.gy ?? 0);
      //  PESO 1. Un escritorio cerca del muro estorba el paso, pero no TAPA la
      //  puerta: esta sigue viendose. Si hay que elegir entre pasar por detras
      //  de una silla y quedar detras de un tablero, se elige lo primero.
      tramos.push({ desde: centro - 1.1, hasta: centro + 1.1, clase: 'puesto' });
    }

    //  EL MOBILIARIO DE SUELO QUE LLEGA HASTA EL MURO. No tapa la puerta: la
    //  TAPIA. El vano se abre en el muro y, un paso despues, el mueble vuelve
    //  a pintar esa misma celda de obstaculo — la puerta se dibuja, se ve, y
    //  no se pasa.
    //
    //  Medido el 02/11/2026 con ocho departamentos: en la sala de finanzas el
    //  archivador del rincon ocupaba las celdas del vano y la sala entera
    //  quedo aislada, con su puerta dibujada. Por eso es un filtro DURO como
    //  los puestos y no una penalizacion: no hay nada que compensar.
    const ALCANCE = 1.2;
    for (const mu of planta.mobiliario ?? []) {
      //  UNA MAMPARA PERPENDICULAR parte el muro en dos justo donde toca. Una
      //  puerta en ese punto abriria contra el canto del tabique.
      if (mu.tipo === 'mampara') {
        const tocaElFrente = (mu.hasta ?? 0) >= m.fondo - 0.6;
        if (lado === 'frente' && mu.gx != null && tocaElFrente) {
          tramos.push({ desde: mu.gx - 0.6, hasta: mu.gx + 0.6, clase: 'bulto' });
        }
        continue;
      }
      const r = BULTO[mu.tipo];
      //  Sin bulto declarado es de pared o de techo: no tapia nada.
      if (!r) continue;
      const gx = mu.gx ?? 0;
      const gy = mu.gy ?? 0;
      const hueco = lado === 'izquierda' ? gx - r
        : lado === 'derecha' ? m.ancho - (gx + r)
          : m.fondo - (gy + r);
      if (hueco > ALCANCE) continue;
      const centro = lado === 'frente' ? gx : gy;
      tramos.push({ desde: centro - r, hasta: centro + r, clase: 'bulto' });
    }

    //  Y el mobiliario de pared, sólo en el muro donde de verdad está: los de
    //  pared van en el LATERAL (`gx = 0`), colocados por su `gy`.
    if (lado === 'izquierda') {
      for (const mu of planta.mobiliario ?? []) {
        const def = LARGO_EN_EL_MURO[mu.tipo];
        if (!def) continue;
        const desde = (mu.gy ?? 0) + def[0];
        const largoPieza = def[1] ?? ((mu.largo ?? 2) + (def[0] < 0 ? 0.2 : 0));
        //  PESO 10: un mueble de pared se dibuja DESPUES del muro y tapa el
        //  vano entero. Es el estorbo que de verdad hace invisible una puerta.
        tramos.push({ desde, hasta: desde + largoPieza, clase: 'pared' });
      }
    }
    return tramos;
  };

  const LARGO_EN_EL_MURO = {
    tablero: [-0.12, 2.74],
    panel_fibra: [0, 2.1],
    armario: [0, 1.5],
    estanteria: [0, null],
    pizarra: [-0.1, null],
    videoconferencia: [-0.1, null],
    biblioteca: [0, null]
  };

  /**
   * LO QUE CUELGA DEL MURO SE MUDA AL FONDO CUANDO EL LATERAL ES DE VIDRIO.
   *
   * Un tablero, una pizarra, una pantalla de videoconferencia o un panel de
   * empalmes van atornillados a una pared. En cuanto esa pared pasa a ser el
   * cerramiento acristalado que da al pasillo, no tienen de dónde colgar.
   *
   * Los que se APOYAN —armario, biblioteca, estantería— no se tocan: un
   * armario contra una mampara de vidrio es lo que hay en cualquier oficina.
   *
   * Se empaqueta a lo largo del muro del fondo respetando el MURAL, que son
   * pantallas y es lo único con lo que de verdad no puede compartir sitio.
   * Sobre el cartel pintado sí puede pasar: es texto en la pared y la sala ya
   * lleva su nombre en un letrero de pantalla.
   *
   * MUEVE, NO BORRA, igual que `apartarDelVano`: si en el fondo no queda
   * hueco —Atención al Cliente y Recepción tienen 6,4 de mural sobre 13— la
   * pieza se queda donde estaba y la medición lo dice.
   */
  const COLGADOS = new Set(['tablero', 'pizarra', 'videoconferencia', 'panel_fibra']);

  const alMuroDelFondo = (mobiliario, cierre, puesta, mural) => {
    if (!cierre.antepecho?.izquierda || !mobiliario?.length) return mobiliario ?? [];
    const SEPARACION = 0.25;
    //  Lo que ya ocupa el muro del fondo: los paneles del mural.
    const ocupados = (mural?.paneles ?? []).map((p) => [p.gx, p.gx + p.ancho]);
    const pisa = (a, b, c, d) => Math.min(b, d) - Math.max(a, c) > 0.001;

    const salida = mobiliario.slice();
    //  De mayor a menor: al grande le cuesta más encontrar sitio.
    const candidatos = mobiliario
      .map((mu, i) => ({ mu, i, t: tramoEnElMuro(mu) }))
      .filter((c) => c.t !== null && COLGADOS.has(c.mu.tipo))
      .sort((a, b) => b.t.largo - a.t.largo);

    for (const c of candidatos) {
      const largo = c.t.largo;
      let sitio = null;
      for (let d = 0.3; d + largo <= puesta.ancho - 0.3 + 1e-9; d += 0.05) {
        if (ocupados.some(([a, b]) => pisa(d, d + largo, a - SEPARACION, b + SEPARACION))) continue;
        sitio = d;
        break;
      }
      if (sitio === null) continue;        // no cabe: se queda donde está
      ocupados.push([sitio, sitio + largo]);
      salida[c.i] = {
        ...c.mu,
        muro: 'fondo',
        gx: Number((sitio - c.t.borde).toFixed(2)),
        gy: undefined
      };
    }
    return salida;
  };

  /** El tramo que ocupa en su muro un mueble de pared, o `null` si no va ahí. */
  const tramoEnElMuro = (mu) => {
    const def = LARGO_EN_EL_MURO[mu.tipo];
    if (!def) return null;
    const desde = (mu.gy ?? 0) + def[0];
    const largo = def[1] ?? ((mu.largo ?? 2) + (def[0] < 0 ? 0.2 : 0));
    return { desde, largo, borde: def[0] };
  };

  /**
   * APARTA DEL VANO EL MOBILIARIO DE PARED.
   *
   * POR QUÉ ESTO VIVE EN EL COMPOSITOR Y NO EN LA PLANTILLA. Una plantilla no
   * puede saber dónde va su puerta: depende de qué tiene pegado a cada lado,
   * y eso lo decide el reparto. La misma plantilla, en dos sitios del plano,
   * abre por muros distintos. Así que quien elige el vano es quien tiene que
   * resolver el choque — pedirle a cada plantilla que deje libre «el sitio de
   * la puerta» sería pedirle que adivine.
   *
   * Y HACÍA FALTA DE VERDAD: medido el 02/11/2026 sobre las doce plantillas
   * base, **diez** no dejaban en su muro izquierdo ningún tramo de 1,8 libre
   * de muebles de pared, maceteros y escritorios. No era que la puerta
   * estuviera mal elegida: no había dónde ponerla. El síntoma era que seis de
   * las once puertas quedaban debajo de un tablero o de un armario — «las
   * entradas del lado derecho no se distinguen».
   *
   * Se MUEVE y no se borra. Un armario que desaparece al mover una sala de
   * columna es una sala que cambia de contenido según dónde caiga, y eso ya
   * costó una vez: la primera versión del despeje de puertas del patio
   * borraba el mostrador de recepción. Si no hay sitio en todo el muro, la
   * pieza se queda donde está y la medición lo dice.
   *
   * @param mobiliario el de la plantilla
   * @param vano el de la puerta lateral, o `undefined`
   * @param fondo cuánto mide ese muro en la sala ya colocada
   */
  const apartarDelVano = (mobiliario, vano, fondo) => {
    if (!vano || !mobiliario?.length) return mobiliario ?? [];
    //  Aire a cada lado de la puerta, y entre dos muebles.
    const CLARO = 0.2;
    const SEPARACION = 0.1;
    const va = vano[0] - CLARO;
    const vb = vano[1] + CLARO;
    const pisa = (a, b, c, d) => Math.min(b, d) - Math.max(a, c) > 0.001;

    const piezas = mobiliario
      .map((mu, i) => ({ mu, i, t: tramoEnElMuro(mu) }))
      .filter((p) => p.t !== null);
    const estorban = piezas.filter(
      (p) => pisa(p.t.desde, p.t.desde + p.t.largo, va, vb));
    if (estorban.length === 0) return mobiliario;

    //  Los que ya están fuera del vano no se tocan, y son el obstáculo de los
    //  que hay que mover.
    const ocupados = piezas
      .filter((p) => !estorban.includes(p))
      .map((p) => [p.t.desde, p.t.desde + p.t.largo]);

    const salida = mobiliario.slice();
    //  De mayor a menor: al grande le cuesta más encontrar sitio, y si va
    //  último se encuentra el muro repartido en trozos que no le sirven.
    for (const p of [...estorban].sort((a, b) => b.t.largo - a.t.largo)) {
      const { desde, largo, borde } = p.t;
      let mejor = null;
      //  0,05 y no 0,1 contra el canto: con 0,1 el segundo tablero de la
      //  sala de atencion se quedaba fuera por CUATRO centimetros y la puerta
      //  seguia debajo de el.
      for (let d = 0.05; d + largo <= fondo - 0.05 + 1e-9; d += 0.05) {
        if (pisa(d, d + largo, va, vb)) continue;
        if (ocupados.some(([a, b]) => pisa(d, d + largo, a - SEPARACION, b + SEPARACION))) continue;
        const coste = Math.abs(d - desde);
        if (mejor === null || coste < mejor.coste) mejor = { d, coste };
      }
      //  Sin sitio en todo el muro se queda donde estaba. Pasa en salas muy
      //  cargadas y es preferible a hacerle desaparecer un mueble.
      if (mejor === null) continue;
      ocupados.push([mejor.d, mejor.d + largo]);
      salida[p.i] = { ...p.mu, gy: Number((mejor.d - borde).toFixed(2)) };
    }
    return salida;
  };

  /**
   * EL CERRAMIENTO DE UNA SALA, DEDUCIDO DEL PLANO.
   *
   * Se decide por geometría y no por el nombre del departamento: preguntarle
   * al plano —¿qué tengo pegado a cada lado?— sigue siendo cierto el día que
   * el reparto cambie, y además es la única forma de que valga para una
   * empresa que declare otros departamentos.
   *
   * Las reglas, y cada una tiene su motivo:
   *
   * - Los muros ALTOS de fondo e izquierda ya los dibuja la sala. Llevan vano
   *   sólo si ese lado da a una circulación; contra otra sala sería una puerta
   *   a un escritorio ajeno.
   * - Los dos lados que miran a la cámara llevan PETO, que cierra el recinto
   *   sin tapar a nadie. Ver `ALTURA_DE_ANTEPECHO`.
   * - **Ningún peto donde ya hay otra sala pegada**: ahí está su muro alto, y
   *   dos cerramientos en el mismo borde son la «pared duplicada» que hay que
   *   evitar. Es también lo que hace que una columna de salas se lea como una
   *   manzana maciza y no como una fila de cajas.
   * - Y ningún vano contra el borde del edificio: un hueco que no da a ningún
   *   sitio es un agujero, no una puerta.
   */
  const cerramientoDe = (p, planta) => {
    const ladoIzq = daACirculacion(p, 'izquierda');
    const ladoDer = daACirculacion(p, 'derecha');
    const alFrente = daACirculacion(p, 'frente');
    const petoDerecha = !salaPegada(p, 'derecha');
    const petoFrente = !salaPegada(p, 'frente');
    const con = (lado) => estorbosDe(planta, lado);
    return {
      puertaLateral: ladoIzq ? vanoDe(p.fondo, con('izquierda')) : undefined,
      //  LA CARA IZQUIERDA ES DE CRISTAL CUANDO DA A UN PASILLO.
      //
      //  Es la misma pregunta geométrica que decide todo lo demás acá, y sale
      //  de que el pasillo central tiene salas a los dos lados: para las de
      //  la derecha, ese pasillo cae en su cara izquierda. Mientras sólo
      //  hubo cristal en las dos caras de la cámara, el pasillo tenía vidrio
      //  de un lado y muro ciego del otro.
      antepecho: (petoDerecha || petoFrente || ladoIzq)
        ? { frente: petoFrente, derecha: petoDerecha, izquierda: ladoIzq }
        : undefined,
      puertaDerecha: petoDerecha && ladoDer ? vanoDe(p.fondo, con('derecha')) : undefined,
      puertaFrente: petoFrente && alFrente ? vanoDe(p.ancho, con('frente')) : undefined
    };
  };

  //  1. EL SUELO DE LA SEDE, bajo todo.
  //
  //     Una sola pieza y no una por sala: en una planta abierta el suelo es
  //     continuo y lo que separa un departamento de otro son sus muros, no un
  //     escalón. Es justo al revés que en el edificio apilado, donde cada sala
  //     llevaba su losa porque entre ellas había aire.
  plantas.push({
    mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: 0.8 },
    origen: { gx: 0, gy: 0, gz: -0.8 },
    nivel: null,
    papel: 'arquitectura',
    pasillo: null,
    mobiliario: [],
    puestos: [],
    arquitectura: {
      tipo: 'basamento',
      ancho: huella.ancho,
      fondo: huella.fondo,
      altura: 0.8
    }
  });

  //  2. LA PLAZA, al frente. Suelo por el que se pasa, sin muros: es por donde
  //     se entra y es lo que hace que la planta se lea como una sede y no como
  //     un almacén de cubículos.
  plantas.push({
    mundo: { ancho: entrada.ancho, fondo: entrada.fondo, alto: 0 },
    origen: { gx: entrada.x, gy: entrada.y, gz: 0 },
    nivel: null,
    papel: 'circulacion',
    pasillo: { desde: 0, hasta: entrada.ancho },
    cartel: null,
    mural: null,
    muros: false,
    losa: true,
    baranda: false,
    //  El mostrador que marca el acceso. No reemplaza a la recepción: esa es
    //  una sala declarada y sigue donde la ponga el reparto.
    //  SE RELLENA MAS ABAJO, cuando ya se sabe donde caen los vanos que dan
    //  a esta franja: las salas se colocan despues de este bloque.
    mobiliario: [],
    puestos: []
  });
  //  La franja de entrada, para amueblarla al final.
  const plantaDeLaEntrada = plantas[plantas.length - 1];

  //  3. Los departamentos, cada uno en su celda y para siempre en la misma.
  const ids = [];
  for (const puesta of puestas) {
    if (soloSala !== null && puesta.sala.id !== soloSala) continue;
    //  LA SALA EN SU TAMANO REAL, pegada a la esquina de su celda.
    //
    //  Se probó estirarla hasta llenar la celda —así compartía muros con la
    //  vecina— y en el navegador se vio por qué está mal: todas las salas
    //  quedaban del mismo tamaño, perdiendo que el NOC es ancho y Dirección
    //  chica, y cada una arrastraba un halo de suelo pelado porque el
    //  mobiliario de una plantilla de 13 × 9 quedaba centrado en una sala de
    //  21 × 13. «Se ve muy estirada», y era verdad.
    //
    //  Pegadas a la esquina y no centradas: así las de una misma columna
    //  alinean su muro izquierdo y las de una misma fila su muro de fondo. Lo
    //  que sobra no queda repartido alrededor de cada sala sino junto, al
    //  frente y a la derecha, y eso se lee como pasillo.
    const planta = plantaDe(puesta.sala, agentes);
    const cierre = cerramientoDe(puesta, { ...planta, mundo: { ...planta.mundo, ancho: puesta.ancho, fondo: puesta.fondo } });
    //  Si este vano da al patio, se anota en coordenadas LOCALES del patio.
    if (patio) {
      if (cierre.puertaDerecha && Math.abs(patio.x - (puesta.x + puesta.ancho)) < 0.01) {
        vanosAlPatio.push({
          lado: 'izquierda',
          desde: puesta.y + cierre.puertaDerecha[0] - patio.y,
          hasta: puesta.y + cierre.puertaDerecha[1] - patio.y
        });
      }
      if (cierre.puertaLateral && Math.abs(patio.x + patio.ancho - puesta.x) < 0.01) {
        vanosAlPatio.push({
          lado: 'derecha',
          desde: puesta.y + cierre.puertaLateral[0] - patio.y,
          hasta: puesta.y + cierre.puertaLateral[1] - patio.y
        });
      }
    }
    if (entrada) {
      if (cierre.puertaDerecha && Math.abs(entrada.x - (puesta.x + puesta.ancho)) < 0.01) {
        vanosALaEntrada.push({
          lado: 'izquierda',
          desde: puesta.y + cierre.puertaDerecha[0] - entrada.y,
          hasta: puesta.y + cierre.puertaDerecha[1] - entrada.y
        });
      }
      if (cierre.puertaLateral && Math.abs(entrada.x + entrada.ancho - puesta.x) < 0.01) {
        vanosALaEntrada.push({
          lado: 'derecha',
          desde: puesta.y + cierre.puertaLateral[0] - entrada.y,
          hasta: puesta.y + cierre.puertaLateral[1] - entrada.y
        });
      }
    }
    //  EL ANCHO SALE DEL REPARTO, NO DE LA PLANTILLA. `anillo.js` ensancha
    //  cada sala hasta llenar su columna para que no quede suelo muerto al
    //  costado; si acá se dibujara con el ancho de la plantilla, ese suelo
    //  volvería a aparecer —y encima la sala ya no tocaría la circulación—.
    //  Y el fondo igual: una columna mas corta que la otra dejaba una franja
    //  muerta al frente del edificio, asi que el sobrante se reparte entre sus
    //  salas.
    plantas.push({
      ...planta,
      //  CON LA PUERTA DESPEJADA. Ver `apartarDelVano`: el vano se acaba de
      //  elegir arriba, y lo que lo tape se corre por el muro.
      //  PRIMERO SE MUDA LO QUE CUELGA —si ese muro pasó a ser de vidrio— y
      //  sólo después se aparta de la puerta lo que haya quedado: apartar algo
      //  que ya no está en ese muro sería mover un mueble por un motivo que
      //  dejó de existir.
      mobiliario: apartarDelVano(
        alMuroDelFondo(planta.mobiliario, cierre, puesta, planta.mural),
        cierre.puertaLateral, puesta.fondo),
      mundo: {
        ...planta.mundo,
        ancho: puesta.ancho,
        fondo: puesta.fondo,
        //  CUANTO SE CIERRA ESTA SALA. Sale de la plantilla -es una propiedad
        //  del tipo de sala, como tener estanterias- y decide si la puerta
        //  lleva hoja y lector. Ver `dibujarPuerta`.
        privacidad: planta.privacidad ?? 'estandar',
        ...(cierre.puertaLateral ? { puertaLateral: cierre.puertaLateral } : {}),
        ...(cierre.antepecho ? { antepecho: cierre.antepecho } : {}),
        ...(cierre.puertaDerecha ? { puertaDerecha: cierre.puertaDerecha } : {}),
        ...(cierre.puertaFrente ? { puertaFrente: cierre.puertaFrente } : {})
      },
      origen: { gx: puesta.x, gy: puesta.y, gz: 0 },
      //  SIN LOSA PROPIA: el suelo ya está, y dos suelos a la misma altura se
      //  solapan de forma indefinida —ahí aparece el parpadeo entre
      //  fotogramas—. Es la misma lección que la fachada a −0,6 en
      //  `edificio.js`.
      losa: false,
      baranda: false,
      rotuloFrontal: puesta.sala.rotulo,
      nivel: puesta.sala.piso ?? null,
      papel: 'sala',
      sala: puesta.sala.id,
      banda: puesta.banda
    });
    ids.push(puesta.sala.id);
  }

  //  3b. YA SE PUEDE AMUEBLAR LA ENTRADA. Hasta acá no se sabía dónde caen
  //      los vanos que dan a ella, y amueblarla antes fue exactamente el
  //      defecto que tapó la puerta de una sala.
  plantaDeLaEntrada.mobiliario = mobiliarioDeEntrada(entrada, vanosALaEntrada);

  //  4. EL PATIO. Suelo por el que se pasa, sin muros, y AMUEBLADO: un
  //     rectángulo de suelo liso en el medio de la empresa se lee como un
  //     descampado por grande o chico que sea. Lo que lo convierte en patio no
  //     es el tamaño sino que tenga para qué estar. Ver `patio.js`.
  if (patio) {
    plantas.push({
      mundo: { ancho: patio.ancho, fondo: patio.fondo, alto: 0 },
      origen: { gx: patio.x, gy: patio.y, gz: 0 },
      nivel: null,
      papel: 'circulacion',
      pasillo: { desde: 0, hasta: patio.ancho },
      cartel: null,
      mural: null,
      muros: false,
      losa: true,
      baranda: false,
      mobiliario: mobiliarioDePatio(patio, vanosAlPatio),
      puestos: []
    });
  }

  //  4b. LOS PASILLOS entre columnas de una misma manzana. Sin ellos la
  //      columna de atrás no tiene por dónde entrar: su única salida da contra
  //      el muro de la sala de adelante. Van SIN mobiliario —un pasillo de
  //      tres de ancho con un banco deja de ser un pasillo— y como
  //      `circulacion`, así que las figuras de ambiente también los recorren.
  for (const pasillo of pasillos) {
    plantas.push({
      mundo: { ancho: pasillo.ancho, fondo: pasillo.fondo, alto: 0 },
      origen: { gx: pasillo.x, gy: pasillo.y, gz: 0 },
      nivel: null,
      papel: 'circulacion',
      pasillo: { desde: 0, hasta: pasillo.ancho },
      cartel: null,
      mural: null,
      muros: false,
      losa: true,
      baranda: false,
      mobiliario: [],
      puestos: []
    });
  }

  //  5. EL PERÍMETRO: el muro de fondo y los dos costados.
  //
  //     El frente queda ABIERTO, y no por falta de ganas: en esta isometría el
  //     muro del frente estaría entre la cámara y la oficina entera. Es la
  //     misma razón por la que las salas no llevan techo.
  const periferia = (pieza, origen, profundidad) => plantas.unshift({
    profundidad,
    mundo: { ancho: pieza.ancho ?? 0.6, fondo: pieza.fondo ?? 0.6, alto: ALTURA_DE_MURO },
    origen,
    nivel: null,
    papel: 'arquitectura',
    pasillo: null,
    mobiliario: [],
    puestos: [],
    arquitectura: pieza
  });
  periferia(
    { tipo: 'fachada', ancho: huella.ancho, altura: ALTURA_DE_MURO },
    { gx: 0, gy: -0.6, gz: 0 }
  );
  periferia(
    { tipo: 'extremo', fondo: huella.fondo, altura: ALTURA_DE_MURO },
    { gx: -0.6, gy: 0, gz: 0 }
  );
  //  EL EXTREMO DERECHO VA DELANTE DE LAS SALAS QUE CRUZA.
  //
  //  Su origen es (ancho, 0) y `profundidad = gx + gy` lo dejaba en 35,
  //  mientras las salas que recorre llegan a 89: se pintaba detrás de ellas.
  //  Una pieza de 54 celdas de largo no tiene una sola profundidad, y la que
  //  le sirve al pintor es la de su extremo más cercano.
  periferia(
    { tipo: 'extremo', fondo: huella.fondo, altura: ALTURA_DE_MURO },
    { gx: huella.ancho, gy: 0, gz: 0 },
    huella.ancho + huella.fondo
  );

  //  EL FRENTE, CERRADO CON UN PETO DE HORMIGÓN.
  //
  //  Aquí decía «el frente queda ABIERTO, y no por falta de ganas: en esta
  //  isometría el muro del frente estaría entre la cámara y la oficina
  //  entera». Es cierto para un MURO y no para un PETO: a 1,15 no tapa a
  //  nadie —la misma tabla de oclusión que fijó el antepecho de sala en 1,2—
  //  y el edificio deja de terminar en el aire.
  //
  //  Va a +1 del fondo de las salas para quedar por delante de todo.
  periferia(
    { tipo: 'peto', ancho: huella.ancho, altura: 1.15 },
    { gx: 0, gy: huella.fondo + 0.6, gz: 0 },
    huella.ancho + huella.fondo + 1
  );

  return {
    plantas,
    //  Un solo nivel, y lo dice con esas palabras: quien navega pregunta por
    //  niveles y tiene que recibir una respuesta honesta, no una lista vacía
    //  que se lea como «no hay datos».
    niveles: [{ nivel: 1, rotulo: 'Planta', declarado: true, gz: 0, salas: ids }],
    mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: ALTURA_DE_MURO }
  };
}

//  Acá vivía `sitioDe`, y no la reemplaza nada: no tenía un solo llamador y
//  llamaba a `repartirPlantaUnica`, que este archivo NO importa. O sea que si
//  alguien la hubiera usado habría reventado con un ReferenceError. Es el
//  mismo caso que `colocarCorte()` unas horas antes: una función que quedó sin
//  llamador al extraer un módulo y que nada señaló. Cuando haga falta llevar la
//  cámara a un departamento, el dato sale de `repartirAnillo`.

export { ENTRADA, PASILLO };
