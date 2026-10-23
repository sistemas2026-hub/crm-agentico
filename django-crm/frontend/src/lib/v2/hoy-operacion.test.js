/**
 * LA COLA DE "HOY DE LA OPERACION": QUE ENTRA, CON QUE TONO Y EN QUE ORDEN.
 *
 * Lo que importa afirmar es el veredicto: que algo se pinte "vencido" solo
 * cuando hay un plazo real que paso, y que lo mas urgente quede primero.
 */
import { describe, expect, it } from 'vitest';
import { armarCola, contarPorTono, duracion, resumen } from './hoy-operacion.js';

const AHORA = Date.parse('2026-10-23T15:00:00Z');
const hace = (min) => new Date(AHORA - min * 60000).toISOString();

describe('conversaciones', () => {
  it('un cliente esperando mas que el SLA es vencido, con la barra llena', () => {
    const [item] = armarCola({
      conversaciones: [{ id: 'c1', banda: 1, esperando_desde: hace(18), motivo_cola: 'Sin servicio' }],
      slaTomaMinutos: 15,
      ahora: AHORA
    });
    expect(item.tono).toBe('urg');
    expect(item.titulo).toBe('Un cliente espera respuesta de una persona');
    expect(item.detalle).toBe('Sin servicio');
    expect(item.href).toBe('/conversaciones/c1');
    expect(item.plazo).toEqual({ uso: 100, texto: '18 min de 15 min' });
  });

  it('dentro del SLA necesita atencion pero no esta vencido', () => {
    const [item] = armarCola({
      conversaciones: [{ id: 'c1', banda: 1, esperando_desde: hace(9) }],
      slaTomaMinutos: 15,
      ahora: AHORA
    });
    expect(item.tono).toBe('aten');
    expect(item.plazo?.uso).toBe(60);
  });

  it('sin SLA configurado nunca es vencido ni dibuja barra', () => {
    const [item] = armarCola({
      conversaciones: [{ id: 'c1', banda: 1, esperando_desde: hace(500) }],
      slaTomaMinutos: 0,
      ahora: AHORA
    });
    expect(item.tono).toBe('aten');
    expect(item.plazo).toBeNull();
  });

  it('varias en la misma banda se juntan en un solo item que cuenta y mira la mas vieja', () => {
    const cola = armarCola({
      conversaciones: [
        { id: 'a', banda: 2, esperando_desde: hace(3) },
        { id: 'b', banda: 2, esperando_desde: hace(11) },
        { id: 'c', banda: 5, esperando_desde: hace(90) }
      ],
      slaTomaMinutos: 15,
      ahora: AHORA
    });
    expect(cola).toHaveLength(1);
    expect(cola[0].titulo).toBe('2 conversaciones escaladas sin asignar');
    expect(cola[0].cuando).toBe('La más vieja: 11 min');
  });
});

describe('fuentes sin plazo', () => {
  it('bloqueos del NOC, instalaciones y pedidos piden atencion, nunca vencido', () => {
    const cola = armarCola({
      bloqueos: [
        { requiere_noc: true, minutos_detenido: 47, motivo: 'La ONU no aparece en la OLT' },
        { requiere_noc: false, minutos_detenido: 300 }
      ],
      solicitudes: [{ enviada_en: hace(60 * 20) }],
      pedidos: [{ estado: 'pendiente', en: hace(35) }, { estado: 'resuelto', en: hace(5) }],
      ahora: AHORA
    });
    expect(cola.map((i) => i.tono)).toEqual(['aten', 'aten', 'aten']);
    const noc = cola.find((i) => i.origen === 'NOC');
    expect(noc?.titulo).toBe('Una orden está detenida esperando al NOC');
    expect(noc?.detalle).toBe('La ONU no aparece en la OLT');
    expect(cola.find((i) => i.origen === 'Bodega')?.titulo).toBe('1 pedido de material sin resolver');
  });

  it('un bloqueo que NO requiere NOC no entra: lo destraba otro, no esta mesa', () => {
    expect(armarCola({ bloqueos: [{ requiere_noc: false, minutos_detenido: 99 }] })).toEqual([]);
  });
});

describe('orden y CRM', () => {
  it('vencido primero, y dentro de atencion quien espera hace mas', () => {
    const cola = armarCola({
      conversaciones: [{ id: 'c1', banda: 1, esperando_desde: hace(30) }],
      slaTomaMinutos: 15,
      solicitudes: [{ enviada_en: hace(60 * 24) }],
      pedidos: [{ estado: 'pendiente', en: hace(10) }],
      crm: [
        { id: 7, tone: 'slate', title: 'Ticket sin respuesta', href: '/tickets/7', due: 'Hace 3 h' },
        { id: 8, tone: 'rust', title: 'Factura vencida', href: '/invoices/8', due: 'Vencida' }
      ],
      ahora: AHORA
    });
    expect(cola.map((i) => i.id)).toEqual(['conv-espera', 'crm-8', 'instalaciones', 'bodega-pedidos', 'crm-7']);
    expect(cola[1].origen).toBe('Facturas');
    expect(cola[4].icono).toBe('ticket');
  });

  it('una fuente que no se pudo leer (null) no tumba a las demas', () => {
    const cola = armarCola({ conversaciones: null, pedidos: [{ estado: 'pendiente', en: hace(5) }] });
    expect(cola).toHaveLength(1);
  });
});

describe('resumen y formato', () => {
  it('cuenta, dice cuantas vencieron y nombra la primera', () => {
    const cola = armarCola({
      conversaciones: [{ id: 'c1', banda: 1, esperando_desde: hace(20) }],
      slaTomaMinutos: 15,
      pedidos: [{ estado: 'pendiente', en: hace(5) }],
      ahora: AHORA
    });
    expect(contarPorTono(cola)).toEqual({ urg: 1, aten: 1, neutro: 0 });
    expect(resumen(cola)).toBe(
      '2 cosas te necesitan ahora; 1 ya pasó su plazo. Lo primero: un cliente espera respuesta de una persona.'
    );
  });

  it('sin nada pendiente no dice "0 cosas"', () => {
    expect(resumen([])).toBe('Nada te necesita ahora. Dexter sigue atendiendo.');
  });

  it('duracion habla como una persona', () => {
    expect(duracion(18)).toBe('18 min');
    expect(duracion(80)).toBe('1 h 20 min');
    expect(duracion(120)).toBe('2 h');
    expect(duracion(60 * 24 * 3)).toBe('3 días');
  });
});
