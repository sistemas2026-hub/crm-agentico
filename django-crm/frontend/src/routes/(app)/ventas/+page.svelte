<script>
  /**
   * El embudo de ventas del ISP (12/11/2026, auditoría del menú, ítem 10).
   *
   * Responde tres preguntas del dueño, en este orden: ¿cuántos llegan a cada
   * paso?, ¿cuánto tardan entre pasos?, ¿dónde se caen y quiénes están
   * detenidos hoy? Esta pantalla no cuenta ni divide nada: todo número viene
   * de Django (`leads/embudo.py`). Una etapa que no se puede medir dice
   * «sin dato» y por qué, en vez de un cero que se leería como «no hubo».
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { AlertTriangle, Filter } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  const PERIODOS = [7, 30, 90];

  /** @param {number|null} h */
  function duracion(h) {
    if (h === null || h === undefined) return 'Sin dato';
    if (h < 1) return `${Math.round(h * 60)} min`;
    if (h < 48) return `${h.toLocaleString('es-CO', { maximumFractionDigits: 1 })} h`;
    return `${(h / 24).toLocaleString('es-CO', { maximumFractionDigits: 1 })} días`;
  }

  /** @param {number} n */
  const num = (n) => n.toLocaleString('es-CO');

  /** @param {string|null} iso */
  function fecha(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('es-CO', { day: 'numeric', month: 'short' });
  }

  const titulo = $derived(
    data.periodo?.dias
      ? `Links generados en los últimos ${data.periodo.dias} días`
      : `Links generados del ${data.periodo?.desde} al ${data.periodo?.hasta}`
  );
  const vacio = $derived(!data.error && (data.etapas ?? []).find((/** @type {any} */ e) => e.clave === 'links')?.valor === 0);
</script>

<svelte:head><title>Embudo de ventas</title></svelte:head>

