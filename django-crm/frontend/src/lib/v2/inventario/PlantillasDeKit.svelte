<script>
  /**
   * Plantillas de kit: la lista que se repite todas las mañanas.
   *
   * SON DE LA EMPRESA, Y ESO ES LA DECISIÓN
   * «Un kit de instalación lleva 24 conectores y 300 metros» es verdad en una
   * empresa y falso en la siguiente: depende del tipo de acometida, del material
   * que compra cada ISP y de cómo arma sus cuadrillas. Por eso son filas de una
   * tabla por organización y no una lista en el código — el jefe de bodega las
   * cambia sin que nadie toque el repositorio.
   *
   * UNA PLANTILLA NO MUEVE MATERIAL
   * Solo rellena las líneas del despacho, que después alguien revisa y confirma.
   * Lo que quedó escrito de lo que de verdad salió es el acta de entrega.
   *
   * Y NO GUARDA SERIES: puede decir «una ONT», nunca «la ONT HWTCA6FB5263».
   * Cada aparato es distinto y su número se lee al despachar.
   */
  import { enhance } from '$app/forms';

  /** @type {{ plantillas: any[], materiales: any[] }} */
  let { plantillas, materiales } = $props();

  /** Qué se está editando: '' = una nueva. */
  let editando = $state('');
  let nombre = $state('');
  let descripcion = $state('');
  let lineas = $state([{ n: 1, material: '', cantidad: '' }]);
  let siguiente = 2;
  let abierto = $state(false);
  /** Qué plantilla está preguntando «¿seguro?». Misma razón que en Materiales:
   *  dar de baja con un solo clic se hace sin querer. */
  let confirmando = $state('');

  function nueva() {
    editando = '';
    nombre = '';
    descripcion = '';
    lineas = [{ n: siguiente++, material: '', cantidad: '' }];
    abierto = true;
  }

  /** @param {any} p */
  function editar(p) {
    editando = p.id;
    nombre = p.nombre;
    descripcion = p.descripcion ?? '';
    lineas = p.lineas.map((/** @type {any} */ l) => ({
      n: siguiente++,
      material: l.material,
      cantidad: String(Number(l.cantidad))
    }));
    if (lineas.length === 0) lineas = [{ n: siguiente++, material: '', cantidad: '' }];
    abierto = true;
  }

  function agregar() {
    lineas = [...lineas, { n: siguiente++, material: '', cantidad: '' }];
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

  let activas = $derived((plantillas ?? []).filter((p) => p.activa));
  let guardadas = $derived((plantillas ?? []).filter((p) => !p.activa));
</script>

<section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
  <div class="p-space-lg flex flex-wrap items-start justify-between gap-space-md">
    <div class="flex items-start gap-space-sm">
      <div class="w-8 h-8 rounded bg-surface-container flex items-center justify-center text-primary shrink-0">
        <span class="material-symbols-outlined text-[18px]">list_alt</span>
      </div>
      <div>
        <h2 class="font-headline-sm text-body-md text-on-surface font-semibold">
          Plantillas de kit
        </h2>
        <p class="font-body-sm text-body-sm text-secondary">
          Lo que se entrega todas las mañanas, guardado con un nombre. Son de esta
          empresa: cada ISP arma sus kits distinto.
        </p>
      </div>
    </div>
    <div class="flex items-center gap-space-sm">
      <button
        type="button"
        onclick={() => (abierto = !abierto)}
        class="h-9 px-space-md bg-surface-container-lowest hover:bg-surface-container text-secondary rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors inline-flex items-center gap-1"
      >
        <span class="material-symbols-outlined text-[16px]">
          {abierto ? 'expand_less' : 'expand_more'}
        </span>
        {abierto ? 'Ocultar' : 'Ver'}
      </button>
      <button
        type="button"
        onclick={nueva}
        class="h-9 px-space-md bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors inline-flex items-center gap-1"
      >
        <span class="material-symbols-outlined text-[16px]">add</span>
        Nueva plantilla
      </button>
    </div>
  </div>

  {#if abierto}
    <!-- Las que hay -->
    <div class="px-space-lg pb-space-md flex flex-col gap-space-sm">
      {#if activas.length === 0}
        <p class="font-body-sm text-body-sm text-secondary">
          Todavía no hay ninguna. Armá una con lo que el técnico se lleva un día normal
          y la próxima entrega se carga de una vez.
        </p>
      {/if}

      {#each activas as p (p.id)}
        <div class="border border-outline-variant/30 rounded-lg p-space-md flex flex-wrap items-start justify-between gap-space-md">
          <div class="flex flex-col min-w-0">
            <div class="flex items-center gap-space-sm flex-wrap">
              <span class="font-headline-sm text-body-md text-on-surface font-semibold">
                {p.nombre}
              </span>
              <span class="font-label-numeric text-body-sm text-secondary bg-surface-container px-2 py-0.5 rounded">
                {p.lineas.length} {p.lineas.length === 1 ? 'material' : 'materiales'}
              </span>
            </div>
            {#if p.descripcion}
              <span class="font-body-sm text-body-sm text-secondary">{p.descripcion}</span>
            {/if}
            <ul class="flex flex-wrap gap-x-space-lg gap-y-0.5 mt-space-xs">
              {#each p.lineas as l (l.material)}
                <li class="font-body-sm text-body-sm text-secondary">
                  <span class="font-label-code text-label-code text-on-surface">{l.material}</span>
                  · {Number(l.cantidad)} {l.unidad}
                </li>
              {/each}
            </ul>
          </div>
          <div class="flex items-center gap-space-xs">
            <button
              type="button"
              onclick={() => editar(p)}
              class="h-8 px-space-md bg-surface-container-lowest hover:bg-surface-container text-on-surface rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors"
            >
              Editar
            </button>
            {#if confirmando === p.id}
              <div class="flex items-center gap-space-xs">
                <span class="font-body-sm text-body-sm text-secondary">¿Darla de baja?</span>
                <form method="POST" action="?/plantillaBaja" use:enhance={() => {
                  confirmando = '';
                  return async ({ update }) => await update();
                }}>
                  <input type="hidden" name="plantilla" value={p.id} />
                  <button
                    type="submit"
                    class="h-8 px-space-md bg-error text-on-error rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors"
                  >
                    Sí
                  </button>
                </form>
                <button
                  type="button"
                  onclick={() => (confirmando = '')}
                  class="h-8 px-space-md bg-surface-container-lowest hover:bg-surface-container text-on-surface rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors"
                >
                  No
                </button>
              </div>
            {:else}
              <button
                type="button"
                onclick={() => (confirmando = p.id)}
                class="h-8 px-space-md bg-surface-container-lowest hover:bg-error-container/30 text-secondary hover:text-error rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors"
                title="Deja de ofrecerse. No se borra: sigue explicando los despachos que la usaron"
              >
                Dar de baja
              </button>
            {/if}
          </div>
        </div>
      {/each}

      {#if guardadas.length}
        <p class="font-body-sm text-body-sm text-secondary">
          Hay {guardadas.length} plantilla(s) dadas de baja. No se borran: siguen
          explicando por qué un despacho viejo llevaba lo que llevaba.
        </p>
      {/if}
    </div>

    <!-- Armar o editar una -->
    <form
      method="POST"
      action="?/plantilla"
      use:enhance
      class="p-space-lg bg-surface-container-low/40 flex flex-col gap-space-md"
    >
      <input type="hidden" name="plantilla" value={editando} />

      <div class="flex items-center gap-space-xs">
        <span class="material-symbols-outlined text-primary text-[18px]">
          {editando ? 'edit' : 'add_circle'}
        </span>
        <h3 class="font-headline-sm text-body-md text-on-surface font-semibold">
          {editando ? `Editar «${nombre}»` : 'Nueva plantilla'}
        </h3>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-space-md max-w-3xl">
        <div class="flex flex-col gap-space-xs">
          <label for="pl-nombre" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Nombre <span class="text-error">*</span>
          </label>
          <input
            id="pl-nombre"
            name="nombre"
            bind:value={nombre}
            required
            placeholder="Kit instalación FTTH"
            class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div class="flex flex-col gap-space-xs">
          <label for="pl-descripcion" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Para qué sirve <span class="text-secondary font-normal opacity-75">(opcional)</span>
          </label>
          <input
            id="pl-descripcion"
            name="descripcion"
            bind:value={descripcion}
            placeholder="lo que lleva una cuadrilla de instalación un día normal"
            class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      <div class="w-full overflow-x-auto">
        <table class="w-full text-left max-w-3xl">
          <thead>
            <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
              <th class="py-2 px-space-md">Material</th>
              <th class="py-2 px-space-md w-48 text-right">Cantidad</th>
              <th class="py-2 px-space-md w-20 text-center">Quitar</th>
            </tr>
          </thead>
          <tbody>
            {#each lineas as linea (linea.n)}
              {@const m = materialDe(linea.material)}
              <tr>
                <td class="py-2 px-space-md">
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
                <td class="py-2 px-space-md text-right">
                  <div class="inline-flex items-center gap-1.5">
                  <!--
                    EL `min` SIGUE AL `step`, y no es un detalle de estilo.

                    `type="number"` valida contra min MÁS múltiplos de step. Con
                    min="0.001" y step="1" los válidos eran 0.001, 1.001, 2.001…
                    así que escribir 12 daba «Introduce un valor válido. Los dos
                    valores válidos más aproximados son 11,001 y 12,001». Un
                    consumible se cuenta en enteros y su mínimo es 1; una bobina
                    admite milésimas y el suyo es 0.001.
                  -->
                    <input
                      name="cantidad"
                      type="number"
                      step={m?.clase === 'bobina' ? '0.001' : '1'}
                      min={m?.clase === 'bobina' ? '0.001' : '1'}
                      bind:value={linea.cantidad}
                      class="w-28 h-9 px-2.5 text-right font-label-numeric text-body-md bg-surface-container-lowest text-on-surface rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                    <span class="font-body-sm text-body-sm text-secondary w-16 text-left">
                      {m?.unidad ?? ''}
                    </span>
                  </div>
                  <!-- La plantilla no fija series: son cuántos aparatos, no cuáles. -->
                  <input type="hidden" name="serie" value="" />
                </td>
                <td class="py-2 px-space-md text-center">
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

      <div class="flex flex-wrap items-center justify-between gap-space-md max-w-3xl">
        <button
          type="button"
          onclick={agregar}
          class="h-9 px-4 bg-surface-container-lowest hover:bg-surface-container text-on-surface font-body-sm text-body-sm font-medium rounded shadow-sm transition-colors flex items-center gap-1.5"
        >
          <span class="material-symbols-outlined text-[18px] text-primary">add</span>
          <span>Agregar material</span>
        </button>
        <div class="flex items-center gap-space-sm">
          {#if editando}
            <button
              type="button"
              onclick={nueva}
              class="h-10 px-space-md bg-surface-container-lowest hover:bg-surface-container text-secondary rounded font-body-sm text-body-sm font-medium transition-colors"
            >
              Cancelar la edición
            </button>
          {/if}
          <button
            type="submit"
            class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-headline-sm text-body-md font-medium shadow-sm transition-colors flex items-center gap-space-xs"
          >
            <span class="material-symbols-outlined text-[18px]">save</span>
            <span>{editando ? 'Guardar los cambios' : 'Crear la plantilla'}</span>
          </button>
        </div>
      </div>

      <p class="font-body-sm text-body-sm text-secondary max-w-3xl">
        Una plantilla no mueve material: solo rellena las líneas del despacho, que
        después se revisan. Al cargarla se descuenta lo que el técnico ya tiene encima,
        porque su custodia no se vacía al terminar el día.
      </p>
    </form>
  {/if}
</section>
