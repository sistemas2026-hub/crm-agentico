<script>
  /**
   * El buscador de la cola.
   *
   * Escribe en `busqueda`, que vive en el layout: el filtrado entero se
   * deriva allá (`visibles`) sobre lo ya cargado, sin un viaje de red por
   * tecla. Acá no hay ningún algoritmo de búsqueda -- solo el campo.
   */
  import { Search, X } from '@lucide/svelte';

  let { busqueda = $bindable('') } = $props();
</script>

  <label class="buscar">
    <Search size={14} />
    <input
      type="text"
      bind:value={busqueda}
      placeholder="Buscar cliente o mensaje…"
      aria-label="Buscar conversaciones"
    />
    {#if busqueda}
      <button
        type="button"
        class="limpiar"
        onclick={() => (busqueda = '')}
        aria-label="Limpiar"
      >
        <X size={13} />
      </button>
    {/if}
  </label>

<style>

  .buscar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
    margin: 9px 10px 3px;
    padding: 5px 9px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    background: var(--v2-card);
    color: var(--v2-slate);
  }

  .buscar:focus-within {
    border-color: var(--v2-slate);
  }

  .buscar input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--v2-ink);
    font: inherit;
    font-size: 12.5px;
    outline: none;
  }

  .limpiar {
    border: 0;
    background: none;
    color: var(--v2-slate);
    cursor: pointer;
    display: grid;
    place-items: center;
    padding: 0;
  }

  .limpiar:hover {
    color: var(--v2-ink);
  }
</style>
