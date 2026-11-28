import { describe, expect, it } from 'vitest';
import { actorDelEvento, partirNombreDelTicket, textoDelEvento } from './ticket-detalle.js';

describe('partirNombreDelTicket', () => {
  it('separa asunto, cliente e identificador del nombre que escribe el asistente', () => {
    expect(partirNombreDelTicket('Sin internet · Ana Pérez · #a1b2c3d4')).toEqual({
      asunto: 'Sin internet',
      cliente: 'Ana Pérez',
      id: '#a1b2c3d4'
    });
  });
  it('el formato viejo sigue legible', () => {
    expect(partirNombreDelTicket('WhatsApp 573001234567 - a1b2c3d4')).toEqual({
      asunto: 'Conversación de 573001234567',
      cliente: '',
      id: '#a1b2c3d4'
    });
  });
  it('un asunto con " · " que no termina en # se deja entero', () => {
    expect(partirNombreDelTicket('Corte · barrio norte').asunto).toBe('Corte · barrio norte');
    expect(partirNombreDelTicket('').asunto).toBe('Sin asunto');
  });
});

describe('actorDelEvento', () => {
  it('con usuario es una persona', () => {
    expect(actorDelEvento({ action: 'CREATE', by: 'Ana' }, { delAsistente: true }).clave).toBe('persona');
  });
  it('derivar y escalar los escribe el CRM: sistema', () => {
    expect(actorDelEvento({ action: 'ROUTED', by: null }).clave).toBe('sistema');
    expect(actorDelEvento({ action: 'ESCALATED', by: null }).clave).toBe('sistema');
  });
  it('la creacion sin usuario de un ticket del asistente es la IA; la de otro no', () => {
    expect(actorDelEvento({ action: 'CREATE', by: null }, { delAsistente: true }).clave).toBe('ia');
    expect(actorDelEvento({ action: 'CREATE', by: null }, { delAsistente: false }).clave).toBe('ambos');
  });
  it('lo demas sin usuario no se adivina', () => {
    const a = actorDelEvento({ action: 'STATUS_CHANGED', by: null }, { delAsistente: true });
    expect(a.clave).toBe('ambos');
    expect(a.rotulo).toBe('IA o sistema');
  });
});

describe('textoDelEvento', () => {
  const nombres = { 'p-1': 'Ana Pérez', 'p-2': 'Luis Gómez' };
  it('una asignacion dice A QUIEN, por nombre', () => {
    expect(textoDelEvento({ action: 'ASSIGN', metadata: { added: ['p-1'] } }, nombres)).toBe('Asignado a Ana Pérez');
    expect(textoDelEvento({ action: 'ASSIGN', metadata: { removed: ['p-2'] } }, nombres)).toBe('Se quitó a Luis Gómez');
  });
  it('un id desconocido no se muestra crudo', () => {
    const t = textoDelEvento({ action: 'ASSIGN', metadata: { added: ['p-1', 'zzz'] } }, nombres);
    expect(t).toBe('Asignado a Ana Pérez, una persona que ya no está');
    expect(t).not.toContain('zzz');
  });
  it('una derivacion a una persona la nombra', () => {
    expect(textoDelEvento({ action: 'ROUTED', metadata: { target_profile_id: 'p-2' } }, nombres)).toBe('Derivado a Luis Gómez');
  });
  it('sin metadata cae al verbo traducido', () => {
    expect(textoDelEvento({ action: 'ASSIGN', metadata: null })).toBe('Asignado');
    expect(textoDelEvento({ action: 'STATUS_CHANGED' })).toBe('Estado cambiado');
  });
});
