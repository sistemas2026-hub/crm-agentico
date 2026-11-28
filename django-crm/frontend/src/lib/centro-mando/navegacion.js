/**
 * LA REJILLA POR LA QUE SE PUEDE CAMINAR.
 *
 * Hasta acá, las figuras de ambiente caminaban por rectángulos de circulación
 * y nunca entraban a una sala — y eso estaba bien mientras las salas no
 * tuvieran puerta: una figura dentro de un recinto cerrado se vería
 * atravesando un muro. Con los cerramientos y los vanos ya dibujados, lo que
 * falta es el mapa: por dónde se pasa, por dónde no, y si de verdad se llega.
 *
 * QUÉ ES Y QUÉ NO ES
 * ------------------
 * Esto es **geometría**, no conducta. Dice qué celdas son transitables y cómo
 * ir de una a otra. No mueve a nadie, no decide quién camina ni cuándo, y no
 * sabe de quién es cada puesto. Esa separación importa: el día que un
 * personaje se levante, lo que decida ese movimiento tiene que ser otra cosa
 * y tiene que poder distinguirse de una actividad laboral de verdad.
 *
 * Lo vigila `navegacion.test.js`, que prohibe el vocabulario del negocio en
 * este archivo y en `paseo.js`, comentarios incluidos: así el mismo código
 * sirve el día que caminen visitantes o personal humano.
 *
 * SE DERIVA DEL PLANO, NO SE ESCRIBE
 * ----------------------------------
 * Las celdas salen de las mismas plantas que dibuja la escena: el patio y los
 * pasillos son transitables, las salas también pero sólo desde sus puertas, y
 * el mobiliario y los puestos son obstáculos. Escribir el mapa a mano sería
 * tener la geometría dos veces, y el día que una se mueva la otra mentiría —
 * una puerta que se ve y por la que no se puede pasar, o al revés.
 *
 * LA AFIRMACIÓN QUE IMPORTA es `conectividad()`: desde el pasillo principal se
 * llega a **todos** los puestos. Una oficina no está accesible porque tenga un
 * hueco dibujado en el muro; lo está cuando existe un camino.
 */

/** Cuánto mide el lado de una celda, en unidades del plano. */
export const CELDA = 0.5;

/** Qué puede ser una celda. */
export const LIBRE = 0;
export const MUEBLE = 1;
export const PUESTO = 2;
export const MURO = 3;

/**
 * Cuánto ocupa cada tipo de mueble alrededor de su punto, en unidades.
 *
 * Es un radio y no una caja a propósito: los muebles se declaran por un punto
 * y una orientación que la escena interpreta de formas distintas según el
 * tipo. Un radio generoso es más barato que leer la geometría de cada pieza, y
 * el error cae del lado seguro — un personaje rodea un poco más de la cuenta.
 *
 * Los de PARED (`gy` a lo largo del muro) no entran acá: no estorban el paso
 * porque están pegados al muro, y el muro ya es un obstáculo.
 */
export const BULTO = {
  mesa: 1.5,
  mesa_revision: 1.6,
  banco_trabajo: 1.4,
  mostrador: 1.5,
  banco: 0.8,
  //  Mas que un banco: tiene brazos y respaldo, y nadie lo atraviesa.
  sofa: 1.3,
  //  Una caseta cerrada: se rodea entera.
  cabina: 0.9,
  dispensador: 0.5,
  planta: 0.6,
  cajas: 0.7,
  bobina: 0.8,
  rack: 0.8,
  impresora: 0.7,
  turnero: 0.4,
  bandejas: 0.7,
  caja_fuerte: 0.6,
  columna: 0.7,
  ascensor: 1.2,
  escalera: 1.5
};

/** Los que van colgados o en el techo: no estorban a nadie que camine. */
const NO_ESTORBAN = new Set([
  'luminaria', 'tablero', 'videowall', 'panel_fibra', 'pizarra',
  'videoconferencia', 'biblioteca', 'estanteria', 'armario', 'ducto',
  'zona'
]);

/**
 * La rejilla de una sede.
 *
 * @param {{plantas: any[], mundo: {ancho: number, fondo: number}}} sede
 */
