<!--
  CONFIRMAR CON RESUMEN  --  21/11/2026 (rediseño del Supervisor NOC).

  Para lo que no se deshace o le llega a mucha gente: publicar la jornada,
  avisar a N clientes de una caída, dar de baja. Antes eran un clic. El
  resumen (qué, a cuántos, qué no pasa) va en `children`.

  Escape y el velo cancelan; el foco entra al botón de cancelar, no al de
  confirmar, para que un Enter apurado no dispare la acción.
-->
<script>
  import { tick } from 'svelte';

  /**
   * @type {{
   *   abierto: boolean,
   *   titulo: string,
   *   confirmar: string,
   *   tono?: 'accion' | 'peligro',
   *   ocupado?: boolean,
   *   alConfirmar: () => void,
   *   alCancelar: () => void,
   *   children?: import('svelte').Snippet
   * }}
   */
  let { abierto, titulo, confirmar, tono = 'accion', ocupado = false, alConfirmar, alCancelar, children } = $props();

  /** @type {HTMLButtonElement | undefined} */
  let cancelar = $state();

  $effect(() => {
    if (abierto) tick().then(() => cancelar?.focus());
  });

  /** @param {KeyboardEvent} e */
  function tecla(e) {
    if (abierto && e.key === 'Escape') {
      e.stopPropagation();
      alCancelar();
    }
  }
</script>

<svelte:window onkeydown={tecla} />

{#if abierto}
  <div class="cf-velo" onclick={alCancelar} aria-hidden="true"></div>
  <div class="cf" role="alertdialog" aria-modal="true" aria-label={titulo}>
    <h2 class="cf-titulo">{titulo}</h2>
    {#if children}<div class="cf-cuerpo">{@render children()}</div>{/if}
    <div class="cf-botones">
      <button type="button" class="snoc-btn" bind:this={cancelar} onclick={alCancelar} disabled={ocupado}>Cancelar</button>
      <button
        type="button"
        class="snoc-btn {tono === 'peligro' ? 'snoc-btn-error' : 'snoc-btn-primario'}"
        onclick={alConfirmar}
        disabled={ocupado}
      >
        {confirmar}
      </button>
    </div>
  </div>
{/if}

<style>
  .cf-velo { position: fixed; inset: 0; background: rgba(20, 18, 46, 0.32); z-index: 80; }
  .cf {
    position: fixed; left: 50%; top: 50%; transform: translate(-50%, -50%); z-index: 81;
    width: min(540px, calc(100% - 32px)); max-height: calc(100% - 48px); overflow: auto;
    background: var(--v2-card); color: var(--v2-ink);
    border-radius: 16px; box-shadow: var(--v2-shadow-lift);
    padding: 20px 22px; display: flex; flex-direction: column; gap: 14px;
  }
  .cf-titulo { margin: 0; font-size: 18px; line-height: 24px; font-weight: 700; }
  .cf-cuerpo { display: flex; flex-direction: column; gap: 10px; font-size: 13.5px; }
  .cf-botones { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
</style>
