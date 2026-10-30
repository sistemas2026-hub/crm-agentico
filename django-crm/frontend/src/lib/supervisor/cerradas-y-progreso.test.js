import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import EsperanCuadrilla from './EsperanCuadrilla.svelte';
import OrdenCerrada from './OrdenCerrada.svelte';
import OrdenDelDia from './OrdenDelDia.svelte';
import ProgresoDeLaOrden from './ProgresoDeLaOrden.svelte';
import {
  gruposQueEsperan,
  pasoDelProgreso,
  rangoDeCerradas,
  textoDeQuien,
  textoDelTicket
} from './dia-publicado.js';

/**
 * PROGRAMACIÓN: EL PROGRESO, LAS QUE ESPERAN Y LAS CERRADAS (30/10/2026),
 * sobre el boceto que aprobó el usuario.
 */

describe('el progreso de cada orden', () => {
  it('el paso sale del estado; bloqueada y devuelta siguen en sitio; cancelada no tiene', () => {
    expect(['asignada', 'en_camino', 'en_sitio', 'completada_campo', 'cerrada'].map(pasoDelProgreso))
      .toEqual([0, 1, 2, 3, 4]);
    expect([pasoDelProgreso('bloqueada'), pasoDelProgreso('correccion_requerida')]).toEqual([2, 2]);
    expect(pasoDelProgreso('cancelada')).toBe(-1);
  });

  it('lo hecho, donde está y lo que falta, con el paso actual anunciado', () => {
    const h = render(ProgresoDeLaOrden, { props: { estado: 'en_sitio' } }).body;
    expect((h.match(/class="[^"]*pg-hecho/g) ?? []).length).toBe(2);
    expect(h).toMatch(/aria-current="step" class="[^"]*pg-actual"><span class="pg-barra[^"]*"><\/span> <span class="pg-nombre[^"]*">En sitio/);
    expect(render(ProgresoDeLaOrden, { props: { estado: 'cancelada' } }).body).not.toContain('pg-');
  });

  it('sale en la tarjeta de cada orden de Hoy', () => {
    const h = render(OrdenDelDia, {
      props: { orden: { id: 'o', numero: 12, estado: 'en_camino', estado_texto: 'En camino', tecnicos: [] }, dia: '2026-10-30' }
    }).body;
    expect(h).toContain('Progreso de la orden');
    expect(h).toMatch(/aria-current="step" class="[^"]*pg-actual"><span class="pg-barra[^"]*"><\/span> <span class="pg-nombre[^"]*">En camino/);
  });
});

describe('las que esperan cuadrilla', () => {
  //  El grupo chico llega PRIMERO: si no se ordenara, quedaría arriba.
  const esperan = [
    { id: 'b', numero: 16, tipo: 'Trabajo general', prioridad: 'alta', barrio: 'RENACER', por_que: 'Ninguna cuadrilla cubre zona 1 con Trabajos.' },
    { id: 'a', numero: 40, tipo: 'Soporte en campo', prioridad: 'alta', barrio: 'VILLA SOL', por_que: 'Ninguna cuadrilla cubre zona 2 con Soporte.' },
    { id: 'c', numero: 41, tipo: 'Soporte en campo', prioridad: 'alta', barrio: 'VILLA SOL', por_que: 'Ninguna cuadrilla cubre zona 2 con Soporte.' }
  ];

  it('agrupadas por el motivo, la más numerosa primero', () => {
    const g = gruposQueEsperan(esperan);
    expect(g.map((x) => [x.motivo, x.ordenes.length])).toEqual([
      ['Ninguna cuadrilla cubre zona 2 con Soporte.', 2],
      ['Ninguna cuadrilla cubre zona 1 con Trabajos.', 1]
    ]);
  });

  it('plegadas: el total y un grupo por motivo, sin abrir nada', () => {
    const h = render(EsperanCuadrilla, { props: { esperan } }).body;
    expect(h).toContain('Esperan cuadrilla (3)');
    expect(h).not.toMatch(/<details[^>]* open/);
    expect(h).toMatch(/class="ec-cuantas[^"]*">2<\/span> <span class="ec-motivo[^"]*">Ninguna cuadrilla cubre zona 2/);
    expect(render(EsperanCuadrilla, { props: { esperan: [] } }).body).not.toContain('Esperan');
  });
});

