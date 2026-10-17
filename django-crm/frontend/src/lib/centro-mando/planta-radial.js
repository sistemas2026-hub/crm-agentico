/**
 * PLANTA RADIAL: el orquestador al centro y las areas en anillo.
 *
 * Es una PROPUESTA en paralelo a planta.js, no su reemplazo. Vive aparte a
 * proposito: la planta en rejilla esta en uso y no se toca mientras esta se
 * mira. Comparten `ejes`, `iso` y `poli`, que son la proyeccion y no el
 * diseño.
 *
 * QUE CAMBIA RESPECTO A LA REJILLA
 * En la rejilla, la puerta de entrada del tenant es una sala mas, colocada
 * en una esquina por el mismo reparto que a las demas. Aqui es el centro, y
 * las areas cuelgan de ella. Eso NO es decoracion: es la topologia real del
 * motor --todo el que escribe por un canal publico entra por `rol_de_entrada`
 * (config/schema.py) y de ahi se deriva--, asi que el dibujo dice algo que
 * es cierto aunque no se mueva nada.
 *
 * LO QUE EL ANILLO NO AFIRMA
 * Los pasillos radiales dicen "de aqui se deriva alla", que es estructura.
 * NO dicen cuanto trafico pasa ni cuando: el destino de cada derivacion vive
 * en tool_calls.parametros y hoy no sale en el payload. Un pasillo mas ancho
 * o iluminado seria inventarse el dato.
 */

import { ejes, iso } from './planta.js';

/**
 * Las salas repartidas en un anillo alrededor de un centro.
 *
 * El radio NO es una constante: sale de que dos salas contiguas no se toquen.
 * Con n salas la separacion angular es 2*PI/n, asi que la distancia entre dos
 * centros contiguos es 2*R*sen(PI/n) -- y esa distancia tiene que ser mayor
 * que lo que miden las dos salas. Despejando R queda el radio minimo. Con
 * pocas areas el anillo se cierra y manda el hueco del centro; con muchas
 * manda el solapamiento.
 *
 * @param {{n:number, area?:string, principal?:boolean}[]} grupos la principal va al CENTRO
 * @param {{ancho:number, alto:number, lado:number, separacion?:number,
 *          pared?:number, rotulo?:number, holguraAlto?:number,
 *          elevacion?:number, escalaMaxima?:number, pasillo?:number}} caja
 */
