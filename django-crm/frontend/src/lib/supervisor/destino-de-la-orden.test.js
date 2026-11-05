import { describe, expect, it } from 'vitest';

import { opcionesDelDestino, ordenDelFoco, queDibujar } from './destino-de-la-orden.js';

/**
 * LOS CUATRO ESCENARIOS DEL MAPA (05/11/2026).
 *
 * Son del pedido del usuario, no casos de borde inventados: empezó a cargar
 * coordenadas a sus clientes y hay que decidir qué se dibuja cuando falta
 * una punta, la otra, o las dos.
 *
 * Lo que atraviesa los cuatro y es lo que de verdad se está probando: **no
 * se inventa un punto**. Ni geocodificando la dirección, ni usando el centro
 * del barrio, ni dejando una posición vieja pasar por la de ahora.
 */
const POS = { latitud: 10.9185, longitud: -74.7668, minutos: 3, fresca: true };
const DEST = { latitud: 10.93, longitud: -74.78 };

const orden = (extra = {}) => ({
  id: 'o-1', numero: 7, asunto: 'Cambio de contraseña', destino: null,
  siguiente: true, ...extra
});
const cuadrilla = (extra = {}) => ({
  jornada: 'j-1', cuadrilla: 'Cuadrilla #5', posicion: null,
  ordenes: [orden()], ...extra
});

describe('qué dibujar de una cuadrilla', () => {
  it('D · con las dos puntas: se ven las dos y se unen', () => {
    const q = queDibujar(cuadrilla({
      posicion: POS,
      ordenes: [orden({ destino: DEST })]
    }));

    expect(q.escenario).toBe('D');
    expect(q.vehiculo).toEqual({ latitud: POS.latitud, longitud: POS.longitud });
    expect(q.destino).toEqual(DEST);
    expect(q.une).toBe(true);
    expect(q.falta).toBe('');
  });

  it('A · técnico sí, orden sin coordenadas: NO se le inventa un punto', () => {
    const q = queDibujar(cuadrilla({ posicion: POS }));

    expect(q.escenario).toBe('A');
    expect(q.vehiculo).not.toBeNull();
    expect(q.destino).toBeNull();
    //  Y sin línea: con una sola punta sería una ruta hacia un lugar que
    //  nadie midió.
    expect(q.une).toBe(false);
    expect(q.falta).toContain('OT #7 sin ubicación');
  });

  it('B · sin técnico pero con destino: se ve a dónde va, y se dice', () => {
    const q = queDibujar(cuadrilla({ ordenes: [orden({ destino: DEST })] }));

    expect(q.escenario).toBe('B');
    expect(q.vehiculo).toBeNull();
    expect(q.destino).toEqual(DEST);
    expect(q.une).toBe(false);
    expect(q.falta).toContain('Sin ubicación del técnico');
  });

  it('C · sin ninguna de las dos: ni un marcador, y la cuadrilla se nombra', () => {
    const q = queDibujar(cuadrilla());

    expect(q.escenario).toBe('C');
    expect(q.vehiculo).toBeNull();
    expect(q.destino).toBeNull();
    expect(q.une).toBe(false);
    expect(q.falta).toContain('OT #7');
  });

  it('una coordenada a medias no cuenta como destino', () => {
    for (const roto of [{ latitud: 10.9 }, { longitud: -74.7 }, { latitud: null, longitud: null }]) {
      const q = queDibujar(cuadrilla({ posicion: POS, ordenes: [orden({ destino: roto })] }));
      expect(q.destino).toBeNull();
      expect(q.escenario).toBe('A');
    }
  });

  it('el cero es una coordenada válida, no un dato que falta', () => {
    //  `0` es falsy en JavaScript y es el ecuador: tratarlo como ausente
    //  borraría del mapa a media África y a Ecuador entero.
    const q = queDibujar(cuadrilla({
      posicion: POS,
      ordenes: [orden({ destino: { latitud: 0, longitud: 0 } })]
    }));

    expect(q.destino).toEqual({ latitud: 0, longitud: 0 });
    expect(q.escenario).toBe('D');
  });

  it('sin órdenes no revienta', () => {
    expect(queDibujar({ ordenes: [] }).escenario).toBe('C');
    expect(queDibujar({}).escenario).toBe('C');
    expect(queDibujar(null).escenario).toBe('C');
  });
});

describe('cuál orden manda en el mapa', () => {
  it('la que la cuadrilla hace ahora, no la primera de la lista', () => {
    const c = cuadrilla({
      ordenes: [
        orden({ numero: 1, siguiente: false }),
        orden({ numero: 9, siguiente: true })
      ]
    });

    expect(ordenDelFoco(c).numero).toBe(9);
  });

  it('sin ninguna marcada, la primera', () => {
    const c = cuadrilla({ ordenes: [orden({ numero: 4, siguiente: false })] });
    expect(ordenDelFoco(c).numero).toBe(4);
  });
});

describe('el pin del destino', () => {
  it('se ancla en su punta, no en el medio', () => {
    const o = opcionesDelDestino();
    expect(o.iconAnchor).toEqual([13, 30]);
    expect(o.className).toBe('mp-destino');
    expect(o.html.startsWith('<svg')).toBe(true);
  });
});
