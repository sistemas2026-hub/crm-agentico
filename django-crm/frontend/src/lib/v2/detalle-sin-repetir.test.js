import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import {
  comparacionAporta,
  filasComparables,
  filasDeAceptar,
  analisisSeparado,
  loteDeSeleccion,
  AUSENTE
} from './supervisor-noc-detalle.js';

/**
 * EL MISMO PÁRRAFO, CUATRO VECES.
 *
 * Medido el 13/10/2026 sobre una propuesta real de producción: el texto «El
 * ticket sigue abierto en WispHub hace 7 días…» aparecía en la banda del
 * hallazgo, en «¿Qué está pasando?», al pie de «¿Qué detectó el Supervisor?» y
 * otra vez como «Interpretación del Supervisor». Más tres renglones que decían
 * «No disponible en la fuente» y una tabla comparativa cuyas cuatro filas
 * estaban vacías salvo un identificador que ya estaba arriba.
 *
 * POR QUÉ UNA GUARDA Y NO «SE ARREGLÓ Y YA»
 * -----------------------------------------
 * La repetición entra sola. Cada vez que alguien agrega una sección a esta
 * pantalla, el motivo es lo más fácil de poner adentro --siempre existe y
 * siempre dice algo-- y nadie ve el total hasta que abre el panel entero.
 *
 * LO QUE MIDE, Y POR QUÉ ASÍ
 * --------------------------
 * Cuenta en el markup los lugares que pintan el mismo campo. No es «presencia
 * del mecanismo»: acá cada aparición ES un párrafo más en la pantalla, que es
 * exactamente lo que se vio y lo que se quiso sacar.
 *
 * LO QUE NO MIDE: cómo se ve. Que el orden de las secciones sea el bueno o que
 * entre en una pantalla de portátil no se decide acá.
 */

const PANEL = new URL('../../routes/(app)/supervisor-noc/+page.svelte', import.meta.url).pathname
  .replace(/^\/([A-Za-z]:)/, '$1');

const markup = readFileSync(PANEL, 'utf8');
//  Sin los comentarios: varios EXPLICAN que el motivo ya no va, y nombrarlo
//  para explicar que se quitó no es pintarlo.
const sinComentarios = markup.replace(/<!--[\s\S]*?-->/g, '');

