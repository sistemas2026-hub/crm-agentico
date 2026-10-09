<script>
  /**
   * Reportes: tres, y cada uno contesta una pregunta distinta.
   *
   * Portada de la pantalla "Reportes" de Stitch.
   *
   * EL REPORTE POR TÉCNICO NO TRAE NINGUNA MÉTRICA DE EFICIENCIA, A PROPÓSITO
   * Dos técnicos con distinto tipo de trabajo no son comparables por metros de
   * fibra, y un número que parece comparable se usa como si lo fuera. El diseño
   * respetó esa ausencia y la dejó escrita; acá también, porque es una decisión y
   * no un pendiente.
   *
   * LOS DESCUADRES SON UNA LISTA, NO UN CONTADOR
   * Un número en un tablero se mira una vez y se ignora; una lista con fecha,
   * material, persona y motivo se puede resolver.
   *
   * EL FILTRO DE FECHAS ES REAL
   * La API ya aceptaba `desde` y `hasta`; el cliente del frontend no los mandaba.
   * Ahora sí, así que el rango del diseño acota de verdad. «Exportar CSV» no
   * existe todavía y queda marcado.
   */

  /** @type {{ reporte: any, internas: any[] }} */
  let { reporte, internas } = $props();

  let cual = $derived(reporte?.de ?? 'consumo');
  let filas = $derived(reporte?.filas ?? []);

  const REPORTES = [
    { id: 'consumo', texto: 'En qué se fue', icono: 'summarize' },
    { id: 'tecnicos', texto: 'Por técnico', icono: 'engineering' },
    { id: 'descuadres', texto: 'Descuadres abiertos', icono: 'report_problem' }
  ];

  /** @param {string} id */
  function enlaceReporte(id) {
    const q = new URLSearchParams({ ver: 'reportes', de: id });
    if (reporte?.desde) q.set('desde', reporte.desde);
    if (reporte?.hasta) q.set('hasta', reporte.hasta);
    return `?${q}`;
  }

  /** @param {string|null} iso */
  function fecha(iso) {
    return iso ? iso.slice(0, 16).replace('T', ' ') : '—';
  }
</script>

<!-- ============ SUB-NAVEGACIÓN ============ -->
<div class="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-wrap items-center justify-between gap-space-md">
  <nav class="flex items-center gap-space-md">
    {#each REPORTES as r (r.id)}
      <a
        href={enlaceReporte(r.id)}
        class="h-9 px-space-md inline-flex items-center gap-space-xs rounded font-body-sm text-body-sm transition-colors {cual ===
        r.id
          ? 'bg-primary-fixed text-on-primary-fixed font-semibold'
          : 'text-secondary hover:text-on-surface hover:bg-surface-container-low'}"
      >
        <span class="material-symbols-outlined text-[18px]">{r.icono}</span>
        {r.texto}
      </a>
    {/each}
  </nav>

  <div class="flex items-center gap-space-sm">
    <span class="font-label-numeric text-body-sm text-secondary bg-surface-container px-2 py-0.5 rounded">
      {filas.length} {filas.length === 1 ? 'fila' : 'filas'}
    </span>
    <button
      type="button"
      disabled
      data-sin-dato="exportar-csv"
      class="h-9 px-space-md bg-surface-container-lowest text-outline rounded font-body-sm text-body-sm font-medium shadow-sm inline-flex items-center gap-1"
      title="Pendiente: todavía no hay exportación a CSV"
    >
      <span class="material-symbols-outlined text-[16px]">file_download</span>
      <span>Exportar CSV</span>
    </button>
  </div>
</div>

