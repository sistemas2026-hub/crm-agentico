/**
 * «Consultando» no es «no hay»  (07/11/2026).
 *
 * La ficha del ISP, la óptica y el ticket del CRM llegan DESPUÉS de la
 * conversación. Mientras viajan, cada panel tiene que decir que los está
 * buscando, y no su aviso de ausencia: «Sin consultar» invita a apretar el
 * botón y pedir la misma lectura dos veces, y un bloque que aparece de golpe
 * --o nunca-- no dice nada. Se afirma sobre lo que SALE dibujado, en las dos
 * direcciones: mientras viaja dice «consultando», y cuando llegó ya no.
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from 'svelte/server';

// CasePanel usa `enhance` en el formulario de asignar. Fuera de SvelteKit ese
// módulo no existe, y al dibujar en el servidor la acción no corre.
vi.mock('$app/forms', () => ({ enhance: () => ({ destroy() {} }) }));
import CustomerPanel from './CustomerPanel.svelte';
import CasePanel from './CasePanel.svelte';
import NetworkPanel from './NetworkPanel.svelte';

const texto = (/** @type {any} */ Componente, /** @type {any} */ props) =>
  render(Componente, { props }).body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

const conversacion = { id: 'c1', estado: 'abierta', usuario_externo: '573001112233', id_cliente: '77' };

describe('la ficha del cliente', () => {
  it('mientras viaja, dice que consulta el sistema del ISP', () => {
    expect(texto(CustomerPanel, { conversacion, ficha: null, consultando: true }))
      .toContain('Consultando el sistema del ISP');
  });

  it('cuando llegó, ya no', () => {
    const t = texto(CustomerPanel, { conversacion, ficha: { plan_internet: 'PLAN 300' }, consultando: false });
    expect(t).not.toContain('Consultando');
    expect(t).toContain('PLAN 300');
  });
});

describe('el caso del CRM', () => {
  const base = { conversacion: { ...conversacion, caso_id: 'k1' }, owners: [], ownerActual: null };

  it('mientras viaja, dice que consulta el CRM', () => {
    expect(texto(CasePanel, { ...base, caso: null, cargandoCaso: true })).toContain('Consultando el CRM');
  });

  it('si llegó sin ticket (el CRM no contestó), no queda «consultando» para siempre', () => {
    expect(texto(CasePanel, { ...base, caso: null, cargandoCaso: false })).not.toContain('Consultando');
  });
});

describe('la óptica de una escalada', () => {
  const base = { acciones: [], serial: 'ZTEG1', conversacionId: 'c1' };

  it('mientras viaja, dice que consulta el equipo y no ofrece pedirla otra vez', () => {
    const html = render(NetworkPanel, { props: { ...base, optica: null, consultandoAlAbrir: true } }).body;
    const t = texto(NetworkPanel, { ...base, optica: null, consultandoAlAbrir: true });
    expect(t).toContain('Consultando el equipo');
    expect(t).not.toContain('Sin consultar');
    expect(html).toMatch(/<button[^>]*disabled[^>]*>[\s\S]*?Consultando…/);
  });

  it('si llegó sin medición, vuelve el aviso y el botón', () => {
    const optica = { disponible: false, motivo: 'no_consultada', optica: null };
    const t = texto(NetworkPanel, { ...base, optica, consultandoAlAbrir: false });
    expect(t).toContain('Sin consultar');
    expect(t).toContain('Consultar ahora');
  });
});

/* «Confirmado — en vivo» sólo cuando hay una medición (07/11/2026). La banda
   lo decía siempre --con «Sin consultar», con «El sistema de red no
   respondió», mientras la lectura viajaba--, y con el nombre del proveedor de
   una sola empresa. */
describe('la banda de procedencia', () => {
  const base = { acciones: [], serial: 'HWTCA6FB5263', conversacionId: 'c1' };
  const medida = {
    disponible: true,
    umbral_rx_dbm: -27,
    leido_en: '2026-11-07T15:00:00Z',
    optica: {
      serial: 'HWTCA6FB5263',
      estado: { response_code: 'success', status: true, onu_status: 'Online' },
      senal: { onu_signal: 'Very good', onu_signal_1490: '-21.02 dBm', status: true },
      topologia: null
    }
  };

  it('sin medición no afirma nada confirmado', () => {
    for (const optica of [
      { disponible: false, motivo: 'no_consultada', optica: null },
      { disponible: false, motivo: 'sin_conexion', optica: null },
      null
    ]) {
      const t = texto(NetworkPanel, { ...base, optica, consultandoAlAbrir: optica === null });
      expect(t).not.toContain('Confirmado');
      expect(t).not.toContain('En vivo');
    }
  });

  it('con medición lo dice, sin nombrar a ningún proveedor', () => {
    const t = texto(NetworkPanel, { ...base, optica: medida });
    expect(t).toContain('Confirmado — en vivo desde el sistema de red');
    expect(t).toContain('En vivo');
    expect(t).not.toMatch(/SmartOLT/i);
  });
});
