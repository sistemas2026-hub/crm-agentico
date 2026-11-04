import { describe, it, expect } from 'vitest';
import {
  resumenDe,
  agrupar,
  sugerirIdentificador,
  avisosDelAgente,
  PLANTILLA_INSTRUCCIONES
} from './formulario.js';

/**
 * Crear un agente sin ser desarrollador (02/11/2026). El usuario: "que la
 * persona que cree un agente se le haga facil... la grilla de herramientas,
 * el prompt, mas entendible". Lo que se protege aca es la LOGICA del
 * formulario: que cada herramienta se lea en una linea, que caigan en el grupo
 * de lo que hacen, y que los avisos digan lo que va a pasar ANTES de guardar.
 */

const CATALOGO = [
  { nombre: 'consultar_saldo', descripcion: 'Consulta el saldo del cliente. Usala cuando pregunte cuanto debe.',
    escribe: false, pide_aprobacion: false, critica: true, deriva: false, de_sistema: false, campos_conocidos: ['saldo'] },
  { nombre: 'reiniciar_ont', descripcion: 'LLAMA A ESTA HERRAMIENTA (no sugieras el reinicio manual) apenas la senal de aceptable y el ping responda.',
    escribe: true, pide_aprobacion: true, critica: false, deriva: false, de_sistema: false, campos_conocidos: ['response'] },
  { nombre: 'derivar_a_area', descripcion: 'Pasa la conversacion al area que corresponde.',
    escribe: false, pide_aprobacion: false, critica: true, deriva: true, de_sistema: false, campos_conocidos: [] },
  { nombre: 'cerrar_ticket_operativo', descripcion: 'Cierra el ticket. NO la llames tu.',
    escribe: true, pide_aprobacion: true, critica: true, deriva: false, de_sistema: true, campos_conocidos: [] }
];

describe('cada herramienta en una linea', () => {
  it('la primera oracion, no el parrafo entero', () => {
    expect(resumenDe(CATALOGO[0].descripcion)).toBe('Consulta el saldo del cliente.');
  });
  it('un texto largo se corta con puntos suspensivos, sin partir una palabra', () => {
    const r = resumenDe('palabra '.repeat(60));
    expect(r.length).toBeLessThanOrEqual(141);
    expect(r.endsWith('…')).toBe(true);
    expect(r).not.toMatch(/pal…$/);
  });
  it('sin descripcion, vacio', () => {
    expect(resumenDe('')).toBe('');
  });
});

describe('agrupadas por lo que hacen', () => {
  it('consulta, actua, deriva y del sistema, cada una en su grupo', () => {
    const g = Object.fromEntries(agrupar(CATALOGO, '').map((x) => [x.clave, x.items.map((i) => i.nombre)]));
    expect(g.consulta).toEqual(['consultar_saldo']);
    expect(g.actua).toEqual(['reiniciar_ont']);
    expect(g.deriva).toEqual(['derivar_a_area']);
    expect(g.sistema).toEqual(['cerrar_ticket_operativo']);
  });
  it('el buscador filtra por nombre o por descripcion, sin tildes ni mayusculas', () => {
    const nombres = agrupar(CATALOGO, 'SALDO').flatMap((x) => x.items.map((i) => i.nombre));
    expect(nombres).toEqual(['consultar_saldo']);
    const porTexto = agrupar(CATALOGO, 'senal').flatMap((x) => x.items.map((i) => i.nombre));
    expect(porTexto).toEqual(['reiniciar_ont']);
  });
  it('un grupo vacio no aparece', () => {
    expect(agrupar(CATALOGO, 'saldo').map((x) => x.clave)).toEqual(['consulta']);
  });
});

describe('el identificador se sugiere solo', () => {
  it('del cargo, en minusculas, sin tildes ni espacios', () => {
    expect(sugerirIdentificador('Atención de Facturas')).toBe('atencion_de_facturas');
  });
  it('empieza con letra y no pasa de 30', () => {
    expect(sugerirIdentificador('1 agente')).toBe('agente');
    expect(sugerirIdentificador('a'.repeat(50)).length).toBe(30);
  });
});

describe('los avisos antes de guardar', () => {
  const base = { orientadoA: 'colaborador', descripcion: 'Hace algo.', atiende: '', conectar: false,
                 seleccion: {}, campos: {}, catalogo: CATALOGO };
  /** @param {any} cambios */
  const avisos = (cambios) => avisosDelAgente({ ...base, ...cambios }).map((a) => a.clave);

  it('un agente de clientes sin conectar al router: nunca le llega nada', () => {
    expect(avisos({ orientadoA: 'cliente_final', conectar: false })).toContain('sin_router');
  });
  it('conectado pero sin decir que atiende: el router no sabe cuando mandarle', () => {
    expect(avisos({ orientadoA: 'cliente_final', conectar: true, atiende: '' })).toContain('sin_atiende');
    expect(avisos({ orientadoA: 'cliente_final', conectar: true, atiende: 'saldo' })).not.toContain('sin_atiende');
  });
  it('una herramienta de consulta sin ningun dato elegido: no va a ver nada', () => {
    expect(avisos({ seleccion: { consultar_saldo: true }, campos: {} })).toContain('sin_campos:consultar_saldo');
    expect(avisos({ seleccion: { consultar_saldo: true }, campos: { consultar_saldo: ['saldo'] } }))
      .not.toContain('sin_campos:consultar_saldo');
  });
  it('una del sistema elegida: se avisa que la dispara el codigo', () => {
    expect(avisos({ seleccion: { cerrar_ticket_operativo: true } })).toContain('de_sistema:cerrar_ticket_operativo');
  });
  it('sin instrucciones: el modelo no sabe que hacer', () => {
    expect(avisos({ descripcion: '   ' })).toContain('sin_instrucciones');
  });
  it('un agente interno bien armado: sin avisos', () => {
    expect(avisos({})).toEqual([]);
  });
});

describe('la plantilla de instrucciones', () => {
  it('trae las cuatro partes que hacen falta', () => {
    for (const parte of ['Qué hace', 'Con quién habla', 'Qué NO debe hacer', 'Cuándo pasa a una persona']) {
      expect(PLANTILLA_INSTRUCCIONES).toContain(parte);
    }
  });
});
