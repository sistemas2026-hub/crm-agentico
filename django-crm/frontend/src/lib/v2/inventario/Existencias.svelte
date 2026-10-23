<script>
  /**
   * Existencias: la pestaña de entrada, y la que contesta «¿tengo con qué
   * despachar?».
   *
   * Portada de la pantalla "Existencias" del proyecto de Stitch. Un panel por
   * ubicación, y las bodegas y las custodias de los técnicos se ven igual: para
   * este módulo la mochila de una persona es una ubicación como cualquier otra.
   *
   * LOS NEGATIVOS SE MUESTRAN, Y CON ÉNFASIS
   * Una existencia negativa es exactamente lo que alguien tiene que ver. La fila
   * va en rojo con su chip, y arriba aparece un aviso que dice cuántas hay. Lo
   * que no se hace es corregirla a cero: el descuadre desaparecería de la
   * pantalla sin haberse resuelto.
   */

  /** @type {{ existencias: any[], metricas: any, enlace: (v: string) => string }} */
  let { existencias, metricas, enlace } = $props();

  /** El icono del diseño según el tipo de ubicación. */
  const ICONO = { bodega: 'home_work', vehiculo: 'directions_car', tecnico: 'person_pin' };
  const NOMBRE_TIPO = { bodega: 'Bodega', vehiculo: 'Vehículo', tecnico: 'Técnico' };

  /**
   * Un número con tres decimales se lee mal cuando el material se cuenta en
   * unidades. La API manda un solo formato a propósito y acá se decide cómo
   * mostrarlo, que es donde se sabe la unidad.
   * @param {string} valor
   * @param {string} clase
   */
  function cantidad(valor, clase) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return valor;
    return clase === 'bobina' ? n.toFixed(2) : String(Math.round(n * 1000) / 1000);
  }

  /** @param {any} m */
  function esNegativo(m) {
    return Number(m.existencia) < 0;
  }
</script>

<!-- ============ TIRA DE INDICADORES ============ -->
<div class="grid grid-cols-1 md:grid-cols-4 gap-gutter">
  <div class="bg-surface-container-lowest p-space-md rounded-xl flex items-center justify-between shadow-sm">
    <div class="flex flex-col">
      <span class="font-body-sm text-body-sm text-secondary uppercase tracking-wider font-semibold">
        Ubicaciones con movimiento
      </span>
      <span class="font-headline-md text-headline-md text-on-surface tabular-nums">
        {metricas.ubicaciones ?? '—'}
      </span>
    </div>
    <div class="w-10 h-10 rounded-lg bg-surface-container-low flex items-center justify-center text-primary">
      <span class="material-symbols-outlined text-[20px]">warehouse</span>
    </div>
  </div>

  <div class="bg-surface-container-lowest p-space-md rounded-xl flex items-center justify-between shadow-sm">
    <div class="flex flex-col">
      <span class="font-body-sm text-body-sm text-secondary uppercase tracking-wider font-semibold">
        Materiales con movimiento
      </span>
      <span class="font-headline-md text-headline-md text-on-surface tabular-nums">
        {metricas.materiales ?? '—'}
      </span>
    </div>
    <div class="w-10 h-10 rounded-lg bg-surface-container-low flex items-center justify-center text-primary">
      <span class="material-symbols-outlined text-[20px]">fact_check</span>
    </div>
  </div>

  <!--
    EQUIPOS EN TRÁNSITO: el diseño lo pide y el sistema no lo sabe todavía.
    Queda puesto con `—` en vez de un número: haría falta contar los activos
    serializados cuya posición es la custodia de un técnico, y esa consulta no
    existe en la API. Cuando exista, entra acá y nada más cambia.
  -->
  <div
    class="bg-surface-container-lowest p-space-md rounded-xl flex items-center justify-between shadow-sm"
    data-sin-dato="equipos-en-transito"
  >
    <div class="flex flex-col">
      <span class="font-body-sm text-body-sm text-secondary uppercase tracking-wider font-semibold">
        Equipos en tránsito
      </span>
      <span class="font-headline-md text-headline-md text-on-surface tabular-nums">—</span>
      <span class="font-body-sm text-body-sm text-secondary">sin dato todavía</span>
    </div>
    <div class="w-10 h-10 rounded-lg bg-surface-container-low flex items-center justify-center text-secondary">
      <span class="material-symbols-outlined text-[20px]">local_shipping</span>
    </div>
  </div>

  <div
    class="p-space-md rounded-xl flex items-center justify-between shadow-sm {metricas.negativos
      ? 'bg-error-container/40'
      : 'bg-surface-container-lowest'}"
  >
    <div class="flex flex-col">
      <span
        class="font-body-sm text-body-sm uppercase tracking-wider font-semibold {metricas.negativos
          ? 'text-error'
          : 'text-secondary'}"
      >
        Existencias en negativo
      </span>
      <span
        class="font-headline-md text-headline-md tabular-nums {metricas.negativos
          ? 'text-error'
          : 'text-on-surface'}"
      >
        {metricas.negativos ?? '—'}
        {#if metricas.negativos}
          <span class="font-body-sm text-body-sm text-error font-normal">
            {metricas.negativos === 1 ? 'alerta' : 'alertas'}
          </span>
        {/if}
      </span>
    </div>
    <div
      class="w-10 h-10 rounded-lg flex items-center justify-center {metricas.negativos
        ? 'bg-error-container text-error'
        : 'bg-surface-container-low text-secondary'}"
    >
      <span class="material-symbols-outlined text-[20px]">emergency</span>
    </div>
  </div>
