import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import PlantaOficina from './PlantaOficina.svelte';

/**
 * Se afirma sobre LO QUE DIBUJA, no sobre que el componente exista.
 *
 * Una prueba que dice que algo existe no prueba que funcione, y esta pantalla
 * ya lo demostro: el componente compilaba y `{@const}` suelto lo dejaba sin
 * renderizar. Aqui se monta con un panorama y se mira el HTML resultante.
 */

const agente = (nombre, extra = {}) => ({
  nombre,
  area: extra.area ?? nombre,
  cargo: 'Agente',
  orientado_a: 'colaborador',
  estado: 'idle',
  haciendo: 'Sin conversaciones en curso',
  conversaciones: 0,
  abiertas_total: 0,
  esperando_humano: 0,
  esperando_cliente: 0,
  esperando_aprobacion: 0,
  recibidas_hoy: 0,
  llamadas_ventana: 0,
  fallos_ventana: 0,
  serie: Array(15).fill(0),
  duracion_media_ms: null,
  ultima_herramienta: null,
  ultima_actividad: new Date().toISOString(),
  ...extra
});

const panorama = (agentes, extra = {}) => ({
  tenant: 'rapilink',
  generado_en: new Date().toISOString(),
  ventana_min: 10,
  rol_de_entrada: 'cliente_final',
  totales: {},
  agentes,
  servicios: [],
  eventos: [],
  ...extra
});

/** Cuantos puestos dibujo, contando los grupos con su rotulo. */
const cuentaPuestos = (html) => (html.match(/class="[^"]*\bpuesto\b/g) || []).length;

describe('la planta dibuja', () => {
  it('un puesto por agente', () => {
    for (const n of [1, 3, 8, 12]) {
      const agentes = Array.from({ length: n }, (_, i) => agente(`rol_${i}`));
      const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
      expect(cuentaPuestos(body)).toBe(n);
    }
  });

  it('sin agentes no revienta', () => {
    const { body } = render(PlantaOficina, { props: { panorama: panorama([]) } });
    expect(cuentaPuestos(body)).toBe(0);
  });

  it('sin panorama tampoco', () => {
    const { body } = render(PlantaOficina, { props: { panorama: null } });
    expect(body).toBeTypeOf('string');
  });

  it('dos agentes de la MISMA area se distinguen', () => {
    // El defecto que se vio en produccion: la planta rotulaba por area, y en
    // Rapilink tres pares comparten una -- Atencion al Cliente, Facturacion y
    // Administracion tienen dos agentes cada una. Habia dos puestos que
    // decian "FACTURACIÓN" y no habia forma de saber cual era cual.
    const agentes = [
      agente('facturacion', { area: 'Facturación' }),
      agente('facturacion_cliente', { area: 'Facturación' })
    ];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).toContain('FACTURACION');
    expect(body).toContain('FACTURACION CLIENTE');
  });

  it('los ocho roles de Rapilink dan ocho rótulos distintos', () => {
    const reales = [
      ['administracion', 'Administración'], ['cliente_final', 'Atención al Cliente'],
      ['configuracion_guiada', 'Administración'], ['facturacion', 'Facturación'],
      ['facturacion_cliente', 'Facturación'], ['soporte', 'Atención al Cliente'],
      ['soporte_tecnico_cliente', 'Soporte Técnico'], ['ventas', 'Ventas']
    ];
    const { body } = render(PlantaOficina, {
      props: { panorama: panorama(reales.map(([n, a]) => agente(n, { area: a }))) }
    });
    // Se leen los rotulos pintados y se comprueba que no haya dos iguales.
    const rotulos = [...body.matchAll(/letter-spacing="[^"]*"[^>]*>([A-ZÁÉÍÓÚÑ ]{4,})</g)]
      .map((m) => m[1].trim());
    expect(rotulos.length).toBeGreaterThanOrEqual(8);
    expect(new Set(rotulos).size).toBe(rotulos.length);
  });

  it('el nombre sale ENTERO, no recortado', () => {
    // Recortar el rotulo es lo peor que puede hacerse aqui: "SOPORTE TE..."
    // no identifica a nadie, que es lo unico para lo que existe.
    const agentes = [
      agente('soporte_tecnico_cliente', { area: 'Soporte Técnico' }),
      agente('cliente_final', { area: 'Atención al Cliente', orientado_a: 'cliente_final' })
    ];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).toContain('SOPORTE TECNICO CLIENTE');
    expect(body).toContain('CLIENTE FINAL');
    expect(body).not.toContain('SOPORTE TE…');
  });

  it('los filtros cuentan lo que hay', () => {
    const agentes = [
      agente('a', { estado: 'error' }),
      agente('b', { estado: 'working', conversaciones: 3 }),
      agente('c', { esperando_humano: 2 })
    ];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).toContain('Con errores');
    expect(body).toContain('Esperan a alguien');
    expect(body).toContain('Todos');
  });

  it('trae los mandos de la camara', () => {
    const { body } = render(PlantaOficina, { props: { panorama: panorama([agente('soporte')]) } });
    expect(body).toContain('Volver al encuadre automático');
  });
});

