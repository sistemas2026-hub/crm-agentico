<!--
  LAS QUE ESPERAN CUADRILLA, plegadas y agrupadas por el motivo (30/10/2026).
  El usuario: «estos ticket que están a la espera colocalos que se puedan
  contraer para no hacer tan larga la pestaña». Eran 48 renglones con el mismo
  motivo repetido; ahora un grupo por motivo, con cuántas, y se abre el que
  interesa. El motivo lo calcula el servidor (`dia_publicado`), igual que antes.
-->
<script>
  import { gruposQueEsperan, textoDePrioridad } from './dia-publicado.js';

  /** @type {{ esperan: any[] }} */
  let { esperan = [] } = $props();

  const grupos = $derived(gruposQueEsperan(esperan));
</script>

{#if esperan.length}
  <details class="ec">
    <summary class="ec-titulo">
      <span class="snoc-label">Esperan cuadrilla ({esperan.length})</span>
      <span class="snoc-body-sm snoc-secundario">Órdenes sin nadie, agrupadas por el motivo.</span>
    </summary>
    <div class="ec-grupos">
      {#each grupos as g (g.motivo)}
        <details class="ec-grupo">
          <summary class="ec-fila">
            <span class="ec-cuantas">{g.ordenes.length}</span>
            <span class="ec-motivo">{g.motivo}</span>
          </summary>
          <ul class="ec-lista">
            {#each g.ordenes as o (o.id)}
              <li>
                <span class="snoc-mono">#{o.numero}</span>
                <span>{o.tipo}</span>
                <span class="ec-prio">{textoDePrioridad(o.prioridad)}</span>
                <span class="snoc-secundario">{o.barrio}</span>
              </li>
            {/each}
          </ul>
        </details>
      {/each}
    </div>
  </details>
{/if}

<style>
  .ec { border-top: 1px solid var(--snoc-outline-variant); padding-top: var(--snoc-sm); }
  .ec-titulo { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; cursor: pointer; }
  .ec-grupos { display: grid; gap: 6px; margin-top: var(--snoc-sm); }
  .ec-grupo { border: 1px solid var(--snoc-surface-container-high); border-radius: var(--snoc-r-xl); padding: 6px 10px; }
  .ec-fila { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; cursor: pointer; font-size: 13px; }
  .ec-cuantas {
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 12px;
    font-weight: 600;
    padding: 0 8px;
    border-radius: 999px;
    background: var(--snoc-surface-container);
    color: var(--snoc-on-surface-variant);
  }
  .ec-motivo { font-weight: 600; }
  .ec-lista { list-style: none; margin: 6px 0 0; padding: 0; display: grid; }
  .ec-lista li {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 4px 0;
    border-top: 1px solid var(--snoc-surface-container-low);
    font-size: 13px;
  }
  .ec-prio { color: var(--snoc-error); font-weight: 600; }
</style>
