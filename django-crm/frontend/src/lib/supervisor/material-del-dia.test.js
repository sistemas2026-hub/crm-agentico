import { describe, expect, it } from 'vitest';

import {
  cantidad,
  cuerpoDeConfiguracion,
  estadoDeCarga,
  lineaDeMaterial,
  tituloDelMaterial,
  opcionDelSupervisor,
  porQue,
  resumenDeAvisos,
  resumenDeLineas
} from './material-del-dia.js';

describe('si el Supervisor ya cargó el material (fase 3)', () => {
  it('la hora, sin el acta (29/10/2026: «está de más»), o nada', () => {
    expect(estadoDeCarga({ cargado_en: '2026-10-28T06:07:10-05:00', acta: 'MAT-20261028-1a2b3c4d' })).toBe(
      'Cargado a las 06:07'
    );
    expect(estadoDeCarga({ cargado_en: null, acta: 'MAT-x' })).toBe('');
  });

  it('los avisos en una línea: lo que falta y los equipos con que no sale', () => {
    const falta = 'Le falta material para completar el kit (13 de 14 materiales): sale con lo que hay en bodega.';
    const catv = 'Sale sin ONU CATV: no puede hacer el trabajo que lo necesita.';
    const wifi = 'Sale sin ONU WIFI: no puede hacer el trabajo que lo necesita.';
    const tv = 'Sale sin SPLITER DE TV 1X2: no puede hacer el trabajo que lo necesita.';
    expect(resumenDeAvisos([falta, catv, wifi])).toBe('Falta material · sale sin ONU CATV y ONU WIFI');
    expect(resumenDeAvisos([falta, catv, wifi, tv])).toBe(
      'Falta material · sale sin ONU CATV, ONU WIFI y SPLITER DE TV 1X2'
    );
    expect(resumenDeAvisos([catv])).toBe('Sale sin ONU CATV');
    expect(resumenDeAvisos([falta, 'No tiene líder con cuenta activa: no hay a quién cargarle.'])).toBe(
      'Falta material · 1 aviso más'
    );
    expect(resumenDeAvisos([])).toBe('');
  });

  it('el título dice cuántas ya se cargaron, o que es una propuesta', () => {
    expect(tituloDelMaterial([{ cargado_en: null }, { cargado_en: null }])).toBe(
      'Material del día · propuesta: el Supervisor todavía no cargó nada'
    );
    expect(tituloDelMaterial([{ cargado_en: '2026-10-28T06:07:00-05:00' }, { cargado_en: null }])).toBe(
      'Material del día · el Supervisor ya cargó 1 de 2 cuadrillas'
    );
  });
});

describe('lo que eligió el Supervisor, y por qué', () => {
  it('una persona o el Supervisor con su motivo', () => {
    expect(porQue('lo eligió una persona')).toBe('elegido por una persona');
    expect(porQue('su zona la nombra')).toBe('lo eligió el Supervisor: su zona la nombra');
    expect(porQue('')).toBe('');
  });

  it('la opción del panel dice qué elegiría hoy', () => {
    expect(opcionDelSupervisor('BOG-SOLEDAD')).toBe('Que elija el Supervisor (hoy: BOG-SOLEDAD)');
    expect(opcionDelSupervisor('')).toBe('Que elija el Supervisor (hoy no puede: ver el motivo)');
  });
});

describe('el material del día, como lo lee una persona', () => {
  it('lo que carga, y lo que ya tiene', () => {
    expect(
      lineaDeMaterial({ material: 'Conector UPC', unidad: 'unidades', en_mano: '4', necesita: '6', asignado: '6' })
    ).toBe('Conector UPC: carga 6 unidades (ya tiene 4)');
    expect(
      lineaDeMaterial({ material: 'ONU WIFI', unidad: 'unidades', en_mano: '0', necesita: '1', asignado: '1' })
    ).toBe('ONU WIFI: carga 1 unidad');
  });

  it('lo que falta va en la misma línea, y «no hay en bodega» en vez de «carga 0»', () => {
    expect(
      lineaDeMaterial({ material: 'CABLE COAXIAL', unidad: 'm', en_mano: '0', necesita: '200', asignado: '100', falta: '100' })
    ).toBe('CABLE COAXIAL: carga 100 m (faltan 100 m)');
    expect(
      lineaDeMaterial({ material: 'CHAZO', unidad: 'unidades', en_mano: '0', necesita: '10', asignado: '0', falta: '10' })
    ).toBe('CHAZO: no hay en bodega (faltan 10 unidades)');
    expect(
      lineaDeMaterial({ material: 'TENSOR', unidad: 'unidades', en_mano: '2', necesita: '8', asignado: '5', falta: '3' })
    ).toBe('TENSOR: carga 5 unidades (ya tiene 2 · faltan 3 unidades)');
  });

  it('el rótulo de la lista plegada', () => {
    expect(resumenDeLineas([{ falta: '0' }, { falta: '3' }, { falta: '1' }])).toBe(
      'Ver los 3 materiales del kit · 2 incompletos'
    );
    expect(resumenDeLineas([{ falta: '0' }])).toBe('Ver el material del kit');
  });

  it('si ya tiene el kit completo no dice «carga 0»', () => {
    expect(
      lineaDeMaterial({ material: 'Cable drop', unidad: 'metros', en_mano: '300', necesita: '0', asignado: '0' })
    ).toBe('Cable drop: tiene el kit completo (ya tiene 300)');
  });

  it('las unidades', () => {
    expect([cantidad('1', 'unidades'), cantidad('2', 'unidades'), cantidad('300', 'metros')]).toEqual([
      '1 unidad',
      '2 unidades',
      '300 metros'
    ]);
  });
});

describe('el formulario de configuración', () => {
  it('kits y bodegas, y vacío es «sin»', () => {
    const f = new FormData();
    f.set('kit:correctivo', 'k-1');
    f.set('kit:trabajos', '');
    f.set('bodega:c-1', 'b-1');
    f.set('otra_cosa', 'x');

    expect(cuerpoDeConfiguracion(f)).toEqual({
      kits: { correctivo: 'k-1', trabajos: null },
      bodegas: { 'c-1': 'b-1' }
    });
  });
});