describe('la puerta de entrada', () => {
  it('marca como recepción al rol_de_entrada que manda el motor', () => {
    const agentes = [agente('cliente_final', { orientado_a: 'cliente_final' }), agente('soporte')];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).toContain('PUERTA DE ENTRADA');
    expect(body).toContain('RECEPCIÓN');
  });

  it('cuando el motor NO lo manda, lo dice en vez de adivinarlo', () => {
    // Deducirlo del "primer rol orientado al cliente" es el error que el
    // 07/09/2026 dejo a un suscriptor sin internet hablando con ventas.
    const agentes = [agente('ventas', { orientado_a: 'cliente_final' }), agente('soporte')];
    const { body } = render(PlantaOficina, {
      props: { panorama: panorama(agentes, { rol_de_entrada: null }) }
    });
    expect(body).toContain('Sin recepción declarada');
    expect(body).not.toContain('PUERTA DE ENTRADA');
  });
});

describe('lo que necesita a una persona', () => {
  it('muestra la cifra de los que esperan', () => {
    const agentes = [agente('soporte', { esperando_humano: 4, conversaciones: 9 })];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).toContain('4 esperan a una persona');
  });

  it('suma los que esperan aprobación', () => {
    const agentes = [agente('soporte', { esperando_humano: 2, esperando_aprobacion: 1 })];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).toContain('3 esperan a una persona');
  });

  it('un puesto tranquilo no lo menciona', () => {
    const { body } = render(PlantaOficina, { props: { panorama: panorama([agente('soporte')]) } });
    expect(body).not.toContain('esperan a una persona');
  });
});

describe('privacidad: nada del cliente llega a la planta', () => {
  it('no pinta nada que no venga del panorama', () => {
    // El contrato del motor dice "tampoco viaja nada del cliente"
    // (panorama_centro_mando). Esta guarda comprueba el otro lado: que la
    // pantalla no invente ni filtre nada aunque el panorama traiga campos de
    // mas -- un payload con un telefono dentro no debe terminar dibujado.
    const agentes = [agente('soporte', {
      telefono_cliente: '3001234567',
      ultimo_mensaje: 'mi cedula es 1098765432',
      nombre_cliente: 'Rafael Olivero'
    })];
    const { body } = render(PlantaOficina, { props: { panorama: panorama(agentes) } });
    expect(body).not.toContain('3001234567');
    expect(body).not.toContain('1098765432');
    expect(body).not.toContain('Rafael Olivero');
  });
});

describe('el sello de frescura', () => {
  it('dice hace cuanto se leyó la operación', () => {
    // Lo menos vistoso y lo mas importante: deja dicho que lo que se ve es
    // una lectura cada 12 s y no un flujo continuo.
    const { body } = render(PlantaOficina, { props: { panorama: panorama([agente('soporte')]) } });
    expect(body).toMatch(/leído hace \d+s/);
  });

  it('sin marca de tiempo no inventa una', () => {
    const p = panorama([agente('soporte')]);
    delete p.generado_en;
    const { body } = render(PlantaOficina, { props: { panorama: p } });
    expect(body).not.toContain('leído hace');
  });
});

describe('las zonas', () => {
  it('nombra solo las zonas que el tenant realmente tiene', () => {
    const soloInternos = [agente('admin'), agente('datos')];
    const { body } = render(PlantaOficina, {
      props: { panorama: panorama(soloInternos, { rol_de_entrada: null }) }
    });
    expect(body).toContain('TRASTIENDA');
    expect(body).not.toContain('ATIENDE AL CLIENTE');
  });
});
