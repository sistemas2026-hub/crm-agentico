<!--
  EL PROGRESO DE UNA ORDEN, como en la app (30/10/2026). El usuario, sobre la
  tarjeta: «debe salir este progreso para cada ticket». Asignada → En camino →
  En sitio → Completada → Cerrada: lo hecho en azul, donde está en oscuro, lo
  que falta claro. Una orden cancelada no lo dibuja.
-->
<script>
  import { PASOS, pasoDelProgreso } from './dia-publicado.js';

  /**
   * `compacto`: las cinco barras y UN solo rótulo, el del paso actual
   * (07/11/2026). En el cuadro de seguimiento la tarjeta mide unos 210 px y
   * ahí los cinco nombres salían «En cami… · Comple… · C»: cinco rótulos
   * truncados dicen menos que uno entero. Donde hay ancho --las tarjetas de
   * orden, que es donde el usuario pidió este progreso el 30/10-- no cambia
   * nada.
   * @type {{ estado: string, compacto?: boolean }}
   */
  let { estado, compacto = false } = $props();

  const k = $derived(pasoDelProgreso(estado));
</script>

{#if k >= 0}
  <ol class="pg" class:pg-compacto={compacto} aria-label="Progreso de la orden">
    {#each PASOS as nombre, i (nombre)}
      <li class:pg-hecho={i < k} class:pg-actual={i === k} aria-current={i === k ? 'step' : undefined}>
        <span class="pg-barra"></span>
        <!-- En compacto el rótulo se oculta por CSS y NO se quita del DOM:
             es lo que nombra cada paso para un lector de pantalla. -->
        <span class="pg-nombre">{nombre}</span>
      </li>
    {/each}
  </ol>
  {#if compacto}<p class="pg-solo">{PASOS[k]}</p>{/if}
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
  /*  COMPACTO (07/11/2026): las barras cuentan la historia y el rótulo dice
      dónde está. `clip` y no `display: none`, para que el nombre del paso
      siga llegando a un lector de pantalla. */
  .pg-compacto .pg-nombre {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .pg-solo {
    margin: 2px 0 0;
    font-size: 11px;
    line-height: 14px;
    font-weight: 700;
    color: var(--snoc-on-surface);
  }
  .pg-hecho .pg-barra { background: var(--snoc-primary); }
  .pg-hecho .pg-nombre { color: var(--snoc-on-surface-variant); }
  .pg-actual .pg-barra { background: var(--snoc-on-surface); }
  .pg-actual .pg-nombre { color: var(--snoc-on-surface); font-weight: 700; }
</style>
