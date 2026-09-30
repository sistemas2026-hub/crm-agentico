<script>
  /**
   * Despachar: la bodega le entrega material a un técnico.
   *
   * Portada de la pantalla "Despachar" de Stitch, que es la más rica de las diez.
   *
   * ES EL ÚNICO ACTO DEL CICLO QUE SE PUEDE NEGAR
   * Un consumo ya ocurrió en la calle; un despacho todavía no — el material está
   * sobre el mostrador. Por eso acá sí hay validación que impide, y por eso el
   * banner de conflicto es el elemento central del diseño: cuando una serie
   * figura en otra custodia, el mensaje del servidor dice DÓNDE está y el camino
   * para resolverlo es registrar su devolución.
   *
   * EL EDITOR DE VARIAS LÍNEAS ES REAL, NO UNA MAQUETA
   * El diseño pide cargar varios materiales en un acta, y el servicio del backend
   * ya lo aceptaba: lo que faltaba era que la pantalla los mandara. La columna
   * «disponible en origen» también sale de datos de verdad — la existencia de esa
   * bodega, que el load ya trae— así que avisa antes de que el técnico viaje.
   *
   * LO QUE EL DISEÑO PIDE Y NO EXISTE
   * El legajo y el vehículo del técnico, el último arqueo, «imprimir remito» y
   * «omitir serie en conflicto». Los tres primeros quedan con `—`; el cuarto no
   * se pone: sería un botón que promete saltear la única validación que protege de
   * entregar dos veces el mismo aparato.
   */
  import { enhance } from '$app/forms';
  import PlantillasDeKit from './PlantillasDeKit.svelte';

  /** @type {{ materiales: any[], personas: any[], internas: any[], existencias: any[], ubicaciones: any[], plantillas: any[], form: any }} */
  let { materiales, personas, internas, existencias, ubicaciones, plantillas, form } =
    $props();

  // svelte-ignore state_referenced_locally
  // Es a propósito: se quiere el valor INICIAL. Los props de esta pantalla no
  // cambian sin una recarga --vienen del load-- y lo que sigue es una elección
  // del usuario, que no debe volver al primer elemento cuando el padre repinta.
  let origen = $state(internas[0]?.id ?? '');
  // svelte-ignore state_referenced_locally
  // Es a propósito: se quiere el valor INICIAL. Los props de esta pantalla no
  // cambian sin una recarga --vienen del load-- y lo que sigue es una elección
  // del usuario, que no debe volver al primer elemento cuando el padre repinta.
  let tecnico = $state(personas[0]?.id ?? '');

  /** Las líneas del acta. `n` es solo la clave del bucle. */
  let lineas = $state([{ n: 1, material: '', cantidad: '', serie: '' }]);
  let siguiente = 2;

  function agregar() {
    lineas = [...lineas, { n: siguiente++, material: '', cantidad: '', serie: '' }];
  }

  /** @param {number} n */
  function quitar(n) {
    lineas = lineas.filter((l) => l.n !== n);
    if (lineas.length === 0) agregar();
  }

  /** @param {string} codigo */
  function materialDe(codigo) {
    return materiales.find((m) => m.codigo === codigo) ?? null;
  }

  // --- PLANTILLAS DE KIT ----------------------------------------------------
  //
  // Una plantilla es la lista que se repite todas las mañanas, y es de la
  // empresa: lo que lleva un kit en una no es lo que lleva en otra.

  let plantillaElegida = $state('');
  /** Lo que se descontó al cargar, para poder decirlo. */
  let loQueYaTenia = $state(/** @type {any[]} */ ([]));

  let activas = $derived((plantillas ?? []).filter((p) => p.activa));

  /**
   * Carga la plantilla en el editor, descontando lo que el técnico ya tiene.
   *
   * POR QUÉ SE DESCUENTA
   * La custodia no se vacía al terminar el día: si le quedaron 6 conectores y el
   * kit pide 24, entregarle 24 le deja 30 y el saldo empieza a crecer solo. Lo
   * que hace falta a la mañana es la diferencia.
   *
   * La sugerencia se puede cambiar: es una cuenta, no una orden. Un técnico que
   * arranca una zona lejos puede querer llevar el kit completo igual.
   *
   * UN SERIALIZADO NO SE DESCUENTA ASÍ. Cada aparato es uno, y «ya tiene una
   * ONT» no significa que sea la que necesita hoy: se abren tantas líneas como
   * pida el kit, con la serie vacía para leerla con el lector.
   */
  function cargarPlantilla() {
    const p = activas.find((x) => x.id === plantillaElegida);
    if (!p) return;

    /** @type {any[]} */
    const nuevas = [];
    /** @type {any[]} */
    const descontado = [];

    for (const l of p.lineas) {
      const enMano = custodia
        ? (custodia.materiales.find((/** @type {any} */ m) => m.codigo === l.material)
            ?.existencia ?? 0)
        : 0;

      if (l.es_serializado) {
        const cuantos = Math.max(1, Math.round(Number(l.cantidad)));
        for (let i = 0; i < cuantos; i += 1) {
          nuevas.push({ n: siguiente++, material: l.material, cantidad: '1', serie: '' });
        }
        continue;
      }

      const pide = Number(l.cantidad);
      const tiene = Number(enMano);
      const falta = Math.max(0, pide - tiene);
      if (tiene > 0) {
        descontado.push({ material: l.material, pide, tiene, falta });
      }
      // Una línea en cero NO se agrega: el servidor la rechazaría --«la línea 1
      // no dice cuánto se entrega»-- y el despacho entero fallaría por un
      // material que justamente no hace falta entregar. Que no esté se explica
      // arriba, en el aviso, con los tres números.
      if (falta > 0) {
        nuevas.push({
          n: siguiente++,
          material: l.material,
          cantidad: String(falta),
          serie: ''
        });
      }
    }

    lineas = nuevas.length ? nuevas : [{ n: siguiente++, material: '', cantidad: '', serie: '' }];
    loQueYaTenia = descontado;
  }

  /**
   * Cuánto hay de ese material en la bodega de origen, de verdad.
   *
   * `null` no es cero: significa que ese material nunca tuvo movimientos en esa
   * ubicación, y decirlo así evita el «0» que parece un faltante confirmado.
   * @param {string} codigo
   * @param {string} ubicacionId
   */
  function disponible(codigo, ubicacionId) {
    const bloque = existencias.find((b) => b.ubicacion.id === ubicacionId);
    if (!bloque) return null;
    return bloque.materiales.find((m) => m.codigo === codigo) ?? null;
  }

  /** La custodia de una persona, con lo que tiene encima ahora. */
  function custodiaDe(profileId) {
    const u = ubicaciones.find((x) => x.tipo === 'tecnico' && x.profile === profileId);
    if (!u) return null;
    return existencias.find((b) => b.ubicacion.id === u.id) ?? { ubicacion: u, materiales: [] };
  }

  let persona = $derived(personas.find((p) => p.id === tecnico) ?? null);
  let custodia = $derived(custodiaDe(tecnico));
  let bloqueOrigen = $derived(existencias.find((b) => b.ubicacion.id === origen) ?? null);
  let nombreOrigen = $derived(internas.find((u) => u.id === origen)?.nombre ?? '');

  /** Las iniciales para el círculo del diseño. */
  let iniciales = $derived(
    (persona?.nombre ?? '?')
      .split(/\s+/)
      .slice(0, 2)
      .map((/** @type {string} */ p) => p[0] ?? '')
      .join('')
      .toUpperCase()
  );

  /** Cuántos equipos con serie tiene encima, y cuántas bobinas. */
  let enPosesion = $derived({
    serializados: (custodia?.materiales ?? []).filter(
      (/** @type {any} */ m) => m.clase === 'serializado' && Number(m.existencia) > 0
    ),
    bobinas: (custodia?.materiales ?? []).filter(
      (/** @type {any} */ m) => m.clase === 'bobina' && Number(m.existencia) > 0
    )
  });

  /** @param {string} valor @param {string} clase */
  function cantidad(valor, clase) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return valor;
    return clase === 'bobina' ? n.toFixed(3) : String(Math.round(n * 1000) / 1000);
  }

  const ICONO_CLASE = { consumible: 'join_inner', bobina: 'cable', serializado: 'router' };
