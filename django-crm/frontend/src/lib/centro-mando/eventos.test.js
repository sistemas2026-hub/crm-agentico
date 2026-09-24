import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { crearServicioEventos, transporteSondeo } from './eventos.js';

/**
 * Lo que se prueba es la CONDUCTA del servicio, no que tenga metodos: que no
 * consulte con la pestaña oculta, que no solape peticiones, que un fallo no
 * lo deje mudo, y que un evento suelto actualice al agente que nombra sin
 * tocar a los demas. Esas cuatro son las que, al romperse, no se ven: la
 * pantalla sigue pintando lo ultimo que recibio.
 */

const respuesta = (datos, ok = true) => ({ ok, json: async () => datos });

describe('transporte por sondeo', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('no consulta con la pestaña oculta', async () => {
    const traer = vi.fn(async () => respuesta({ agentes: [] }));
    const t = transporteSondeo({ fetch: traer, intervalo: 1000, visible: () => false });
    const corriendo = t.arrancar(
      () => {},
      () => {}
    );
    await vi.advanceTimersByTimeAsync(3000);
    expect(traer).not.toHaveBeenCalled();
    corriendo.detener();
  });

  it('consulta cuando la pestaña esta a la vista', async () => {
    const traer = vi.fn(async () => respuesta({ agentes: [] }));
    const t = transporteSondeo({ fetch: traer, intervalo: 1000, visible: () => true });
    const corriendo = t.arrancar(
      () => {},
      () => {}
    );
    await vi.advanceTimersByTimeAsync(2500);
    expect(traer).toHaveBeenCalledTimes(2);
    corriendo.detener();
  });

  it('no solapa peticiones cuando la base va lenta', async () => {
    let resolver;
    const traer = vi.fn(() => new Promise((r) => (resolver = () => r(respuesta({ agentes: [] })))));
    const t = transporteSondeo({ fetch: traer, intervalo: 100, visible: () => true });
    const corriendo = t.arrancar(
      () => {},
      () => {}
    );
    await vi.advanceTimersByTimeAsync(1000); // diez intervalos, una sola en vuelo
    expect(traer).toHaveBeenCalledTimes(1);
    resolver();
    corriendo.detener();
  });

  it('un fallo se informa y el sondeo sigue', async () => {
    let falla = true;
    const traer = vi.fn(async () => {
      if (falla) throw new Error('sin red');
      return respuesta({ agentes: [{ nombre: 'soporte' }] });
    });
    const errores = [];
    const recibidos = [];
    const t = transporteSondeo({ fetch: traer, intervalo: 100, visible: () => true });
    const corriendo = t.arrancar((p) => recibidos.push(p), (e) => errores.push(e));

    await vi.advanceTimersByTimeAsync(150);
    expect(errores).toEqual(['sin red']);

    // Lo que importa no es cuantas veces entrego, sino que despues de fallar
    // volvio a entregar: un transporte que se queda mudo tras el primer error
    // deja la pantalla con datos viejos y sin decirlo.
    falla = false;
    await vi.advanceTimersByTimeAsync(150);
    expect(recibidos.length).toBeGreaterThan(0);
    corriendo.detener();
  });

  it('al detenerse deja de consultar', async () => {
    const traer = vi.fn(async () => respuesta({ agentes: [] }));
    const t = transporteSondeo({ fetch: traer, intervalo: 100, visible: () => true });
    const corriendo = t.arrancar(
      () => {},
      () => {}
    );
    await vi.advanceTimersByTimeAsync(150);
    const llamadas = traer.mock.calls.length;
    corriendo.detener();
    await vi.advanceTimersByTimeAsync(1000);
    expect(traer).toHaveBeenCalledTimes(llamadas);
  });
});

describe('el servicio', () => {
  it('reparte el panorama a quien se suscribio', async () => {
    const transporte = {
      nombre: 'falso',
      arrancar(alRecibir) {
        setTimeout(() => alRecibir({ agentes: [{ nombre: 'ventas', estado: 'idle' }] }), 0);
        return { ahora() {}, detener() {} };
      }
    };
    const servicio = crearServicioEventos({ transporte });
    const vistos = [];
    servicio.alPanorama((p) => vistos.push(p));
    servicio.arrancar();
    await new Promise((r) => setTimeout(r, 1));
    expect(vistos).toHaveLength(1);
    expect(servicio.panorama.agentes[0].nombre).toBe('ventas');
    expect(servicio.ultimoCambio).toBeTruthy();
  });

  it('un evento suelto cambia solo al agente que nombra', () => {
    const servicio = crearServicioEventos({
      inicial: {
        agentes: [
          { nombre: 'soporte', estado: 'idle', haciendo: 'Sin conversaciones' },
          { nombre: 'ventas', estado: 'idle', haciendo: 'Sin conversaciones' }
        ]
      }
    });
    const aplicado = servicio.aplicarEvento({
      type: 'agent_status',
      agent: 'soporte',
      status: 'working',
      task: 'consultar_senal_ont'
    });

    expect(aplicado).toBe(true);
    const [soporte, ventas] = servicio.panorama.agentes;
    expect(soporte.estado).toBe('working');
    expect(soporte.haciendo).toBe('consultar_senal_ont');
    expect(ventas.estado).toBe('idle');
    expect(ventas.haciendo).toBe('Sin conversaciones');
  });

  it('ignora un evento de otro tipo o de un agente que no existe', () => {
    const servicio = crearServicioEventos({
      inicial: { agentes: [{ nombre: 'soporte', estado: 'idle' }] }
    });
    expect(servicio.aplicarEvento({ type: 'otra_cosa', agent: 'soporte' })).toBe(false);
    expect(servicio.aplicarEvento({ type: 'agent_status' })).toBe(false);
    expect(servicio.panorama.agentes[0].estado).toBe('idle');
  });

  it('desuscribirse deja de recibir', async () => {
    let empujar;
    const transporte = {
      nombre: 'falso',
      arrancar(alRecibir) {
        empujar = alRecibir;
        return { ahora() {}, detener() {} };
      }
    };
    const servicio = crearServicioEventos({ transporte });
    const vistos = [];
    const cancelar = servicio.alPanorama((p) => vistos.push(p));
    servicio.arrancar();
    empujar({ agentes: [] });
    cancelar();
    empujar({ agentes: [] });
    expect(vistos).toHaveLength(1);
  });
});
