<script>
  /**
   * Recibir devolución: el técnico trae material de vuelta y la bodega lo recibe.
   *
   * Portada de la pantalla "Recibir devolución" de Stitch.
   *
   * LO QUE DEFINE ESTA PANTALLA ES EL CAMPO «CUÁNTO SE ESPERABA»
   * Es opcional, y esa decisión es el corazón del diseño. Devolver 12 de 18 es
   * legítimo —al técnico le quedan 6 y sigue trabajando—, así que el sistema no
   * supone un faltante. Solo cuando quien recibe declara cuánto debía volver, la
   * diferencia abre una incidencia con su motivo y NO se absorbe en un ajuste
   * silencioso: «faltan 3 conectores» y «se dañaron 3 al retirarlos» son hechos
   * distintos y la empresa necesita saber cuál de los dos tiene.
   *
   * Ese camino estaba cortado hasta el 29/09/2026: la pantalla mandaba el
   * esperado y la vista del backend lo descartaba, así que por la web nunca se
   * abría una incidencia. Está arreglado y con dos pruebas que lo miden.
   */
  import { enhance } from '$app/forms';

  /** @type {{ materiales: any[], personas: any[], internas: any[], existencias: any[], ubicaciones: any[], form: any }} */
  let { materiales, personas, internas, existencias, ubicaciones, form } = $props();

  // svelte-ignore state_referenced_locally
  // Es a propósito: se quiere el valor INICIAL. Los props de esta pantalla no
  // cambian sin una recarga --vienen del load-- y lo que sigue es una elección
  // del usuario, que no debe volver al primer elemento cuando el padre repinta.
  let tecnico = $state(personas[0]?.id ?? '');
  let lineas = $state([{ n: 1, material: '', cantidad: '', serie: '', esperado: '' }]);
  let siguiente = 2;

  function agregar() {
    lineas = [...lineas, { n: siguiente++, material: '', cantidad: '', serie: '', esperado: '' }];
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

  /** Lo que ese técnico tiene encima, para comparar contra lo que trae. */
  function custodiaDe(profileId) {
    const u = ubicaciones.find((x) => x.tipo === 'tecnico' && x.profile === profileId);
    if (!u) return null;
    return existencias.find((b) => b.ubicacion.id === u.id) ?? { ubicacion: u, materiales: [] };
  }

  let custodia = $derived(custodiaDe(tecnico));

  /** @param {string} codigo */
  function enCustodia(codigo) {
    return (custodia?.materiales ?? []).find((/** @type {any} */ m) => m.codigo === codigo) ?? null;
  }

  /** @param {any} linea */
  function diferencia(linea) {
    if (!linea.esperado || linea.cantidad === '') return null;
    const d = Number(linea.cantidad) - Number(linea.esperado);
    return Number.isFinite(d) ? d : null;
  }

  /** @param {string} valor @param {string} clase */
  function cantidad(valor, clase) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return valor;
    return clase === 'bobina' ? n.toFixed(3) : String(Math.round(n * 1000) / 1000);
  }
</script>