</script>

<!-- ============ CABECERA DE CONTEXTO ============ -->
<div class="flex flex-wrap items-center justify-between gap-space-md bg-surface-container-lowest p-space-md rounded-xl shadow-sm">
  <div class="flex items-center gap-space-md">
    <div class="w-10 h-10 rounded bg-primary-container/10 flex items-center justify-center text-primary-container shrink-0">
      <span class="material-symbols-outlined text-[22px]">local_shipping</span>
    </div>
    <div class="flex flex-col">
      <span class="font-headline-sm text-headline-sm text-on-surface">Despacho a técnicos y vehículos</span>
      <p class="font-body-sm text-body-sm text-secondary">
        El material sale de una bodega y entra a la custodia de una persona. Queda el acta
        que las dos firman y los movimientos de los que sale la existencia.
      </p>
    </div>
  </div>
  <!-- El último despacho no está en la API: no hay lista de despachos todavía. -->
  <div class="flex items-center gap-space-sm bg-surface-container-low px-space-md py-space-xs rounded-lg" data-sin-dato="ultimo-despacho">
    <span class="material-symbols-outlined text-[18px] text-secondary">history</span>
    <div class="flex flex-col">
      <span class="font-table-header text-table-header text-secondary uppercase">Último despacho</span>
      <span class="font-label-code text-label-code text-on-surface">—</span>
    </div>
  </div>
