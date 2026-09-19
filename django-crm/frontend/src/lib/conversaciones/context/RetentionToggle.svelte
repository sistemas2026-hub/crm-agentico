<script>
  /**
   * Sacar la conversación de la purga por retención.
   *
   * Distinto de marcar un ejemplo: eso dice "esta respuesta fue buena" y
   * alimenta el manual; esto dice "no la borres todavía" -- un reclamo, un
   * caso que puede volver. Guardar lo hace la página.
   */
  let {
    conservada = false,
    motivoConservar = $bindable(''),
    pidiendoMotivo = $bindable(false),
    guardandoConservar = false,
    errorConservar = '',
    onGuardar
  } = $props();
</script>

  <!-- Conservar. Va arriba de todo y fuera de cualquier plegable: es una
     decisión sobre si esta conversación va a seguir existiendo, y hay que
     poder verla sin abrir nada. -->
  <div class="conservar" class:activa={conservada}>
  <label class="conservar-linea">
    <input
      type="checkbox"
      checked={conservada}
      disabled={guardandoConservar}
      onchange={(e) => onGuardar?.(/** @type {HTMLInputElement} */ (e.currentTarget).checked)}
    />
    <span>
      <b>Conservar</b>
      <span class="v2-muted">— no borrar al vencer la retención</span>
    </span>
  </label>

  {#if pidiendoMotivo && !conservada}
    <div class="conservar-motivo">
      <input
        class="v2-input"
        type="text"
        bind:value={motivoConservar}
        placeholder="¿Por qué? Ej: reclamo en curso"
        onkeydown={(e) => { if (e.key === 'Enter') onGuardar?.(true); }}
      />
      <button
        class="v2-btn v2-btn-sm"
        type="button"
        disabled={guardandoConservar || !motivoConservar.trim()}
        onclick={() => onGuardar?.(true)}
      >
        Guardar
      </button>
    </div>
  {:else if conservada && motivoConservar}
    <p class="conservar-nota">{motivoConservar}</p>
  {/if}

  {#if errorConservar}<p class="conservar-mal">{errorConservar}</p>{/if}
  </div>

<style>


  /* ── conservar ──────────────────────────────────────────────────────── */
  /* Sin recuadro mientras está apagada: es una casilla más, no una alerta.
     Al encenderla toma superficie, porque a partir de ahí sí es un estado
     que hay que poder ver de un vistazo. */
  .conservar {
    padding: 0 0 14px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  .conservar.activa {
    background: var(--v2-line-soft);
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 14px;
    border-bottom: 0;
  }

  .conservar-linea {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12.5px;
    line-height: 1.4;
    cursor: pointer;
  }

  .conservar-linea input {
    margin-top: 2px;
    flex: none;
    accent-color: var(--v2-ink);
  }

  .conservar-motivo {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }

  .conservar-motivo input {
    flex: 1;
    min-width: 0;
    font-size: 12.5px;
  }

  .conservar-nota {
    margin: 6px 0 0 22px;
    font-size: 11.5px;
    color: var(--v2-slate);
    line-height: 1.4;
  }

  .conservar-mal {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--bandeja-error);
  }
</style>
