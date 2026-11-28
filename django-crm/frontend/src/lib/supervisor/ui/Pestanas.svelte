<!--
  PESTAÑAS DENTRO DE UNA PANTALLA  --  21/11/2026 (rediseño del Supervisor NOC).

  Separan lo del día de lo que se configura una vez (Cuadrillas tenía diez
  paneles en una columna; Programación metía el contrato y la marca de agua
  entre las cuadrillas del día).

  La pestaña elegida vive en la URL (`?pestana=`): recargar o compartir el
  enlace abre la misma. Se cambia con `replaceState`, sin volver a cargar la
  página ni sumar una entrada al historial por cada clic.
-->
<script>
  import { page } from '$app/state';
  import { replaceState } from '$app/navigation';

  /**
   * @type {{
   *   pestanas: { id: string, texto: string, n?: number | string | null }[],
   *   activa: string,
   *   param?: string,
   *   etiqueta?: string
   * }}
   */
  let { pestanas, activa = $bindable(), param = 'pestana', etiqueta = 'Secciones' } = $props();

  /** @param {string} id */
  function elegir(id) {
    activa = id;
    const url = new URL(page.url);
    if (id === pestanas[0]?.id) url.searchParams.delete(param);
    else url.searchParams.set(param, id);
    replaceState(url, page.state);
  }

  /** @param {KeyboardEvent} e @param {number} i */
  function flechas(e, i) {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const sig = pestanas[(i + d + pestanas.length) % pestanas.length];
    elegir(sig.id);
    /** @type {HTMLElement | null} */ (document.getElementById(`pestana-${sig.id}`))?.focus();
  }
</script>

<div class="ps" role="tablist" aria-label={etiqueta}>
  {#each pestanas as p, i (p.id)}
    <button
      type="button"
      role="tab"
      id="pestana-{p.id}"
      class="ps-una"
      class:ps-activa={activa === p.id}
      aria-selected={activa === p.id}
      tabindex={activa === p.id ? 0 : -1}
      onclick={() => elegir(p.id)}
      onkeydown={(e) => flechas(e, i)}
    >
      {p.texto}
      {#if p.n !== undefined && p.n !== null && p.n !== ''}<span class="ps-n">{p.n}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .ps { display: flex; gap: 2px; border-bottom: 1px solid var(--v2-line); flex-wrap: wrap; }
  .ps-una {
    font: inherit; font-size: 13.5px; font-weight: 600; color: var(--v2-slate);
    background: none; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px;
    padding: 10px 14px; cursor: pointer; display: inline-flex; gap: 7px; align-items: center;
  }
  .ps-una:hover { color: var(--v2-ink); }
  .ps-una:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: -2px; border-radius: 6px; }
  .ps-activa { color: var(--v2-ember-text); border-bottom-color: var(--v2-ember); }
  .ps-n {
    min-width: 22px; height: 20px; padding: 0 7px; border-radius: 999px;
    background: var(--v2-origen); color: var(--v2-origen-ink);
    font-size: 11.5px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
  }
</style>
