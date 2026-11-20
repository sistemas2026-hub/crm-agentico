<script>
  /**
   * Lo que hizo el agente en un turno del simulador (12/11/2026): las
   * herramientas en orden, el área a la que derivó y lo que falló.
   *
   * Tres estados de cada llamada, con la misma regla que «Ver proceso» en
   * Conversaciones: corrió, la frenó el código (un bloqueo NO es un fallo: es
   * la protección funcionando) o falló el sistema externo.
   *
   * Una traza incompleta se dice: «no llamó a nada» y «todavía no llegó» no
   * pueden verse igual.
   *
   * @type {{ traza: any }}
   */
  let { traza } = $props();
</script>

{#if traza === 'cargando'}
  <div class="traza v2-sub">Leyendo lo que hizo el agente…</div>
{:else if traza}
  <details class="traza" open={!!traza.derivo_a || (traza.errores ?? []).length > 0}>
    <summary>
      {(traza.herramientas ?? []).length} herramienta(s)
      {#if traza.derivo_a}· derivó a <b>{traza.derivo_a}</b>{/if}
      {#if (traza.errores ?? []).length > 0}
        · <span class="error">{traza.errores.length} error(es)</span>
      {/if}
      {#if !traza.completa}· <span class="v2-muted">traza incompleta</span>{/if}
    </summary>
    {#if traza.error}
      <p class="error">{traza.error}</p>
    {:else if (traza.herramientas ?? []).length === 0}
      <p class="v2-muted">
        {traza.completa ? 'No llamó a ninguna herramienta.' : 'Todavía no llegó la traza de este turno.'}
      </p>
    {:else}
      <ol>
        {#each traza.herramientas as h, i (i)}
          <li>
            <code>{h.herramienta}</code>
            {#if h.area}→ {h.area}{/if}
            {#if h.bloqueo}
              <span class="bloqueo">frenada por el código{h.codigo_error ? ` (${h.codigo_error})` : ''}</span>
            {:else if !h.exito}
              <span class="error">falló{h.codigo_error ? `: ${h.codigo_error}` : ''}</span>
            {/if}
            {#if h.escritura}<span class="v2-muted">· escribe</span>{/if}
          </li>
        {/each}
      </ol>
    {/if}
  </details>
{/if}

<style>
  .traza {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px dashed var(--v2-line);
    font-size: 11.5px;
    white-space: normal;
  }
  .traza summary {
    cursor: pointer;
    color: var(--v2-slate);
  }
  .traza ol {
    margin: 6px 0 0;
    padding-left: 18px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .traza p {
    margin: 6px 0 0;
  }
  .error {
    color: var(--v2-rust);
  }
  .bloqueo {
    color: var(--v2-clay, #b4642e);
  }
</style>