describe('las cerradas', () => {
  const orden = (extra = {}) => ({
    id: 'o3', numero: 3, asunto: 'Instalación Tdt', tipo: 'Soporte', cuadrilla: 'Cuadrilla #5',
    cliente: 'Cliente', direccion: 'Calle 1', barrio: 'CENTRO', cerrada_en: '2026-10-30T11:58:00-05:00',
    quien: { de: 'persona', nombre: 'Laura Gómez' }, ticket: { estado: 'cerrado', detalle: '' },
    tiempos: { traslado_min: 20, en_sitio_min: 40 }, solucion: 'Cambié el conector',
    revision: { veredicto: 'se_puede_cerrar', texto: 'Se puede cerrar',
                puntos: [{ clave: 'checklist', ok: true, texto: 'El checklist está completo: datos y fotos.' }] },
    historial: [{ cuando: '30/10 10:00', texto: 'Salió hacia la orden', de: 'tecnico' },
                { cuando: '30/10 11:58', texto: 'Laura Gómez la aprobó', de: 'persona' }],
    ...extra
  });

  it('quién, el ticket, los tiempos, qué hizo, la revisión y su historial plegado', () => {
    const h = render(OrdenCerrada, { props: { orden: orden() } }).body;
    expect(h).toContain('Cerrada 11:58');
    expect(h).toContain('Laura Gómez la aprobó y la cerró');
    expect(h).toContain('Cerrado en el sistema del ISP');
    expect(h).toContain('20 min en camino · 40 min en sitio');
    expect(h).toContain('Qué hizo: «Cambié el conector»');
    expect(h).toContain('Lo que revisó el Supervisor:</strong> Se puede cerrar');
    expect(h).toContain('Historial de la OT (2)');
    expect(h).not.toMatch(/<details[^>]* open/);
    expect((h.match(/class="[^"]*pg-hecho/g) ?? []).length).toBe(4);
  });

  it('el ticket que no se cerró en rojo, y sin foto lo dice', () => {
    const h = render(OrdenCerrada, {
      props: { orden: orden({ ticket: { estado: 'no_cerrado', detalle: 'FALLO_AL_CERRAR' }, revision: null }) }
    }).body;
    expect(h).toMatch(/class="[^"]*oc-mal[^"]*">No se pudo cerrar en el sistema del ISP: FALLO_AL_CERRAR/);
    expect(h).toContain('Se cerró antes de que se guardara lo que revisaba el Supervisor.');
  });

  it('los textos de quién y del ticket', () => {
    expect(textoDeQuien({ de: 'supervisor' })).toBe('El Supervisor la aprobó y la cerró');
    expect(textoDeQuien({ de: 'sin_registro' })).toBe('Se cerró sin una aprobación registrada');
    expect(textoDelTicket({ estado: 'sin_ticket' })).toBe('La orden no tiene ticket del ISP');
    expect(textoDelTicket(null)).toBe('Sin registro de cómo quedó el ticket');
  });

  it('el rango: hoy, ayer o los últimos 7 días con hoy incluido', () => {
    expect(rangoDeCerradas('hoy', '2026-10-30')).toEqual({ desde: '2026-10-30', hasta: '2026-10-30' });
    expect(rangoDeCerradas('ayer', '2026-11-01')).toEqual({ desde: '2026-10-31', hasta: '2026-10-31' });
    expect(rangoDeCerradas('7d', '2026-10-30')).toEqual({ desde: '2026-10-24', hasta: '2026-10-30' });
  });
});
