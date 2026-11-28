/**
 * LA PROPUESTA DE OCUPANTES.
 *
 * Lo que estas pruebas vigilan no es que proponga: es QUÉ NO PROPONE. Sentar
 * automáticamente a todos los agentes del área es exactamente lo que dibujaba
 * nueve empleados donde hay seis, y el motivo por el que la deducción
 * automática se eliminó el 30/10/2026. Esta función vuelve a tocar esa puerta,
 * así que cada regla que la mantiene cerrada tiene su afirmación.
 */
import { describe, it, expect } from 'vitest';
import { sugerirOcupantes, sentadosEnOtrosDepartamentos } from './sugerencias.js';

const PUESTOS = [{ id: 'principal' }, { id: 'p1' }, { id: 'p2' }];

const AGENTES = [
  { nombre: 'coordinador_noc', cargo: 'Coordinación NOC', area: 'Operaciones' },
  { nombre: 'analista_red', cargo: 'Analista de red', area: 'Operaciones' },
  { nombre: 'tecnico_campo', cargo: 'Técnico de campo', area: 'Operaciones' },
  { nombre: 'soporte', cargo: 'Soporte', area: 'Operaciones' },
  { nombre: 'vendedor', cargo: 'Ventas', area: 'Comercial' }
];

describe('sugerirOcupantes', () => {
  it('propone sólo a los agentes cuya área reclama el departamento', () => {
    //  El de Comercial no pertenece y no puede entrar: la propuesta es la
    //  misma pertenencia que después agrupa la oficina, no «quien haya».
    const r = sugerirOcupantes({ areas: ['Operaciones'] }, AGENTES, PUESTOS);
    expect(r.ocupaciones.map((o) => o.agente)).not.toContain('vendedor');
  });

  it('NO propone una capacidad, aunque su área sea la del departamento', () => {
    //  La regla que más cuesta: `soporte` no es un empleado virtual, es una
    //  capacidad que se le asigna a una persona real del CRM. Sentarlo dibuja
    //  personal que no existe, que es el defecto por el que esto se construyó.
    const r = sugerirOcupantes(
      { areas: ['Operaciones'], capacidades: ['soporte'] }, AGENTES, PUESTOS);
    expect(r.ocupaciones.map((o) => o.agente)).not.toContain('soporte');
    expect(r.sentados).not.toContain('soporte');
  });

  it('NO propone a quien ya está sentado en otro departamento, y lo dice', () => {
    //  El esquema del motor rechaza un agente sentado dos veces. Proponerlo
    //  daría un error al guardar que nadie podría explicar: el otro puesto
    //  puede estar en otro piso.
    const r = sugerirOcupantes(
      { areas: ['Operaciones'] }, AGENTES, PUESTOS, ['coordinador_noc']);
    expect(r.ocupaciones.map((o) => o.agente)).not.toContain('coordinador_noc');
    expect(r.ocupadoEnOtra).toEqual(['coordinador_noc']);
  });

  it('NO pisa a quien alguien ya eligió', () => {
    //  Una propuesta que sobreescribe deja de ser una propuesta.
    const r = sugerirOcupantes(
      { areas: ['Operaciones'], ocupaciones: [{ puesto: 'principal', agente: 'tecnico_campo' }] },
      AGENTES, PUESTOS);
    expect(r.ocupaciones.find((o) => o.puesto === 'principal').agente).toBe('tecnico_campo');
  });

  it('no sienta dos veces al mismo dentro del departamento', () => {
    //  Ya está en `principal`: no puede aparecer otra vez en `p1`.
    const r = sugerirOcupantes(
      { areas: ['Operaciones'], ocupaciones: [{ puesto: 'p2', agente: 'analista_red' }] },
      AGENTES, PUESTOS);
    const veces = r.ocupaciones.filter((o) => o.agente === 'analista_red').length;
    expect(veces).toBe(1);
  });

  it('dice quién quedó sin silla en vez de callarlo', () => {
    //  Cuatro pertenecen y hay dos sillas. Callar a los que sobran haría que
    //  la propuesta pareciera completa, y quien organiza la empresa necesita
    //  enterarse de que la sala le quedó chica.
    const r = sugerirOcupantes({ areas: ['Operaciones'] }, AGENTES,
                               [{ id: 'principal' }, { id: 'p1' }]);
    expect(r.sentados).toHaveLength(2);
    expect(r.sinSilla).toHaveLength(2);
  });

  it('devuelve la lista ENTERA, no sólo lo que agregó', () => {
    //  Es la lista que el formulario va a mandar, y el documento se guarda
    //  entero: armarla a medias es como se perdió un agente de verdad el
    //  31/10/2026.
    //  Comercial tiene UN agente: llena `principal` y nada mas. Lo que esta
    //  prueba exige es que `p2` -que nadie toco- siga en la lista.
    const r = sugerirOcupantes(
      { areas: ['Comercial'], ocupaciones: [{ puesto: 'p2', agente: 'tecnico_campo' }] },
      AGENTES, PUESTOS);
    expect(r.sentados).toEqual(['vendedor']);
    expect(r.ocupaciones.map((o) => o.puesto).sort()).toEqual(['p2', 'principal']);
  });

  it('empieza por el puesto principal', () => {
    const r = sugerirOcupantes({ areas: ['Operaciones'] }, AGENTES, PUESTOS);
    expect(r.ocupaciones.find((o) => o.puesto === 'principal')).toBeTruthy();
  });

  it('propone lo mismo dos veces seguidas', () => {
    //  Sin orden estable, cada «sugerir» sentaría a gente distinta y nadie
    //  podría revisar lo que acaba de ver.
    const a = sugerirOcupantes({ areas: ['Operaciones'] }, AGENTES, PUESTOS);
    const b = sugerirOcupantes({ areas: ['Operaciones'] }, [...AGENTES].reverse(), PUESTOS);
    expect(a.ocupaciones).toEqual(b.ocupaciones);
  });

  it('un departamento sin áreas declaradas no propone a nadie', () => {
    //  No es un error: es un departamento que todavía no dijo qué roles
    //  reclama. Llenarlo con cualquiera sería inventar.
    const r = sugerirOcupantes({ areas: [] }, AGENTES, PUESTOS);
    expect(r.ocupaciones).toEqual([]);
    expect(r.sentados).toEqual([]);
  });

  it('sin plantilla elegida no hay sillas, y nadie se sienta', () => {
    const r = sugerirOcupantes({ areas: ['Operaciones'] }, AGENTES, []);
    expect(r.sentados).toEqual([]);
    expect(r.sinSilla).toHaveLength(4);
  });

  it('casa las áreas igual que la oficina: sin tildes y sin mayúsculas', () => {
    //  Si normalizara distinto, propondría a alguien que la oficina después no
    //  agrupa en esa sala.
    const r = sugerirOcupantes({ areas: ['atencion_cliente'] },
      [{ nombre: 'x', cargo: 'X', area: 'Atención Cliente' }], PUESTOS);
    expect(r.sentados).toEqual(['x']);
  });

  it('no acepta parecidos: `operaciones` no es `operativo`', () => {
    //  Misma regla que `normalizar`. Aceptar sinónimos serviría hoy y el día
    //  que una empresa tenga las dos cosas sentaría al agente equivocado.
    const r = sugerirOcupantes({ areas: ['operativo'] },
      [{ nombre: 'x', cargo: 'X', area: 'Operaciones' }], PUESTOS);
    expect(r.sentados).toEqual([]);
  });

  it('un agente sin área no entra por descarte', () => {
    const r = sugerirOcupantes({ areas: ['Operaciones'] },
      [{ nombre: 'huerfano', cargo: 'H', area: null }], PUESTOS);
    expect(r.sentados).toEqual([]);
  });
});

