<script>
  /**
   * Boton "marcar como buen ejemplo" para una burbuja de respuesta del
   * agente -- base del manual de procedimientos (ver /manual). Se usa tanto
   * en el Simulador de WhatsApp como en Conversaciones reales, de ahi que
   * viva en $lib en vez de duplicarse en las dos paginas.
   *
   * Solo marca lo BUENO (decision del cliente): no hay flujo de "invalida"
   * ni de corregir en el momento, solo marcar/desmarcar.
   *
   * Dropdown propio sin libreria, mismo patron que el selector de
   * "Asignado a" en conversaciones/[id]/+page.svelte (fondo invisible +
   * lista absoluta) -- bits-ui rompio el build una vez en este proyecto,
   * ver esa pagina para el porque no se reintenta.
   *
   * @type {{
   *   conversacionId: string,
   *   mensajeId?: string | null,
   *   casoInicial?: string | null,
   *   casos: string[]
   * }}
   */
  let { conversacionId, mensajeId = null, casoInicial = null, casos } = $props();

  let casoMarcado = $state(casoInicial);
  let abierto = $state(false);
  let guardando = $state(false);

  const etiqueta = (c) => c.replaceAll('_', ' ');

  async function marcar(caso) {
    if (!mensajeId || guardando) return;
    guardando = true;
    abierto = false;
    try {
      const resp = await fetch(
        `/api/conversaciones/${conversacionId}/mensajes/${mensajeId}/marcar`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ caso })
        }
      );
      if (resp.ok) casoMarcado = caso;
    } finally {
      guardando = false;
    }
  }

  async function desmarcar() {
    if (!mensajeId || guardando) return;
    guardando = true;
    abierto = false;
    try {
      const resp = await fetch(
        `/api/conversaciones/${conversacionId}/mensajes/${mensajeId}/marcar`,
        { method: 'DELETE' }
      );
      if (resp.ok) casoMarcado = null;
    } finally {
      guardando = false;
    }
  }
</script>

<div class="marcar-ejemplo">
  <button
    type="button"
    class="marcar-trigger"
    class:marcado={!!casoMarcado}
    disabled={guardando || !mensajeId}
    title={casoMarcado ? `Buen ejemplo de: ${etiqueta(casoMarcado)}` : 'Marcar como buen ejemplo'}
    onclick={() => (abierto = !abierto)}
  >
    {#if casoMarcado}★ {etiqueta(casoMarcado)}{:else}☆ Marcar{/if}
  </button>

  {#if abierto}
    <button type="button" class="marcar-fondo" aria-label="Cerrar" onclick={() => (abierto = false)}
    ></button>
    <ul class="marcar-lista">
      {#if casoMarcado}
        <li>
          <button type="button" class="marcar-item marcar-quitar" onclick={desmarcar}>
            Quitar marca
          </button>
        </li>
      {/if}
      {#each casos as c (c)}
        <li>
          <button
            type="button"
            class="marcar-item"
            class:activo={c === casoMarcado}
            onclick={() => marcar(c)}
          >
            {etiqueta(c)}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .marcar-ejemplo {
    position: relative;
    display: inline-block;
    margin-top: 6px;
  }
  .marcar-trigger {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid var(--v2-border, #e5e5e5);
    background: transparent;
    cursor: pointer;
    color: inherit;
    opacity: 0.65;
  }
  .marcar-trigger:hover {
    opacity: 1;
  }
  .marcar-trigger:disabled {
    cursor: default;
    opacity: 0.35;
  }
  .marcar-trigger.marcado {
    opacity: 1;
    border-color: var(--v2-moss, #15803d);
    color: var(--v2-moss, #15803d);
    background: rgba(21, 128, 61, 0.08);
  }
  .marcar-fondo {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: transparent;
    border: none;
    cursor: default;
    padding: 0;
  }
  .marcar-lista {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--v2-surface, #fff);
    border: 1px solid var(--v2-border, #e5e5e5);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 6px;
    min-width: 180px;
    max-height: 260px;
    overflow-y: auto;
    z-index: 50;
    list-style: none;
    margin: 0;
  }
  .marcar-item {
    display: block;
    width: 100%;
    padding: 6px 10px;
    border-radius: 7px;
    font-size: 12.5px;
    cursor: pointer;
    background: none;
    border: none;
    text-align: left;
    color: inherit;
    font-family: inherit;
    text-transform: capitalize;
  }
  .marcar-item:hover,
  .marcar-item:focus-visible {
    background: var(--v2-surface-2, #f1f1f1);
    outline: none;
  }
  .marcar-item.activo {
    font-weight: 600;
  }
  .marcar-quitar {
    color: var(--v2-rust, #b91c1c);
    border-bottom: 1px solid var(--v2-border, #e5e5e5);
    margin-bottom: 4px;
    padding-bottom: 8px;
    text-transform: none;
  }
</style>
