/**
 * Lo que se le hizo al equipo del cliente (fase 1.8).
 *
 * La aserción que más importa es que «confirmada» NO se cuente como
 * «resuelto»: es la lectura que se malinterpreta sola, y la que haría cerrar
 * un caso con el cliente todavía sin internet.
 */
import { describe, it, expect } from 'vitest';
import { lineaDeAccion, estadoDeAccion, nombreDeAccion } from './red.js';

const acc = (extra) => ({
  herramienta: 'reiniciar_ont', estado: 'ACCION_CONFIRMADA',
  por_que: null, intentos: 1, max_intentos: 3,
  ejecutada_en: '2026-09-19T14:05:00Z', ...extra
});

describe('confirmada no es resuelto', () => {
  it('dice qué hizo el equipo, no que el cliente tenga servicio', () => {
    const l = lineaDeAccion(acc());
    expect(l.texto).toMatch(/el equipo hizo lo que se le pidió/i);
    expect(l.texto).not.toMatch(/resuelto|solucionad|funcionando|con servicio/i);
  });

  it('y lo aclara explícitamente, no lo deja implícito', () => {
    expect(lineaDeAccion(acc()).matiz).toMatch(/preguntárselo/i);
  });
});

describe('no verificable no es no confirmada', () => {
  it('«no se pudo medir» no se cuenta como que la acción falló', () => {
    const nv = lineaDeAccion(acc({ estado: 'NO_VERIFICABLE' }));
    expect(nv.texto).toMatch(/no se pudo comprobar/i);
    expect(nv.texto).not.toMatch(/no está|fall/i);
    expect(nv.matiz).toMatch(/no significa que la acción haya fallado/i);
    expect(nv.tono).toBe('aviso');   // ámbar, no rojo
  });

  it('y la que sí se midió y falló se dice como tal, en rojo', () => {
    const nc = lineaDeAccion(acc({ estado: 'ACCION_NO_CONFIRMADA' }));
    expect(nc.texto).toMatch(/se midió y el efecto esperado no está/i);
    expect(nc.tono).toBe('mal');
  });

  it('los dos estados no comparten ni texto ni tono', () => {
    const nv = lineaDeAccion(acc({ estado: 'NO_VERIFICABLE' }));
    const nc = lineaDeAccion(acc({ estado: 'ACCION_NO_CONFIRMADA' }));
    expect(nv.texto).not.toBe(nc.texto);
    expect(nv.tono).not.toBe(nc.tono);
  });
});

describe('lo pendiente y lo desconocido', () => {
  it('esperando para comprobar no es un veredicto', () => {
    const p = lineaDeAccion(acc({ estado: 'VERIFICACION_PENDIENTE' }));
    expect(p.clave).toBe('pendiente');
    expect(p.tono).toBe('neutro');
  });

  it('un estado que esta pantalla no conoce no recibe veredicto', () => {
    const d = estadoDeAccion({ estado: 'ALGO_NUEVO' });
    expect(d.clave).toBe('sin_registro');
    expect(d.tono).toBe('neutro');
  });

  it('un registro vacío no rompe ni inventa', () => {
    expect(() => lineaDeAccion(null)).not.toThrow();
    expect(lineaDeAccion(null).clave).toBe('sin_registro');
  });
});

describe('el resto de la línea', () => {
  it('una herramienta sin nombre en castellano se muestra igual', () => {
    expect(nombreDeAccion('otra_cosa_del_tenant')).toBe('otra cosa del tenant');
    expect(nombreDeAccion('reiniciar_ont')).toBe('Reinicio de la ONT');
  });

  it('el motivo lo escribe Dexter y se muestra tal cual', () => {
    expect(lineaDeAccion(acc({ por_que: 'El equipo volvió a las 14:07.' })).porQue)
      .toBe('El equipo volvió a las 14:07.');
    expect(lineaDeAccion(acc({ por_que: '   ' })).porQue).toBeNull();
  });

  it('los intentos sólo aparecen cuando explican algo', () => {
    // "1 de 1" no dice nada; "2 de 3" explica una espera.
    expect(lineaDeAccion(acc({ intentos: 1, max_intentos: 1 })).intentos).toBeNull();
    expect(lineaDeAccion(acc({ intentos: 1, max_intentos: 3 })).intentos).toBeNull();
    expect(lineaDeAccion(acc({ intentos: 2, max_intentos: 3 })).intentos)
      .toBe('intento 2 de 3');
  });
});
