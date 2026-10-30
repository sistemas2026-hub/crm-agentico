import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import FichaDePuesto from './FichaDePuesto.svelte';
import { frescura } from '$lib/centro-mando/frescura.js';

/**
 * LA FICHA, PROBADA POR LO QUE DIBUJA.
 *
 * `render()` de 'svelte/server' devuelve el HTML sin tocar el DOM. No sirve
 * para pulsar nada —en este repositorio jsdom no arranca— pero sí para la
 * pregunta que importa acá: **qué dice la ficha en cada estado**.
 *
 * Y es justo donde el banco de navegador NO llega: montar este componente desde
 * fuera de la aplicación carga una segunda copia del runtime de Svelte y
 * revienta. Así que la escena se verifica mirando y la ficha se verifica acá.
 */

const T = 1_700_000_000_000;
const uuid = '3f1a2b4c-0000-4000-8000-000000000001';

const puesto = {
  id: 'puesto-supervision',
  agente: 'supervisor_noc',
  nombre: 'Supervisor NOC',
  area: 'NOC y Redes'
};
const vacio = { id: 'puesto-monitoreo-1', agente: null, nombre: 'Monitoreo 1', area: 'puesto libre' };

const alDia = frescura({ ultimaRespuestaOk: T, retraso_s: 0.2, ahora: T });
const caido = frescura({ ultimaRespuestaOk: T - 90_000, ahora: T });

const pintar = (props) => render(FichaDePuesto, { props }).body;

describe('la cabecera dice quién es', () => {
  it('nombre, rol y área', () => {
    const html = pintar({ puesto, estado: null, veredicto: alDia });
    expect(html).toContain('Supervisor NOC');
    expect(html).toContain('NOC y Redes');
    expect(html).toContain('Agente IA');
  });

  it('un puesto vacío lo dice y no se disfraza', () => {
    const html = pintar({ puesto: vacio, estado: null, veredicto: alDia });
    expect(html).toContain('sin agente asignado');
    expect(html).toContain('no es un fallo del flujo');
  });

  it('sin puesto no dibuja nada', () => {
    // Svelte deja sus marcas de hidratación (`<!--[-1-->`) aunque el bloque no
    // produzca contenido. Lo que se afirma es que no hay panel, no que la
    // cadena esté literalmente vacía.
    const html = pintar({ puesto: null });
    expect(html).not.toContain('<aside');
    expect(html.replace(/<!--.*?-->/g, '').trim()).toBe('');
  });
});

describe('la calidad de la información va PRIMERO', () => {
  it('con el flujo al día lo dice', () => {
    const html = pintar({ puesto, estado: null, veredicto: alDia });
    expect(html).toContain('Actualizado');
  });

  it('con el motor caído dice desde cuándo, no una frase genérica', () => {
    // El detalle concreto gana a la explicación de respaldo: «sin respuesta
    // hace 90s» le dice a quien mira cuánto hace que esto dejó de ser presente.
    const html = pintar({ puesto, estado: null, veredicto: caido });
    expect(html).toContain('Sin información');
    expect(html).toContain('sin respuesta hace 90s');
  });

  it('y aparece ANTES que la actividad en el documento', () => {
    // Si el flujo está caído, lo que viene abajo no es presente. Leerlo como
    // presente es el error que esta pantalla existe para evitar, y el orden de
    // lectura es parte de la defensa.
    const html = pintar({ puesto, estado: null, veredicto: caido });
    expect(html.indexOf('Sin información')).toBeLessThan(html.indexOf('Actividad'));
  });

  it('la pestaña oculta tiene su propia frase', () => {
    const v = frescura({ ultimaRespuestaOk: T - 120_000, pausado: true, ahora: T });
    expect(pintar({ puesto, estado: null, veredicto: v })).toContain('oculta');
  });

  it('un veredicto ausente se trata como «no sé», no como «al día»', () => {
    const html = pintar({ puesto, estado: null, veredicto: null });
    expect(html).toContain('Sin información');
  });
});

describe('«sin información» no deja ver la actividad vieja', () => {
  const actividad = {
    agente: 'supervisor_noc',
    animacion: 'teclear',
    rotulo: 'consultar_estado_enlace',
    procedencia: `evento:${uuid}`,
    confiable: true,
    hasta: T + 1000
  };

  it('con datos frescos, la actividad se muestra', () => {
    const html = pintar({ puesto, estado: actividad, veredicto: alDia });
    expect(html).toContain('consultar_estado_enlace');
  });

  it('con el motor caído, NO se muestra', () => {
    // Mostrar actividad vieja como si fuera actual es peor que no mostrar nada.
    const html = pintar({ puesto, estado: actividad, veredicto: caido });
    expect(html).not.toContain('consultar_estado_enlace');
    expect(html).toContain('No se puede afirmar qué está haciendo ahora');
  });

  it('sin actividad y con datos frescos, dice reposo y no «disponible»', () => {
    const html = pintar({ puesto, estado: null, veredicto: alDia });
    expect(html).toContain('En reposo');
    expect(html).not.toContain('disponible');
  });
});