describe('sentadosEnOtrosDepartamentos', () => {
  it('junta los agentes de los demás y excluye el propio', () => {
    //  Contar el propio los volvería inamovibles: sus ocupaciones ya viajan
    //  dentro del departamento que se está editando.
    const deps = [
      { ocupaciones: [{ puesto: 'principal', agente: 'a' }] },
      { ocupaciones: [{ puesto: 'principal', agente: 'b' }] },
      { ocupaciones: [{ puesto: 'p1', agente: 'c' }] }
    ];
    expect(sentadosEnOtrosDepartamentos(deps, 1).sort()).toEqual(['a', 'c']);
  });

  it('ignora las ocupaciones sin agente', () => {
    const deps = [{ ocupaciones: [{ puesto: 'p1', agente: '' }] }, { ocupaciones: [] }];
    expect(sentadosEnOtrosDepartamentos(deps, 1)).toEqual([]);
  });
});

describe('la propuesta no desaloja a una persona', () => {
  it('una silla con una persona del equipo NO está libre', () => {
    //  Mirar solo `agente` la daba por vacia y la propuesta sentaba un agente
    //  encima de alguien: el documento declara las dos cosas en el mismo
    //  puesto, el motor lo rechaza, y el sintoma habria sido un error al
    //  guardar que no nombra la silla que lo causo.
    const r = sugerirOcupantes(
      { areas: ['Operaciones'], ocupaciones: [{ puesto: 'principal', persona: 'Ana Gómez' }] },
      AGENTES, PUESTOS);
    const principal = r.ocupaciones.find((o) => o.puesto === 'principal');
    expect(principal.persona).toBe('Ana Gómez');
    expect(principal.agente).toBeUndefined();
  });

  it('y la conserva en la lista que se va a guardar', () => {
    const r = sugerirOcupantes(
      { areas: ['Comercial'], ocupaciones: [{ puesto: 'p2', persona: 'Luis' }] },
      AGENTES, PUESTOS);
    expect(r.ocupaciones.find((o) => o.puesto === 'p2')).toEqual({ puesto: 'p2', persona: 'Luis' });
  });
});