export function rejillaDe(sede) {
  const ancho = Math.ceil((sede?.mundo?.ancho ?? 0) / CELDA);
  const fondo = Math.ceil((sede?.mundo?.fondo ?? 0) / CELDA);
  if (ancho <= 0 || fondo <= 0) {
    return { ancho: 0, fondo: 0, celdas: new Uint8Array(0), puertas: [], destinos: new Map() };
  }

  //  Todo empieza siendo MURO: lo que no se declara transitable, no lo es.
  //  Fail-closed, igual que las listas blancas del motor — una celda que nadie
  //  abrió no se cruza.
  const celdas = new Uint8Array(ancho * fondo).fill(MURO);
  const en = (cx, cy) => cy * ancho + cx;

  const pintar = (x, y, w, f, valor, dentroDe = null) => {
    //  RECORTADO A SU RECINTO. Un mueble pertenece a una planta y no puede
    //  ocupar la de al lado: el bulto es un radio generoso y, sin recortar,
    //  atraviesa el muro y tapia celdas del otro lado.
    //
    //  Medido el 02/11/2026: la mesa del patio, en gx 14,9 con bulto 1,5,
    //  llegaba hasta gx 13,4 — medio metro DENTRO de la sala vecina, cuyo
    //  muro está en gx 14 — y tapaba el único paso entre sus racks y la
    //  pared. La sala entera quedaba aislada por un mueble que no está en
    //  ella. Un muro que no detiene a un mueble tampoco detiene a nadie.
    let ix = x; let iy = y; let fx = x + w; let fy = y + f;
    if (dentroDe) {
      ix = Math.max(ix, dentroDe.gx);
      iy = Math.max(iy, dentroDe.gy);
      fx = Math.min(fx, dentroDe.gx + dentroDe.ancho);
      fy = Math.min(fy, dentroDe.gy + dentroDe.fondo);
      if (fx <= ix || fy <= iy) return;
    }
    const x0 = Math.max(0, Math.floor(ix / CELDA));
    const y0 = Math.max(0, Math.floor(iy / CELDA));
    const x1 = Math.min(ancho, Math.ceil(fx / CELDA));
    const y1 = Math.min(fondo, Math.ceil(fy / CELDA));
    for (let cy = y0; cy < y1; cy++) {
      for (let cx = x0; cx < x1; cx++) celdas[en(cx, cy)] = valor;
    }
  };

  const plantas = Array.isArray(sede?.plantas) ? sede.plantas : [];

  //  1 · La circulación: el patio, la entrada y los pasillos.
  for (const p of plantas.filter((x) => x.papel === 'circulacion')) {
    pintar(p.origen.gx, p.origen.gy, p.mundo.ancho, p.mundo.fondo, LIBRE);
  }

  //  2 · El suelo de cada sala. Queda transitable POR DENTRO; lo que la separa
  //     del pasillo son sus muros, que se pintan después.
  const salas = plantas.filter((x) => x.papel === 'sala');
  for (const p of salas) {
    pintar(p.origen.gx, p.origen.gy, p.mundo.ancho, p.mundo.fondo, LIBRE);
  }

  //  3 · Los muros de cada sala, con sus vanos. Se pintan DESPUÉS del suelo
  //     para que ganen, y los vanos después de los muros por lo mismo.
  const puertas = [];
  for (const p of salas) {
    const o = p.origen;
    const m = p.mundo;
    //  El grosor de un muro en la rejilla: una celda. Menos y el paso se
    //  colaría por la diagonal entre dos celdas de esquina.
    const g = CELDA;
    //  fondo (gy = 0) e izquierda (gx = 0) son muros altos; frente y derecha
    //  llevan peto si la sala está cerrada por ahí.
    pintar(o.gx, o.gy, m.ancho, g, MURO);
    pintar(o.gx, o.gy, g, m.fondo, MURO);
    if (m.antepecho?.frente) pintar(o.gx, o.gy + m.fondo - g, m.ancho, g, MURO);
    if (m.antepecho?.derecha) pintar(o.gx + m.ancho - g, o.gy, g, m.fondo, MURO);

    const abrir = (vano, lado) => {
      if (!vano) return;
      const [a, b] = vano;
      if (lado === 'fondo') pintar(o.gx + a, o.gy, b - a, g, LIBRE);
      if (lado === 'izquierda') pintar(o.gx, o.gy + a, g, b - a, LIBRE);
      if (lado === 'frente') pintar(o.gx + a, o.gy + m.fondo - g, b - a, g, LIBRE);
      if (lado === 'derecha') pintar(o.gx + m.ancho - g, o.gy + a, g, b - a, LIBRE);
      puertas.push({ sala: p.sala, lado, vano: [a, b] });
    };
    abrir(m.puerta, 'fondo');
    abrir(m.puertaLateral, 'izquierda');
    abrir(m.puertaFrente, 'frente');
    abrir(m.puertaDerecha, 'derecha');
  }

  //  4 · El mobiliario que estorba, y los puestos.
  const destinos = new Map();
  for (const p of [...salas, ...plantas.filter((x) => x.papel === 'circulacion')]) {
    const o = p.origen;
    //  El recinto al que pertenece cada pieza. Nada de lo que hay aqui dentro
    //  puede tapiar una celda de la planta de al lado.
    const recinto = { gx: o.gx, gy: o.gy, ancho: p.mundo.ancho, fondo: p.mundo.fondo };
    for (const mu of p.mobiliario ?? []) {
      //  LA MAMPARA ES UN TABIQUE, y hasta hoy la rejilla la cruzaba como si
      //  fuera aire. Se dibuja de pared a pared con su propio vano, asi que
      //  alguien podia aparecer atravesandola — la mentira simetrica de la
      //  que este archivo se cuida en su cabecera, que es una puerta que se
      //  ve y no se pasa. Se pinta como muro y se le abre el vano.
      if (mu.tipo === 'mampara') {
        const g = CELDA;
        const desde = mu.desde ?? 0;
        const hasta = mu.hasta ?? (mu.gx != null ? p.mundo.fondo : p.mundo.ancho);
        if (mu.gx != null) {
          pintar(o.gx + mu.gx, o.gy + desde, g, hasta - desde, MURO, recinto);
          if (mu.vano) {
            pintar(o.gx + mu.gx, o.gy + mu.vano[0], g, mu.vano[1] - mu.vano[0], LIBRE, recinto);
          }
        } else if (mu.gy != null) {
          pintar(o.gx + desde, o.gy + mu.gy, hasta - desde, g, MURO, recinto);
          if (mu.vano) {
            pintar(o.gx + mu.vano[0], o.gy + mu.gy, mu.vano[1] - mu.vano[0], g, LIBRE, recinto);
          }
        }
        continue;
      }
      if (NO_ESTORBAN.has(mu.tipo)) continue;
      const r = BULTO[mu.tipo] ?? 0.7;
      pintar(o.gx + (mu.gx ?? 0) - r, o.gy + (mu.gy ?? 0) - r, r * 2, r * 2, MUEBLE, recinto);
    }
    for (const q of p.puestos ?? []) {
      const gx = o.gx + (q.gx ?? 0);
      const gy = o.gy + (q.gy ?? 0);
      //  El escritorio con su silla: no se pasa por encima.
      pintar(gx - 0.9, gy - 0.9, 1.8, 1.8, PUESTO, recinto);
      //  EL PUNTO DE LLEGADA. No es el puesto: a un escritorio se llega por su
      //  lado, y la celda del escritorio la ocupa el escritorio.
      //
      //  SE BUSCA, NO SE SUPONE. La primera versión lo ponía siempre 1,2 por
      //  delante, y la rejilla encontró el caso: en la sala comercial ese
      //  punto cae sobre el mostrador y el puesto quedaba inalcanzable con la
      //  puerta abierta y el camino libre. Se prueban los cuatro lados y el
      //  frente primero, que es por donde se sienta alguien.
      destinos.set(q.id, { gx, gy, candidatos: [
        { gx, gy: gy + 1.2 }, { gx, gy: gy - 1.2 },
        { gx: gx + 1.2, gy }, { gx: gx - 1.2, gy }
      ] });
    }
  }

  //  A DONDE SE LLEGA DESDE LA CIRCULACION, calculado una vez y guardado.
  //
  //  Va aqui y no en quien pregunta porque es una propiedad del plano, no de
  //  la pregunta: la misma rejilla no puede decirle a uno que a un puesto se
  //  llega y a otro que no. Cuesta unos milisegundos sobre siete mil celdas.
  const rejilla = { ancho, fondo, celdas, puertas, destinos };
  rejilla.alcanzable = alcanzablesDesde(rejilla, plantas
    .filter((x) => x.papel === 'circulacion')
    .map((x) => ({
      x: x.origen.gx, y: x.origen.gy, ancho: x.mundo.ancho, fondo: x.mundo.fondo
    })));
  return rejilla;
}