describe('el detalle no repite el mismo texto', () => {
  it('el motivo del Supervisor se pinta en un solo lugar', () => {
    //  'resumen' es quePasa(), que para casi todos los tipos ES d.motivo.
    const veces =
      (sinComentarios.match(/\{detalle\.motivo/g) ?? []).length +
      (sinComentarios.match(/\{resumen\}/g) ?? []).length +
      (sinComentarios.match(/\{analisis\.interpretacion\}/g) ?? []).length;
    expect(veces, 'el mismo párrafo vuelve a aparecer en otra sección').toBe(1);
  });

  it('la acción propuesta se pinta en un solo lugar', () => {
    const veces =
      (sinComentarios.match(/\{detalle\.accion_propuesta/g) ?? []).length +
      (sinComentarios.match(/\{aceptar\.accion\}/g) ?? []).length;
    expect(veces, 'la propuesta se repite en chico debajo de sí misma').toBe(1);
  });
});

describe('no se pinta lo que no tiene dato', () => {
  it('la tabla Dexter ↔ WispHub no sale cuando no hay nada que comparar', () => {
    //  Un ticket leído: el estado del proveedor no viaja, la lectura tampoco,
    //  y el responsable es de la orden, que no existe.
    const filas = [
      { campo: 'Estado', dexter: AUSENTE, wisphub: AUSENTE },
      { campo: 'Identificador', dexter: 'CS-12c0bd1c', wisphub: AUSENTE },
      { campo: 'Última lectura', dexter: AUSENTE, wisphub: AUSENTE },
      { campo: 'Responsable', dexter: AUSENTE, wisphub: AUSENTE }
    ];
    expect(comparacionAporta(filas)).toBe(false);
  });

  it('un dato que solo tiene UNA fuente no hace aparecer la tabla', () => {
    //  Medido en pantalla el 13/10/2026: al hacer que el técnico del caso
    //  viajara, «Responsable» paso a tener dato en Dexter y la tabla volvio a
    //  salir -- con tres filas enteras diciendo «No disponible en la fuente».
    //  Una fila con un solo lado no compara: es un dato suelto en una tabla de
    //  dos columnas.
    const filas = [
      { campo: 'Estado', dexter: AUSENTE, wisphub: AUSENTE },
      { campo: 'Identificador', dexter: 'CS-46a1de31', wisphub: '94660' },
      { campo: 'Última lectura', dexter: AUSENTE, wisphub: AUSENTE },
      { campo: 'Responsable', dexter: 'Mario Vasquez', wisphub: AUSENTE }
    ];
    expect(comparacionAporta(filas)).toBe(false);
  });

  it('las filas que se pintan son solo las que tienen las dos fuentes', () => {
    const filas = [
      { campo: 'Estado', dexter: 'Assigned', wisphub: 'Cerrado' },
      { campo: 'Responsable', dexter: 'Mario Vasquez', wisphub: AUSENTE },
      { campo: 'Última lectura', dexter: AUSENTE, wisphub: AUSENTE }
    ];
    expect(filasComparables(filas).map((f) => f.campo)).toEqual(['Estado']);
  });

  it('pero sí sale cuando las dos fuentes dicen cosas distintas', () => {
    const filas = [
      { campo: 'Estado', dexter: 'Assigned', wisphub: 'Cerrado' },
      { campo: 'Identificador', dexter: 'CS-1', wisphub: '94721' }
    ];
    expect(comparacionAporta(filas)).toBe(true);
  });

  it('«Si aceptas» deja fuera las filas sin dato y la acción repetida', () => {
    const filas = filasDeAceptar({
      estadoActual: AUSENTE,
      accion: 'Decidir qué se hace con este ticket',
      origenDecision: AUSENTE,
      tipo: 'Revisión humana · propuesta del Supervisor NOC IA'
    });
    expect(filas.map((f) => f.rotulo)).toEqual(['Tipo']);
    expect(JSON.stringify(filas)).not.toContain('Decidir qué se hace');
  });
});

describe('cada observación se cuenta una vez', () => {
  it('lo que falta no sale además como hecho observado', () => {
    const d = {
      motivo: 'm',
      impacto: 'i',
      evidencia: [
        { dato: 'ticket 94721 en estado Nuevo', fuente: 'proveedor' },
        { dato: 'falta para estar seguro: historial de señal del servicio', fuente: 'lectura' }
      ]
    };
    const a = analisisSeparado(d);
    expect(a.hechos.map((h) => h.dato)).toEqual(['ticket 94721 en estado Nuevo']);
    expect(a.faltantes).toHaveLength(1);
  });
});


describe('el botón de aceptar varias no promete un cierre que no ocurre', () => {
  //  Lo vio el usuario en producción el 13/10/2026: seis tickets leídos
  //  tildados, y el botón ofreciendo «Aceptar y cerrar 6». Ninguno de esos
  //  seis cierra nada -- aceptar registra el acuerdo y se acabó.
  const leido = (id) => ({ id, tipo_senal: 'ticket_sin_diagnostico' });
  const desinc = (id) => ({ id, tipo_senal: 'caso_desincronizado' });

  it('seis tickets leídos no se «cierran»', () => {
    const filas = ['1', '2', '3', '4', '5', '6'].map(leido);
    const r = loteDeSeleccion(filas, ['1', '2', '3', '4', '5', '6']);
    expect(r.etiqueta).toBe('Aceptar 6');
    expect(r.etiqueta).not.toContain('cerrar');
    expect(r.aclaracion).toBe('');
  });

  it('seis desincronizaciones sí, porque el backend las cierra', () => {
    const filas = ['1', '2'].map(desinc);
    expect(loteDeSeleccion(filas, ['1', '2']).etiqueta).toBe('Aceptar y cerrar 2');
  });

  it('mezcladas: promete lo chico y dice el reparto', () => {
    const filas = [desinc('1'), leido('2'), leido('3')];
    const r = loteDeSeleccion(filas, ['1', '2', '3']);
    expect(r.etiqueta).toBe('Aceptar 3');
    expect(r.aclaracion).toContain('1 cierran');
    expect(r.aclaracion).toContain('2 solo quedan registradas');
  });

  it('solo cuenta lo tildado, no lo que está en pantalla', () => {
    const filas = [desinc('1'), desinc('2'), leido('3')];
    expect(loteDeSeleccion(filas, ['1']).etiqueta).toBe('Aceptar y cerrar 1');
  });
});