export function anilloDeSalas(grupos, caja) {
  const {
    ancho, alto, lado,
    separacion = 22, pared = 30, rotulo = 0, pasillo = 46,
    holguraAlto = 0, elevacion = null, escalaMaxima = 1.6
  } = caja;

  const lista = grupos || [];
  if (!lista.length) {
    return { salas: [], centro: null, radios: [], escala: 1, ancho: 0, alto: 0, ejes: ejes(34) };
  }

  const paso = lado + separacion;
  const centroDe = lista.find((g) => g.principal) || null;
  const alrededor = lista.filter((g) => !g.principal);
  const n = alrededor.length;

  /* Cada sala mide lo que SU contenido, igual que en la rejilla: una sala de
     un puesto con el ancho de una de dos queda medio vacia. */
  const medida = (g) => {
    const cols = Math.min(g.n, 2);
    const filas = Math.ceil(g.n / Math.min(2, Math.max(1, g.n)));
    return {
      cols,
      w: cols * paso - separacion + pared * 2,
      h: filas * paso - separacion + pared * 2 + rotulo
    };
  };
  const medidas = alrededor.map(medida);
  const medidaCentro = centroDe ? medida(centroDe) : { cols: 1, w: paso - separacion + pared * 2, h: paso - separacion + pared * 2 + rotulo };

  // Lo que ocupa una sala vista desde el centro: su semidiagonal.
  const semi = (m) => Math.hypot(m.w, m.h) / 2;
  const mayor = Math.max(...medidas.map(semi), 1);
  const semiCentro = semi(medidaCentro);

  /* EL RADIO, por las dos condiciones que lo aprietan. */
  const porSolape = n > 1 ? (mayor * 2 * 1.06) / (2 * Math.sin(Math.PI / n)) : 0;
  const porCentro = semiCentro + mayor + pasillo;
  const R = Math.max(porSolape, porCentro);

  /* El anillo arranca ARRIBA (-PI/2) y gira. Arriba en planta es el fondo de
     la escena, asi que la primera area queda detras del centro y no delante,
     tapandolo. */
  const angulo = (i) => -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, n);

  const crudas = alrededor.map((g, i) => {
    const m = medidas[i];
    const t = angulo(i);
    const cu = R * Math.cos(t), cv = R * Math.sin(t);
    return {
      ...g, indice: i, angulo: t, subCols: m.cols, rotulo,
      u0: cu - m.w / 2, v0: cv - m.h / 2, u1: cu + m.w / 2, v1: cv + m.h / 2
    };
  });

  const centro = centroDe ? {
    ...centroDe, indice: -1, subCols: medidaCentro.cols, rotulo, principal: true,
    u0: -medidaCentro.w / 2, v0: -medidaCentro.h / 2,
    u1: medidaCentro.w / 2, v1: medidaCentro.h / 2,
    radio: semiCentro
  } : null;

  const todas = centro ? [centro, ...crudas] : crudas;

  /* LA ELEVACION SE DERIVA, igual que en la rejilla: un rombo isometrico
     tiene siempre la relacion ex/ey de su elevacion, y un monitor ronda 2:1.
     Con la elevacion fija sobra ancho que ningun reparto aprovecha. */
  const candidatas = elevacion != null ? [elevacion] : [26, 29, 32, 35];
  let mejor = null;
  for (const grados of candidatas) {
    const e = ejes(grados);
    const qs = todas.flatMap((s) => [
      iso(s.u0, s.v0, 0, e), iso(s.u1, s.v0, 0, e),
      iso(s.u1, s.v1, 0, e), iso(s.u0, s.v1, 0, e)
    ]);
    const w = Math.max(...qs.map((q) => q[0])) - Math.min(...qs.map((q) => q[0]));
    const h = Math.max(...qs.map((q) => q[1])) - Math.min(...qs.map((q) => q[1])) + holguraAlto * lado;
    const escala = Math.min(ancho / w, alto / h, escalaMaxima);
    if (!mejor || escala > mejor.escala) mejor = { escala, e, w, h, qs };
  }
  const { escala, e, w, h, qs } = mejor;

  const puestosDe = (s) => Array.from({ length: s.n }, (_, k) => ({
    u: s.u0 + pared + (k % s.subCols) * paso,
    v: s.v0 + pared + Math.floor(k / s.subCols) * paso
  }));

  /* ORDEN DE PINTADO: en isometrica lo que esta delante tapa a lo que esta
     detras, y "delante" es u+v mayor. Sin esto una sala del fondo se dibuja
     encima de una de delante y la escena se deshace. */
  const salas = crudas
    .map((s) => ({ ...s, puestos: puestosDe(s) }))
    .sort((a, b) => (a.u0 + a.v0) - (b.u0 + b.v0));

  /* LOS PASILLOS RADIALES: del centro a cada area.
     El arranque NO es un radio fijo. Lo era --semiCentro * 0.9, o sea un
     circulo-- y las salas son RECTANGULOS: en las diagonales la semidiagonal
     es mucho mayor que la distancia a la pared, asi que el pasillo nacia
     despegado de la sala y en las direcciones de los ejes nacia metido
     dentro. Ese era el desalineado que se veia.
     Ahora el arranque es donde el rayo CORTA la pared del centro: para un
     rectangulo centrado y semiejes (hw,hh), el rayo sale a la distancia
     min(hw/|cos|, hh/|sen|). Exacto, no aproximado. */
  const corte = (hw, hh, dx, dy) => {
    const ax = Math.abs(dx), ay = Math.abs(dy);
    return Math.min(ax > 1e-9 ? hw / ax : Infinity, ay > 1e-9 ? hh / ay : Infinity);
  };
  const anchoVia = Math.max(18, pasillo * 0.52);
  const radios = crudas.map((s, i) => {
    const t = s.angulo;
    const dx = Math.cos(t), dy = Math.sin(t);
    const px = -Math.sin(t), py = Math.cos(t);
    const m = medidas[i];
    /* NACE EN EL CENTRO MISMO, no en su pared. Naciendo justo en la pared
       el empalme se veia: el borde del ducto y el canto del suelo no caen en
       la misma linea y quedaba un escalon. Metido debajo, el suelo opaco de
       la sala lo tapa y el pasillo simplemente sale de la oficina. */
    const r0 = 0;
    /* El otro extremo se mete un poco BAJO la sala a proposito: el suelo de
       la sala se pinta opaco encima y el pasillo muere en su pared, sin
       dejar la cuña que queda al cortarlo en angulo contra un muro. */
    const r1 = R - corte(m.w / 2, m.h / 2, dx, dy) + Math.min(m.w, m.h) * 0.42;
    const q = (r, lado2) => [dx * r + px * anchoVia * lado2, dy * r + py * anchoVia * lado2];
    return {
      area: s.area, angulo: t,
      // por donde camina alguien: el eje del pasillo, de pared a pared
      eje: { desde: [dx * r0, dy * r0], hasta: [dx * (R - corte(m.w / 2, m.h / 2, dx, dy)), dy * (R - corte(m.w / 2, m.h / 2, dx, dy))] },
      esquinas: [q(r0, 0.5), q(r1, 0.5), q(r1, -0.5), q(r0, -0.5)]
    };
  });

  /* LO QUE HAY ENTRE LAS OFICINAS. Un anillo con pocas areas deja huecos
     grandes, y un hueco vacio se lee como error de encaje. Van en el angulo
     MEDIO entre dos salas contiguas --justo donde no hay pasillo-- y a un
     radio derivado, no a ojo: asi el reparto sigue siendo correcto con tres
     areas o con nueve. */
  const jardin = n > 1 ? crudas.map((s2, i) => {
    const t = (s2.angulo + crudas[(i + 1) % n].angulo +
      (i + 1 === n ? 2 * Math.PI : 0)) / 2;
    const rr = R * 0.78;
    return { u: rr * Math.cos(t), v: rr * Math.sin(t), angulo: t, semilla: i };
  }) : [];

  const minX = Math.min(...qs.map((q) => q[0]));
  const minY = Math.min(...qs.map((q) => q[1]));

  return {
    salas,
    centro: centro ? { ...centro, puestos: puestosDe(centro) } : null,
    radios, jardin, radio: R, escala, ejes: e,
    dx: -minX, dy: -minY, ancho: w, alto: h
  };
}
