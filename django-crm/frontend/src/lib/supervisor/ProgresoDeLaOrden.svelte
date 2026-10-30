<!--
  EL PROGRESO DE UNA ORDEN, como en la app (30/10/2026). El usuario, sobre la
  tarjeta: «debe salir este progreso para cada ticket». Asignada → En camino →
  En sitio → Completada → Cerrada: lo hecho en azul, donde está en oscuro, lo
  que falta claro. Una orden cancelada no lo dibuja.
-->
<script>
  import { PASOS, pasoDelProgreso } from './dia-publicado.js';

  /** @type {{ estado: string }} */
  let { estado } = $props();

  const k = $derived(pasoDelProgreso(estado));
</script>

{#if k >= 0}
  <ol class="pg" aria-label="Progreso de la orden">
    {#each PASOS as nombre, i (nombre)}
      <li class:pg-hecho={i < k} class:pg-actual={i === k} aria-current={i === k ? 'step' : undefined}>
        <span class="pg-barra"></span>
        <span class="pg-nombre">{nombre}</span>
      </li>
    {/each}
  </ol>
{/if}

<style>
  .pg {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 4px;
  }
  .pg li { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .pg-barra { height: 5px; border-radius: 3px; background: var(--snoc-surface-container-high); }
  .pg-nombre {
    font-size: 11px;
    line-height: 14px;
    text-align: center;
    color: var(--snoc-outline);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .pg-hecho .pg-barra { background: var(--snoc-primary); }
  .pg-hecho .pg-nombre { color: var(--snoc-on-surface-variant); }
  .pg-actual .pg-barra { background: var(--snoc-on-surface); }
  .pg-actual .pg-nombre { color: var(--snoc-on-surface); font-weight: 700; }
</style>
