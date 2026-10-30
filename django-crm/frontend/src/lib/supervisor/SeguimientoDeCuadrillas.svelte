<!--
  EL SEGUIMIENTO DE LAS CUADRILLAS, arriba de Programación (30/10/2026). El
  usuario: «unos cuadros indicando la cuadrilla, qué tiene en progreso y qué
  tiempo lleva, y un log contraíble de los seguimientos que le ha hecho el
  Supervisor al técnico».

  Un cuadro por cuadrilla: en qué está ahora y hace cuánto, cuántas lleva de
  cuántas, y lo que pide atención (una novedad, o una orden sin reporte). Al
  pie, el log del día plegado: lo que hizo el Supervisor y lo que reportó el
  técnico, en orden de hora. Todo lo calcula el servidor
  (`campo/tiempos_del_dia.py`); acá no se resta nada.
-->
<script>
  import { textoDeNovedad } from './dia-publicado.js';

  /** @type {{ cuadrillas: any[] }} */
  let { cuadrillas = [] } = $props();

  /** @param {any} r */
  function enQueEsta(r) {
    const c = r?.en_curso;
    if (!c) return r?.hechas && r.hechas === r.total ? 'Terminó el día' : r?.salio ? 'Entre órdenes' : 'Todavía no sale';
    return `${c.estado === 'en_sitio' ? 'En sitio' : 'En camino'} · OT #${c.numero}`;
  }
</script>

{#if cuadrillas.length}
  <section class="sc" aria-label="Seguimiento de las cuadrillas">
    {#each cuadrillas as c (c.jornada)}
      {@const r = c.resumen_del_dia ?? { hechas: 0, total: 0 }}
      {@const vigentes = (c.novedades ?? []).filter((n) => n.vigente)}
      <article class="sc-cuadro" class:sc-alerta={vigentes.length || c.sin_reporte}>
        <header class="sc-cabeza">
          <strong>{c.cuadrilla}</strong>
          {#if c.labor}<span class="sc-labor">{c.labor}</span>{/if}
        </header>

        <p class="sc-ahora">{enQueEsta(r)}</p>
        {#if r.en_curso?.asunto}<p class="sc-asunto">{r.en_curso.asunto}</p>{/if}
        {#if r.en_curso?.minutos != null}
          <p class="sc-reloj" aria-label={`Lleva ${r.en_curso.minutos} minutos`}>⏱ {r.en_curso.minutos} min</p>
        {:else if r.en_curso?.desde}
          <!-- Empezó otro día y nadie la cerró: la fecha, no «21159 min». -->
          <p class="sc-viejo">⏱ Desde el {r.en_curso.desde}, sin cerrar</p>
        {/if}

        <div class="sc-avance">
          <progress max={r.total || 1} value={r.hechas}></progress>
          <span>{`${r.hechas} de ${r.total}${r.salio ? ` · salió ${r.salio}` : ''}`}</span>
        </div>

        {#each vigentes as n (n.id)}
          <p class="sc-aviso">⚠ {n.tipo_texto} · {textoDeNovedad(n)}</p>
        {/each}
        {#if c.sin_reporte}
          <p class="sc-aviso">⚠ Sin reporte hace {c.sin_reporte.minutos} min · OT #{c.sin_reporte.numero}</p>
        {/if}

        {#if c.log?.length}
          <details class="sc-log">
            <summary>Seguimiento ({c.log.length})</summary>
            <ol>
              {#each c.log as e, i (i)}
                <li class="sc-log-{e.de}"><time>{e.hora}</time> <span>{e.texto}</span></li>
              {/each}
            </ol>
          </details>
        {/if}
      </article>
    {/each}
  </section>
{/if}

<style>
  .sc {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
    gap: 10px;
  }
  .sc-cuadro {
    display: grid;
    gap: 4px;
    align-content: start;
    padding: 10px 12px;
    border-radius: var(--snoc-r-xl);
    background: var(--snoc-surface-container-lowest, #fff);
    border: 1px solid var(--snoc-outline-variant);
    font-size: 13px;
    line-height: 18px;
    color: var(--snoc-on-surface-variant);
    min-width: 0;
  }
  .sc-alerta { border-left: 3px solid var(--snoc-error); }
  .sc-cabeza { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
  .sc-cabeza strong { font-size: 14px; color: var(--snoc-on-surface); }
  .sc-labor {
    padding: 0 8px;
    border-radius: 999px;
    background: var(--snoc-surface-container);
    font-size: 12px;
    font-weight: 600;
  }
  .sc-ahora { margin: 0; font-weight: 700; color: var(--snoc-on-surface); }
  .sc-asunto { margin: 0; overflow-wrap: anywhere; }
  .sc-reloj { margin: 0; font-size: 18px; font-weight: 700; color: var(--snoc-primary); font-variant-numeric: tabular-nums; }
  .sc-viejo { margin: 0; font-weight: 600; color: var(--snoc-error); font-variant-numeric: tabular-nums; }
  .sc-avance { display: grid; gap: 2px; font-size: 12px; }
  .sc-avance progress { width: 100%; height: 6px; accent-color: var(--snoc-primary); }
  .sc-aviso { margin: 0; color: var(--snoc-error); font-weight: 600; }
  .sc-log summary { cursor: pointer; font-weight: 600; color: var(--snoc-secondary); }
  .sc-log ol { list-style: none; margin: 6px 0 0; padding: 0; display: grid; gap: 3px; }
  .sc-log li { display: grid; grid-template-columns: 40px 1fr; gap: 6px; font-size: 12px; }
  .sc-log time { font-variant-numeric: tabular-nums; color: var(--snoc-secondary); }
  .sc-log-supervisor span { color: var(--snoc-primary); }
  .sc-log-alerta span { color: var(--snoc-error); font-weight: 600; }
</style>
