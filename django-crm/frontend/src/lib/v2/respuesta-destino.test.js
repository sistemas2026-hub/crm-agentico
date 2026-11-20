/**
 * A DONDE VA LA RESPUESTA. Se afirma sobre lo que la caja le dice a quien
 * escribe y sobre que boton le ofrece, que es lo que decide si cree que el
 * cliente fue avisado. El caso que destapo esto: un ticket sin chat decia
 * "Responder al cliente por donde escribió…" y no le llegaba a nadie.
 */
import { describe, expect, it } from 'vitest';
import { destinoDeLaRespuesta, nombreDelCanal } from './respuesta-destino.js';

describe('destinoDeLaRespuesta', () => {
  it('una nota interna no le llega al cliente, aunque haya chat', () => {
    const d = destinoDeLaRespuesta({ interna: true, hayConversacion: true, cliente: 'Ana' });
    expect(d.clave).toBe('nota');
    expect(d.aviso).toContain('Solo la ve el equipo');
    expect(d.aviso).toContain('ni cuenta como primera respuesta');
    expect(d.boton).toBe('Guardar nota');
    expect(d.primario).toBe(false);
    expect(d.ofreceDevolver).toBe(false);
  });

  it('con chat detras sale por WhatsApp, nombra al cliente y es la accion principal', () => {
    const d = destinoDeLaRespuesta({ interna: false, hayConversacion: true, cliente: 'Ana Pérez', canal: 'whatsapp' });
    expect(d.clave).toBe('chat');
    expect(d.tono).toBe('accion');
    expect(d.aviso).toBe('Sale por WhatsApp a Ana Pérez.');
    expect(d.boton).toBe('Enviar por WhatsApp');
    expect(d.primario).toBe(true);
    expect(d.ofreceDevolver).toBe(true);
  });

  it('SIN chat dice que el cliente no lo recibe y no promete un envio', () => {
    const d = destinoDeLaRespuesta({ interna: false, hayConversacion: false, cliente: 'Ana Pérez' });
    expect(d.clave).toBe('sin_chat');
    expect(d.tono).toBe('atencion');
    expect(d.aviso).toContain('el cliente no va a recibir este mensaje');
    expect(d.aviso).toContain('llamalo o escribile por otro medio');
    expect(d.aviso).not.toMatch(/Sale por/);
    expect(d.boton).toBe('Guardar respuesta');
    expect(d.boton).not.toMatch(/Enviar/);
    expect(d.primario).toBe(false);
    // Devolver la conversacion al asistente no tiene sentido sin conversacion.
    expect(d.ofreceDevolver).toBe(false);
  });

  it('mientras carga no afirma ninguna de las dos cosas', () => {
    for (const hay of [null, undefined]) {
      const d = destinoDeLaRespuesta({ interna: false, hayConversacion: hay, cliente: 'Ana' });
      expect(d.clave).toBe('comprobando');
      expect(d.aviso).toBe('Comprobando si hay un chat de WhatsApp…');
      expect(d.aviso).not.toMatch(/Sale por|no va a recibir/);
      expect(d.primario).toBe(false);
      expect(d.ofreceDevolver).toBe(false);
    }
  });

  it('si la lectura fallo lo dice, sin prometer ni negar la entrega', () => {
    const d = destinoDeLaRespuesta({ interna: false, hayConversacion: 'no_se_pudo' });
    expect(d.clave).toBe('no_se_pudo');
    expect(d.aviso).toContain('No se pudo comprobar');
    expect(d.primario).toBe(false);
  });

  it('sin nombre del cliente no deja un hueco', () => {
    const d = destinoDeLaRespuesta({ interna: false, hayConversacion: true, cliente: '  ' });
    expect(d.aviso).toBe('Sale por WhatsApp al cliente.');
  });

  it('un canal que no es WhatsApp se nombra como es, no como WhatsApp', () => {
    expect(nombreDelCanal('simulador')).toBe('Simulador');
    expect(nombreDelCanal('whatsapp')).toBe('WhatsApp');
    expect(nombreDelCanal('')).toBe('WhatsApp');
    const d = destinoDeLaRespuesta({ interna: false, hayConversacion: true, cliente: 'Ana', canal: 'simulador' });
    expect(d.boton).toBe('Enviar por Simulador');
  });
});
