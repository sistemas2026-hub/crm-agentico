/**
 * RECORRER LAS ÓRDENES DE UNA CUADRILLA (07/11/2026).
 *
 * El usuario: «agregá una flecha que tenga el nombre de con qué sigue después
 * de este ticket y al presionarla muestre la tarjeta de la siguiente, y así
 * hasta mostrar todos los tickets».
 *
 * Las pruebas del componente corren con `render` de `svelte/server`: dibujan,
 * no hacen clic. Por eso la decisión de QUÉ orden se muestra vive en un módulo
 * aparte y se afirma acá sobre el EFECTO —qué orden queda a la vista, qué dice
 * el título, a cuántas se llega encadenando la flecha—, que es lo único que
 * un clic podría cambiar.
 */
import { describe, expect, it } from 'vitest';

import {
  indiceDelFoco,
  nombreDeLaOrden,
  recorrido,
  tituloDel
} from './recorrido-de-la-cuadrilla.js';

/** La forma de `dia_publicado.filas_de`: en el orden de la app. */
const ot = (numero, extra = {}) => ({
  numero,
  asunto: `Asunto ${numero}`,
  direccion: `CL ${numero}`,
  barrio: '',
  estado: 'asignada',
  estado_texto: 'Asignada',
  siguiente: false,
  ...extra
});

const DIEZ = [2, 5, 9, 12, 21, 30, 44, 51, 60, 167].map((n) => ot(n));

describe('de qué orden habla el cuadro cuando nadie tocó nada', () => {
  it('la que tiene en curso, aunque otra esté marcada como siguiente', () => {
    const l = [ot(2), ot(5, { siguiente: true }), ot(9)];
    expect(indiceDelFoco(l, 9)).toBe(2);
    expect(recorrido(l, 9).orden.numero).toBe(9);
  });

  it('sin orden en curso, la marcada como siguiente', () => {
    const l = [ot(2), ot(5, { siguiente: true }), ot(9)];
    expect(recorrido(l, null).orden.numero).toBe(5);
  });

  it('sin ninguna marcada, la primera del día: siempre se puede empezar a recorrer', () => {
    expect(recorrido([ot(2), ot(5)], null).orden.numero).toBe(2);
  });

  it('sin órdenes no hay nada que recorrer y no hay flecha', () => {
    for (const vacio of [[], undefined, null]) {
      const p = recorrido(vacio, null);
      expect(p.orden).toBeNull();
      expect(p.siguiente).toBeNull();
      expect(p.total).toBe(0);
    }
  });

  it('con una sola orden no hay siguiente ni anterior', () => {
    const p = recorrido([ot(7)], 7);
    expect(p.siguiente).toBeNull();
    expect(p.anterior).toBeNull();
    expect(p.total).toBe(1);
  });
});

describe('la flecha avanza, y se llega a TODAS', () => {
  //  EL PEDIDO, medido: «y así hasta mostrar todos los tickets». No alcanza
  //  con que la flecha exista — tiene que terminar el recorrido.
  it('encadenando la flecha desde el foco se ven todas las que faltan', () => {
    const l = DIEZ.map((o, i) => (i === 3 ? { ...o, siguiente: true } : o));
    const vistas = [];
    let viendo = null;
    for (let i = 0; i < 50; i++) {
      const p = recorrido(l, null, viendo);
      vistas.push(p.orden.numero);
      if (!p.siguiente) break;
      viendo = p.siguiente.numero;
    }
    expect(vistas).toEqual([12, 21, 30, 44, 51, 60, 167]);
  });

  it('desde la primera se recorren las diez', () => {
    const vistas = [];
    let viendo = null;
    for (let i = 0; i < 50; i++) {
      const p = recorrido(DIEZ, null, viendo);
      vistas.push(p.orden.numero);
      if (!p.siguiente) break;
      viendo = p.siguiente.numero;
    }
    expect(vistas).toEqual(DIEZ.map((o) => o.numero));
    expect(vistas.length).toBe(10);
  });

  it('la última no ofrece flecha: el recorrido termina, no da la vuelta', () => {
    const p = recorrido(DIEZ, null, 167);
    expect(p.siguiente).toBeNull();
    expect(p.posicion).toBe(10);
    expect(p.total).toBe(10);
  });

  it('la de atrás vuelve a la de antes, y la primera no tiene atrás', () => {
    expect(recorrido(DIEZ, null, 21).anterior.numero).toBe(12);
    expect(recorrido(DIEZ, null, 2).anterior).toBeNull();
  });

  it('se cuenta desde 1 y sobre el total del día', () => {
    const p = recorrido(DIEZ, null, 30);
    expect(p.posicion).toBe(6);
    expect(p.total).toBe(10);
  });

  it('volver a lo de ahora es soltar lo que se estaba mirando', () => {
    expect(recorrido(DIEZ, 9, 167).enElFoco).toBe(false);
    expect(recorrido(DIEZ, 9, null).orden.numero).toBe(9);
    expect(recorrido(DIEZ, 9, null).enElFoco).toBe(true);
  });
});

