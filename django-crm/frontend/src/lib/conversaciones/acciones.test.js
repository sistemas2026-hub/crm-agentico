/**
 * El estado real de una acción, en la pantalla (B5).
 *
 * La aserción que más importa, igual que en el panel de sincronización:
 * `desconocida` no puede leerse como «falló». Si la pantalla dice que falló,
 * alguien lo va a rehacer — y rehacer un ticket que quizá ya existe manda dos
 * visitas técnicas al mismo cliente.
 */
import { describe, it, expect } from 'vitest';
import {
  estadoDeAccion, sePuedeAprobar, esperanRevision, lineaDeAccion
} from './acciones.js';

const a = (extra) => ({
  id: 'x1', herramienta: 'crear_ticket', resumen: 'Crear ticket «Sin internet»',
  estado: 'pendiente', vence_en: '2026-09-20T12:00:00Z', expirada: false, ...extra
});

describe('desconocida no es un fallo', () => {
  it('no dice que falló: dice que no se sabe', () => {
    const d = estadoDeAccion(a({ estado: 'desconocida' }));
    expect(d.titulo).toMatch(/no sabemos/i);
    expect(`${d.titulo} ${d.detalle}`).not.toMatch(/falló|fallo|no se pudo hacer/i);
    expect(d.detalle).toMatch(/no se reintenta/i);
  });

  it('se distingue de ejecutada_fallo, que sí afirma que no se hizo', () => {
    const desconocida = estadoDeAccion(a({ estado: 'desconocida' }));
    const fallo = estadoDeAccion(a({ estado: 'ejecutada_fallo' }));
    expect(desconocida.titulo).not.toBe(fallo.titulo);
    expect(fallo.detalle).toMatch(/no quedó hecha/i);
  });

  it('y entra en lo que espera revisión, aunque sea terminal', () => {
    // Dejarla fuera la volvería invisible: es el estado en el que estaban las
    // 36 del legado.
    const espera = esperanRevision([
      a({ estado: 'desconocida' }), a({ estado: 'ejecutada_ok' }),
      a({ estado: 'pendiente' })
    ]);
    expect(espera).toHaveLength(1);
    expect(espera[0].estado).toBe('desconocida');
  });
});

describe('cada final dice lo que pasó de verdad', () => {
  it('los cuatro desenlaces tienen textos distintos', () => {
    const titulos = ['ejecutada_ok', 'ejecutada_fallo', 'vencida', 'desconocida']
      .map((estado) => estadoDeAccion(a({ estado })).titulo);
    expect(new Set(titulos).size).toBe(4);
  });

  it('sólo ejecutada_ok afirma que se hizo', () => {
    expect(estadoDeAccion(a({ estado: 'ejecutada_ok' })).tono).toBe('ok');
    for (const estado of ['ejecutada_fallo', 'vencida', 'desconocida', 'pendiente']) {
      expect(estadoDeAccion(a({ estado })).tono).not.toBe('ok');
    }
  });

  it('vencida explica que no se hizo nada', () => {
    expect(estadoDeAccion(a({ estado: 'vencida' })).detalle).toMatch(/no se hizo nada/i);
  });

  it('«aprobada» del legado se marca como tal', () => {
    // Filas de antes de B5, cuando «aprobada» era el único final y no decía
    // si el efecto había ocurrido.
    expect(estadoDeAccion(a({ estado: 'aprobada' })).titulo).toMatch(/antes de B5/i);
  });

  it('un estado que no se conoce no se muestra como exitoso', () => {
    const d = estadoDeAccion(a({ estado: 'inventado_xyz' }));
    expect(d.tono).not.toBe('ok');
    expect(d.titulo).toMatch(/desconocido/i);
  });
});

