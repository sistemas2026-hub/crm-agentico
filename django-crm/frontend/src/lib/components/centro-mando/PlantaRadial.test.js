import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import PlantaRadial from './PlantaRadial.svelte';

/**
 * Se afirma sobre LO QUE DIBUJA, no sobre que el componente exista.
 *
 * Esta pantalla ya demostro que hace falta: un `{@const}` suelto la dejaba
 * sin renderizar con el componente compilando, y dos regresiones del cambio
 * a salas por area --la banda de zonas borrada y un nombre repetido-- las
 * cazo el render y no mirar la planta.
 *
 * Lo que NO se puede probar aqui: no hay jsdom, asi que nada de interaccion
 * --pulsar un puesto, pasar por encima, arrastrar la camara--. Eso se mira en
 * un banco con navegador, y se dice en vez de fingir que esta cubierto.
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
  servicios: [],
  eventos: [],
  agentes,
  ...extra
});

/** Los ocho roles de Rapilink: tres areas las comparten dos agentes. */
const RAPILINK = [
  ['administracion', 'Administración'], ['cliente_final', 'Atención al Cliente'],
  ['configuracion_guiada', 'Administración'], ['facturacion', 'Facturación'],
  ['facturacion_cliente', 'Facturación'], ['soporte', 'Atención al Cliente'],
  ['soporte_tecnico_cliente', 'Soporte Técnico'], ['ventas', 'Ventas']
].map(([n, a]) => agente(n, { area: a }));

describe('la planta se dibuja', () => {
  it('con los ocho agentes, dibuja ocho puestos', () => {
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    expect([...body.matchAll(/class="celda/g)]).toHaveLength(8);
  });

  it('sin agentes no revienta', () => {
    const { body } = render(PlantaRadial, { props: { panorama: panorama([]) } });
    expect(body).toContain('planta');
  });

  it('sin panorama tampoco', () => {
    const { body } = render(PlantaRadial, { props: { panorama: null } });
    expect(body).toContain('planta');
  });
});

describe('la puerta de entrada', () => {
  it('va al CENTRO, no en el anillo', () => {
    // Es la topologia real del motor: todo el que escribe por un canal
    // publico entra por `rol_de_entrada`. Si acabara en el anillo como una
    // sala mas, este diseño no diria nada que la rejilla no dijera.
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    expect(body).toContain('RECEPCIÓN');
  });

  it('cuando el tenant NO la declara, se DICE en vez de adivinarla', () => {
    // Tomar "el primer rol orientado al cliente" es el error que el
    // 07/09/2026 dejo a un suscriptor sin internet hablando con ventas.
    const { body } = render(PlantaRadial, {
      props: { panorama: panorama([agente('admin'), agente('datos')], { rol_de_entrada: null }) }
    });
    expect(body).toContain('Sin recepción declarada');
  });
});

describe('lo que la planta dice de la operacion', () => {
  it('nombra las zonas que el tenant tiene, y solo esas', () => {
    // La banda de zonas se perdio una vez al rediseñar y nadie lo vio: el
    // rotulo seguia calculandose y solo dejo de pintarse.
    const { body } = render(PlantaRadial, {
      props: { panorama: panorama([agente('admin'), agente('datos')], { rol_de_entrada: null }) }
    });
    expect(body).toContain('TRASTIENDA');
    expect(body).not.toContain('ATIENDE AL CLIENTE');
  });

  it('el nombre de un area no se dice DOS VECES', () => {
    // En una sala de un agente cuyo nombre coincide con el area, el suelo y
    // el cartel decian lo mismo: "VENTAS" sobre "VENTAS".
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    const rotulos = [...body.matchAll(/letter-spacing="[^"]*"[^>]*>([A-ZÁÉÍÓÚÑ ]{4,})</g)]
      .map((m) => m[1].trim());
    expect(rotulos.length).toBeGreaterThanOrEqual(8);
    expect(new Set(rotulos).size).toBe(rotulos.length);
  });

  it('el nombre del agente sale ENTERO, no recortado', () => {
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    expect(body).toContain('SOPORTE TECNICO CLIENTE');
    expect(body).not.toContain('…');
  });

  it('dice hace cuanto se leyo, porque esto es una FOTO y no un flujo', () => {
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    expect(body).toContain('leído hace');
  });

  it('sin marca de tiempo NO inventa una', () => {
    const p = panorama(RAPILINK);
    delete p.generado_en;
    const { body } = render(PlantaRadial, { props: { panorama: p } });
    expect(body).not.toContain('leído hace');
  });
});

describe('los pasillos y lo que hay entre las oficinas', () => {
  it('sale un pasillo del centro por cada area', () => {
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    // Rapilink tiene 5 areas ademas de la recepcion.
    expect([...body.matchAll(/fill="#FAFCFE"/g)]).toHaveLength(5);
  });

  it('los pasillos NO dicen cuanto trafico pasa', () => {
    // El destino de cada derivacion vive en tool_calls.parametros y no sale
    // en el payload. Un grosor o un brillo por pasillo serian un dato que
    // nadie midio. Todos miden igual, a proposito.
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    const anchos = [...body.matchAll(/<polygon points="([^"]+)" fill="#FAFCFE"/g)]
      .map((m) => m[1].split(' ').length);
    expect(new Set(anchos).size).toBe(1);
  });
});

describe('la actividad: nada se mueve sin un evento detras', () => {
  it('sin eventos, nadie camina por los pasillos', () => {
    // Que los pasillos esten vacios ES la informacion.
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK, { eventos: [] }) } });
    expect(body).not.toContain('class="andando"');
  });
});

describe('la salud de los sistemas externos', () => {
  it('viaja al pie de la planta, no a otra columna', () => {
    // Cuando un sistema se cae, el efecto son varios puestos en rojo. Tener
    // la causa lejos obliga a cruzar la pantalla para unir las dos cosas.
    const { body } = render(PlantaRadial, {
      props: {
        panorama: panorama(RAPILINK, {
          servicios: [{ herramienta: 'consultar_olt', usos: 31, fallos: 0, duracion_media_ms: 687 }]
        })
      }
    });
    expect(body).toContain('consultar_olt');
  });
});

describe('los filtros', () => {
  it('ofrece filtrar por lo que exige a una persona', () => {
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    expect(body).toContain('Esperan a alguien');
    expect(body).toContain('Con errores');
  });

  it('un filtro sin nadie detras sale deshabilitado', () => {
    // Ninguno de los ocho tiene errores en este panorama.
    const { body } = render(PlantaRadial, { props: { panorama: panorama(RAPILINK) } });
    expect(body).toMatch(/disabled[^>]*>Con errores|Con errores[^<]*<span[^>]*>0</);
  });
});