/**
 * La celda a la que se llega para ocupar un puesto, o `null` si no hay ninguna.
 *
 * Devuelve la PRIMERA de los cuatro lados que esté libre, en el orden en que
 * se declararon: de frente primero, que es por donde se sienta alguien.
 */
export function llegadaA(rejilla, idPuesto) {
  const punto = rejilla.destinos.get(idPuesto);
  if (!punto) return null;
  const alcanzable = rejilla.alcanzable ?? null;

  //  LIBRE NO ES LO MISMO QUE ALCANZABLE, y durante un tiempo esto devolvio
  //  lo primero creyendo que era lo segundo.
  //
  //  Medido el 02/11/2026 con once departamentos: en la sala comercial, el
  //  cuarto escritorio queda en una bolsa cerrada por los otros tres, un
  //  tabique y un mueble. Su celda de delante esta LIBRE —nadie la ocupa— y
  //  no se llega a ella desde ningun pasillo. Esta funcion la devolvia, la
  //  busqueda de ruta no encontraba camino, y nadie iba nunca a ese puesto.
  //
  //  Asi que primero se buscan los candidatos a los que de verdad se llega.
  //  Si ninguno lo es, se devuelve el primero libre igual: quien pregunta
  //  sabra que no hay ruta, y es mejor que devolver nada.
  let primeroLibre = null;
  for (const c of punto.candidatos ?? [punto]) {
    const celda = celdaDe(c.gx, c.gy);
    if (!transitable(rejilla, celda.cx, celda.cy)) continue;
    if (primeroLibre === null) primeroLibre = celda;
    if (!alcanzable || alcanzable[celda.cy * rejilla.ancho + celda.cx]) return celda;
  }
  return primeroLibre;
}

