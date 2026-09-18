<script>
  /**
   * Lo que dice la documentación interna sobre lo último que preguntó el
   * cliente. Recupera, no genera: son fragmentos reales con su procedencia, y
   * quien atiende decide qué hacer con ellos.
   */
  let {
    sugerencias = [], buscandoDocs = false, errorDocs = '', mejorSimilitud,
    consultaDocs = $bindable(''),
    expandido = $bindable(null),
    copiado = null,
    onAbrir, onBuscar, onCopiar
  } = $props();
</script>

  <!-- Copiloto documental. Mismo patron plegable que "Ver proceso": es ayuda
     lateral, no el contenido de la pantalla. -->
  <details class="docs" ontoggle={(e) => onAbrir?.(e)}>
  <!-- Una linea, no un bloque. Sin contenido activo ocupaba ancho para decir
     que existe, y ese ancho lo necesita el centro: resumen, conversacion y
     compositor. Se abre cuando hace falta. -->
  <summary class="proceso-resumen">
  Buscar en las guías
  {#if sugerencias.length}
    <span class="v2-muted">({sugerencias.length})</span>
  {/if}
  </summary>

  <form class="docs-buscar" onsubmit={(e) => onBuscar?.(e)}>
  <input
    class="v2-input"
    type="text"
    bind:value={consultaDocs}
    placeholder="¿Qué necesitás buscar?"
    aria-label="Buscar en la documentación interna"
  />
  <button class="v2-btn v2-btn-sm" type="submit" disabled={buscandoDocs}>Buscar</button>
  </form>

  {#if buscandoDocs}
  <p class="v2-muted docs-nota">Buscando…</p>
  {:else if errorDocs}
  <p class="docs-nota docs-malo">{errorDocs}</p>
  {:else if sugerencias.length === 0}
  <p class="v2-muted docs-nota">
    La documentación no cubre esta consulta.
    {#if mejorSimilitud !== null}
      Lo más parecido quedó en <span class="v2-num">{mejorSimilitud}</span>, por debajo del umbral.
    {/if}
  </p>
  {:else}
  {#each sugerencias as s, i}
    <article class="doc" class:abierto={expandido === i}>
      <button
        type="button"
        class="doc-head"
        onclick={() => (expandido = expandido === i ? null : i)}
        aria-expanded={expandido === i}
      >
        <span class="doc-codigo v2-num">{s.codigo || '—'}{#if s.version} v{s.version}{/if}</span>
        <span class="doc-titulo">{s.titulo || 'Sin título'}</span>
      </button>
      <p class="doc-texto">{s.contenido}</p>
      <div class="doc-pie">
        <button
          class="v2-btn v2-btn-sm"
          type="button"
          onclick={() => onCopiar?.(s.contenido, i)}
        >
          {copiado === i ? 'Copiado' : 'Copiar'}
        </button>
      </div>
    </article>
  {/each}
  {/if}
  </details>

<style>
  /* Duplicación temporal por CSS scoped durante Fase 0A: el mismo
     `<summary class="proceso-resumen">` lo usan este panel y TracePanel.
     Consolidar en Fase 1 sin cambiar apariencia. */


  .proceso-resumen {
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
    user-select: none;
  }


  .proceso-resumen .v2-muted {
    font-weight: 400;
  }

  .docs {
    padding: 14px 0 0;
  }


  /* ── copiloto documental ────────────────────────────────────────────── */
  .docs-buscar {
    display: flex;
    gap: 6px;
    margin: 10px 0 4px;
  }

  .docs-buscar input {
    flex: 1;
    min-width: 0;
    font-size: 13px;
  }

  .docs-nota {
    font-size: 12.5px;
    line-height: 1.5;
    margin: 8px 0 0;
  }

  .docs-malo {
    color: var(--v2-rust);
  }

  /* Sin tarjeta: son citas de un documento, no objetos que se manipulan. */
  .doc {
    border-top: 1px solid var(--v2-line-soft);
    padding: 9px 0;
  }

  .doc-head {
    display: flex;
    flex-direction: column;
    gap: 1px;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    padding: 0;
    font: inherit;
    color: inherit;
    cursor: pointer;
  }

  .doc-codigo {
    font-size: 10.5px;
    color: var(--v2-slate);
  }

  .doc-titulo {
    font-size: 12.5px;
    font-weight: 620;
    letter-spacing: -0.01em;
    line-height: 1.35;
  }

  .doc-head:hover .doc-titulo {
    text-decoration: underline;
  }

  .doc-texto {
    font-size: 12.2px;
    color: var(--v2-slate);
    line-height: 1.5;
    margin: 5px 0 0;
    white-space: pre-wrap;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* Abierto: el fragmento entero, con su propio scroll para que un documento
     largo no empuje el hilo fuera de la vista. */
  .doc.abierto .doc-texto {
    display: block;
    max-height: 320px;
    overflow-y: auto;
  }

  .doc-pie {
    display: flex;
    justify-content: flex-end;
    margin-top: 6px;
  }
</style>
