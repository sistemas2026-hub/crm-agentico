<script>
  /**
   * QUIEN PUEDE QUE  --  13/11/2026. Ver +page.server.js. La matriz la arma
   * $lib/agentes/presentacion.js::matriz (probada).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ArrowLeft } from '@lucide/svelte';
  import { familia, humanizar, indiceDeAutonomia, matriz, MODOS, nombreDe, vaSola } from '$lib/agentes/presentacion.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  const m = $derived(matriz(data.agentes, indiceDeAutonomia(data.autonomia)));
</script>

<PageHeader title="Quién puede qué">
  {#snippet sub()}
    Las acciones que cambian algo real y qué agente puede usar cada una.
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-sm" href="/agentes"><ArrowLeft size={14} /> Agentes</a>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad pagina">
    <div class="leyenda">
      <span><span class="celda sola">Sola</span> la hace sin preguntar</span>
      <span><span class="celda espera">Aprobación</span> una persona aprueba antes</span>
      <span><span class="vacia">·</span> no la tiene</span>
    </div>
    {#if data.errorAutonomia}<p class="v2-sub">{data.errorAutonomia} Las que piden aprobación se muestran esperando.</p>{/if}

    {#if !m.filas.length}
      <p class="v2-sub">Ningún agente puede cambiar nada: todos solo consultan.</p>
    {:else}
      <div class="marco">
        <table>
          <thead>
            <tr>
              <th scope="col" class="accion-th">Acción</th>
              {#each m.columnas as a (a.nombre)}
                <th scope="col" class="fam-{familia(a)}">
                  <a href="/agentes/{encodeURIComponent(a.nombre)}">{nombreDe(a)}</a>
                  <span class="pill">{familia(a) === 'cliente' ? 'Cliente' : 'Equipo'}</span>
                </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each m.filas as f (f.nombre)}
              <tr>
                <th scope="row">
                  <span class="nombre" title={f.resumen || undefined}>{humanizar(f.nombre)}</span>
                  <span class="clave">{f.nombre}</span>
                </th>
                {#each m.columnas as a (a.nombre)}
                  {@const modo = f.celdas[a.nombre]}
                  <td>
                    {#if modo}
                      <span class="celda {vaSola(modo) ? 'sola' : modo === 'sin_dato' ? 'neutro' : 'espera'}"
                        title={MODOS[modo].texto}>{MODOS[modo].corto}</span>
                    {:else}
                      <span class="vacia" aria-label="no la tiene">·</span>
                    {/if}
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if m.sinAcciones.length}
        <p class="v2-sub">Solo consultan, no cambian nada: {m.sinAcciones.map(nombreDe).join(', ')}.</p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .pagina { display: flex; flex-direction: column; gap: 14px; padding-top: 14px; padding-bottom: 40px; }
  .leyenda { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 12.5px; align-items: center; }
  .leyenda > span { display: inline-flex; align-items: center; gap: 6px; }
  .marco { overflow-x: auto; border: 1px solid var(--v2-line); border-radius: var(--v2-radius); background: var(--v2-card); box-shadow: var(--v2-shadow); }
  table { border-collapse: collapse; width: 100%; min-width: 760px; font-size: 13.5px; }
  thead th { padding: 12px 10px; border-bottom: 1px solid var(--v2-line); vertical-align: bottom; text-align: center; font-weight: 600; font-size: 12.5px; }
  thead th a { color: inherit; text-decoration: none; display: block; line-height: 1.25; }
  thead th a:hover { text-decoration: underline; }
  .accion-th { text-align: left; font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--v2-slate); }
  .fam-cliente { --fam: var(--v2-fam-cliente); --fam-soft: var(--v2-fam-cliente-soft); --fam-line: var(--v2-fam-cliente-line); }
  .fam-equipo { --fam: var(--v2-fam-equipo); --fam-soft: var(--v2-fam-equipo-soft); --fam-line: var(--v2-fam-equipo-line); }
  .pill { display: inline-block; margin-top: 4px; font-size: 10.5px; font-weight: 600; padding: 1px 8px; border-radius: 999px; color: var(--fam); background: var(--fam-soft); border: 1px solid var(--fam-line); }
  tbody th { text-align: left; font-weight: 400; padding: 8px 12px; display: flex; flex-direction: column; gap: 1px; }
  tbody tr { border-top: 1px solid var(--v2-line-soft); }
  tbody tr:hover { background: var(--v2-hover); }
  td { text-align: center; padding: 8px 6px; }
  .nombre { font-size: 13.5px; }
  .clave { font-family: var(--v2-mono); font-size: 11px; color: var(--v2-slate); }
  .celda { display: inline-block; min-width: 82px; font-size: 11.5px; font-weight: 600; padding: 4px 8px; border-radius: 8px; }
  /* Blanco sobre #15803d da 5:1; sobre el verde de la barra (#16a34a) no
     alcanzaria para texto de 11.5px. En oscuro, texto oscuro sobre verde. */
  .celda.sola { color: #fff; background: #15803d; }
  :global(.dark) .celda.sola { color: #052e16; background: var(--v2-sola-fuerte); }
  .celda.espera { color: #3d2400; background: var(--v2-espera-fuerte); }
  .celda.neutro { color: var(--v2-slate); background: var(--v2-line-soft); }
  .vacia { color: var(--v2-line-strong); font-size: 18px; }
</style>