describe('sólo se ofrece aprobar lo que el backend aceptaría', () => {
  it('una pendiente en plazo, sí', () => {
    expect(sePuedeAprobar(a())).toBe(true);
  });

  it('una pendiente ya expirada, no', () => {
    // El backend la rechaza con 409 y la marca vencida: ofrecer el botón sería
    // ofrecer una aprobación que va a fallar.
    expect(sePuedeAprobar(a({ expirada: true }))).toBe(false);
  });

  it('ninguna que ya terminó', () => {
    for (const estado of ['ejecutada_ok', 'ejecutada_fallo', 'vencida',
                          'desconocida', 'cancelada', 'rechazada', 'ejecutando']) {
      expect(sePuedeAprobar(a({ estado }))).toBe(false);
    }
  });
});

describe('lo que la línea expone', () => {
  it('no lleva argumentos aunque llegaran', () => {
    const conPii = a({ argumentos: { telefono: '573001112233' } });
    expect(JSON.stringify(lineaDeAccion(conPii))).not.toContain('573001112233');
  });

  it('el plazo se anuncia sólo mientras importa', () => {
    expect(lineaDeAccion(a()).venceEn).toBeTruthy();
    // Decir «vence en 3 min» de algo ya ejecutado es ruido.
    expect(lineaDeAccion(a({ estado: 'ejecutada_ok' })).venceEn).toBeNull();
  });
});

// =============================================================================
//  El cableado, leído del código
// =============================================================================
//  vitest corre en `node` sin el plugin de Svelte: no puede compilar un
//  `.svelte`. La lógica de arriba puede estar perfecta mientras la pantalla
//  ofrece un botón donde no debe.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
const soloCodigo = (f) => f.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
const panel = leer('./context/ActionsPanel.svelte');
const pagina = leer('../../routes/(app)/conversaciones/[id]/+page.svelte');
const proxyAprobar = soloCodigo(
  leer('../../routes/api/conversaciones/[id]/acciones/[accion]/aprobar/+server.js')
);

const marcado = (f) =>
  f.slice(f.lastIndexOf('</script>'))
    .replace(/<style[\s\S]*?<\/style>/g, '')
    .replace(/<!--[\s\S]*?-->/g, '');

describe('la pantalla ofrece sólo lo que el backend aceptaría', () => {
  it('el botón de aprobar está detrás de puedeAprobarse', () => {
    // Una vencida ofrecería una aprobación que termina en 409, y un botón que
    // falla enseña a desconfiar del resto.
    const visible = marcado(panel);
    expect(visible).toMatch(/\{#if linea\.puedeAprobarse/);
    const boton = (visible.match(/<button[\s\S]*?<\/button>/g) ?? []).join('');
    expect(boton).toMatch(/Aprobar y ejecutar/);
  });

  it('no hay botón de reintentar sobre una desconocida', () => {
    // Nadie puede saber si ya se hizo: un botón invita al gesto que manda dos
    // visitas técnicas al mismo cliente.
    expect(marcado(panel)).not.toMatch(/reintentar/i);
  });

  it('el estado sale de acciones.js y no se decide en el panel', () => {
    expect(panel).toMatch(/lineasDeAcciones/);
    expect(soloCodigo(panel)).not.toMatch(/ejecutada_ok|desconocida/);
  });

  it('quién aprueba sale de la sesión, no del navegador', () => {
    expect(proxyAprobar).toMatch(/autorDeSesion\(locals\)/);
    expect(proxyAprobar).toMatch(/revisado_por: quien/);
    expect(proxyAprobar).toMatch(/if \(!locals\.user\)/);
  });

  it('la página relee después de aprobar, no asume el desenlace', () => {
    // El resultado puede ser 'desconocida': ni hecha ni fallada. Pintar
    // «hecha» porque el fetch devolvió 200 sería afirmar un efecto que
    // no se midió.
    const cuerpo = pagina.slice(pagina.indexOf('async function aprobarAccion'));
    expect(cuerpo.slice(0, 1200)).toMatch(/acciones = \(await r\.json\(\)\)\.acciones/);
  });
});
