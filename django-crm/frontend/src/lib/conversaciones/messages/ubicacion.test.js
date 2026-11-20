/**
 * La ubicación compartida por el cliente, y su enlace al mapa (11/11/2026).
 * El formato lo escribe nucleo/canales/whatsapp.py::texto_de_ubicacion; si uno
 * de los dos cambia, esta prueba es la que lo dice.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import { ubicacionCompartida } from './ubicacion.js';
import MessageThread from './MessageThread.svelte';

describe('ubicacionCompartida', () => {
  it('reconoce el formato del motor, con o sin nombre y dirección', () => {
    expect(ubicacionCompartida('[El cliente compartio su ubicacion: Casa · Calle 50 # 12-30 · coordenadas 10.987812, -74.7889]'))
      .toEqual({ lat: 10.987812, lng: -74.7889, mapa: 'https://www.google.com/maps?q=10.987812,-74.7889' });
    expect(ubicacionCompartida('[El cliente compartio su ubicacion: coordenadas 4.6, -74.08]')?.lat).toBe(4.6);
  });

  it('no arma un enlace con lo que alguien escribió a mano', () => {
    expect(ubicacionCompartida('mis coordenadas 10.98, -74.78')).toBeNull();
    expect(ubicacionCompartida('[El cliente compartio su ubicacion]')).toBeNull();
    expect(ubicacionCompartida('[El cliente compartio su ubicacion: coordenadas 95, 10]')).toBeNull();
    expect(ubicacionCompartida(null)).toBeNull();
  });
});

describe('el hilo', () => {
  const dibujar = (/** @type {string} */ rol, /** @type {string} */ origen, /** @type {string} */ contenido) =>
    render(MessageThread, {
      props: {
        hilo: [{ tipo: 'msg', clave: '1',
                 m: { id: '1', rol, origen, contenido, creado_en: '2026-11-11T15:00:00Z', adjuntos: [] } }],
        cantidadMensajes: 1, conversacionId: 'x', nombreCliente: 'Juana', casos: []
      }
    }).body;

  const UBICACION = '[El cliente compartio su ubicacion: coordenadas 10.98, -74.78]';

  it('una ubicación del cliente lleva «Ver en el mapa»', () => {
    const html = dibujar('user', 'cliente', UBICACION);
    expect(html).toMatch(/href="https:\/\/www\.google\.com\/maps\?q=10\.98,-74\.78"/);
    expect(html).toMatch(/Ver en el mapa/);
  });

  it('el mismo texto escrito por el asistente no lleva enlace', () => {
    expect(dibujar('assistant', 'ia', UBICACION)).not.toMatch(/Ver en el mapa/);
  });
});
