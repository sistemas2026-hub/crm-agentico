import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'svelte/server';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { leerReporte } = await import('$lib/server/v2/inventario.js');
const { default: Reportes } = await import('./Reportes.svelte');

/**
 * Los tres reportes de lo que escribe el técnico (18/10/2026).
 *
 * Pedidos a bodega, faltantes explicados y actas de cierre se guardaban y la web
 * no los mostraba. Acá se recorren los dos saltos de la web con la forma que
 * devuelve el backend (`campo/services/inventario_operacion.py`, probada en
 * `test_reportes_de_lo_que_escribio_el_tecnico.py`): que el servidor pida el
 * reporte y pase las filas enteras, y que la pantalla las dibuje.
 */
const ctx = /** @type {any} */ ({ cookies: { get: () => 'token' } });

/** La pantalla con lo que devolvió el servidor, sin comentarios de hidratación. */
async function pantalla(de, filasDelBackend) {
  apiRequest.mockResolvedValue({ de, filas: filasDelBackend });
  const rep = await leerReporte(ctx, de, '', '');
  return render(Reportes, {
    props: { reporte: { de, filas: rep.filas }, internas: [] }
  }).body.replace(/<!--[\s\S]*?-->/g, '');
}

const PEDIDO = {
  id: 'p1', en: '2026-10-18T14:05:00-05:00', estado: 'pendiente', material: 'CON-SC-APC',
  material_nombre: 'Conector SC/APC', cantidad: '20', unidad: 'unidades',
  persona: 'Carlos Gómez', orden_numero: 1849, motivo: 'se acabaron'
};
const FALTANTE = {
  id: 'i1', en: '2026-10-18T17:00:00-05:00', tipo: 'danado', tipo_texto: 'Dañado',
  material: 'CON-SC-APC', material_nombre: 'Conector SC/APC', cantidad: '3',
  unidad: 'unidades', serie: '', persona: 'Carlos Gómez',
  motivo: 'se partieron al pelar la fibra', jornada: '2026-10-18'
};
const ACTA = {
  id: 'a1', jornada: '2026-10-17', persona: 'Carlos Gómez',
  confirmada_en: '2026-10-17T18:30:00-05:00', recibida_por: null,
  ordenes: { asignadas: 3, completadas: 3, pendientes: 0 }, por_unidad: [],
  materiales: [{ codigo: 'DROP', nombre: 'Cable drop', unidad: 'm', entregado: '100',
    consumido: '35', esperado_devolver: '65', devuelto: '62', diferencia: '3' }],
  notas: ''
};

describe('los reportes de lo que escribe el técnico', () => {
  beforeEach(() => { apiRequest.mockReset(); });

  it('el servidor pide el reporte que se eligió', async () => {
    apiRequest.mockResolvedValue({ filas: [] });
    await leerReporte(ctx, 'pedidos', '2026-10-01', '2026-10-18');
    const [endpoint] = apiRequest.mock.calls[0];
    const q = new URL(`http://x${endpoint}`).searchParams;
    expect([q.get('de'), q.get('desde'), q.get('hasta')]).toEqual(['pedidos', '2026-10-01', '2026-10-18']);
  });

  it('las tres pestañas existen', async () => {
    const b = await pantalla('consumo', []);
    for (const texto of ['Pedidos a bodega', 'Faltantes explicados', 'Cierres de jornada']) {
      expect(b).toContain(texto);
    }
    expect(b).toContain('de=pedidos');
  });

  it('un pedido dice qué, cuánto, quién, para qué orden y por qué', async () => {
    const b = await pantalla('pedidos', [PEDIDO]);
    for (const texto of ['Pendiente', 'Conector SC/APC', '20 unidades', 'Carlos Gómez', '#1849', 'se acabaron']) {
      expect(b).toContain(texto);
    }
  });

  it('un faltante dice qué pasó y la explicación del técnico', async () => {
    const b = await pantalla('faltantes', [FALTANTE]);
    for (const texto of ['Dañado', '3 unidades', 'se partieron al pelar la fibra', 'jornada del 2026-10-18']) {
      expect(b).toContain(texto);
    }
  });

  it('el acta muestra sus números congelados y marca la diferencia', async () => {
    const b = await pantalla('cierres', [ACTA]);
    expect(b).toContain('Carlos Gómez · jornada del 2026-10-17');
    expect(b).toContain('3 de 3 completadas');
    expect(b).toContain('35 m');
    expect(b).toMatch(/text-error font-semibold[^>]*>\s*3\s*</);
  });

  it('vacío lo dice con su propia frase', async () => {
    expect(await pantalla('pedidos', [])).toContain('Nadie pidió material a bodega.');
    expect(await pantalla('faltantes', [])).toContain('Ningún técnico explicó un faltante.');
    expect(await pantalla('cierres', [])).toContain('No hay jornadas cerradas.');
  });

  it('un pedido pendiente ofrece atender o rechazar, sin perder la pestaña', async () => {
    const b = await pantalla('pedidos', [PEDIDO]);
    expect(b).toContain('action="?ver=reportes&amp;de=pedidos&amp;/resolverPedido"');
    expect(b).toContain('name="pedido" value="p1"');
    expect(b).toContain('value="atendido"');
    expect(b).toContain('value="rechazado"');
  });

  it('uno ya resuelto dice quién, cuándo y qué nota dejó, sin botones', async () => {
    const b = await pantalla('pedidos', [{
      ...PEDIDO, estado: 'rechazado', resuelto_por: 'Ana Bodega',
      resuelto_en: '2026-10-18T16:00:00-05:00', nota_de_bodega: 'sin stock hasta el lunes'
    }]);
    expect(b).toContain('Rechazado por Ana Bodega · 2026-10-18 16:00 · sin stock hasta el lunes');
    expect(b).not.toContain('/resolverPedido');
  });
});
