<script>
  /**
   * Compras y valor: la única vía por la que entra un costo al sistema.
   *
   * Portada de la pantalla "Compras y valor" de Stitch: a la izquierda registrar
   * una compra y dar de alta un proveedor, a la derecha cuánto vale lo que hay.
   *
   * LO QUE NO SE PUEDE VALORIZAR SE NOMBRA
   * Un material sin costo conocido NO se cuenta como cero —cero diría que es
   * gratis, que es distinto de no saberlo—. Queda listado aparte con su cantidad y
   * el total avisa que no lo incluye. Un total que se come en silencio lo que no
   * sabe valorizar es la forma más rápida de que alguien decida con un número que
   * parece completo.
   *
   * EL COSTO ES UN PROMEDIO PONDERADO, Y SE DICE
   * Promedio, FIFO y LIFO dan números distintos sobre los mismos datos. Elegir uno
   * sin declararlo es la manera más fácil de que dos informes no cuadren y nadie
   * sepa por qué.
   *
   * LO QUE EL DISEÑO PIDE Y NO EXISTE
   * El gráfico de proporción del valor por material: se puede dibujar con lo que
   * ya hay, así que se dibuja —es una barra por material sobre el total— y no se
   * marca como pendiente.
   */
  import { enhance } from '$app/forms';

  /** @type {{ proveedores: any[], valorizacion: any, materiales: any[], internas: any[], ubicacionElegida: string, form: any }} */
  let { proveedores, valorizacion, materiales, internas, ubicacionElegida, form } = $props();

  let lineas = $state([{ n: 1, material: '', cantidad: '', serie: '', costo: '' }]);
  let siguiente = 2;

  function agregar() {
    lineas = [...lineas, { n: siguiente++, material: '', cantidad: '', serie: '', costo: '' }];
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

  /** @param {any} linea */
  function subtotal(linea) {
    const c = Number(linea.cantidad);
    const p = Number(linea.costo);
    if (!Number.isFinite(c) || !Number.isFinite(p) || !linea.cantidad || !linea.costo) return null;
    return c * p;
  }

  let total = $derived(
    lineas.reduce((acc, l) => {
      const s = subtotal(l);
      return s === null ? acc : acc + s;
    }, 0)
  );

  /** @param {number} n */
  function pesos(n) {
    return n.toLocaleString('es-CO', { maximumFractionDigits: 2 });
  }

  /**
   * El total que manda el backend, legible.
   *
   * Viene como string con dos decimales y sin separadores --"1752000.00"--
   * porque ahí se cuida la precisión, no la lectura. Un número de siete cifras
   * sin puntos se lee mal justo donde alguien decide una compra, así que el
   * formato se pone acá, que es donde se sabe el idioma. Si no es un número, se
   * muestra tal cual en vez de inventar: puede ser un aviso.
   * @param {string} valor
   */
  function totalLegible(valor) {
    const n = Number(valor);
    return Number.isFinite(n) ? pesos(n) : valor;
  }

  let nombreUbicacion = $derived(
    internas.find((u) => u.id === ubicacionElegida)?.nombre ?? 'la bodega'
  );

  /** La proporción de cada material sobre el total valorizado. */
  let proporciones = $derived.by(() => {
    const filas = valorizacion?.materiales ?? [];
    const suma = filas.reduce((/** @type {number} */ a, /** @type {any} */ f) => a + Number(f.valor || 0), 0);
    if (!suma) return [];
    return filas
      .map((/** @type {any} */ f) => ({
        codigo: f.codigo,
        nombre: f.nombre,
        valor: Number(f.valor || 0),
        parte: (Number(f.valor || 0) / suma) * 100
      }))
      .sort((/** @type {any} */ a, /** @type {any} */ b) => b.valor - a.valor);
  });
</script>

<div class="grid grid-cols-1 xl:grid-cols-12 gap-space-lg items-start">
  <!-- ============ IZQUIERDA: COMPRA Y PROVEEDOR ============ -->
  <div class="xl:col-span-7 flex flex-col gap-space-lg">
    <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
      <div class="p-space-lg">
        <div class="flex items-center gap-space-xs">
          <span class="material-symbols-outlined text-primary text-[20px]">receipt_long</span>
          <h2 class="font-headline-sm text-headline-sm text-on-surface">Registrar compra</h2>
        </div>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5">
          Crea la compra y una entrada por línea, con su costo. La existencia sigue saliendo
          de la misma resta: una compra es una entrada del libro común, no otra clase de
          movimiento.
        </p>
      </div>

      {#if form?.error}
        <div class="mx-space-lg mb-space-md bg-error-container/40 p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-error text-[18px] shrink-0 mt-0.5">error</span>
          <p class="font-body-sm text-body-sm text-on-surface">{form.error}</p>
        </div>
      {/if}
      {#if form?.hecho}
        <div class="mx-space-lg mb-space-md bg-primary-fixed/40 p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-primary text-[18px] shrink-0 mt-0.5">check_circle</span>
          <p class="font-body-sm text-body-sm text-on-surface">{form.hecho}</p>
        </div>
      {/if}

      <form method="POST" action="?/compra" use:enhance>
        <!-- Cabecera de la operación -->
        <div class="px-space-lg pb-space-lg grid grid-cols-1 md:grid-cols-4 gap-space-md">
          <div class="flex flex-col gap-space-xs">
            <label for="co-destino" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              Bodega de destino <span class="text-error">*</span>
            </label>
            <select
              id="co-destino"
              name="ubicacion_destino"
              required
              class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
            >
              {#each internas as u (u.id)}
                <option value={u.id} selected={u.id === ubicacionElegida}>{u.nombre}</option>
              {/each}
            </select>
          </div>

          <div class="flex flex-col gap-space-xs">
            <label for="co-proveedor" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              Proveedor <span class="text-secondary font-normal opacity-75">(opcional)</span>
            </label>
            <select
              id="co-proveedor"
              name="proveedor"
              class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
            >
              <option value="">Sin proveedor</option>
              {#each proveedores ?? [] as p (p.id)}
                <option value={p.id}>{p.nombre}</option>
              {/each}
            </select>
          </div>

          <div class="flex flex-col gap-space-xs">
            <label for="co-referencia" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              Referencia de factura
            </label>
            <input
              id="co-referencia"
              name="referencia"
              placeholder="FAC-8891"
              class="h-10 px-3 bg-surface-container-lowest text-on-surface font-label-code text-label-code uppercase rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div class="flex flex-col gap-space-xs">
            <label for="co-moneda" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
              Moneda
            </label>
            <select
              id="co-moneda"
              name="moneda"
              class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
            >
              <option value="COP">COP</option>
              <option value="USD">USD</option>
            </select>
          </div>
        </div>

        <div class="px-space-lg pb-space-sm">
          <p class="font-body-sm text-body-sm text-secondary">
            La referencia de la factura es lo que hace idempotente la compra: la misma
            factura del mismo proveedor, dos veces, no duplica el material.
          </p>
        </div>

        <!-- Líneas de compra -->
        <div class="w-full overflow-x-auto">
          <table class="w-full text-left">
            <thead>
              <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
                <th class="py-2.5 px-space-md">Material</th>
                <th class="py-2.5 px-space-md w-44">Cantidad o serie</th>
                <th class="py-2.5 px-space-md text-right w-40">Costo unitario</th>
                <th class="py-2.5 px-space-md text-right w-40">Subtotal</th>
                <th class="py-2.5 px-space-md text-center w-16">Quitar</th>
              </tr>
            </thead>
            <tbody>
              {#each lineas as linea (linea.n)}
                {@const m = materialDe(linea.material)}
                {@const sub = subtotal(linea)}
                <tr class="hover:bg-surface-container-low/40 transition-colors">
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
                  </td>

                  <td class="py-3 px-space-md">
                    {#if m?.es_serializado}
                      <input
                        name="serie"
                        required
                        placeholder="HWTCA6FB5263"
                        class="w-full h-9 px-2.5 font-label-code text-label-code text-on-surface bg-surface-container-lowest rounded shadow-sm uppercase focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                      <input type="hidden" name="cantidad" value="1" />
                    {:else}
                      <div class="flex items-center gap-1.5">
                        <input
                          name="cantidad"
                          type="number"
                          step={m?.clase === 'bobina' ? '0.001' : '1'}
                          min={m?.clase === 'bobina' ? '0.001' : '1'}
                          bind:value={linea.cantidad}
                          class="w-24 h-9 px-2.5 text-right font-label-numeric text-body-md bg-surface-container-lowest text-on-surface rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                        />
                        <span class="font-body-sm text-body-sm text-secondary">{m?.unidad ?? ''}</span>
                        <input type="hidden" name="serie" value="" />
                      </div>
                    {/if}
                  </td>

                  <td class="py-3 px-space-md text-right">
                    <input
                      name="costo_unitario"
                      type="number"
                      step="0.01"
                      min="0"
                      bind:value={linea.costo}
                      placeholder="—"
                      class="w-32 h-9 px-2.5 text-right font-label-numeric text-body-md bg-surface-container-lowest text-on-surface rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                  </td>

                  <td class="py-3 px-space-md text-right font-label-numeric text-body-md tabular-nums text-on-surface">
                    {sub === null ? '—' : pesos(sub)}
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
            <tfoot>
              <tr class="bg-surface-container-low">
                <td colspan="3" class="py-space-md px-space-md text-right font-table-header text-table-header text-secondary uppercase">
                  Total de la compra
                </td>
                <td class="py-space-md px-space-md text-right font-headline-sm text-body-md tabular-nums text-on-surface font-semibold">
                  {total ? pesos(total) : '—'}
                </td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div class="p-space-lg bg-surface-container-low/40 flex flex-wrap items-center justify-between gap-space-md">
          <button
            type="button"
            onclick={agregar}
            class="h-9 px-4 bg-surface-container-lowest hover:bg-surface-container text-on-surface font-body-sm text-body-sm font-medium rounded shadow-sm transition-colors flex items-center gap-1.5"
          >
            <span class="material-symbols-outlined text-[18px] text-primary">add</span>
            <span>Agregar material</span>
          </button>
          <button
            type="submit"
            class="h-10 px-space-xl bg-primary-container hover:bg-primary text-on-primary font-headline-sm text-body-md font-medium rounded-lg shadow-sm transition-colors flex items-center gap-space-xs"
          >
            <span class="material-symbols-outlined text-[20px]">save</span>
            <span>Registrar compra</span>
          </button>
        </div>
      </form>
    </section>

    <!-- Proveedor nuevo -->
    <section class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-md">
      <div class="flex items-center gap-space-xs">
        <span class="material-symbols-outlined text-primary text-[20px]">domain_add</span>
        <h3 class="font-headline-sm text-headline-sm text-on-surface">Crear proveedor</h3>
      </div>
      <form method="POST" action="?/proveedor" use:enhance class="grid grid-cols-1 md:grid-cols-4 gap-space-md items-end">
        <div class="flex flex-col gap-space-xs">
          <label for="pr-nombre" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Nombre <span class="text-error">*</span>
          </label>
          <input
            id="pr-nombre"
            name="nombre"
            required
            placeholder="Fibras del Norte"
            class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div class="flex flex-col gap-space-xs">
          <label for="pr-nit" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Identificación (NIT)
          </label>
          <input
            id="pr-nit"
            name="identificacion"
            placeholder="900123456-7"
            class="h-10 px-3 bg-surface-container-lowest text-on-surface font-label-code text-label-code rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div class="flex flex-col gap-space-xs">
          <label for="pr-contacto" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Contacto
          </label>
          <input
            id="pr-contacto"
            name="contacto"
            class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <button
          type="submit"
          class="h-10 px-space-lg bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-md text-body-md font-medium transition-colors flex items-center justify-center gap-space-xs"
        >
          <span class="material-symbols-outlined text-[18px]">domain_add</span>
          <span>Crear</span>
        </button>
      </form>
      <p class="font-body-sm text-body-sm text-secondary">
        Crear uno que ya existe no falla: devuelve el que había y lo dice.
        {#if (proveedores ?? []).length}
          Hay {proveedores.length} proveedor(es) dados de alta.
        {/if}
      </p>
    </section>
  </div>

  <!-- ============ DERECHA: VALORIZACIÓN ============ -->
  <div class="xl:col-span-5 flex flex-col gap-space-lg">
    <section class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-md">
      <div class="flex items-start justify-between gap-space-sm">
        <div>
          <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
            Valor del inventario
          </span>
          <h2 class="font-headline-sm text-headline-sm text-on-surface mt-space-xs">
            {nombreUbicacion}
          </h2>
        </div>
        <span class="px-2 py-1 rounded bg-secondary-container text-on-secondary-fixed text-body-sm font-label-code shrink-0">
          promedio ponderado
        </span>
      </div>

      {#if !valorizacion}
        <p class="font-body-md text-body-md text-secondary">
          Elegí una ubicación para ver cuánto vale lo que hay.
        </p>
      {:else if valorizacion.error}
        <p class="font-body-md text-body-md text-error">
          No se pudo leer la valorización. No se muestra un cero porque no sabemos si es
          cero.
        </p>
      {:else}
        <p class="font-headline-lg text-headline-lg text-on-surface tabular-nums" style="font-size:1.7rem;">
          {totalLegible(valorizacion.total)}
          <span class="font-body-sm text-body-sm text-secondary font-normal">COP</span>
        </p>

        {#if valorizacion.advertencia}
          <!--
            El aviso que evita decidir con un número incompleto. Ni error ni éxito:
            algo que hay que mirar.
          -->
          <div class="bg-tertiary-container/20 p-space-md rounded flex flex-col gap-space-xs">
            <div class="flex items-start gap-space-sm">
              <span class="material-symbols-outlined text-tertiary text-[18px] shrink-0">warning</span>
              <div class="flex flex-col">
                <span class="font-headline-sm text-body-sm font-semibold text-tertiary">
                  El total no incluye todo
                </span>
                <p class="font-body-sm text-body-sm text-on-surface mt-0.5">
                  {valorizacion.advertencia} No se cuentan como cero: cero diría que son
                  gratis, y eso es distinto de no saber su costo.
                </p>
              </div>
            </div>
            <ul class="flex flex-col gap-space-xs pl-space-lg">
              {#each valorizacion.sin_costo_conocido ?? [] as m (m.material_id)}
                <li class="font-body-sm text-body-sm text-on-surface">
                  <span class="font-label-code text-label-code">{m.codigo}</span>
                  {m.nombre} · {m.existencia} {m.unidad}
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if (valorizacion.materiales ?? []).length}
          <div class="w-full overflow-x-auto">
            <table class="w-full text-left">
              <thead>
                <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
                  <th class="py-2 px-space-md">Código</th>
                  <th class="py-2 px-space-md text-right">Cantidad</th>
                  <th class="py-2 px-space-md text-right">Costo prom.</th>
                  <th class="py-2 px-space-md text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {#each valorizacion.materiales as m (m.material_id)}
                  <tr class="hover:bg-surface-container-low/40 transition-colors">
                    <td class="py-2.5 px-space-md font-label-code text-label-code text-on-surface font-semibold">
                      {m.codigo}
                    </td>
                    <td class="py-2.5 px-space-md text-right font-label-numeric text-body-sm tabular-nums text-secondary">
                      {m.existencia}
                    </td>
                    <td class="py-2.5 px-space-md text-right font-label-numeric text-body-sm tabular-nums text-secondary">
                      {m.costo_unitario}
                    </td>
                    <td class="py-2.5 px-space-md text-right font-label-numeric text-body-md tabular-nums text-on-surface font-semibold">
                      {m.valor}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>

          <!-- La proporción del valor, calculada de la misma tabla -->
          {#if proporciones.length > 1}
            <div class="flex flex-col gap-space-xs pt-space-xs">
              <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
                En qué está el valor
              </span>
              {#each proporciones as p (p.codigo)}
                <div class="flex items-center gap-space-sm">
                  <span class="font-label-code text-label-code text-secondary w-32 truncate" title={p.nombre}>
                    {p.codigo}
                  </span>
                  <div class="flex-1 h-2 rounded-full bg-surface-container overflow-hidden">
                    <div class="h-full rounded-full bg-primary" style="width:{p.parte}%"></div>
                  </div>
                  <span class="font-label-numeric text-body-sm tabular-nums text-on-surface w-12 text-right">
                    {p.parte.toFixed(0)}%
                  </span>
                </div>
              {/each}
            </div>
          {/if}
        {/if}

        <p class="font-body-sm text-body-sm text-secondary pt-space-xs leading-relaxed">
          El costo de cada material es el <strong>promedio ponderado</strong> de lo que costó
          al entrar. Se dice cuál es el método porque FIFO, LIFO y promedio dan números
          distintos sobre los mismos datos.
        </p>
      {/if}
    </section>

    <!--
      La valorización suma montos sin distinguir la moneda de cada compra. Está
      declarado porque afecta el número de arriba, no porque falte la pantalla.
    -->
    <div class="bg-surface-container-low/60 p-space-md rounded-xl flex items-start gap-space-sm" data-sin-dato="valorizacion-por-moneda">
      <span class="material-symbols-outlined text-tertiary text-[18px] mt-0.5">currency_exchange</span>
      <p class="font-body-sm text-body-sm text-secondary">
        Si se registran compras en más de una moneda, el total las suma sin convertir. Hoy
        eso no está resuelto, así que conviene registrar una sola moneda por empresa hasta
        que lo esté.
      </p>
    </div>
  </div>
</div>