</div>

<!-- ============ AVISO DE DESCUADRE ============ -->
{#if metricas.negativos}
  <div class="bg-error-container/30 px-space-lg py-space-md rounded-xl flex items-center justify-between gap-space-md shadow-sm">
    <div class="flex items-start gap-space-md">
      <span class="material-symbols-outlined text-error text-[20px] shrink-0">report_problem</span>
      <p class="font-body-sm text-body-sm text-on-surface">
        <span class="font-medium text-error">Discrepancia detectada:</span>
        {metricas.negativos === 1
          ? 'un material está'
          : `${metricas.negativos} materiales están`} por debajo de cero.
        Un negativo significa que se registró más salida que entrada, así que hay
        movimientos sin su contraparte. Se muestra en vez de corregirse: es lo que hay
        que resolver.
      </p>
    </div>
    <!-- La función real más cercana a «auditar» es el reporte de descuadres. -->
    <a
      href="?ver=reportes&de=descuadres"
      class="h-9 px-space-md bg-surface-container-lowest text-on-surface hover:bg-surface-container transition-colors rounded text-body-sm font-medium shrink-0 inline-flex items-center gap-1 shadow-sm"
    >
      <span class="material-symbols-outlined text-[16px]">search_check</span>
      Ver descuadres abiertos
    </a>
  </div>
{/if}

<!-- ============ UN PANEL POR UBICACIÓN ============ -->
{#if existencias.length === 0}
  <div class="bg-surface-container-lowest rounded-xl shadow-sm px-space-lg py-space-lg">
    <p class="font-body-md text-body-md text-secondary">
      Todavía no hay ninguna ubicación con movimientos. Empezá registrando una entrada:
      hasta que el material entre al sistema, no hay nada que despachar.
    </p>
  </div>
{/if}

<div class="flex flex-col gap-space-lg">
  {#each existencias as bloque (bloque.ubicacion.id)}
    {@const u = bloque.ubicacion}
    <div class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
      <!-- Cabecera del panel -->
      <div class="px-space-lg py-space-md flex items-center justify-between gap-space-md">
        <div class="flex items-center gap-space-md">
          <div class="flex items-center gap-space-xs">
            <span class="material-symbols-outlined text-secondary text-[20px]">
              {ICONO[u.tipo] ?? 'inventory_2'}
            </span>
            <h2 class="font-headline-sm text-headline-sm text-on-surface font-semibold tracking-tight">
              {u.nombre}
            </h2>
          </div>
          <span class="px-2 py-0.5 rounded text-body-sm font-medium bg-surface-container text-secondary">
            {NOMBRE_TIPO[u.tipo] ?? u.tipo}
          </span>
        </div>
        <div class="flex items-center gap-space-md">
          <!--
            El subtítulo sale de `notas` de la ubicación, que es un campo que ya
            existía en el modelo y no se serializaba. Vacío hasta que alguien
            escriba algo ahí; no se inventa una descripción.
          -->
          {#if u.notas}
            <span class="font-body-sm text-body-sm text-secondary">{u.notas}</span>
          {/if}
          <!--
            «Ver movimientos» de una ubicación no existe como vista todavía. Queda
            puesto y deshabilitado: un botón que parece funcionar y no hace nada es
            peor que uno que dice que falta.
          -->
          <button
            type="button"
            disabled
            data-sin-dato="ver-movimientos"
            class="text-outline p-1 rounded"
            title="Pendiente: todavía no hay una vista de movimientos por ubicación"
          >
            <span class="material-symbols-outlined text-[18px]">open_in_new</span>
          </button>
        </div>
      </div>

      <!-- Tabla -->
      {#if bloque.materiales.length === 0}
        <div class="px-space-lg pb-space-lg">
          <p class="font-body-sm text-body-sm text-secondary">Sin movimientos todavía.</p>
        </div>
      {:else}
        <div class="w-full overflow-x-auto">
          <table class="w-full text-left font-body-md text-body-md">
            <thead class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase tracking-wider">
              <tr>
                <th class="py-2.5 px-space-lg font-semibold w-48" scope="col">Código</th>
                <th class="py-2.5 px-space-lg font-semibold" scope="col">Material</th>
                <th class="py-2.5 px-space-lg font-semibold w-40" scope="col">Categoría</th>
                <th class="py-2.5 px-space-lg font-semibold text-right w-36" scope="col">Existencia</th>
                <th class="py-2.5 px-space-lg font-semibold w-28" scope="col">Unidad</th>
              </tr>
            </thead>
            <tbody>
              {#each bloque.materiales as m (m.material_id)}
                {#if esNegativo(m)}
                  <tr class="h-12 bg-error-container/30 hover:bg-error-container/40 transition-colors">
                    <td class="py-2 px-space-lg font-label-code text-label-code text-error font-bold tracking-tight">
                      <span class="inline-flex items-center gap-1.5">
                        <span class="material-symbols-outlined text-error text-[16px]">priority_high</span>
                        {m.codigo}
                      </span>
                    </td>
                    <td class="py-2 px-space-lg font-body-md">
                      <div class="flex items-center gap-space-sm flex-wrap">
                        <span class="font-medium text-error">{m.nombre}</span>
                        <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium bg-error-container text-error">
                          Existencia negativa · requiere investigación
                        </span>
                      </div>
                    </td>
                    <td class="py-2 px-space-lg font-body-sm text-secondary">{m.categoria || '—'}</td>
                    <td class="py-2 px-space-lg font-label-numeric text-label-numeric font-bold text-right tabular-nums text-error text-[1rem]">
                      {cantidad(m.existencia, m.clase)}
                    </td>
                    <td class="py-2 px-space-lg font-body-sm text-error font-medium">{m.unidad}</td>
                  </tr>
                {:else}
                  <tr class="h-11 hover:bg-surface-container-low transition-colors">
                    <td class="py-2 px-space-lg font-label-code text-label-code text-on-surface font-semibold tracking-tight">
                      {m.codigo}
                    </td>
                    <td class="py-2 px-space-lg font-body-md text-on-surface">{m.nombre}</td>
                    <td class="py-2 px-space-lg font-body-sm text-secondary">{m.categoria || '—'}</td>
                    <td class="py-2 px-space-lg font-label-numeric text-label-numeric font-semibold text-right tabular-nums text-on-surface">
                      {cantidad(m.existencia, m.clase)}
                    </td>
                    <td class="py-2 px-space-lg font-body-sm text-secondary">{m.unidad}</td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>
        </div>
      {/if}

      <!--
        Pie de la custodia de un técnico. En el diseño dice cuándo sincronizó el
        teléfono y cuántos despachos quedaron sin retorno; ninguno de los dos
        existe en la API todavía, así que el texto lo dice y no se inventa una
        hora. «Ajustar saldo» sí existe: es el conteo físico de esa ubicación.
      -->
      {#if u.tipo === 'tecnico'}
        <div class="px-space-lg py-space-sm bg-surface-container-low flex items-center justify-between gap-space-md flex-wrap">
          <span class="font-body-sm text-body-sm text-secondary" data-sin-dato="sincronizacion-telefono">
            Última sincronización del teléfono: — · despachos sin retorno registrado: —
          </span>
          <div class="flex items-center gap-space-sm">
            <button
              type="button"
              disabled
              data-sin-dato="historial-de-entregas"
              class="h-8 px-space-md bg-surface-container-lowest text-outline rounded text-body-sm font-medium shadow-sm"
              title="Pendiente: todavía no hay una vista de historial de entregas"
            >
              Historial de entregas
            </button>
            <a
              href="?ver=conteo&ubicacion={u.id}"
              class="h-8 px-space-md bg-primary text-on-primary hover:bg-primary-container rounded text-body-sm font-medium transition-colors shadow-sm inline-flex items-center gap-1"
              title="Un conteo físico de esta custodia: lo contado contra lo que dice el sistema"
            >
              <span class="material-symbols-outlined text-[16px]">tune</span>
              Ajustar saldo
            </a>
          </div>
        </div>
      {/if}
    </div>
  {/each}
</div>

<!--
  Pie de la pantalla. En el diseño trae «REFRESH_TICK: 30s» y un «DEPOT_ID», que
  son de la maqueta: esta pantalla no refresca sola y no hay un id de depósito en
  el sistema. Queda la parte que sí es verdad.
-->
<div class="flex flex-col sm:flex-row items-center justify-between text-secondary font-body-sm text-body-sm px-space-xs py-space-sm gap-space-sm">
  <div class="flex items-center gap-space-sm">
    <span class="w-2 h-2 rounded-full bg-primary inline-block"></span>
    <span>
      Cada existencia se calcula sumando el libro de movimientos: no hay ningún contador
      guardado.
    </span>
  </div>
  <span class="font-label-code text-label-code" data-sin-dato="ultima-lectura">
    Leído al abrir la pantalla
  </span>
</div>
