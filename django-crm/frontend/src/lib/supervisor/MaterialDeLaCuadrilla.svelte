<!--
  EL MATERIAL DE UNA CUADRILLA en su tarjeta de Programación (29/10/2026).
  Pedido del usuario, mirando la tarjeta: «arriba se ve muy feo… el acta está
  de más… y los avisos, que se contraigan como el material».

  A la vista: el kit, de qué bodega y para quién, y si ya se cargó. Los avisos,
  en una línea roja que se despliega (uno solo se muestra entero). El porqué de
  cada elección del Supervisor y la lista de materiales, adentro del desplegable.
-->
<script>
  import {
    estadoDeCarga,
    lineaDeMaterial,
    porQue,
    resumenDeAvisos,
    resumenDeLineas
  } from './material-del-dia.js';

  /** @type {{ m: any }} */
  let { m } = $props();

  let cargado = $derived(estadoDeCarga(m));
</script>

<section class="mc" aria-label="Material">
  <div class="mc-cabeza">
    <span class="mc-titulo">Material</span>
    <span class="mc-estado" class:mc-cargado={cargado}>{cargado || 'Propuesta'}</span>
  </div>

  {#if m.kit}
    <p class="mc-kit">
      <strong>{m.kit}</strong>{#if m.lineas.length}<span class="mc-desde"> de {m.bodega} para {m.lider}</span>{/if}
    </p>
  {/if}

  {#if m.avisos.length === 1}
    <p class="mc-aviso">{m.avisos[0]}</p>
  {:else if m.avisos.length > 1}
    <details class="mc-avisos">
      <summary>{resumenDeAvisos(m.avisos)}</summary>
      {#each m.avisos as a (a)}<p>{a}</p>{/each}
    </details>
  {/if}

  {#if m.lineas.length}
    <details class="mc-lineas">
      <summary>{resumenDeLineas(m.lineas)}</summary>
      <p class="mc-porque">Kit: {porQue(m.kit_por)}</p>
      <p class="mc-porque">Bodega: {porQue(m.bodega_por)}</p>
      {#each m.lineas as l (l.material)}<p>{lineaDeMaterial(l)}</p>{/each}
    </details>
  {/if}
</section>

<style>
  .mc {
    display: grid;
    gap: 4px;
    padding: 8px 10px;
    border-radius: var(--snoc-r-xl);
    background: var(--snoc-surface-container-low);
    font-size: 13px;
    line-height: 18px;
    color: var(--snoc-on-surface-variant);
  }
  .mc-cabeza {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
  }
  .mc-titulo {
    font-weight: 700;
    color: var(--snoc-on-surface);
  }
  .mc-estado {
    font-size: 12px;
    color: var(--snoc-secondary);
  }
  .mc-cargado {
    color: var(--snoc-primary);
    font-weight: 600;
  }
  .mc-kit { margin: 0; overflow-wrap: anywhere; }
  .mc-kit strong { font-weight: 600; color: var(--snoc-on-surface); }
  .mc-desde { color: var(--snoc-secondary); }

  .mc-aviso,
  .mc-avisos summary { margin: 0; color: var(--snoc-error); font-weight: 600; }
  .mc-avisos p { margin: 2px 0 0 14px; color: var(--snoc-error); }

  summary { cursor: pointer; }
  .mc-lineas summary { color: var(--snoc-on-surface-variant); }
  .mc-lineas p { margin: 2px 0 0 14px; }
  .mc-porque { color: var(--snoc-secondary); }
</style>