/**
 * Las celdas a las que se llega andando desde unos rectangulos de partida.
 *
 * Una sola implementacion, porque antes habia dos criterios distintos de «se
 * llega» y no coincidian: uno aceptaba cualquier celda de la VECINDAD de un
 * destino y el otro exigia la celda misma. Con dos definiciones, una decia
 * que a un puesto se llegaba y la otra no encontraba la ruta, y las dos
 * estaban en verde.
 *
 * @returns {Uint8Array} una marca por celda
 */
export function alcanzablesDesde(rejilla, partidas) {
  const visto = new Uint8Array(rejilla.ancho * rejilla.fondo);
  const cola = [];
  for (const c of partidas ?? []) {
    const { cx: x0, cy: y0 } = celdaDe(c.x, c.y);
    const { cx: x1, cy: y1 } = celdaDe(c.x + c.ancho, c.y + c.fondo);
    for (let cy = y0; cy < y1; cy++) {
      for (let cx = x0; cx < x1; cx++) {
        if (!transitable(rejilla, cx, cy)) continue;
        const i = cy * rejilla.ancho + cx;
        if (visto[i]) continue;
        visto[i] = 1;
        cola.push(i);
      }
    }
  }
  for (let k = 0; k < cola.length; k++) {
    const i = cola[k];
    const cx = i % rejilla.ancho;
    const cy = (i - cx) / rejilla.ancho;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = cx + dx;
      const ny = cy + dy;
      if (!transitable(rejilla, nx, ny)) continue;
      const j = ny * rejilla.ancho + nx;
      if (visto[j]) continue;
      visto[j] = 1;
      cola.push(j);
    }
  }
  visto.cuantas = cola.length;
  return visto;
}

/** ¿Se puede pisar esta celda? */
export function transitable(rejilla, cx, cy) {
  if (cx < 0 || cy < 0 || cx >= rejilla.ancho || cy >= rejilla.fondo) return false;
  return rejilla.celdas[cy * rejilla.ancho + cx] === LIBRE;
}

/** La celda que contiene un punto del plano. */
export function celdaDe(gx, gy) {
  return { cx: Math.floor(gx / CELDA), cy: Math.floor(gy / CELDA) };
}

/**
 * El camino de una celda a otra, o `null` si no hay.
 *
 * A* con distancia octil, que es la que corresponde cuando se permiten las
 * ocho direcciones. Y las diagonales sólo si los dos ortogonales están libres:
 * sin esa condición un personaje cruza la esquina entre dos muros, que es el
 * error clásico y se ve enseguida —alguien atravesando el canto de una pared—.
 */