<PageHeader title="Embudo de ventas">
  {#snippet sub()}
    {titulo}, y hasta dónde llegó cada uno hasta hoy.
  {/snippet}
  {#snippet actions()}
    <nav class="periodos" aria-label="Periodo">
      {#each PERIODOS as d}
        <a
          class="v2-btn v2-btn-sm"
          class:v2-btn-primary={data.periodo?.dias === d}
          aria-current={data.periodo?.dias === d ? 'page' : undefined}
          href="?dias={d}">{d} días</a
        >
      {/each}
    </nav>
    <form method="GET" class="rango">
      <label>Desde <input type="date" name="desde" value={data.periodo?.desde ?? ''} required /></label>
      <label>Hasta <input type="date" name="hasta" value={data.periodo?.hasta ?? ''} required /></label>
      <button class="v2-btn v2-btn-sm" type="submit"><Filter size={14} />Ver rango</button>
    </form>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="hoja">
    {#if data.error}
      <div class="alerta" role="alert"><AlertTriangle size={16} /><span>{data.error}</span></div>
    {:else if vacio}
      <EmptyState
        title="Ningún link en este periodo"
        body="El embudo empieza cuando el asistente le genera a un prospecto su formulario de contratación. Probá un periodo más largo."
      />
    {:else}
      <section aria-labelledby="t-embudo">
        <h2 id="t-embudo" class="v2-label">Cuántos llegan a cada paso</h2>
        <ol class="embudo">
          {#each data.etapas as e (e.clave)}
            <li class:sin-dato={e.valor === null}>
              <div class="etapa">
                <span class="nombre">{e.etiqueta}</span>
                {#if e.valor === null}
                  <span class="valor v2-muted">Sin dato</span>
                {:else}
                  <span class="valor v2-num">{num(e.valor)}</span>
                {/if}
              </div>
              {#if e.valor === null}
                <p class="motivo">{e.sinDato}</p>
              {:else}
                <div class="barra" aria-hidden="true"><span style="width:{e.barra}%"></span></div>
                {#if e.pasoDesdeAnterior !== null}
                  <p class="paso">{e.pasoDesdeAnterior.toLocaleString('es-CO')} % de la etapa anterior</p>
                {/if}
              {/if}
            </li>
          {/each}
        </ol>
        {#if data.instalacionSinDato > 0}
          <p class="nota">
            {data.instalacionSinDato} aprobada{data.instalacionSinDato === 1 ? '' : 's'} sin forma de saber si
            se instaló: no tiene ticket del ISP, o el ticket todavía no llegó como caso. No se
            cuenta como instalada ni como pendiente.
          </p>
        {/if}
      </section>

      <section aria-labelledby="t-tiempos">
        <h2 id="t-tiempos" class="v2-label">Cuánto tardan entre pasos (mediana)</h2>
        <div class="v2-stats">
          {#each data.tiempos as t}
            <StatCard
              label={t.etiqueta}
              value={duracion(t.horas)}
              detail={t.muestras ? `${t.muestras} solicitud${t.muestras === 1 ? '' : 'es'}` : 'Sin casos todavía'}
            />
          {/each}
        </div>
      </section>

      {#if data.caidas}
        <section aria-labelledby="t-caidas">
          <h2 id="t-caidas" class="v2-label">Dónde se caen</h2>
          <div class="v2-stats">
            <StatCard label="Link vencido sin enviar" value={num(data.caidas.link_vencido_sin_enviar)} tone="clay" />
            <StatCard
              label="Canceladas por el cliente"
              value={num(data.caidas.canceladas.total)}
              tone="rust"
              detail={data.caidas.canceladas.sin_motivo ? `${data.caidas.canceladas.sin_motivo} sin motivo dicho` : undefined}
            />
            <StatCard label="Sin factibilidad" value={num(data.caidas.sin_factibilidad.total)} tone="slate" />
          </div>
          <div class="motivos">
            {#if data.caidas.canceladas.motivos.length}
              <div>
                <h3>Por qué cancelaron, en sus palabras</h3>
                <ul>
                  {#each data.caidas.canceladas.motivos as m (m.solicitud_id)}
                    <li><span class="v2-muted">{fecha(m.en)}</span> {m.texto}</li>
                  {/each}
                </ul>
              </div>
            {/if}
            {#if data.caidas.sin_factibilidad.notas.length}
              <div>
                <h3>Por qué no había factibilidad</h3>
                <ul>
                  {#each data.caidas.sin_factibilidad.notas as m (m.solicitud_id)}
                    <li><span class="v2-muted">{fecha(m.en)}</span> {m.texto}</li>
                  {/each}
                </ul>
              </div>
            {/if}
          </div>
        </section>
      {/if}

      <section aria-labelledby="t-detenidas">
        <h2 id="t-detenidas" class="v2-label">Detenidas hoy</h2>
        {#each data.detenidas as g (g.clave)}
          <details open={g.total > 0 && g.total <= 10}>
            <summary>
              <span>{g.etiqueta}</span>
              <span class="v2-num">{num(g.total)}</span>
            </summary>
            {#if g.filas.length === 0}
              <p class="v2-muted vacio-grupo">Ninguna.</p>
            {:else}
              <div class="v2-table-wrap">
                <table class="v2-table">
                  <thead>
                    <tr><th>Prospecto</th><th>Plan</th><th>Barrio</th><th>Detenida hace</th><th></th></tr>
                  </thead>
                  <tbody>
                    {#each g.filas as f (f.solicitud_id)}
                      <tr>
                        <td>
                          <div class="v2-table-primary">{f.nombre}</div>
                          {#if f.motivoTexto}
                            <div class="v2-table-secondary">
                              {f.motivoTexto}{f.orden_numero ? ` · orden #${f.orden_numero}` : ''}
                            </div>
                          {/if}
                        </td>
                        <td>{f.plan}</td>
                        <td>{f.barrio}</td>
                        <td class="v2-num">{duracion(f.horas)}</td>
                        <td>
                          {#if f.destino.href}
                            <a class="v2-btn v2-btn-sm" href={f.destino.href}>{f.destino.texto}</a>
                          {:else}
                            <span class="v2-muted">{f.destino.texto}</span>
                          {/if}
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
              {#if g.total > g.filas.length}
                <p class="v2-muted vacio-grupo">Se muestran las {g.filas.length} más antiguas de {num(g.total)}.</p>
              {/if}
            {/if}
          </details>
        {/each}
      </section>
    {/if}
  </div>
</div>

<style>
  .hoja {
    max-width: 1080px;
    display: grid;
    gap: 28px;
    padding-bottom: 40px;
  }
  section {
    display: grid;
    gap: 12px;
  }
  .periodos,
  .rango {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
  }
  .rango label {
    display: flex;
    gap: 4px;
    align-items: center;
    font-size: 12px;
    color: var(--v2-slate);
  }
  .rango input {
    font: inherit;
    font-size: 12px;
    padding: 3px 6px;
    border: 1px solid var(--v2-line, #ddd);
    border-radius: 6px;
  }
  .embudo {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 10px;
  }
  .etapa {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
  }
  .nombre {
    font-size: 13.5px;
  }
  .valor {
    font-size: 18px;
  }
  .barra {
    height: 8px;
    border-radius: 4px;
    background: var(--v2-line, #ececec);
    overflow: hidden;
    margin-top: 4px;
  }
  .barra span {
    display: block;
    height: 100%;
    background: var(--v2-ink);
  }
  .paso,
  .motivo,
  .nota {
    font-size: 12px;
    color: var(--v2-slate);
    margin: 3px 0 0;
  }
  .sin-dato .nombre {
    color: var(--v2-slate);
  }
  .motivos {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
  }
  .motivos h3 {
    font-size: 12.5px;
    margin: 0 0 6px;
  }
  .motivos ul {
    margin: 0;
    padding-left: 16px;
    font-size: 12.5px;
    display: grid;
    gap: 4px;
  }
  details {
    border: 1px solid var(--v2-line, #e5e5e5);
    border-radius: 8px;
    padding: 8px 12px;
  }
  summary {
    display: flex;
    justify-content: space-between;
    cursor: pointer;
    font-size: 13.5px;
  }
  .vacio-grupo {
    font-size: 12px;
    margin: 8px 0 0;
  }
  .alerta {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 10px 12px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--v2-rust) 10%, transparent);
    color: var(--v2-rust);
    font-size: 13px;
  }
</style>
