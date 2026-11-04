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
      <b>Conservar esta conversación</b>
      <!-- Solo ESTA, no las anteriores del chat (21/10/2026): la bandeja
           muestra el chat entero, pero la retención es por conversación. -->
      <span class="v2-muted">— no borrarla al vencer la retención (las anteriores del chat no)</span>
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
     que hay que poder ver de un vistazo.
     04/11/2026: con los tokens de la Bandeja y no los del CRM (`--v2-*`),
     y el mismo recuadro que `.panel-tarjeta`: borde de 1px y radio chico. */
  .conservar {
    padding: 0 0 12px;
    border-bottom: 1px solid var(--bandeja-borde);
  }

  .conservar.activa {
    background: var(--bandeja-superficie-suave);
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    padding: 8px 12px;
    margin-bottom: 12px;
  }

  .conservar-linea {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 13px;
    line-height: 1.4;
    cursor: pointer;
  }

  .conservar-linea input {
    margin-top: 2px;
    flex: none;
    accent-color: var(--bandeja-accion);
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
    color: var(--bandeja-texto-2);
    line-height: 1.4;
  }

  .conservar-mal {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--bandeja-error);
  }
</style>
