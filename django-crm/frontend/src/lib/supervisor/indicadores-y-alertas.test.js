import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import AlertasDelDia from './AlertasDelDia.svelte';
import FranjaDeIndicadores from './FranjaDeIndicadores.svelte';
import ResumenDelDia from './ResumenDelDia.svelte';
import { alertasDelDia } from './dia-publicado.js';

/**
 * LA FRANJA DE INDICADORES, LAS ALERTAS Y EL RESUMEN (31/10/2026).
 *
 * Se mide lo que se dibuja y lo que el helper decide, con la forma que
 * devuelve `campo/dia_publicado.py::del_dia` y la lectura del material.
 */
const cuentas = {
  publicadas: 41, esperan: 55, por_revisar: 1,
  cuadrillas: 5, en_camino: 1, completadas: 32, pendientes: 9, cumplimiento: 78,
  con_novedad: 1
};

const cuadrilla = (extra = {}) => ({
  jornada: 'j-1', cuadrilla: 'Cuadrilla #1', tope: 10,
  ordenes: [], personas: [{ nombre: 'Mario Vásquez', telefono: true, ultimo_contacto: '2026-10-31T11:20:00-05:00' }],
  novedades: [], sin_reporte: null, ...extra
});
const publicado = (cs, extra = {}) => ({ cuadrillas: cs, cuentas, por_revisar: [], ...extra });

describe('la franja de indicadores', () => {
  it('muestra los seis números que calcula el servidor', () => {
    const h = render(FranjaDeIndicadores, { props: { cuentas, kitsIncompletos: 5 } }).body;

    for (const n of ['5', '1', '41', '55']) expect(h).toContain(`>${n}</strong>`);
    //  El cumplimiento es del resumen, no de la franja.
    expect(h).not.toContain('Cumplimiento');
    expect(h).toContain('Cuadrillas');
    expect(h).toContain('En camino');
    expect(h).toContain('Kits incompletos');
    expect(h).toContain('Con novedad');
  });

  it('si el material no se pudo leer, no inventa un cero', () => {
    const h = render(FranjaDeIndicadores, { props: { cuentas, kitsIncompletos: null } }).body;
    expect(h).not.toContain('Kits incompletos');
  });

  it('un indicador en cero no se pinta de rojo', () => {
    const h = render(FranjaDeIndicadores, { props: { cuentas, kitsIncompletos: 0 } }).body;
    //  Svelte le agrega su sufijo a la clase: `fi-f fi-neutro svelte-…`.
    expect(h).toMatch(/fi-f fi-neutro[^"]*"><strong[^>]*>0<\/strong>\s*<span[^>]*>Kits incompletos/);
    expect(h).not.toMatch(/fi-malo[^"]*"><strong[^>]*>0</);
  });
});

describe('las alertas del día', () => {
  it('lo grave va primero: sin reporte, sin app y sobrecarga', () => {
    const a = alertasDelDia(publicado([
      cuadrilla({ sin_reporte: { numero: 4, minutos: 42 } }),
      cuadrilla({
        jornada: 'j-2', cuadrilla: 'Cuadrilla #3', tope: 10,
        ordenes: new Array(20).fill({}),
        personas: [{ nombre: 'Julio Moreno', telefono: false, ultimo_contacto: null }]
      })
    ]), { cuentas: { con_faltantes: 2 } });

    expect(a.map((x) => x.tono).slice(0, 3)).toEqual(['grave', 'grave', 'grave']);
    expect(a[0].texto).toBe('OT #4 sin reporte hace 42 min');
    expect(a.find((x) => x.clave.startsWith('sin_app'))?.texto)
      .toBe('Julio Moreno no tiene la app: no le llegan las órdenes ni los avisos');
    expect(a.find((x) => x.clave.startsWith('sobrecarga'))?.texto)
      .toBe('20 órdenes para un tope de 10');
    //  Lo que solo avisa va después de todo lo grave.
    expect(a.findIndex((x) => x.tono === 'avisa')).toBeGreaterThan(2);
  });

  it('una novedad resuelta no es una alerta; una vigente sí, con su tipo', () => {
    const vigente = { id: 'n1', vigente: true, tipo_texto: 'Llanta pinchada', avisada_en: '2026-10-31T09:00:00-05:00' };
    const vieja = { id: 'n2', vigente: false, tipo_texto: 'Llanta pinchada', avisada_en: '2026-10-31T07:00:00-05:00' };

    const sola = alertasDelDia(publicado([cuadrilla({ novedades: [vieja] })]), null);
    expect(sola.some((x) => x.clave.startsWith('novedad'))).toBe(false);

    const con = alertasDelDia(publicado([cuadrilla({ novedades: [vigente] })]), null);
    expect(con.find((x) => x.clave.startsWith('novedad'))?.texto)
      .toBe('Llanta pinchada · desde las 09:00 · el resto del día');
  });

  it('el material, lo que espera revisión y lo que espera cuadrilla entran una sola vez', () => {
    const a = alertasDelDia(
      publicado([cuadrilla()], { por_revisar: [{ id: 'o1' }] }),
      { cuentas: { con_faltantes: 1 } }
    );

    expect(a.filter((x) => x.clave === 'material')).toHaveLength(1);
    expect(a.find((x) => x.clave === 'material')?.texto).toBe('1 cuadrilla sale con material faltante');
    expect(a.find((x) => x.clave === 'por_revisar')?.texto).toBe('1 orden terminada espera que la aprueben');
    expect(a.find((x) => x.clave === 'esperan')?.texto).toBe('55 órdenes esperan cuadrilla');
  });

  it('sin nada que atender lo dice, en vez de dibujar una caja vacía', () => {
    const h = render(AlertasDelDia, {
      props: { publicado: { cuadrillas: [cuadrilla()], cuentas: { esperan: 0 }, por_revisar: [] }, material: null }
    }).body;

    expect(h).toContain('Nada que atender');
  });
});

describe('el resumen del día', () => {
  it('usa el porcentaje del servidor, no lo recalcula', () => {
    const h = render(ResumenDelDia, { props: { cuentas } }).body;

    expect(h).toContain('>41<');
    expect(h).toContain('>32<');
    expect(h).toContain('>9<');
    expect(h).toContain('78% de lo publicado está terminado');
    expect(h).toContain('width:78%');
    expect(h).toContain('aria-valuenow="78"');
  });

  it('sin nada publicado lo dice y la barra queda en cero', () => {
    const h = render(ResumenDelDia, {
      props: { cuentas: { publicadas: 0, completadas: 0, pendientes: 0, cumplimiento: 0 } }
    }).body;

    expect(h).toContain('Todavía no hay nada publicado');
    expect(h).toContain('width:0%');
  });
});
