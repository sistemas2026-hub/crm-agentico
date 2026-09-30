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
      placeholder="Buscar conversación, cliente o mensaje…"
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

  /* VIVE EN LA BARRA DE CONSOLA, NO EN LA COLUMNA.
     Estaba dentro de la cola, con 30px de alto más 12 de márgenes, empujando
     las conversaciones hacia abajo. En la referencia el buscador está en la
     barra superior y centrado --"Search conversations, phones, DNI or
     tickets…"-- y la columna de la cola arranca directamente con las
     pestañas de estado.
     Sin márgenes verticales y con `flex: 1` acotado: lo posiciona la barra,
     no él. Radio 6 como el resto de la Bandeja (era 8). */
  .buscar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1 1 auto;
    max-width: 420px;
    min-width: 0;
    padding: 4px 9px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto-2);
  }

  .buscar:focus-within {
    border-color: var(--bandeja-texto-2);
  }

  .buscar input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--bandeja-texto);
    font: inherit;
    font-size: 12.5px;
    outline: none;
  }

  .limpiar {
    border: 0;
    background: none;
    color: var(--bandeja-texto-2);
    cursor: pointer;
    display: grid;
    place-items: center;
    padding: 0;
  }

  .limpiar:hover {
    color: var(--bandeja-texto);
  }
</style>
