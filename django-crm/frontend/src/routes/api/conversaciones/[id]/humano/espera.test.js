import { describe, it, expect, vi } from 'vitest';

/**
 * «Queda en espera» viaja con la respuesta (29/10/2026). Es el salto que la
 * prueba del motor no ve: si este intermediario dejara caer la marca, el motor
 * recibiría siempre null y CERRARÍA la espera en cada respuesta (contrato T5:
 * «sin la marca: cierra el pendiente interno previo»), sin ningún error.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/autor.js', () => ({
  autorDeSesion: () => ({ autor: 'Ana', autor_usuario_id: 'u-1' }),
  claveIdempotencia: (c) => c || 'clave'
}));

const { POST } = await import('./+server.js');

async function enviado(cuerpo) {
  const fetch = vi.fn(async () => new Response('{}', { status: 201 }));
  await POST(/** @type {any} */ ({
    request: { json: async () => cuerpo },
    params: { id: 'c1' },
    locals: { user: { id: 'u-1' } },
    fetch
  }));
  return JSON.parse(/** @type {any} */ (fetch.mock.calls[0])[1].body);
}

describe('POST /api/conversaciones/[id]/humano', () => {
  it('reenvía lo que se espera', async () => {
    const b = await enviado({ mensaje: 'hola', pendiente_interno: '  esperando que reinicie ' });
    expect(b.pendiente_interno).toBe('esperando que reinicie');
  });

  it('sin marca manda null, que es lo que cierra la espera', async () => {
    expect((await enviado({ mensaje: 'hola' })).pendiente_interno).toBeNull();
    expect((await enviado({ mensaje: 'hola', pendiente_interno: '   ' })).pendiente_interno).toBeNull();
  });

  it('no deja pasar más de 200 caracteres', async () => {
    const b = await enviado({ mensaje: 'hola', pendiente_interno: 'x'.repeat(500) });
    expect(b.pendiente_interno).toHaveLength(200);
  });
});