</div>

<!-- ============ RESULTADO ============ -->
{#if form?.hecho}
  <div class="flex items-start justify-between gap-space-md bg-primary-fixed/40 p-space-md rounded-xl shadow-sm">
    <div class="flex items-start gap-space-sm">
      <span class="material-symbols-outlined text-primary text-[20px] mt-0.5 shrink-0">check_circle</span>
      <div class="flex flex-col">
        <span class="font-headline-sm text-body-md text-on-surface font-semibold">{form.hecho}</span>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5">
          El movimiento quedó en el libro y la custodia del técnico ya lo refleja. Si el
          acta se repite, el segundo intento devuelve este mismo despacho en vez de
          descontar otra vez.
        </p>
      </div>
    </div>
    <button
      type="button"
      disabled
      data-sin-dato="imprimir-remito"
      class="h-8 px-space-md bg-surface-container-lowest text-outline font-body-sm text-body-sm rounded font-medium shadow-sm inline-flex items-center gap-1"
      title="Pendiente: todavía no hay un remito imprimible"
    >
      <span class="material-symbols-outlined text-[16px]">print</span>
      <span>Imprimir remito</span>
    </button>
  </div>
{/if}

{#if form?.error}
  <!--
    EL BANNER QUE DEFINE ESTA PANTALLA. El texto viene del servidor y viaja
    entero: nombra la serie y la custodia donde está el aparato. Debajo, el único
    camino que resuelve el caso de verdad.
  -->
  <div class="flex items-start gap-space-md bg-error-container/40 p-space-lg rounded-xl shadow-sm">
    <div class="w-10 h-10 rounded-full bg-error-container flex items-center justify-center shrink-0 text-error">
      <span class="material-symbols-outlined text-[24px]">gpp_maybe</span>
    </div>
    <div class="flex-1 flex flex-col gap-space-xs">
      <span class="font-headline-sm text-body-md text-error font-semibold tracking-tight">
        El despacho no se registró
      </span>
      <p class="font-body-md text-body-md text-on-surface leading-relaxed">{form.error}</p>
      <div class="mt-space-xs flex items-center gap-space-md">
        <a
          href="?ver=devolucion"
          class="h-8 px-space-md bg-error hover:bg-on-error-container text-on-error rounded font-body-sm text-body-sm font-medium flex items-center gap-space-xs transition-colors shadow-sm"
        >
          <span class="material-symbols-outlined text-[16px]">assignment_return</span>
          <span>Ir a registrar la devolución</span>
        </a>
      </div>
    </div>
  </div>
{/if}

<form method="POST" action="?/despacho" use:enhance class="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
  <!-- ============ COLUMNA IZQUIERDA ============ -->
  <div class="lg:col-span-8 flex flex-col gap-space-lg">
    <!-- Cabecera de la orden -->
    <section class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md">
      <div class="flex items-center justify-between pb-space-xs gap-space-sm">
        <div class="flex items-center gap-space-xs">
          <span class="material-symbols-outlined text-primary text-[20px]">tune</span>
          <h2 class="font-headline-sm text-body-md text-on-surface font-semibold">
            Cabecera del despacho
          </h2>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-space-md">
        <div class="flex flex-col gap-1.5">
          <label
            for="despacho-origen"
            class="font-table-header text-table-header text-on-surface-variant flex items-center gap-1 uppercase tracking-wider"
          >
            <span>Bodega de origen</span><span class="text-error">*</span>
          </label>
          <div class="relative">
            <select
              id="despacho-origen"
              name="ubicacion_origen"
              bind:value={origen}
              required
              class="w-full h-10 px-3 pr-8 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded focus:outline-none focus:ring-2 focus:ring-primary shadow-sm appearance-none cursor-pointer"
            >
              {#each internas as u (u.id)}
                <option value={u.id}>{u.nombre}</option>
              {/each}
            </select>
            <span class="material-symbols-outlined absolute right-2.5 top-2.5 pointer-events-none text-secondary text-[20px]">
              expand_more
            </span>
          </div>
          <span class="font-body-sm text-body-sm text-secondary">De dónde sale la carga</span>
        </div>

        <div class="flex flex-col gap-1.5">
          <label
            for="despacho-tecnico"
            class="font-table-header text-table-header text-on-surface-variant flex items-center gap-1 uppercase tracking-wider"
          >
            <span>Técnico que recibe</span><span class="text-error">*</span>
          </label>
          <div class="relative">
            <select
              id="despacho-tecnico"
              name="profile_destino"
              bind:value={tecnico}
              required
              class="w-full h-10 px-3 pr-8 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded focus:outline-none focus:ring-2 focus:ring-primary shadow-sm appearance-none cursor-pointer"
            >
              {#each personas as p (p.id)}
                <option value={p.id}>{p.nombre}</option>
              {/each}
            </select>
            <span class="material-symbols-outlined absolute right-2.5 top-2.5 pointer-events-none text-secondary text-[20px]">
              person
            </span>
          </div>
          <span class="font-body-sm text-body-sm text-secondary">Queda como responsable</span>
        </div>

        <div class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between gap-space-xs">
            <label for="despacho-acta" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              N° de acta
            </label>
            <span class="font-body-sm text-body-sm text-secondary italic">Opcional</span>
          </div>
          <div class="relative">
            <input
              id="despacho-acta"
              name="acta"
              placeholder="K-0412"
              class="w-full h-10 px-3 pr-8 bg-surface-container-lowest text-on-surface font-label-code text-body-md rounded focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
            />
            <span class="material-symbols-outlined absolute right-2.5 top-2.5 text-secondary text-[18px]">tag</span>
          </div>
          <span class="font-body-sm text-body-sm text-secondary leading-tight">
            Con acta, un doble clic o el reintento de un proxy no genera un segundo
            despacho: el mismo acta es el mismo hecho.
          </span>
        </div>
      </div>
    </section>

    <!-- Editor de líneas -->
    <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden flex flex-col">
      <div class="p-space-lg flex items-center justify-between gap-space-md flex-wrap">
        <div class="flex items-center gap-space-sm">
          <div class="w-8 h-8 rounded bg-surface-container flex items-center justify-center text-primary">
            <span class="material-symbols-outlined text-[18px]">format_list_bulleted</span>
          </div>
          <div>
            <h2 class="font-headline-sm text-body-md text-on-surface font-semibold">
              Materiales a entregar
            </h2>
            <p class="font-body-sm text-body-sm text-secondary">
              Consumibles por unidad, bobinas por metro y equipos con su número de serie.
            </p>
          </div>
        </div>
        <div class="flex items-center gap-space-md flex-wrap">
          <!--
            CARGAR UN KIT ARMADO. Las plantillas son de la empresa: lo que lleva
            un kit de instalación acá no es lo que lleva en otra.
          -->
          {#if activas.length}
            <div class="flex items-center gap-space-xs">
              <select
                bind:value={plantillaElegida}
                class="h-9 px-2.5 bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
                aria-label="Plantilla de kit"
              >
                <option value="">Cargar una plantilla…</option>
                {#each activas as p (p.id)}
                  <option value={p.id}>{p.nombre}</option>
                {/each}
              </select>
              <button
                type="button"
                onclick={cargarPlantilla}
                disabled={!plantillaElegida}
                class="h-9 px-space-md rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors inline-flex items-center gap-1 {plantillaElegida
                  ? 'bg-surface-container hover:bg-surface-container-high text-on-surface'
                  : 'bg-surface-container-low text-outline'}"
              >
                <span class="material-symbols-outlined text-[16px]">playlist_add</span>
                Cargar
              </button>
            </div>
          {/if}
          <div class="flex items-center gap-space-xs font-label-numeric text-body-sm text-secondary">
            <span class="w-2 h-2 rounded-full bg-primary-container"></span>
            <span>{lineas.length} {lineas.length === 1 ? 'línea' : 'líneas'}</span>
          </div>
        </div>
      </div>

      {#if loQueYaTenia.length}
        <!--
          Lo que la plantilla descontó, dicho. Una cantidad que aparece más chica
          que la del kit sin explicación se lee como un error de carga.
        -->
        <div class="mx-space-lg mb-space-md bg-surface-container-low rounded p-space-md flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-primary text-[18px] shrink-0">calculate</span>
          <div class="flex flex-col gap-space-xs">
            <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
              Se descontó lo que ya tiene encima
            </span>
            <ul class="flex flex-col">
              {#each loQueYaTenia as d (d.material)}
                <li class="font-body-sm text-body-sm text-secondary">
                  <span class="font-label-code text-label-code text-on-surface">{d.material}</span>
                  · el kit pide {d.pide}, tiene {d.tiene} →
                  {#if d.falta > 0}
                    se propone {d.falta}
                  {:else}
                    ya tiene suficiente, no se agregó la línea
                  {/if}
                </li>
              {/each}
            </ul>
            <span class="font-body-sm text-body-sm text-secondary">
              Es una cuenta, no una orden: cambiá el número si querés entregarle el kit
              completo igual.
            </span>
          </div>
        </div>
      {/if}

      <div class="w-full overflow-x-auto">
        <table class="w-full text-left">
          <thead>
            <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
              <th class="py-2.5 px-space-md tracking-wider">Material</th>
              <th class="py-2.5 px-space-md tracking-wider w-64">Cantidad o serie</th>
              <th class="py-2.5 px-space-md tracking-wider text-right w-56">Disponible en origen</th>
              <th class="py-2.5 px-space-md tracking-wider text-center w-20">Quitar</th>
            </tr>
          </thead>
          <tbody>
            {#each lineas as linea (linea.n)}
              {@const m = materialDe(linea.material)}
              {@const disp = linea.material ? disponible(linea.material, origen) : null}
              <tr class="hover:bg-surface-container-low/60 transition-colors">
                <td class="py-3 px-space-md">
                  <select
                    name="material"
                    bind:value={linea.material}
                    class="w-full h-9 px-2.5 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
                  >
                    <option value="">Elegí un material…</option>
                    {#each materiales as mm (mm.id)}
                      <option value={mm.codigo}>{mm.codigo} · {mm.nombre}</option>
                    {/each}
                  </select>
                  {#if m}
                    <span class="font-body-sm text-body-sm text-secondary mt-0.5 block">
                      {m.clase === 'serializado'
                        ? 'Serializado: una unidad, con su número'
                        : m.clase === 'bobina'
                          ? 'Bobina: se fracciona en metros'
                          : 'Consumible: unidades enteras'}
                    </span>
                  {/if}
                </td>

                <td class="py-3 px-space-md">
                  {#if m?.es_serializado}
                    <div class="flex flex-col gap-1">
                      <div class="relative flex items-center">
                        <input
                          name="serie"
                          required
                          placeholder="HWTCA6FB5263"
                          class="w-full h-9 pl-8 pr-2.5 font-label-code text-label-code text-on-surface bg-surface-container-lowest rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary uppercase"
                        />
                        <span class="material-symbols-outlined absolute left-2 text-secondary text-[16px]">
                          barcode_scanner
                        </span>
                      </div>
                      <span class="font-body-sm text-body-sm text-secondary italic">
                        Cantidad fija: 1 unidad
                      </span>
                      <input type="hidden" name="cantidad" value="1" />
                    </div>
                  {:else}
                    <div class="flex items-center gap-2">
                      <!--
                        `bind:value` no es decoracion: sin el, cargar una
                        plantilla escribia las cantidades en el estado y los
                        campos quedaban vacios. Se vio probando la carga, no
                        leyendo el codigo.
                      -->
                      <input
                        name="cantidad"
                        type="number"
                        step={m?.clase === 'bobina' ? '0.001' : '1'}
                        min={m?.clase === 'bobina' ? '0.001' : '1'}
                        bind:value={linea.cantidad}
                        class="w-28 h-9 px-2.5 text-right font-label-numeric text-body-md bg-surface-container-lowest text-on-surface rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                      <span class="font-body-sm text-body-sm text-secondary">{m?.unidad ?? ''}</span>
                      <input type="hidden" name="serie" value="" />
                    </div>
                  {/if}
                </td>

                <td class="py-3 px-space-md text-right">
                  <div class="flex flex-col items-end">
                    {#if !linea.material}
                      <span class="font-body-sm text-body-sm text-secondary">—</span>
                    {:else if disp === null}
                      <!-- Nunca tuvo movimientos acá: no es «cero», es «no hay registro». -->
                      <span class="font-body-sm text-body-sm text-tertiary">
                        sin movimientos en esta bodega
                      </span>
                    {:else}
                      <span class="font-label-numeric text-body-md text-on-surface font-medium tabular-nums">
                        {cantidad(disp.existencia, disp.clase)} {disp.unidad}
                      </span>
                      {#if Number(disp.existencia) > 0}
                        <span class="font-body-sm text-body-sm text-primary flex items-center gap-0.5">
                          <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                          {nombreOrigen}
                        </span>
                      {:else}
                        <span class="font-body-sm text-body-sm text-error flex items-center gap-0.5">
                          <span class="w-1.5 h-1.5 rounded-full bg-error"></span>
                          no queda en {nombreOrigen}
                        </span>
                      {/if}
                    {/if}
                  </div>
                </td>

                <td class="py-3 px-space-md text-center">
                  <button
                    type="button"
                    onclick={() => quitar(linea.n)}
                    class="w-8 h-8 inline-flex items-center justify-center rounded text-secondary hover:text-error hover:bg-error-container/30 transition-colors"
                    title="Quitar la línea"
                  >
                    <span class="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <div class="p-space-md bg-surface-container-low/40 flex flex-wrap items-center justify-between gap-space-md">
        <button
          type="button"
          onclick={agregar}
          class="h-9 px-4 bg-surface-container-lowest hover:bg-surface-container text-on-surface font-body-sm text-body-sm font-medium rounded shadow-sm transition-colors flex items-center gap-1.5"
        >
          <span class="material-symbols-outlined text-[18px] text-primary">add_circle</span>
          <span>Agregar material</span>
        </button>
        <div class="flex items-center gap-space-sm text-secondary font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[16px]">qr_code_scanner</span>
          <span>El campo de serie acepta un lector de código de barras</span>
        </div>
      </div>
    </section>

    <!-- Acción principal -->
    <div class="flex flex-wrap items-center justify-between gap-space-md p-space-md bg-surface-container-lowest rounded-xl shadow-sm">
      <div class="flex items-center gap-space-sm text-secondary">
        <span class="material-symbols-outlined text-[18px] text-primary">info</span>
        <span class="font-body-sm text-body-sm">
          Es el único acto que el sistema puede negar: el material todavía no salió.
        </span>
      </div>
      <button
        type="submit"
        class="h-10 px-space-xl bg-primary-container hover:bg-primary text-on-primary font-headline-sm text-body-md font-medium rounded-lg shadow-sm transition-all flex items-center gap-space-xs"
      >
        <span class="material-symbols-outlined text-[20px]">send_and_archive</span>
        <span>Despachar</span>
      </button>
    </div>
  </div>

  <!-- ============ COLUMNA DERECHA ============ -->
  <div class="lg:col-span-4 flex flex-col gap-space-lg">
    <!-- Perfil de custodia -->
    <div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md">
      <div class="flex items-center justify-between pb-space-xs gap-space-sm">
        <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
          Qué tiene encima ahora
        </span>
      </div>

      <div class="flex items-center gap-space-md">
        <div class="w-12 h-12 rounded-full bg-primary flex items-center justify-center text-on-primary shrink-0 shadow-sm font-headline-sm text-headline-sm">
          {iniciales}
        </div>
        <div class="flex flex-col min-w-0">
          <span class="font-headline-sm text-body-md text-on-surface font-semibold truncate">
            {persona?.nombre ?? 'Sin técnico elegido'}
          </span>
          <!-- Legajo y vehículo: el diseño los pide, el sistema no los guarda. -->
          <span class="font-label-code text-label-code text-secondary truncate" data-sin-dato="legajo-y-vehiculo">
            Legajo — · vehículo —
          </span>
        </div>
      </div>

      <div class="p-space-md bg-surface-container-low rounded-lg flex flex-col gap-space-xs">
        <div class="flex justify-between items-center gap-space-sm text-body-sm">
          <span class="text-secondary font-body-sm">Equipos con serie en su poder:</span>
          <span class="font-label-numeric text-body-sm font-semibold text-on-surface">
            {custodia ? enPosesion.serializados.length : '—'}
          </span>
        </div>
        <div class="flex justify-between items-center gap-space-sm text-body-sm">
          <span class="text-secondary font-body-sm">Bobinas asignadas:</span>
          <span class="font-label-numeric text-body-sm font-semibold text-on-surface">
            {#if !custodia}
              —
            {:else if enPosesion.bobinas.length === 0}
              0
            {:else}
              {enPosesion.bobinas.length}
              <span class="font-body-sm text-secondary font-normal">
                ({enPosesion.bobinas
                  .map((/** @type {any} */ b) => `${cantidad(b.existencia, b.clase)} ${b.unidad}`)
                  .join(' · ')})
              </span>
            {/if}
          </span>
        </div>
        <div class="flex justify-between items-center gap-space-sm text-body-sm" data-sin-dato="ultimo-arqueo">
          <span class="text-secondary font-body-sm">Último arqueo verificado:</span>
          <span class="font-label-numeric text-body-sm text-on-surface">—</span>
        </div>
      </div>

      {#if custodia && custodia.materiales.some((/** @type {any} */ m) => Number(m.existencia) < 0)}
        <div class="bg-error-container/30 p-space-sm rounded flex items-start gap-1.5">
          <span class="material-symbols-outlined text-error text-[16px] shrink-0">warning</span>
          <span class="font-body-sm text-body-sm text-on-surface leading-tight">
            Esta custodia tiene material en negativo: consumió más de lo que se le
            despachó. Conviene resolverlo antes de entregarle más.
          </span>
        </div>
      {:else if custodia === null}
        <p class="font-body-sm text-body-sm text-secondary">
          Todavía no tiene custodia abierta: se crea sola con el primer despacho.
        </p>
      {/if}
    </div>

    <!-- Existencias de la bodega de origen: real, del mismo load -->
    <div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md">
      <h3 class="font-table-header text-table-header text-secondary uppercase tracking-wider">
        Existencias en {nombreOrigen || 'la bodega'}
      </h3>
      <div class="flex flex-col gap-space-sm">
        {#if !bloqueOrigen || bloqueOrigen.materiales.length === 0}
          <p class="font-body-sm text-body-sm text-secondary">
            Esta bodega todavía no tuvo movimientos.
          </p>
        {:else}
          {#each bloqueOrigen.materiales.slice(0, 6) as m (m.material_id)}
            <div class="flex items-center justify-between gap-space-sm p-space-sm rounded bg-surface-container-low">
              <div class="flex items-center gap-space-xs min-w-0">
                <span class="material-symbols-outlined text-[18px] text-primary shrink-0">
                  {ICONO_CLASE[m.clase] ?? 'inventory_2'}
                </span>
                <span class="font-body-sm text-body-sm text-on-surface truncate">{m.nombre}</span>
              </div>
              <span
                class="font-label-numeric text-body-sm font-semibold tabular-nums shrink-0 {Number(m.existencia) < 0
                  ? 'text-error'
                  : 'text-on-surface'}"
              >
                {cantidad(m.existencia, m.clase)} {m.unidad}
              </span>
            </div>
          {/each}
          {#if bloqueOrigen.materiales.length > 6}
            <a href="?ver=existencias" class="font-body-sm text-body-sm text-primary hover:underline">
              Ver las {bloqueOrigen.materiales.length} filas en Existencias
            </a>
          {/if}
        {/if}
      </div>
    </div>

    <!-- La regla, con el texto del sistema y no el de la maqueta -->
    <div class="bg-surface-container-low/60 p-space-md rounded-xl flex items-start gap-space-sm">
      <span class="material-symbols-outlined text-secondary text-[20px] mt-0.5">policy</span>
      <div class="flex flex-col">
        <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
          Qué pasa al despachar
        </span>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5 leading-relaxed">
          El material pasa a la custodia del técnico y deja de estar en la bodega. Nada se
          borra después: corregir un despacho es registrar su devolución, que es otro
          hecho con su propia acta.
        </p>
      </div>
    </div>
  </div>
</form>

<!--
  Las plantillas van DESPUÉS del formulario y no adentro: un `<form>` dentro de
  otro no es HTML válido, y este panel tiene los suyos para guardar y dar de baja.
-->
<PlantillasDeKit {plantillas} {materiales} />
