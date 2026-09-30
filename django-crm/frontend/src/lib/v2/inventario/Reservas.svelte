<script>
  /**
   * Reservas: material comprometido para un trabajo que todavía no salió.
   *
   * Portada de la pantalla "Reservas" de Stitch, y la que menos huecos tiene: el
   * backend ya calcula las tres cifras, así que todo lo que el diseño muestra es
   * dato real.
   *
   * LAS TRES CIFRAS JUNTAS SON EL PUNTO
   * La pregunta que la operación hace de verdad no es «cuánto hay» sino «cuánto
   * puedo prometer para mañana». Y «quedan 70» sin saber que hay 100 con 30
   * comprometidos no se puede interpretar, así que la tabla muestra las tres y
   * destaca la última. El diseño lo dice con la fórmula arriba, y por eso se
   * conserva: es la explicación de la pantalla en tres palabras.
   *
   * LIBERAR NO BORRA
   * Una reserva liberada queda con su motivo y su desenlace. Es lo que permite
   * contestar después «por qué faltaron ONT el martes», y por eso el motivo de la
   * liberación vale la pena escribirlo.
   */
  import { enhance } from '$app/forms';

  /** @type {{ libre: any[], reservas: any[], materiales: any[], internas: any[], ubicacionElegida: string, form: any }} */
  let { libre, reservas, materiales, internas, ubicacionElegida, form } = $props();

  let material = $state('');
  let filtro = $state('todas');

  let elegido = $derived(materiales.find((m) => m.codigo === material) ?? null);
  let nombreUbicacion = $derived(
    internas.find((u) => u.id === ubicacionElegida)?.nombre ?? 'la ubicación'
  );

  let activas = $derived(reservas ?? []);
  let mostradas = $derived(
    filtro === 'vencen'
      ? activas.filter((/** @type {any} */ r) => r.vence_en)
      : filtro === 'serie'
        ? activas.filter((/** @type {any} */ r) => r.serie)
        : activas
  );

  /** @param {string} valor @param {string} clase */
  function cantidad(valor, clase) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return valor;
    return clase === 'bobina' ? n.toFixed(3) : String(Math.round(n * 1000) / 1000);
  }

  /** @param {string|null} iso */
  function fecha(iso) {
    return iso ? iso.slice(0, 16).replace('T', ' ') : null;
  }

  /** ¿Esta reserva ya pasó su plazo? Se calcula al pintar, no se guarda. */
  function vencida(iso) {
    return iso ? new Date(iso).getTime() < Date.now() : false;
  }
</script>

