import { describe, it, expect } from 'vitest';
import {
  humanizar, nombreDe, resumenDe, familia, indiceDeAutonomia, modoDeAccion, conteoDeAcciones,
  agrupar, resumenGlobal, matriz, textoEscalo, textoDeBitacora, cuandoCorto, pesoDelPrompt
} from './presentacion.js';

const escribe = (nombre, aprobacion_humana, extra = {}) =>
  ({ nombre, solo_lectura: false, requiere_confirmacion: true, aprobacion_humana, ...extra });
const lee = (nombre, tipo = 'http') => ({ nombre, solo_lectura: true, tipo });

const soporteCliente = {
  nombre: 'soporte_tecnico_cliente', orientado_a: 'cliente_final',
  herramientas: [lee('consultar_estado_ont'), escribe('reiniciar_ont', true), escribe('registrar_pedido_wifi', false)]
};
const soporte = {
  nombre: 'soporte', orientado_a: 'colaborador', nombre_visible: 'Soporte (equipo)',
  herramientas: [lee('contar_clientes', 'agregado'), escribe('reiniciar_ont', true), escribe('agendar_visita_tecnica', false)]
};
const recepcion = { nombre: 'cliente_final', orientado_a: 'cliente_final', herramientas: [lee('derivar_a_area', 'interno')] };
const supervisor = { nombre: 'supervisor', automatico: true, descripcion: 'Revisa conversaciones cerradas.', herramientas: [] };

describe('nombres para personas', () => {
  it('pasa la clave a palabras, con las siglas en mayuscula', () => {
    expect(humanizar('consultar_estado_ont')).toBe('Consultar estado ONT');
    expect(humanizar('activar_catv')).toBe('Activar CATV');
    expect(humanizar('wifi_cliente')).toBe('WIFI cliente');
  });
  it('manda el nombre visible; sin el, la clave en palabras (nunca "Soporte_tecnico_cliente")', () => {
    expect(nombreDe(soporte)).toBe('Soporte (equipo)');
    expect(nombreDe(soporteCliente)).toBe('Soporte tecnico cliente');
    expect(nombreDe(soporteCliente)).not.toContain('_');
  });
  it('el resumen NUNCA es el prompt: resumen, si no lo que atiende, si no nada', () => {
    expect(resumenDe({ resumen: 'Hace X', descripcion: 'TODAVIA NO es cliente' })).toBe('Hace X');
    expect(resumenDe({ atiende: 'saldo, facturas', descripcion: 'TODAVIA NO' })).toBe('Atiende: saldo, facturas');
    expect(resumenDe({ descripcion: 'TODAVIA NO es cliente -- ...' })).toBe('');
    expect(resumenDe(supervisor)).toBe('Revisa conversaciones cerradas.');
  });
  it('la familia sale de a quien le habla', () => {
    expect(familia(soporteCliente)).toBe('cliente');
    expect(familia(soporte)).toBe('equipo');
    expect(familia(supervisor)).toBe('auto');
    expect(familia({ operativo: true })).toBe('auto');
  });
});

describe('el freno real, no el declarado', () => {
  const autonomia = indiceDeAutonomia({
    acciones: [{ accion: 'reiniciar_ont', por_agente: { soporte: { autonoma: true }, soporte_tecnico_cliente: { autonoma: false } } }]
  });

  it('requiere_confirmacion NO cuenta: sin aprobacion_humana va sola', () => {
    expect(modoDeAccion(escribe('registrar_pedido_wifi', false), autonomia, 'x')).toBe('sola');
  });
  it('con aprobacion_humana espera, salvo que ESTE agente la haya ganado', () => {
    expect(modoDeAccion(escribe('reiniciar_ont', true), autonomia, 'soporte_tecnico_cliente')).toBe('espera');
    expect(modoDeAccion(escribe('reiniciar_ont', true), autonomia, 'soporte')).toBe('ganada');
  });
  it('si la perdio sola, se dice', () => {
    const a = indiceDeAutonomia({ acciones: [{ accion: 'r', por_agente: { s: { estado: 'degradada' } } }] });
    expect(modoDeAccion(escribe('r', true), a, 's')).toBe('degradada');
  });
  it('si el motor no mando el dato, "sin dato" -- nunca se supone que va sola', () => {
    expect(modoDeAccion({ nombre: 'x', solo_lectura: false, requiere_confirmacion: true }, null, 's')).toBe('sin_dato');
  });
  it('sin el reporte de autonomia, una con aprobacion sigue esperando (falla cerrado)', () => {
    expect(modoDeAccion(escribe('reiniciar_ont', true), null, 'soporte')).toBe('espera');
    expect(indiceDeAutonomia(null)).toBeNull();
  });
  it('una consulta no tiene modo', () => {
    expect(modoDeAccion(lee('consultar'), autonomia, 'x')).toBeNull();
  });
  it('cuenta acciones por agente', () => {
    expect(conteoDeAcciones(soporte, autonomia)).toEqual(
      { consultas: 0, cuentas: 1, acciones: 2, solas: 2, espera: 0, sinDato: 0 });
    expect(conteoDeAcciones(soporteCliente, autonomia)).toEqual(
      { consultas: 1, cuentas: 0, acciones: 2, solas: 1, espera: 1, sinDato: 0 });
  });
});