<!-- ============ EL AVISO DE DIFERENCIA, cuando la hubo ============ -->
{#if form?.incidencias?.length}
  <div class="bg-tertiary-container/20 p-space-lg rounded-xl shadow-sm flex flex-col md:flex-row gap-space-lg justify-between items-start md:items-center">
    <div class="flex items-start gap-space-md">
      <div class="w-10 h-10 rounded bg-tertiary-container/40 text-tertiary flex items-center justify-center shrink-0">
        <span class="material-symbols-outlined text-[24px]">assignment_late</span>
      </div>
      <div class="flex flex-col">
        <h2 class="font-headline-sm text-headline-sm text-tertiary font-semibold leading-tight">
          Quedó una diferencia abierta
        </h2>
        <p class="font-body-md text-body-md text-on-surface mt-1 max-w-2xl">
          La devolución se registró por lo que realmente llegó. Lo que falta quedó como
          incidencia y no fue absorbido por un ajuste.
        </p>
      </div>
    </div>

    <!-- Los cuatro números que originaron cada incidencia, del servidor. -->
    <div class="flex flex-col gap-space-sm shrink-0">
      {#each form.incidencias as i (i.id)}
        <div class="bg-surface-container-lowest/90 px-space-lg py-space-sm rounded-lg shadow-sm flex items-center gap-space-lg text-left">
          <div class="flex flex-col pr-space-xs">
            <span class="font-table-header text-table-header text-secondary uppercase">Material</span>
            <span class="font-label-code text-label-code text-on-surface font-semibold">{i.material}</span>
          </div>
          <div class="flex flex-col pl-space-md">
            <span class="font-table-header text-table-header text-secondary uppercase">Esperado</span>
            <span class="font-label-numeric text-label-numeric text-on-surface tabular-nums">
              {i.esperado || '—'}
            </span>
          </div>
          <div class="flex flex-col pl-space-md">
            <span class="font-table-header text-table-header text-secondary uppercase">Recibido</span>
            <span class="font-label-numeric text-label-numeric text-on-surface tabular-nums font-semibold">
              {i.recibido || '—'}
            </span>
          </div>
          <div class="flex flex-col pl-space-md">
            <span class="font-table-header text-table-header text-tertiary uppercase font-bold">Falta explicar</span>
            <span class="font-label-numeric text-label-numeric text-tertiary tabular-nums font-bold">
              {i.cantidad}
            </span>
          </div>
        </div>
      {/each}
    </div>
  </div>
{/if}

<form method="POST" action="?/devolucion" use:enhance class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
  <!-- Cabecera de la sección -->
  <div class="p-space-lg flex flex-col sm:flex-row justify-between sm:items-center gap-space-sm">
    <div>
      <h2 class="font-headline-md text-headline-md text-on-surface">
        Recepción de materiales y equipos
      </h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        El material sale de la custodia del técnico y entra a la bodega. Quien recibe es
        el único que sabe si esto es un cierre de jornada o una entrega parcial.
      </p>
    </div>
    <div class="flex items-center gap-space-sm">
      <label class="flex flex-col gap-1">
        <span class="font-table-header text-table-header text-secondary uppercase">
          N° de acta de devolución
        </span>
        <input
          name="referencia"
          placeholder="DEV-0412"
          class="h-9 px-3 bg-surface-container-low text-on-surface font-label-code text-label-code rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
          title="Con acta, dos envíos del mismo formulario no registran dos devoluciones"
        />
      </label>
    </div>
  </div>

  <!-- Origen y destino -->
  <div class="p-space-lg bg-surface-container-low/50">
    <div class="grid grid-cols-1 md:grid-cols-12 gap-space-lg">
      <div class="md:col-span-4 flex flex-col gap-1.5">
        <label for="dev-tecnico" class="font-table-header text-table-header text-on-surface-variant uppercase flex items-center gap-1">
          <span>Técnico que devuelve</span><span class="text-tertiary font-bold">*</span>
        </label>
        <div class="relative">
          <select
            id="dev-tecnico"
            name="profile_origen"
            bind:value={tecnico}
            required
            class="w-full h-10 px-3 pr-9 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer"
          >
            {#each personas as p (p.id)}
              <option value={p.id}>{p.nombre}</option>
            {/each}
          </select>
          <span class="material-symbols-outlined absolute right-2.5 top-2.5 pointer-events-none text-secondary text-[20px]">
            expand_more
          </span>
        </div>
        <span class="font-body-sm text-body-sm text-secondary">
          {#if custodia}
            Tiene {custodia.materiales.filter((/** @type {any} */ m) => Number(m.existencia) !== 0).length}
            material(es) en su custodia.
          {:else}
            No tiene custodia abierta: no hay nada que devolver.
          {/if}
        </span>
      </div>

      <div class="md:col-span-4 flex flex-col gap-1.5">
        <label for="dev-bodega" class="font-table-header text-table-header text-on-surface-variant uppercase flex items-center gap-1">
          <span>Bodega que recibe</span><span class="text-tertiary font-bold">*</span>
        </label>
        <div class="relative">
          <select
            id="dev-bodega"
            name="ubicacion_destino"
            required
            class="w-full h-10 px-3 pr-9 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer"
          >
            {#each internas as u (u.id)}
              <option value={u.id}>{u.nombre}</option>
            {/each}
          </select>
          <span class="material-symbols-outlined absolute right-2.5 top-2.5 pointer-events-none text-secondary text-[20px]">
            expand_more
          </span>
        </div>
        <span class="font-body-sm text-body-sm text-secondary">Donde ingresa el material.</span>
      </div>

      <div class="md:col-span-4 flex flex-col gap-1.5">
        <label for="dev-notas" class="font-table-header text-table-header text-on-surface-variant uppercase">
          Notas del reingreso (opcional)
        </label>
        <input
          id="dev-notas"
          name="notas"
          placeholder="el cliente canceló, vuelve sin instalar"
          class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm placeholder:text-outline focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
        <span class="font-body-sm text-body-sm text-secondary">
          Lo que reportó quien trajo el material.
        </span>
      </div>
    </div>
  </div>

  <!-- Encabezado del editor de líneas -->
  <div class="px-space-lg pt-space-lg pb-space-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-space-sm">
    <div>
      <h3 class="font-headline-sm text-headline-sm text-on-surface">Material recibido en mano</h3>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Contá lo que llegó de verdad, no lo que debería haber llegado.
      </p>
    </div>
    <div class="flex items-start gap-2 bg-tertiary-container/20 px-3 py-1.5 rounded-lg text-tertiary max-w-md">
      <span class="material-symbols-outlined text-[18px] shrink-0">info</span>
      <p class="font-body-sm text-body-sm leading-tight">
        <strong>Cuánto se esperaba:</strong> usalo solamente cuando sabés cuánto debía
        volver. Si se deja vacío, el sistema no supone que exista un faltante.
      </p>
    </div>
  </div>

  <!-- Las líneas -->
  <div class="w-full overflow-x-auto">
    <table class="w-full text-left">
      <thead>
        <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
          <th class="py-space-sm px-space-lg w-12 text-center" scope="col">#</th>
          <th class="py-space-sm px-space-lg w-1/3" scope="col">Material</th>
          <th class="py-space-sm px-space-lg w-1/3" scope="col">Cantidad o serie recibida</th>
          <th class="py-space-sm px-space-lg text-right" scope="col">Cuánto se esperaba</th>
          <th class="py-space-sm px-space-lg w-24 text-center" scope="col">Quitar</th>
        </tr>
      </thead>
      <tbody>
        {#each lineas as linea, idx (linea.n)}
          {@const m = materialDe(linea.material)}
          {@const tiene = linea.material ? enCustodia(linea.material) : null}
          {@const dif = diferencia(linea)}
          <tr class="hover:bg-surface-container-low/40 transition-colors">
            <td class="py-space-md px-space-lg text-center font-label-numeric text-body-sm text-secondary">
              {String(idx + 1).padStart(2, '0')}
            </td>

            <td class="py-space-md px-space-lg">
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
              {#if tiene}
                <span class="font-body-sm text-body-sm text-secondary mt-0.5 block">
                  En su custodia figuran {cantidad(tiene.existencia, tiene.clase)} {tiene.unidad}.
                </span>
              {:else if linea.material}
                <span class="font-body-sm text-body-sm text-tertiary mt-0.5 block">
                  Su custodia no registra este material. Se puede recibir igual: el hecho
                  ya pasó, y el saldo va a quedar en negativo para que se vea.
                </span>
              {/if}
            </td>

            <td class="py-space-md px-space-lg">
              {#if m?.es_serializado}
                <div class="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded">
                  <span class="material-symbols-outlined text-secondary text-[16px]">barcode_scanner</span>
                  <input
                    name="serie"
                    required
                    placeholder="HWTCA6FB5263"
                    class="w-48 h-7 px-2 bg-surface-container-lowest rounded font-label-code text-label-code text-on-surface uppercase focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <input type="hidden" name="cantidad" value="1" />
                </div>
              {:else}
                <div class="flex items-center gap-space-sm flex-wrap">
                  <div class="flex items-center gap-1.5 bg-surface-container-low px-3 py-1.5 rounded">
                    <span class="font-body-sm text-body-sm text-secondary font-medium">Recibido:</span>
                    <input
                      name="cantidad"
                      type="number"
                      step={m?.clase === 'bobina' ? '0.001' : '1'}
                      min="0"
                      bind:value={linea.cantidad}
                      class="w-20 h-7 text-right px-2 bg-surface-container-lowest rounded font-label-numeric text-body-md text-on-surface font-semibold focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    <span class="font-body-sm text-body-sm text-secondary">{m?.unidad ?? ''}</span>
                  </div>
                  <input type="hidden" name="serie" value="" />
                  {#if dif !== null && dif !== 0}
                    <span
                      class="px-2 py-1 rounded font-label-code text-body-sm font-medium {dif < 0
                        ? 'bg-tertiary-container/30 text-tertiary'
                        : 'bg-primary-fixed/40 text-primary'}"
                    >
                      {dif < 0 ? `Falta ${Math.abs(dif)}` : `Vuelven ${dif} de más`}
                    </span>
                  {/if}
                </div>
              {/if}
            </td>

            <td class="py-space-md px-space-lg text-right">
              <div class="inline-flex items-center gap-1.5 justify-end">
                <span class="font-body-sm text-body-sm text-secondary">Esperado:</span>
                <input
                  name="esperado"
                  type="number"
                  step="0.001"
                  min="0"
                  bind:value={linea.esperado}
                  placeholder="—"
                  class="w-20 h-8 text-right px-2.5 bg-surface-container-lowest rounded font-label-numeric text-body-md text-on-surface focus:outline-none focus:ring-1 focus:ring-primary tabular-nums"
                />
              </div>
            </td>

            <td class="py-space-md px-space-lg text-center">
              <button
                type="button"
                onclick={() => quitar(linea.n)}
                class="inline-flex items-center justify-center h-8 w-8 rounded text-secondary hover:text-tertiary hover:bg-surface-container transition-colors"
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

  <!-- Pie de acciones -->
  <div class="p-space-lg bg-surface-container-low/40 flex flex-wrap items-center justify-between gap-space-md">
    <button
      type="button"
      onclick={agregar}
      class="h-9 px-4 bg-surface-container-lowest hover:bg-surface-container text-on-surface font-body-sm text-body-sm font-medium rounded shadow-sm transition-colors flex items-center gap-1.5"
    >
      <span class="material-symbols-outlined text-[18px] text-primary">add</span>
      <span>Agregar línea</span>
    </button>
    <button
      type="submit"
      class="h-10 px-space-xl bg-primary-container hover:bg-primary text-on-primary font-headline-sm text-body-md font-medium rounded-lg shadow-sm transition-colors flex items-center gap-space-xs"
    >
      <span class="material-symbols-outlined text-[20px]">assignment_turned_in</span>
      <span>Registrar devolución</span>
    </button>
  </div>
</form>

<!-- La guía del flujo, que el diseño pone como cajón informativo -->
<div class="bg-surface-container-low/60 p-space-lg rounded-xl flex items-start gap-space-md">
  <span class="material-symbols-outlined text-secondary text-[20px] mt-0.5">route</span>
  <div class="flex flex-col gap-space-xs">
    <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
      Dónde encaja esta operación
    </span>
    <p class="font-body-sm text-body-sm text-secondary leading-relaxed">
      Un equipo que vuelve puede seguir dos caminos y conviene no confundirlos: si se
      recibe acá, entra a la bodega y queda disponible para despacharse otra vez. Si en
      cambio se instaló en la casa de un cliente, no vuelve — eso es un consumo, lo
      registra el técnico desde su teléfono, y el material sale del sistema.
    </p>
    <p class="font-body-sm text-body-sm text-secondary leading-relaxed">
      Para un aparato con número de serie, recibir la devolución es además lo que lo
      libera: mientras figure en una custodia, ningún despacho lo puede volver a entregar.
    </p>
  </div>
</div>