describe('los dos historiales no se mezclan', () => {
  const real = [
    { id: uuid, agente: 'supervisor_noc', tipo: 'consulta', etiqueta: 'consultar_alarmas_nodo',
      procedencia: `evento:${uuid}`, en: '2026-10-30T14:05:00Z', visto: T }
  ];
  const simulado = [
    { id: uuid, agente: 'supervisor_noc', tipo: 'accion', etiqueta: 'reiniciar_equipo_cliente',
      procedencia: 'simulado', en: '2026-10-30T14:06:00Z', visto: T }
  ];

  it('el historial real se rotula como historial de eventos', () => {
    const html = pintar({ puesto, estado: null, veredicto: alDia, historial: real });
    expect(html).toContain('Historial de eventos');
    expect(html).toContain('consultar_alarmas_nodo');
  });

  it('en demostración el cartel aparece ANTES de cualquier dato', () => {
    // Quien mire esta ficha durante una demostración tiene que saberlo antes de
    // leer un solo dato.
    const html = pintar({ puesto, estado: null, veredicto: alDia, historial: simulado, simulado: true });
    expect(html).toContain('Demostración');
    expect(html.indexOf('Demostración')).toBeLessThan(html.indexOf('reiniciar_equipo_cliente'));
    expect(html).toContain('No entra en el historial real');
    expect(html).toContain('Historial de la demostración');
  });

  it('cada línea lleva el rastro del hecho que la respalda', () => {
    // De la figura que se movió al hecho que la causó.
    const html = pintar({ puesto, estado: null, veredicto: alDia, historial: real });
    expect(html).toContain(uuid.slice(0, 8));
  });

  it('una línea simulada se rotula como simulada, no con un identificador', () => {
    const html = pintar({ puesto, estado: null, veredicto: alDia, historial: simulado, simulado: true });
    expect(html).toContain('simulado');
  });

  it('sin historial lo dice en vez de dejar un hueco', () => {
    const html = pintar({ puesto, estado: null, veredicto: alDia, historial: [] });
    expect(html).toContain('Todavía no llegó ningún evento');
  });
});

describe('el diagnóstico del flujo', () => {
  it('muestra consultas, retraso y cursor', () => {
    const html = pintar({
      puesto, estado: null, veredicto: alDia,
      diagnostico: { consultas: 7, retraso_s: 0.42, cursor: '742100.3f1a2b4c-0000', saltos: 0 }
    });
    expect(html).toContain('Flujo de eventos');
    expect(html).toContain('0.42 s');
    expect(html).toContain('742100');
  });

  it('un retraso que no se pudo medir lo dice, no lo inventa en cero', () => {
    const html = pintar({
      puesto, estado: null, veredicto: alDia,
      diagnostico: { consultas: 1, retraso_s: null, cursor: null, saltos: 0 }
    });
    expect(html).toContain('sin medir');
    expect(html).toContain('sin cursor');
  });

  it('un salto del flujo se muestra; cero saltos no ocupa sitio', () => {
    const con = pintar({ puesto, estado: null, veredicto: alDia, diagnostico: { consultas: 3, saltos: 2 } });
    const sin = pintar({ puesto, estado: null, veredicto: alDia, diagnostico: { consultas: 3, saltos: 0 } });
    expect(con).toContain('Saltos');
    expect(sin).not.toContain('Saltos');
  });
});

describe('un turno EN CURSO no se cuenta como uno que terminó', () => {
  const enCurso = {
    agente: 'supervisor_noc',
    animacion: 'teclear',
    rotulo: null,
    procedencia: `ejecucion:${uuid}`,
    confiable: true,
    hasta: null
  };

  it('lo dice, y dice que todavía no se sabe con qué', () => {
    // Hasta la fase 3B la ficha solo podía contar cosas que ya habían pasado:
    // `tool_calls` se escribe cuando la llamada termina.
    const html = pintar({ puesto, estado: enCurso, veredicto: alDia });
    expect(html).toContain('Un turno en curso');
    expect(html).toContain('todavía no terminó');
  });

  it('NO lo muestra como reposo', () => {
    const html = pintar({ puesto, estado: enCurso, veredicto: alDia });
    expect(html).not.toContain('En reposo');
  });

  it('un turno abierto desde hace demasiado se dice «no sé», no «trabajando»', () => {
    const v = { confiable: false, motivo: 'ejecucion_sin_noticias', detalle: null };
    const html = pintar({ puesto, estado: null, veredicto: v });
    expect(html).toContain('Sin información');
    expect(html).toContain('no se sabe si sigue');
  });

  it('el diagnóstico cuenta cuántos hay, y calla cuando no lo sabe', () => {
    const con = pintar({ puesto, estado: null, veredicto: alDia,
                         diagnostico: { consultas: 2, enCurso: 3 } });
    const sin = pintar({ puesto, estado: null, veredicto: alDia,
                         diagnostico: { consultas: 2 } });
    expect(con).toContain('Turnos en curso');
    expect(sin).not.toContain('Turnos en curso');
  });
});