<!-- ============ FILTROS ============ -->
{#if cual !== 'descuadres'}
  <form method="GET" class="bg-surface-container-lowest p-space-md rounded-xl shadow-sm flex flex-wrap items-end gap-space-md">
    <input type="hidden" name="ver" value="reportes" />
    <input type="hidden" name="de" value={cual} />

    <div class="flex flex-col gap-space-xs">
      <label for="rep-desde" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
        Desde
      </label>
      <input
        id="rep-desde"
        name="desde"
        type="date"
        value={reporte?.desde ?? ''}
        class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
      />
    </div>

    <div class="flex flex-col gap-space-xs">
      <label for="rep-hasta" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
        Hasta
      </label>
      <input
        id="rep-hasta"
        name="hasta"
        type="date"
        value={reporte?.hasta ?? ''}
        class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
      />
    </div>

    <button
      type="submit"
      class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-body-md text-body-md font-medium shadow-sm transition-colors inline-flex items-center gap-space-xs"
    >
      <span class="material-symbols-outlined text-[18px]">filter_alt</span>
      Aplicar
    </button>
    <a
      href={enlaceReporte(cual).split('&desde')[0]}
      class="h-10 px-space-md inline-flex items-center bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-md text-body-md font-medium transition-colors"
    >
      Limpiar
    </a>

    <!-- El filtro por depósito: el reporte agrupa por material o por persona en
         toda la empresa, no por ubicación. La API no lo acepta. -->
    <div class="flex flex-col gap-space-xs ml-auto" data-sin-dato="filtro-por-deposito">
      <span class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
        Depósito
      </span>
      <div class="h-10 px-3 flex items-center bg-surface-container-low rounded font-body-md text-body-md text-secondary">
        toda la empresa
      </div>
    </div>
  </form>
{/if}

<!-- ============ EL REPORTE ============ -->
{#if filas.length === 0}
  <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg">
    <p class="font-body-md text-body-md text-secondary">
      {#if cual === 'descuadres'}
        No hay descuadres abiertos: todos los movimientos entraron como aceptados.
      {:else}
        Nada que mostrar todavía en este reporte{reporte?.desde || reporte?.hasta
          ? ' para ese rango de fechas'
          : ''}.
      {/if}
    </p>
  </div>
{:else if cual === 'consumo'}
  <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg">
      <h2 class="font-headline-sm text-headline-sm text-on-surface">En qué se fue el material</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Consumo agrupado por material. Un consumo siempre pertenece a un trabajo: es la
        única forma de saber después en qué se gastó.
      </p>
    </div>
    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-space-lg w-48">Código</th>
            <th class="py-2.5 px-space-lg">Material</th>
            <th class="py-2.5 px-space-lg text-right w-40">Consumido</th>
            <th class="py-2.5 px-space-lg w-32">Unidad</th>
          </tr>
        </thead>
        <tbody>
          {#each filas as f, i (i)}
            <tr class="hover:bg-surface-container-low/40 transition-colors">
              <td class="py-space-md px-space-lg font-label-code text-label-code text-on-surface font-semibold">
                {f.codigo}
              </td>
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">{f.nombre}</td>
              <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums font-semibold text-on-surface">
                {f.consumido}
              </td>
              <td class="py-space-md px-space-lg font-body-sm text-body-sm text-secondary">{f.unidad}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{:else if cual === 'tecnicos'}
  <section class="flex flex-col gap-space-md">
    <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg">
      <h2 class="font-headline-sm text-headline-sm text-on-surface">Consumo por técnico</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Qué gastó cada persona, agrupado por material.
      </p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-space-md">
      {#each filas as f, i (i)}
        <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-sm">
          <div class="flex items-center gap-space-sm">
            <div class="w-9 h-9 rounded-full bg-surface-container flex items-center justify-center text-primary shrink-0">
              <span class="material-symbols-outlined text-[18px]">engineering</span>
            </div>
            <h3 class="font-headline-sm text-body-md text-on-surface font-semibold">{f.nombre}</h3>
          </div>
          <ul class="flex flex-col gap-space-xs">
            {#each f.materiales as m, j (j)}
              <li class="flex items-center justify-between gap-space-sm py-1">
                <span class="font-label-code text-label-code text-secondary">{m.codigo}</span>
                <span class="font-label-numeric text-body-sm tabular-nums text-on-surface font-semibold">
                  {m.consumido}
                </span>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    </div>

    <!-- La ausencia deliberada, escrita donde se lee. -->
    <div class="bg-surface-container-low/60 p-space-lg rounded-xl flex items-start gap-space-sm">
      <span class="material-symbols-outlined text-secondary text-[20px] mt-0.5">policy</span>
      <div class="flex flex-col">
        <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
          Sin ranking ni eficiencia, a propósito
        </span>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5 leading-relaxed">
          Dos técnicos con distinto tipo de trabajo no son comparables por metros de fibra,
          y un número que parece comparable se usa como si lo fuera. Este reporte dice qué
          se gastó y en qué, no quién lo hizo mejor.
        </p>
      </div>
    </div>
  </section>
{:else}
  <section class="flex flex-col gap-space-md">
    <div class="bg-error-container/30 p-space-lg rounded-xl shadow-sm flex items-start gap-space-md">
      <span class="material-symbols-outlined text-error text-[20px] shrink-0 mt-0.5">priority_high</span>
      <div class="flex flex-col">
        <span class="font-headline-sm text-body-md text-error font-semibold">
          {filas.length} {filas.length === 1 ? 'movimiento' : 'movimientos'} sin resolver
        </span>
        <p class="font-body-sm text-body-sm text-on-surface mt-0.5">
          Un descuadre es un consumo que entró aunque no cuadrara —el material ya se usó, y
          rechazarlo habría borrado el único registro— y un conflicto es una serie que otro
          ya había consumido. Los dos necesitan que alguien los mire.
        </p>
      </div>
    </div>

    <div class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
      <div class="w-full overflow-x-auto">
        <table class="w-full text-left">
          <thead>
            <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
              <th class="py-2.5 px-space-lg w-44">Cuándo</th>
              <th class="py-2.5 px-space-lg w-28">Estado</th>
              <th class="py-2.5 px-space-lg w-40">Material</th>
              <th class="py-2.5 px-space-lg text-right w-28">Cantidad</th>
              <th class="py-2.5 px-space-lg w-48">Persona</th>
              <th class="py-2.5 px-space-lg">Motivo</th>
            </tr>
          </thead>
          <tbody>
            {#each filas as f, i (i)}
              <tr class="bg-error-container/20 hover:bg-error-container/30 transition-colors">
                <td class="py-space-md px-space-lg font-label-numeric text-body-sm text-secondary">
                  {fecha(f.en)}
                </td>
                <td class="py-space-md px-space-lg">
                  <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-error-container text-error">
                    {f.estado}
                  </span>
                </td>
                <td class="py-space-md px-space-lg font-label-code text-label-code text-on-surface font-semibold">
                  {f.material}
                </td>
                <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-on-surface">
                  {f.cantidad}
                </td>
                <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">
                  {f.persona ?? '—'}
                </td>
                <td class="py-space-md px-space-lg font-body-sm text-body-sm text-secondary">
                  {f.motivo}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="px-space-lg py-space-md bg-surface-container-low/40">
        <p class="font-body-sm text-body-sm text-secondary">
          Una lista y no un contador: un número en un tablero se mira una vez y se ignora;
          esto se puede resolver. La vía para hacerlo es un conteo físico de esa ubicación,
          que escribe el ajuste con su motivo.
        </p>
      </div>
    </div>
  </section>
{/if}