describe('la lista', () => {
  it('agrupa: primero los que le hablan al cliente, por nombre', () => {
    const g = agrupar([soporte, supervisor, soporteCliente, recepcion]);
    expect(g.map((x) => x.clave)).toEqual(['cliente', 'equipo', 'auto']);
    expect(g[0].items.map((a) => a.nombre)).toEqual(['cliente_final', 'soporte_tecnico_cliente']);
  });
  it('no muestra familias vacias', () => {
    expect(agrupar([soporte]).map((x) => x.clave)).toEqual(['equipo']);
  });
  it('el resumen de arriba separa las acciones solas de las que esperan', () => {
    const r = resumenGlobal([soporte, soporteCliente, recepcion, supervisor], null);
    expect(r).toEqual({ cliente: 2, conAcciones: 2, acciones: 4, solas: 2, espera: 2, sinDato: 0 });
  });
  it('escalo: sin conversaciones es un guion, no cero', () => {
    expect(textoEscalo(undefined)).toBe('—');
    expect(textoEscalo({ conversaciones: 0, escaladas: 0 })).toBe('—');
    expect(textoEscalo({ conversaciones: 40, escaladas: 10 })).toBe('10 · 25 %');
  });
});

describe('quien puede que', () => {
  it('una fila por accion, una columna por agente que tiene alguna', () => {
    const m = matriz([soporte, soporteCliente, recepcion, supervisor], null);
    expect(m.columnas.map((a) => a.nombre)).toEqual(['soporte', 'soporte_tecnico_cliente']);
    const reiniciar = m.filas.find((f) => f.nombre === 'reiniciar_ont');
    expect(reiniciar.celdas).toEqual({ soporte: 'espera', soporte_tecnico_cliente: 'espera' });
    expect(m.filas.find((f) => f.nombre === 'registrar_pedido_wifi').celdas).toEqual({ soporte_tecnico_cliente: 'sola' });
    expect(m.sinAcciones.map((a) => a.nombre)).toEqual(['cliente_final']);
  });
});

describe('bitacora y detalles', () => {
  it('dice quien decidio y que paso', () => {
    expect(textoDeBitacora({ decidio: 'aprobo', quien: 'Ana', resultado: 'ok' }))
      .toEqual({ decidio: 'Aprobó: Ana', resultado: 'Salió bien', tono: 'sola' });
    expect(textoDeBitacora({ decidio: 'solo', resultado: 'fallo', error: 'TIMEOUT' }).resultado).toBe('Falló (TIMEOUT)');
    expect(textoDeBitacora({ decidio: 'rechazo', resultado: 'no_se_ejecuto' }).tono).toBe('neutro');
  });
  it('las horas van en Bogota', () => {
    expect(cuandoCorto('2026-11-13T15:42:00Z')).toBe('13/11 10:42');
    expect(cuandoCorto('no es fecha')).toBe('—');
  });
  it('el peso del prompt suma las piezas', () => {
    expect(pesoDelPrompt([{ texto: 'abc' }, { texto: 'de' }, {}])).toBe(5);
  });
});