<!-- ============ BARRA DE UBICACIÓN Y LA FÓRMULA ============ -->
<div class="w-full bg-surface-container-lowest p-space-md rounded-lg shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-space-md">
  <div class="flex flex-wrap items-center gap-space-md">
    <div class="flex items-center gap-space-xs text-secondary">
      <span class="material-symbols-outlined text-[20px] text-primary">warehouse</span>
      <label for="res-ubicacion" class="font-table-header text-table-header uppercase tracking-wider text-on-surface-variant">
        Ubicación
      </label>
    </div>
    <!--
      Cambiar de ubicación recarga: lo comprometido y lo libre se calculan en el
      servidor para UNA ubicación. Un «reservado» global no se puede despachar
      desde ningún lado.
    -->
    <form method="GET" class="relative min-w-[280px]">
      <input type="hidden" name="ver" value="reservas" />
      <select
        id="res-ubicacion"
        name="ubicacion"
        onchange={(e) => e.currentTarget.form?.requestSubmit()}
        class="w-full h-10 pl-3 pr-9 bg-surface-container-low text-on-surface font-headline-sm text-body-md rounded appearance-none focus:outline-none focus:bg-surface-container-lowest cursor-pointer"
      >
        {#each internas as u (u.id)}
          <option value={u.id} selected={u.id === ubicacionElegida}>{u.nombre}</option>
        {/each}
      </select>
      <span class="material-symbols-outlined absolute right-2.5 top-2.5 text-[20px] pointer-events-none text-secondary">
        arrow_drop_down
      </span>
    </form>

    <div class="h-6 w-px bg-surface-container-high hidden md:block"></div>

    <div class="flex items-center gap-space-xs">
      <span class="inline-flex items-center justify-center w-2 h-2 rounded-full bg-primary"></span>
      <span class="font-body-sm text-body-sm text-secondary">Reservas activas acá:</span>
      <span class="font-label-numeric text-label-numeric text-on-surface font-semibold bg-surface-container px-2 py-0.5 rounded">
        {activas.length}
      </span>
    </div>
  </div>

  <div class="flex items-center gap-space-sm bg-surface-container-low px-space-md py-space-xs rounded font-label-code text-label-code text-secondary">
    <span class="text-on-surface font-semibold">LA CUENTA:</span>
    <span class="px-1.5 py-0.5 rounded bg-surface-container-lowest text-on-surface-variant font-medium">HAY</span>
    <span class="text-primary font-bold">−</span>
    <span class="px-1.5 py-0.5 rounded bg-surface-container-lowest text-on-surface-variant font-medium">COMPROMETIDO</span>
    <span class="text-primary font-bold">=</span>
    <span class="px-2 py-0.5 rounded bg-primary-fixed text-on-primary-fixed font-bold">LIBRE</span>
  </div>
</div>

<div class="grid grid-cols-1 xl:grid-cols-12 gap-space-lg">
  <!-- ============ LO DISPONIBLE ============ -->
  <section class="xl:col-span-7 bg-surface-container-lowest rounded-lg shadow-sm p-space-lg flex flex-col">
    <div class="flex items-start justify-between gap-space-md pb-space-sm">
      <div>
        <div class="flex items-center gap-space-xs">
          <span class="material-symbols-outlined text-primary text-[20px]">fact_check</span>
          <h2 class="font-headline-sm text-headline-sm text-on-surface">
            Material disponible para comprometer
          </h2>
        </div>
        <p class="font-body-sm text-body-sm text-secondary mt-1">
          Lo que importa para planificar no es cuánto hay, sino cuánto sigue libre después
          de descontar lo ya prometido. Sin esto, dos despachadores prometen el mismo
          equipo y el segundo técnico llega a la bodega y no está.
        </p>
      </div>
      <span class="px-2 py-1 rounded bg-secondary-container text-on-secondary-fixed text-body-sm font-label-code shrink-0">
        {nombreUbicacion}
      </span>
    </div>

    <div class="overflow-x-auto mt-space-md">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-3 rounded-l">Código</th>
            <th class="py-2.5 px-3">Material</th>
            <th class="py-2.5 px-3 text-right">Hay</th>
            <th class="py-2.5 px-3 text-right">Comprometido</th>
            <th class="py-2.5 px-3 text-right bg-surface-container">Libre</th>
            <th class="py-2.5 px-3 rounded-r text-right">Unidad</th>
          </tr>
        </thead>
        <tbody class="font-body-sm text-body-sm">
          {#if !libre || libre.length === 0}
            <tr>
              <td colspan="6" class="py-space-lg px-3 text-secondary">
                Esta ubicación todavía no tuvo movimientos, así que no hay nada que
                comprometer.
              </td>
            </tr>
          {/if}
          {#each libre ?? [] as m (m.material_id)}
            {@const enNegativo = Number(m.libre) < 0}
            <tr class="transition-colors {enNegativo ? 'bg-error-container/20' : 'hover:bg-surface-bright'}">
              <td class="py-3 px-3 font-label-code font-medium {enNegativo ? 'text-error' : 'text-on-surface'}">
                {m.codigo}
              </td>
              <td class="py-3 px-3">
                <div class="font-medium text-on-surface">{m.nombre}</div>
                {#if enNegativo}
                  <div class="text-[11px] text-error font-medium flex items-center gap-1">
                    <span class="material-symbols-outlined text-[13px]">warning</span>
                    Se prometió más de lo que hay
                  </div>
                {/if}
              </td>
              <td class="py-3 px-3 text-right font-label-numeric tabular-nums text-secondary">
                {cantidad(m.existencia, m.clase)}
              </td>
              <td class="py-3 px-3 text-right font-label-numeric tabular-nums text-secondary">
                {cantidad(m.reservado, m.clase)}
              </td>
              <td class="py-3 px-3 text-right {enNegativo ? 'bg-error-container/40' : 'bg-surface-container/60'}">
                <span
                  class="font-label-numeric tabular-nums {enNegativo
                    ? 'font-bold text-headline-sm text-error'
                    : 'font-semibold text-body-md text-on-surface'}"
                >
                  {cantidad(m.libre, m.clase)}
                </span>
              </td>
              <td class="py-3 px-3 text-right text-secondary">{m.unidad}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <!-- ============ NUEVA RESERVA ============ -->
  <section class="xl:col-span-5">
    <div class="bg-surface-container-lowest rounded-lg shadow-sm p-space-lg flex flex-col gap-space-md max-w-[480px] w-full">
      <div>
        <div class="flex items-center gap-space-xs">
          <span class="material-symbols-outlined text-primary text-[20px]">lock</span>
          <h2 class="font-headline-sm text-headline-sm text-on-surface">Nueva reserva</h2>
        </div>
        <p class="font-body-sm text-body-sm text-secondary mt-1">
          Comprometer no mueve el material: lo aparta. Sigue en la bodega hasta que se
          despache.
        </p>
      </div>

      {#if form?.error}
        <!--
          El 409 de una reserva trae los tres números: cuánto queda libre, cuánto
          hay y cuánto está comprometido. Ese mensaje es el que resuelve la duda,
          así que va entero.
        -->
        <div class="bg-error-container/40 p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-error text-[18px] shrink-0 mt-0.5">error</span>
          <p class="font-body-sm text-body-sm text-on-surface">{form.error}</p>
        </div>
      {/if}
      {#if form?.hecho}
        <div class="bg-primary-fixed/40 p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-primary text-[18px] shrink-0 mt-0.5">check_circle</span>
          <p class="font-body-sm text-body-sm text-on-surface">{form.hecho}</p>
        </div>
      {/if}

      <form method="POST" action="?/reservar" use:enhance class="flex flex-col gap-space-md">
        <input type="hidden" name="ubicacion" value={ubicacionElegida} />

        <div class="flex flex-col gap-space-xs">
          <label for="res-material" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Material a comprometer <span class="text-error">*</span>
          </label>
          <div class="relative">
            <select
              id="res-material"
              name="material"
              bind:value={material}
              required
              class="w-full h-10 px-3 pr-9 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm appearance-none focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
            >
              <option value="">Elegí un material…</option>
              {#each materiales as m (m.id)}
                <option value={m.codigo}>{m.codigo} · {m.nombre}</option>
              {/each}
            </select>
            <span class="material-symbols-outlined absolute right-2.5 top-2.5 pointer-events-none text-secondary text-[20px]">
              arrow_drop_down
            </span>
          </div>
        </div>

        {#if elegido?.es_serializado}
          <div class="flex flex-col gap-space-xs">
            <label for="res-serie" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              Número de serie <span class="text-error">*</span>
            </label>
            <div class="relative flex items-center">
              <input
                id="res-serie"
                name="serie"
                required
                placeholder="HWTCA6FB5263"
                class="w-full h-10 pl-9 pr-3 bg-surface-container-lowest text-on-surface font-label-code text-label-code uppercase rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <span class="material-symbols-outlined absolute left-2.5 text-secondary text-[18px]">
                barcode_scanner
              </span>
            </div>
            <span class="font-body-sm text-body-sm text-secondary">
              Reservar un aparato concreto. Una serie se reserva una sola vez.
            </span>
            <input type="hidden" name="cantidad" value="1" />
          </div>
        {:else}
          <div class="flex flex-col gap-space-xs">
            <label for="res-cantidad" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              Cantidad a reservar <span class="text-error">*</span>
            </label>
            <input
              id="res-cantidad"
              name="cantidad"
              type="number"
              step={elegido?.clase === 'bobina' ? '0.001' : '1'}
              min={elegido?.clase === 'bobina' ? '0.001' : '1'}
              required
              class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-label-numeric text-body-md rounded shadow-sm text-right focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        {/if}

        <div class="flex flex-col gap-space-xs">
          <label for="res-vence" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Vence <span class="text-secondary font-normal opacity-75">(opcional, pero conviene)</span>
          </label>
          <input
            id="res-vence"
            name="vence_en"
            type="datetime-local"
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <span class="font-body-sm text-body-sm text-secondary">
            Sin plazo, una orden que se cae deja el material comprometido para siempre y
            quien lo reservó ya se fue a su casa.
          </span>
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="res-motivo" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Para qué <span class="text-secondary font-normal opacity-75">(opcional)</span>
          </label>
          <input
            id="res-motivo"
            name="motivo"
            placeholder="instalaciones de mañana"
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm placeholder:text-secondary/60 focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        <button
          type="submit"
          class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-headline-sm text-body-md font-medium shadow-sm transition-colors flex items-center justify-center gap-space-xs"
        >
          <span class="material-symbols-outlined text-[18px]">lock</span>
          <span>Reservar</span>
        </button>
      </form>
    </div>
  </section>
</div>

<!-- ============ RESERVAS ACTIVAS ============ -->
<section class="bg-surface-container-lowest rounded-lg shadow-sm overflow-hidden">
  <div class="p-space-lg flex flex-wrap items-center justify-between gap-space-md">
    <div>
      <h2 class="font-headline-sm text-headline-sm text-on-surface">Reservas activas</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Liberar no borra la reserva: queda con su motivo y su desenlace. Es lo que permite
        contestar después «por qué faltaron ONT el martes».
      </p>
    </div>
    <!-- Los filtros son locales: las reservas de esta ubicación ya están en la página. -->
    <div class="flex items-center gap-space-xs">
      {#each [['todas', 'Todas'], ['vencen', 'Con plazo'], ['serie', 'Con serie']] as [clave, texto] (clave)}
        <button
          type="button"
          onclick={() => (filtro = clave)}
          class="h-8 px-space-md rounded font-body-sm text-body-sm font-medium transition-colors {filtro === clave
            ? 'bg-primary-fixed text-on-primary-fixed'
            : 'bg-surface-container-low text-secondary hover:bg-surface-container'}"
        >
          {texto}
          <span class="font-label-numeric">
            ({clave === 'todas'
              ? activas.length
              : clave === 'vencen'
                ? activas.filter((/** @type {any} */ r) => r.vence_en).length
                : activas.filter((/** @type {any} */ r) => r.serie).length})
          </span>
        </button>
      {/each}
    </div>
  </div>

  <div class="w-full overflow-x-auto">
    <table class="w-full text-left">
      <thead>
        <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
          <th class="py-2.5 px-space-lg">Material</th>
          <th class="py-2.5 px-space-lg text-right w-32">Cantidad</th>
          <th class="py-2.5 px-space-lg w-48">Serie</th>
          <th class="py-2.5 px-space-lg w-48">Vence</th>
          <th class="py-2.5 px-space-lg w-28">Estado</th>
          <th class="py-2.5 px-space-lg w-80">Liberar</th>
        </tr>
      </thead>
      <tbody>
        {#if mostradas.length === 0}
          <tr>
            <td colspan="6" class="py-space-lg px-space-lg font-body-sm text-body-sm text-secondary">
              {activas.length === 0
                ? 'No hay nada comprometido en esta ubicación: todo lo que hay está libre.'
                : 'Ninguna reserva coincide con este filtro.'}
            </td>
          </tr>
        {/if}
        {#each mostradas as r (r.id)}
          <tr class="hover:bg-surface-container-low/40 transition-colors">
            <td class="py-space-md px-space-lg">
              <span class="font-label-code text-label-code text-on-surface font-semibold">{r.material}</span>
              <span class="font-body-sm text-body-sm text-secondary block">{r.nombre}</span>
            </td>
            <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-on-surface">
              {r.cantidad}
            </td>
            <td class="py-space-md px-space-lg font-label-code text-label-code text-secondary">
              {r.serie || '—'}
            </td>
            <td class="py-space-md px-space-lg font-body-sm text-body-sm">
              {#if !r.vence_en}
                <span class="text-secondary">sin plazo</span>
              {:else if vencida(r.vence_en)}
                <span class="text-tertiary font-medium">{fecha(r.vence_en)} · pasó el plazo</span>
              {:else}
                <span class="text-on-surface">{fecha(r.vence_en)}</span>
              {/if}
            </td>
            <td class="py-space-md px-space-lg">
              <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-primary-fixed text-on-primary-fixed">
                {r.activa ? 'Activa' : r.desenlace}
              </span>
            </td>
            <td class="py-space-md px-space-lg">
              <form method="POST" action="?/liberar" use:enhance class="flex items-center gap-space-xs">
                <input type="hidden" name="reserva" value={r.id} />
                <input
                  name="motivo"
                  placeholder="por qué se libera"
                  class="h-8 px-2 w-44 bg-surface-container-low text-on-surface font-body-sm text-body-sm rounded focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="submit"
                  class="h-8 px-space-md rounded bg-surface-container-lowest hover:bg-surface-container text-on-surface font-body-sm text-body-sm font-medium shadow-sm transition-colors inline-flex items-center gap-1"
                >
                  <span class="material-symbols-outlined text-[16px]">lock_open</span>
                  Liberar
                </button>
              </form>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <!--
    Las reservas con plazo vencido no se liberan solas todavía: hace falta un
    proceso que las barra, y eso es una decisión de operación. Mientras no exista,
    la tabla las marca para que alguien las libere a mano.
  -->
  {#if activas.some((/** @type {any} */ r) => vencida(r.vence_en))}
    <div class="px-space-lg py-space-md bg-tertiary-container/20 flex items-start gap-space-sm" data-sin-dato="vencimiento-automatico">
      <span class="material-symbols-outlined text-tertiary text-[18px] shrink-0">schedule</span>
      <p class="font-body-sm text-body-sm text-on-surface">
        Hay reservas que pasaron su plazo. Todavía no se liberan solas —falta el proceso
        que las barra— así que siguen comprometiendo material hasta que alguien las libere
        acá.
      </p>
    </div>
  {/if}
</section>
