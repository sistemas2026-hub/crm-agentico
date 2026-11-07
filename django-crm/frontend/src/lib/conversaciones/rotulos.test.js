/**
 * Los rótulos de motivos, etiquetas y casos (29/10/2026).
 *
 * Lo que protege: que la palabra de la empresa gane cuando existe, y que sin
 * ella la fila siga teniendo texto. La segunda es la negativa que importa: un
 * motivo nuevo sin rótulo no puede dejar un hueco en la cola.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { rotuloDe } from './rotulos.js';

describe('rotuloDe', () => {
  const rotulos = { frustracion_detectada: 'Frustración detectada' };

  it('usa el rótulo de la empresa', () => {
    expect(rotuloDe('frustracion_detectada', rotulos)).toBe('Frustración detectada');
  });

  it('sin rótulo, la clave con espacios: nunca vacío', () => {
    expect(rotuloDe('informacion_a_confirmar', rotulos)).toBe('informacion a confirmar');
    expect(rotuloDe('informacion_a_confirmar', null)).toBe('informacion a confirmar');
  });

  it('un rótulo en blanco no tapa la clave', () => {
    expect(rotuloDe('queja', { queja: '   ' })).toBe('queja');
  });

  it('sin clave no hay nada que decir', () => {
    expect(rotuloDe(null, rotulos)).toBe('');
  });
});

describe('ya no quedan copias, leído del código', () => {
  // Eran cinco copias de `replaceAll('_', ' ')` para motivos y etiquetas, y
  // por eso ninguna podía mostrar una tilde. Si vuelve una, esta pantalla
  // vuelve a ignorar los rótulos en ese lugar sin que nada falle.
  const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
  it.each([
    '../../routes/(app)/conversaciones/+layout.svelte',
    '../../routes/(app)/conversaciones/[id]/+page.svelte',
    './conversation/HandoffControls.svelte',
    './cola/ConversationRow.svelte',
    './context/CasePanel.svelte'
  ])('%s no rotula con replaceAll', (rel) => {
    expect(leer(rel)).not.toMatch(/(motivoLabel|etiquetaLabel)\s*=.*replaceAll\('_'/);
  });
});
