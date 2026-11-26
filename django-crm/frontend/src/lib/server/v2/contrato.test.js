import { describe, expect, it, vi } from 'vitest';

//  La traducción del formulario es pura; la llamada al backend no se prueba
//  acá y su módulo carga el entorno del servidor.
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: vi.fn() }));

import { cuerpoDeContrato, FILAS_DE_SERVIDOR } from './contrato.js';

/** @param {Record<string, string>} campos */
function formulario(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return f;
}

describe('cuerpoDeContrato', () => {
  it('los servidores llegan con el número como entero', () => {
    const c = cuerpoDeContrato(formulario({
      servidor_id_0: '20053', servidor_nombre_0: 'CORTE 15 - SERVIDOR 1',
      servidor_id_1: ' 20061 ', servidor_nombre_1: 'CORTE 30 - SERVIDOR 2',
      nit: ' 900.000.000-0 ', texto_condiciones: 'Primera...'
    }));
    expect(c.servidores).toEqual([
      { id_zona: 20053, nombre: 'CORTE 15 - SERVIDOR 1' },
      { id_zona: 20061, nombre: 'CORTE 30 - SERVIDOR 2' }
    ]);
    expect(c.nit).toBe('900.000.000-0');
    expect(c.texto_condiciones).toBe('Primera...');
  });

  it('una fila vacía se ignora', () => {
    const c = cuerpoDeContrato(formulario({ servidor_id_3: '7', servidor_nombre_3: 'S3' }));
    expect(c.servidores).toEqual([{ id_zona: 7, nombre: 'S3' }]);
  });

  it('UNA FILA A MEDIAS SE MANDA, para que el backend diga qué falta', () => {
    //  Perderla en silencio dejaría a la empresa creyendo que cargó un
    //  servidor que no está.
    const c = cuerpoDeContrato(formulario({ servidor_id_0: '20053' }));
    expect(c.servidores).toEqual([{ id_zona: 20053, nombre: '' }]);
  });

  it('un número con letras viaja como texto y no se vuelve NaN', () => {
    const c = cuerpoDeContrato(formulario({ servidor_id_0: '20a', servidor_nombre_0: 'X' }));
    expect(c.servidores[0].id_zona).toBe('20a');
  });

  it('borrar todos los servidores manda la lista vacía', () => {
    expect(cuerpoDeContrato(formulario({})).servidores).toEqual([]);
    expect(FILAS_DE_SERVIDOR).toBeGreaterThanOrEqual(2);
  });
});

//  CÓMO ESCRIBE LA EMPRESA LOS DATOS DEL CLIENTE (25/11/2026)
describe('cuerpoDeContrato · las costumbres de la empresa', () => {
  it('una casilla marcada viaja como true', () => {
    const c = cuerpoDeContrato(formulario({
      datos_en_mayusculas: 'on', barrio_en_la_direccion: 'on', digitos_del_telefono: ' 10 '
    }));
    expect(c.datos_en_mayusculas).toBe(true);
    expect(c.barrio_en_la_direccion).toBe(true);
    expect(c.digitos_del_telefono).toBe(10);
  });

  it('UNA CASILLA SIN MARCAR VIAJA COMO false, no desaparece', () => {
    //  El navegador no manda una casilla desmarcada. Si el cuerpo tampoco la
    //  mandara, el backend la dejaría como estaba y no habría forma de apagarla.
    const c = cuerpoDeContrato(formulario({ nit: '900' }));
    expect(c).toHaveProperty('datos_en_mayusculas', false);
    expect(c).toHaveProperty('barrio_en_la_direccion', false);
  });

  it('EL INTERRUPTOR DE CREAR EN EL PROVEEDOR: marcado es true, y desmarcado viaja como false', () => {
    //  Es el que más importa que se pueda apagar: enciende crear clientes en
    //  el sistema del proveedor.
    expect(cuerpoDeContrato(formulario({ crear_en_el_isp: 'on' })).crear_en_el_isp).toBe(true);
    expect(cuerpoDeContrato(formulario({ nit: '900' }))).toHaveProperty('crear_en_el_isp', false);
  });

  it('LAS ABREVIATURAS: un renglón por regla, «formas = cómo queda»', () => {
    const c = cuerpoDeContrato(formulario({
      abreviaturas_de_direccion: 'CLL, CL , call = CALLE\n\n  KRA; KR = CRA  \nsolo formas'
    }));
    expect(c.abreviaturas_de_direccion).toEqual([
      { como_lo_escriben: ['CLL', 'CL', 'call'], como_queda: 'CALLE' },
      { como_lo_escriben: ['KRA', 'KR'], como_queda: 'CRA' },
      //  Sin «=» se manda igual: el backend dice qué falta.
      { como_lo_escriben: ['solo formas'], como_queda: '' }
    ]);
    expect(cuerpoDeContrato(formulario({})).abreviaturas_de_direccion).toEqual([]);
  });

  it('LA VLAN DE CADA SERVIDOR viaja con él; vacía no viaja; y el interruptor de la ONU es sí/no', () => {
    const c = cuerpoDeContrato(formulario({
      servidor_id_0: '20049', servidor_nombre_0: 'CORTE 30 - SERVIDOR 1', servidor_vlan_0: ' 300 ',
      servidor_id_1: '20061', servidor_nombre_1: 'CORTE 30 - SERVIDOR 2', servidor_vlan_1: '',
      servidor_id_2: '32278', servidor_nombre_2: 'SABANAGRANDE', servidor_vlan_2: 'tres'
    }));
    expect(c.servidores).toEqual([
      { id_zona: 20049, nombre: 'CORTE 30 - SERVIDOR 1', vlan: 300 },
      { id_zona: 20061, nombre: 'CORTE 30 - SERVIDOR 2' },
      { id_zona: 32278, nombre: 'SABANAGRANDE', vlan: 'tres' }
    ]);
    expect(cuerpoDeContrato(formulario({ activar_onu: 'on' })).activar_onu).toBe(true);
    expect(cuerpoDeContrato(formulario({ nit: '900' }))).toHaveProperty('activar_onu', false);
  });

  it('los dígitos vacíos son 0: no recortar', () => {
    expect(cuerpoDeContrato(formulario({ digitos_del_telefono: '' })).digitos_del_telefono).toBe(0);
    expect(cuerpoDeContrato(formulario({})).digitos_del_telefono).toBe(0);
  });

  it('unos dígitos con letras viajan como texto, para que el backend lo diga', () => {
    expect(cuerpoDeContrato(formulario({ digitos_del_telefono: 'diez' })).digitos_del_telefono).toBe('diez');
  });
});
