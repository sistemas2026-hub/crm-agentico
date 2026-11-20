import { describe, expect, it } from 'vitest';
import { origenDelTicket } from './ticket-origen.js';

describe('origenDelTicket', () => {
  it('un ticket con numero del ISP vino de WispHub, aunque el nombre parezca de Dexter', () => {
    expect(origenDelTicket({ name: 'Instalacion TDT · Cliente · #ab12', external_ticket_id: '88231' }).clave)
      .toBe('wisphub');
  });
  it('el nombre "Asunto · Cliente · #id8" lo armo Dexter al escalar', () => {
    expect(origenDelTicket({ name: 'Sin internet · Cliente 20418 · #a1b2c3d4' }))
      .toEqual({ clave: 'whatsapp', etiqueta: 'WhatsApp · Dexter' });
  });
  it('el formato viejo de Dexter tambien cuenta', () => {
    expect(origenDelTicket({ name: 'WhatsApp 573001234567 - a1b2c3d4' }).clave).toBe('whatsapp');
  });
  it('lo demas se creo a mano', () => {
    expect(origenDelTicket({ name: 'Traslado de servicio' })).toEqual({ clave: 'manual', etiqueta: 'Creado a mano' });
    expect(origenDelTicket({})).toEqual({ clave: 'manual', etiqueta: 'Creado a mano' });
  });
});
