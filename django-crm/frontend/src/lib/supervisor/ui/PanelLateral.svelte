<!--
  PANEL LATERAL  --  21/11/2026 (rediseño del Supervisor NOC).

  Lo que antes se abría EN LÍNEA, al fondo de la página y lejos de lo que se
  tocó —«Armar el día», «Despachar», «Editar plantilla», «Elegir barrios»—
  se abre ahora al costado, al lado de la lista, sin perder el lugar.

  Escape cierra, el foco entra al panel al abrirse y vuelve al botón que lo
  abrió al cerrarse. El velo cierra con un clic.
-->
<script>
  import { tick } from 'svelte';

  /**
   * @type {{
   *   abierto: boolean,
   *   titulo: string,
   *   antetitulo?: string,
   *   ancho?: 'normal' | 'ancho' | 'muy-ancho',
   *   alCerrar: () => void,
   *   children: import('svelte').Snippet,
   *   pie?: import('svelte').Snippet,
   *   acciones?: import('svelte').Snippet
   * }}
   */
  let { abierto, titulo, antetitulo = '', ancho = 'normal', alCerrar, children, pie, acciones } = $props();

  /** @type {HTMLElement | undefined} */
  let caja = $state();
  /** @type {Element | null} */
  let previo = null;

  $effect(() => {
    if (abierto) {
      previo = document.activeElement;
      tick().then(() => caja?.focus());
    } else if (previo instanceof HTMLElement) {
      previo.focus();
      previo = null;
    }
  });

  /** @param {KeyboardEvent} e */
  function tecla(e) {
    if (abierto && e.key === 'Escape') {
      e.stopPropagation();
      alCerrar();
    }
  }
</script>

<svelte:window onkeydown={tecla} />

{#if abierto}
  <div class="pl-velo" onclick={alCerrar} aria-hidden="true"></div>
  <div
    class="pl pl-{ancho} snoc-capa"
    role="dialog"
    aria-modal="true"
    aria-label={titulo}
    tabindex="-1"
    bind:this={caja}
  >
    <header class="pl-cabeza">
      <div class="pl-titulos">
        {#if antetitulo}<span class="pl-ante">{antetitulo}</span>{/if}
        <h2 class="pl-titulo">{titulo}</h2>
      </div>
      <div class="pl-acciones">
        {@render acciones?.()}
        <button type="button" class="pl-cerrar" onclick={alCerrar} aria-label="Cerrar (Esc)">✕</button>
      </div>
    </header>
    <div class="pl-cuerpo">
      {@render children()}
    </div>
    {#if pie}
      <footer class="pl-pie">{@render pie()}</footer>
    {/if}
  </div>
{/if}

<style>
  .pl-velo { position: fixed; inset: 0; background: rgba(20, 18, 46, 0.32); z-index: 70; }
  .pl {
    position: fixed; top: 0; right: 0; bottom: 0; z-index: 71;
    width: min(540px, 100%);
    background: var(--v2-card); color: var(--v2-ink);
    border-left: 1px solid var(--v2-line); box-shadow: var(--v2-shadow-lift);
    display: flex; flex-direction: column; outline: none;
  }
  .pl-ancho { width: min(640px, 100%); }
  .pl-muy-ancho { width: min(1120px, 100%); }
  .pl-cabeza {
    display: flex; justify-content: space-between; align-items: center; gap: 12px;
    padding: 14px 18px; border-bottom: 1px solid var(--v2-line);
  }
  .pl-titulos { display: grid; gap: 2px; min-width: 0; }
  .pl-ante { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--v2-slate); font-weight: 600; }
  .pl-titulo { margin: 0; font-size: 15px; font-weight: 700; line-height: 20px; }
  .pl-acciones { display: flex; align-items: center; gap: 6px; flex: none; }
  .pl-cerrar {
    width: 34px; height: 34px; border-radius: var(--v2-radius-control);
    border: 1px solid var(--v2-line-strong); background: var(--v2-card); color: var(--v2-ink);
    cursor: pointer; font: inherit;
  }
  .pl-cerrar:hover { background: var(--v2-ember-soft); }
  .pl-cerrar:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: 2px; }
  .pl-cuerpo { flex: 1; overflow-y: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 16px; }
  .pl-pie { padding: 12px 18px; border-top: 1px solid var(--v2-line); background: var(--v2-paper); display: flex; flex-direction: column; gap: 10px; }
</style>