export function camino(rejilla, desde, hasta) {
  if (!transitable(rejilla, desde.cx, desde.cy)) return null;
  if (!transitable(rejilla, hasta.cx, hasta.cy)) return null;

  const n = rejilla.ancho * rejilla.fondo;
  const idx = (c) => c.cy * rejilla.ancho + c.cx;
  const meta = idx(hasta);
  const g = new Float64Array(n).fill(Infinity);
  const padre = new Int32Array(n).fill(-1);
  const cerrado = new Uint8Array(n);
  const h = (cx, cy) => {
    const dx = Math.abs(cx - hasta.cx);
    const dy = Math.abs(cy - hasta.cy);
    return (dx + dy) + (Math.SQRT2 - 2) * Math.min(dx, dy);
  };

  //  Una cola de prioridad de verdad: con una lista y `Math.min` por paso,
  //  una rejilla de 70 x 108 celdas cuesta cientos de miles de comparaciones.
  const monton = [{ f: h(desde.cx, desde.cy), i: idx(desde) }];
  g[idx(desde)] = 0;
  const sacar = () => {
    let mejor = 0;
    for (let k = 1; k < monton.length; k++) if (monton[k].f < monton[mejor].f) mejor = k;
    const x = monton[mejor];
    monton[mejor] = monton[monton.length - 1];
    monton.pop();
    return x;
  };

  while (monton.length > 0) {
    const actual = sacar();
    if (cerrado[actual.i]) continue;
    cerrado[actual.i] = 1;
    if (actual.i === meta) break;
    const cx = actual.i % rejilla.ancho;
    const cy = (actual.i - cx) / rejilla.ancho;
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        if (dx === 0 && dy === 0) continue;
        const nx = cx + dx;
        const ny = cy + dy;
        if (!transitable(rejilla, nx, ny)) continue;
        //  La esquina: en diagonal, los dos ortogonales tienen que estar
        //  libres. Si no, se cruza el canto de un muro.
        if (dx !== 0 && dy !== 0) {
          if (!transitable(rejilla, cx + dx, cy) || !transitable(rejilla, cx, cy + dy)) continue;
        }
        const j = ny * rejilla.ancho + nx;
        const paso = dx !== 0 && dy !== 0 ? Math.SQRT2 : 1;
        if (g[actual.i] + paso < g[j]) {
          g[j] = g[actual.i] + paso;
          padre[j] = actual.i;
          monton.push({ f: g[j] + h(nx, ny), i: j });
        }
      }
    }
  }

  if (!Number.isFinite(g[meta])) return null;
  const ruta = [];
  for (let i = meta; i !== -1; i = padre[i]) {
    const cx = i % rejilla.ancho;
    ruta.push({ cx, cy: (i - cx) / rejilla.ancho });
    if (i === idx(desde)) break;
  }
  return ruta.reverse();
}

/**
 * ¿A qué puestos se llega desde la circulación, y a cuáles no?
 *
 * ESTA ES LA AFIRMACIÓN QUE VALE. Una oficina no está accesible porque tenga
 * un hueco dibujado en el muro: lo está cuando existe un camino desde el
 * pasillo. Las dos cosas se pueden desincronizar con un mueble mal puesto
 * delante de la puerta, y entonces el dibujo dice una cosa y el mapa otra.
 *
 * Se recorre en anchura desde la circulación una sola vez —no un A* por
 * puesto— porque la pregunta es de alcance, no de ruta.
 *
 * @param {any} rejilla
 * @param {{x: number, y: number, ancho: number, fondo: number}[]} circulacion
 */
export function conectividad(rejilla, circulacion) {
  const visto = alcanzablesDesde(rejilla, circulacion);
  const alcanzables = [];
  const aislados = [];
  for (const [id, punto] of rejilla.destinos) {
    //  LA CELDA MISMA de alguno de los cuatro lados del escritorio.
    //
    //  Antes valia cualquier celda de su VECINDAD, para absorber el error con
    //  que se pintan los bultos. Esa holgura dejaba pasar un puesto cuya
    //  unica celda libre estaba dentro de una bolsa cerrada: la vecina de al
    //  lado, del otro lado del mueble, si se alcanzaba. Ya no hace falta
    //  —ahora ningun bulto cruza un muro— y afirmar de menos es peor que
    //  rodear de mas.
    const llega = (punto.candidatos ?? [punto]).some((c) => {
      const { cx, cy } = celdaDe(c.gx, c.gy);
      if (cx < 0 || cy < 0 || cx >= rejilla.ancho || cy >= rejilla.fondo) return false;
      return Boolean(visto[cy * rejilla.ancho + cx]);
    });
    (llega ? alcanzables : aislados).push(id);
  }
  return { alcanzables, aislados, celdasAlcanzadas: visto.cuantas };
}
