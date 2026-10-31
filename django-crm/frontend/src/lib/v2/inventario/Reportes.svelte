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
    { id: 'descuadres', texto: 'Descuadres abiertos', icono: 'report_problem' },
    // Lo que escribe el técnico y la oficina no veía (18/10/2026). Los pide
    // gestión o bodega: un técnico recibe 403 y la lista sale vacía.
    { id: 'pedidos', texto: 'Pedidos a bodega', icono: 'local_shipping' },
    { id: 'faltantes', texto: 'Faltantes explicados', icono: 'help' },
    { id: 'cierres', texto: 'Cierres de jornada', icono: 'task_alt' },
    // Cada acta de entrega a un técnico (28/10/2026): «¿dónde puedo ver el
    // registro de lo entregado? Se tiene que guardar por entrega».
    { id: 'entregas', texto: 'Entregas a técnicos', icono: 'inventory_2' }
  ];

  /** @type {Record<string, string>} */
  const VACIO = {
    pedidos: 'Nadie pidió material a bodega',
    faltantes: 'Ningún técnico explicó un faltante',
    cierres: 'No hay jornadas cerradas',
    entregas: 'No se le entregó material a ningún técnico en estas fechas'
  };

  /** @type {Record<string, string>} */
  const ESTADO_PEDIDO = { pendiente: 'Pendiente', atendido: 'Atendido', rechazado: 'Rechazado' };

  /** @param {string} id */
  function enlaceReporte(id) {
    const q = new URLSearchParams({ ver: 'reportes', de: id });
    if (reporte?.desde) q.set('desde', reporte.desde);
    if (reporte?.hasta) q.set('hasta', reporte.hasta);
    return `?${q}`;
  }

  /**
   * A dónde va el formulario de un pedido: a la acción, sin perder la pestaña.
   * `?/resolverPedido` a secas borraría `ver=reportes&de=pedidos` y, al volver,
   * la pantalla abriría otra pestaña.
   */
  function accionPedido() {
    const q = new URLSearchParams({ ver: 'reportes', de: 'pedidos' });
    if (reporte?.desde) q.set('desde', reporte.desde);
    if (reporte?.hasta) q.set('hasta', reporte.hasta);
    return `?${q}&/resolverPedido`;
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
      {:else if VACIO[cual]}
        {VACIO[cual]}{reporte?.desde || reporte?.hasta ? ' en ese rango de fechas' : ''}.
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
{:else if cual === 'pedidos'}
  <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg">
      <h2 class="font-headline-sm text-headline-sm text-on-surface">Pedidos a bodega</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Lo que los técnicos pidieron desde la app, el más nuevo primero. Antes solo llegaba
        si la empresa tenía un canal de avisos configurado.
      </p>
    </div>
    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-space-lg w-44">Cuándo</th>
            <th class="py-2.5 px-space-lg w-28">Estado</th>
            <th class="py-2.5 px-space-lg">Material</th>
            <th class="py-2.5 px-space-lg text-right w-32">Cantidad</th>
            <th class="py-2.5 px-space-lg w-48">Quién</th>
            <th class="py-2.5 px-space-lg w-24">Orden</th>
            <th class="py-2.5 px-space-lg">Motivo</th>
            <th class="py-2.5 px-space-lg w-80">Bodega</th>
          </tr>
        </thead>
        <tbody>
          {#each filas as f (f.id)}
            <tr class="hover:bg-surface-container-low/40 transition-colors">
              <td class="py-space-md px-space-lg font-label-numeric text-body-sm text-secondary">{fecha(f.en)}</td>
              <td class="py-space-md px-space-lg font-body-sm text-body-sm text-on-surface">
                {ESTADO_PEDIDO[f.estado] ?? f.estado}
              </td>
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">
                {f.material_nombre}
                <span class="font-label-code text-label-code text-secondary">{f.material}</span>
              </td>
              <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-on-surface">
                {f.cantidad} {f.unidad}
              </td>
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">{f.persona ?? '—'}</td>
              <td class="py-space-md px-space-lg font-label-numeric text-body-sm text-secondary">
                {f.orden_numero ? `#${f.orden_numero}` : '—'}
              </td>
              <td class="py-space-md px-space-lg font-body-sm text-body-sm text-secondary">{f.motivo || '—'}</td>
              <td class="py-space-md px-space-lg">
                {#if f.estado === 'pendiente'}
                  <!-- Atender o rechazar. La nota es la misma caja: opcional para
                       atender, obligatoria para rechazar (lo exige el backend). -->
                  <form method="POST" action={accionPedido()} class="flex flex-col gap-space-xs">
                    <input type="hidden" name="pedido" value={f.id} />
                    <input
                      name="nota"
                      maxlength="255"
                      placeholder="Nota (obligatoria para rechazar)"
                      aria-label="Nota de bodega"
                      class="h-9 px-2 bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                    <div class="flex gap-space-xs">
                      <button type="submit" name="estado" value="atendido"
                              class="h-8 px-space-sm bg-primary-container hover:bg-primary text-on-primary rounded font-body-sm text-body-sm font-medium">
                        Atender
                      </button>
                      <button type="submit" name="estado" value="rechazado"
                              class="h-8 px-space-sm bg-surface-container hover:bg-surface-container-high text-error rounded font-body-sm text-body-sm font-medium">
                        Rechazar
                      </button>
                    </div>
                  </form>
                {:else}
                  <span class="font-body-sm text-body-sm text-secondary">
                    {ESTADO_PEDIDO[f.estado] ?? f.estado}{f.resuelto_por ? ` por ${f.resuelto_por}` : ''}{f.resuelto_en ? ` · ${fecha(f.resuelto_en)}` : ''}{f.nota_de_bodega ? ` · ${f.nota_de_bodega}` : ''}
                  </span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{:else if cual === 'faltantes'}
  <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg">
      <h2 class="font-headline-sm text-headline-sm text-on-surface">Faltantes explicados</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Lo que el técnico dijo que no tenía al cerrar la jornada, y por qué. «Faltan 3» y «se
        dañaron 3 al retirarlos» son hechos distintos: acá se lee cuál de los dos fue.
      </p>
    </div>
    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-space-lg w-44">Cuándo</th>
            <th class="py-2.5 px-space-lg w-48">Quién</th>
            <th class="py-2.5 px-space-lg">Material</th>
            <th class="py-2.5 px-space-lg text-right w-32">Cantidad</th>
            <th class="py-2.5 px-space-lg w-40">Qué pasó</th>
            <th class="py-2.5 px-space-lg">Explicación</th>
          </tr>
        </thead>
        <tbody>
          {#each filas as f (f.id)}
            <tr class="hover:bg-surface-container-low/40 transition-colors">
              <td class="py-space-md px-space-lg font-label-numeric text-body-sm text-secondary">{fecha(f.en)}</td>
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">{f.persona ?? '—'}</td>
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">
                {f.material_nombre}
                {#if f.serie}<span class="font-label-code text-label-code text-secondary">· {f.serie}</span>{/if}
              </td>
              <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-on-surface">
                {f.cantidad} {f.unidad}
              </td>
              <td class="py-space-md px-space-lg font-body-sm text-body-sm text-on-surface">{f.tipo_texto}</td>
              <td class="py-space-md px-space-lg font-body-sm text-body-sm text-secondary">
                {f.motivo || 'Sin explicación'}
                {#if f.jornada}<span class="text-outline">· jornada del {f.jornada}</span>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{:else if cual === 'entregas'}
  <!-- ENTREGAS A TÉCNICOS (28/10/2026): cada acta tal como quedó, una por
       entrega, con la serie de cada equipo y si el técnico la confirmó. -->
  <section class="flex flex-col gap-space-md">
    <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg">
      <h2 class="font-headline-sm text-headline-sm text-on-surface">Entregas a técnicos</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Cada acta de lo que salió de una bodega hacia un técnico, tal como quedó: no se
        recalcula. La más reciente primero.
      </p>
    </div>
    {#each filas as f (f.id)}
      <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-sm">
        <div class="flex flex-wrap items-baseline justify-between gap-space-sm">
          <h3 class="font-headline-sm text-body-md text-on-surface font-semibold">
            {f.tecnico ?? '—'}{f.acta ? ` · acta ${f.acta}` : ''}
          </h3>
          <span class="font-label-numeric text-body-sm text-secondary">{fecha(f.entregado_en)}</span>
        </div>
        <p class="font-body-sm text-body-sm text-secondary">
          Desde {f.bodega ?? 'una bodega que no quedó registrada'}{f.despachado_por
            ? ` · despachó ${f.despachado_por}`
            : ''} ·
          <span class={f.confirmado_en ? 'text-on-surface' : 'text-error font-semibold'}>
            {f.confirmado_en ? `el técnico la confirmó ${fecha(f.confirmado_en)}` : 'el técnico no la confirmó'}
          </span>
        </p>
        <div class="w-full overflow-x-auto">
          <table class="w-full text-left">
            <thead>
              <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
                <th class="py-2 px-space-md">Material</th>
                <th class="py-2 px-space-md text-right">Cantidad</th>
                <th class="py-2 px-space-md">Serie</th>
              </tr>
            </thead>
            <tbody>
              {#each f.lineas as l, j (j)}
                <tr>
                  <td class="py-2 px-space-md font-body-sm text-body-sm text-on-surface">{l.material}</td>
                  <td class="py-2 px-space-md text-right font-label-numeric text-body-sm tabular-nums">{l.cantidad} {l.unidad}</td>
                  <td class="py-2 px-space-md font-label-code text-label-code text-secondary">{l.serie || '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if f.notas}
          <p class="font-body-sm text-body-sm text-secondary">Notas: {f.notas}</p>
        {/if}
      </div>
    {/each}
  </section>
{:else if cual === 'cierres'}
  <section class="flex flex-col gap-space-md">
    <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg">
      <h2 class="font-headline-sm text-headline-sm text-on-surface">Cierres de jornada</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Las actas firmadas, con los números que quedaron congelados ese día. No se recalculan:
        el acta es lo que se acordó, aunque algo cambie después.
      </p>
    </div>
    {#each filas as f (f.id)}
      <div class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-sm">
        <div class="flex flex-wrap items-baseline justify-between gap-space-sm">
          <h3 class="font-headline-sm text-body-md text-on-surface font-semibold">
            {f.persona ?? '—'} · jornada del {f.jornada}
          </h3>
          <span class="font-label-numeric text-body-sm text-secondary">
            Cerrada {fecha(f.confirmada_en)}{f.recibida_por ? ` · recibió ${f.recibida_por}` : ''}
          </span>
        </div>
        {#if f.ordenes?.asignadas != null}
          <p class="font-body-sm text-body-sm text-secondary">
            Órdenes: {f.ordenes.completadas ?? 0} de {f.ordenes.asignadas} completadas
          </p>
        {/if}
        {#if (f.materiales ?? []).length}
          <div class="w-full overflow-x-auto">
            <table class="w-full text-left">
              <thead>
                <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
                  <th class="py-2 px-space-md">Material</th>
                  <th class="py-2 px-space-md text-right">Recibido</th>
                  <th class="py-2 px-space-md text-right">Consumido</th>
                  <th class="py-2 px-space-md text-right">A devolver</th>
                  <th class="py-2 px-space-md text-right">Devuelto</th>
                  <th class="py-2 px-space-md text-right">Diferencia</th>
                </tr>
              </thead>
              <tbody>
                {#each f.materiales as m, j (j)}
                  <tr>
                    <td class="py-2 px-space-md font-body-sm text-body-sm text-on-surface">{m.nombre}</td>
                    <td class="py-2 px-space-md text-right font-label-numeric text-body-sm tabular-nums">{m.entregado} {m.unidad}</td>
                    <td class="py-2 px-space-md text-right font-label-numeric text-body-sm tabular-nums">{m.consumido} {m.unidad}</td>
                    <td class="py-2 px-space-md text-right font-label-numeric text-body-sm tabular-nums">{m.esperado_devolver} {m.unidad}</td>
                    <td class="py-2 px-space-md text-right font-label-numeric text-body-sm tabular-nums">{m.devuelto} {m.unidad}</td>
                    <td class="py-2 px-space-md text-right font-label-numeric text-body-sm tabular-nums {m.diferencia && m.diferencia !== '0' ? 'text-error font-semibold' : 'text-secondary'}">
                      {m.diferencia}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
        {#if f.notas}
          <p class="font-body-sm text-body-sm text-secondary">Notas: {f.notas}</p>
        {/if}
      </div>
    {/each}
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