describe('el recorrido sobrevive a la recarga de los 15 s', () => {
  //  Programación se refresca sola. Si el recorrido guardara «voy en la
  //  tercera», un reparto nuevo correría la lista y el cuadro saltaría a otra
  //  orden sin que nadie tocara nada, mientras alguien la está leyendo.
  it('EL DEFECTO DEL ÍNDICE: si entra una orden adelante, se sigue viendo LA MISMA', () => {
    const antes = recorrido(DIEZ, null, 30);
    expect(antes.posicion).toBe(6);

    const despues = recorrido([ot(1), ...DIEZ], null, 30);
    expect(despues.orden.numero).toBe(30);
    expect(despues.posicion).toBe(7); // se corrió de lugar, no de orden
  });

  it('si se termina la que se estaba mirando, vuelve solo a lo de ahora', () => {
    const quedan = DIEZ.filter((o) => o.numero !== 30);
    const p = recorrido(quedan, 12, 30);
    expect(p.orden.numero).toBe(12);
    expect(p.enElFoco).toBe(true);
  });

  it('y si además cambió la orden en curso, se la muestra', () => {
    const p = recorrido(DIEZ, 44, 999);
    expect(p.orden.numero).toBe(44);
  });
});

describe('el título dice de qué está hablando el cuadro', () => {
  const r = { salio: '07:42', hechas: 3, total: 10, en_curso: { numero: 12, estado: 'en_sitio' } };

  //  EL RIESGO DE ESTA FUNCIÓN. Es el mismo error que se arregló el
  //  30/10/2026 al revés, y acá es peor: el cuadro sirve para decidir a quién
  //  llamar, y «En sitio · OT #12» encima de la dirección de la #21 manda a
  //  llamar por lo que no es.
  it('EL DEFECTO: mirando otra orden NO repite lo que la cuadrilla hace ahora', () => {
    const t = tituloDel(r, recorrido(DIEZ, 12, 21));
    expect(t).not.toContain('#12');
    expect(t).toContain('#21');
  });

  it('mirando otra orden dice el estado DE ESA orden', () => {
    const l = DIEZ.map((o) => (o.numero === 21 ? { ...o, estado_texto: 'Completada' } : o));
    expect(tituloDel(r, recorrido(l, 12, 21))).toBe('Completada · OT #21');
  });

  it('sin estado_texto igual dice de cuál habla', () => {
    const l = [ot(2), { numero: 21 }];
    expect(tituloDel(r, recorrido(l, 2, 21))).toBe('OT #21');
  });

  //  EL CONTROL: la mitad que no se puede romper al arreglar la otra. Sin
  //  recorrer, el cuadro tiene que decir exactamente lo de antes.
  it('en el foco, en sitio y en camino, como siempre', () => {
    expect(tituloDel(r, recorrido(DIEZ, 12, null))).toBe('En sitio · OT #12');
    const yendo = { ...r, en_curso: { numero: 12, estado: 'en_camino' } };
    expect(tituloDel(yendo, recorrido(DIEZ, 12, null))).toBe('En camino · OT #12');
  });

  it('sin salir dice por cuál empieza; habiendo salido, por cuál sigue', () => {
    const l = [ot(2, { siguiente: true }), ot(5)];
    const sin = { salio: null, hechas: 0, total: 7, en_curso: null };
    expect(tituloDel(sin, recorrido(l, null, null))).toBe('Empieza por OT #2');
    expect(tituloDel({ ...sin, salio: '07:42' }, recorrido(l, null, null))).toBe('Sigue OT #2');
  });

  it('terminó el día, entre órdenes y todavía no sale', () => {
    const p = recorrido([], null, null);
    expect(tituloDel({ salio: '07:42', hechas: 4, total: 4, en_curso: null }, p)).toBe('Terminó el día');
    expect(tituloDel({ salio: '07:42', hechas: 2, total: 4, en_curso: null }, p)).toBe('Entre órdenes');
    expect(tituloDel({ salio: null, hechas: 0, total: 4, en_curso: null }, p)).toBe('Todavía no sale');
  });

  it('con todo cancelado NO inventa que la cuadrilla sigue por una orden que ya pasó', () => {
    //  El recorrido arranca en la primera para poder recorrer; el título no
    //  tiene derecho a leer eso como «sigue por».
    const canceladas = [ot(2, { estado: 'cancelada' }), ot(5, { estado: 'cancelada' })];
    const t = tituloDel({ salio: '07:42', hechas: 2, total: 4, en_curso: null },
                        recorrido(canceladas, null, null));
    expect(t).toBe('Entre órdenes');
  });
});

describe('el nombre con el que se anuncia la que sigue', () => {
  it('el número no alcanza: va el asunto, que es lo que decide si abrirla', () => {
    expect(nombreDeLaOrden(ot(167, { asunto: 'Problemas De Conexión' })))
      .toBe('OT #167 · Problemas De Conexión');
  });

  it('sin asunto cae al tipo de trabajo', () => {
    expect(nombreDeLaOrden({ numero: 5, asunto: '', tipo: 'Instalación' })).toBe('OT #5 · Instalación');
  });

  it('sin nada, el número solo, y nunca un separador colgando', () => {
    expect(nombreDeLaOrden({ numero: 5 })).toBe('OT #5');
    expect(nombreDeLaOrden({ numero: 5, asunto: '   ' })).toBe('OT #5');
  });

  it('sin orden, cadena vacía', () => {
    expect(nombreDeLaOrden(null)).toBe('');
  });
});
