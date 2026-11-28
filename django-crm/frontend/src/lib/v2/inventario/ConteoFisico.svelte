<script>
  /**
   * Conteo físico: alguien cuenta la bodega a mano y registra lo que encontró.
   *
   * Portada de la pantalla "Conteo físico" de Stitch, que la organiza en tres
   * filas: abrir la sesión, anotar mientras el conteo está en borrador, y el
   * resultado al cerrarlo.
   *
   * CERRAR UN CONTEO NO REESCRIBE EL SALDO
   * Escribe un movimiento de ajuste por cada diferencia, con su motivo y su
   * responsable. «El sistema dice 50 y tengo 48» no es un error del sistema: es un
   * hecho nuevo que alguien tiene que explicar, y un conteo que sobreescribiera el
   * saldo perdería lo único interesante que tiene.
   *
   * Y EL RESULTADO MUESTRA TAMBIÉN LO QUE CUADRÓ
   * Un conteo que solo lista diferencias no deja ver cuánto se revisó.
   *
   * LO QUE EL DISEÑO PIDE Y NO EXISTE
   * El folio del conteo, el auditor asignado, «exportar acta», «descartar
   * borrador» y la lista de lo ya anotado mientras el conteo sigue abierto: la API
   * devuelve cuántas líneas tiene, no cuáles. Todo eso queda marcado.
   */
  import { enhance } from '$app/forms';

  /** @type {{ conteos: any[], materiales: any[], internas: any[], ubicacionElegida: string, form: any }} */
  let { conteos, materiales, internas, ubicacionElegida, form } = $props();

  let abiertos = $derived((conteos ?? []).filter((c) => c.estado === 'borrador'));
  let cerrados = $derived((conteos ?? []).filter((c) => c.estado !== 'borrador'));

  /** @param {string|null} iso */
  function fecha(iso) {
    return iso ? iso.slice(0, 16).replace('T', ' ') : '—';
  }

  /** Las líneas que devolvió el cierre, con su resumen. */
  let resultado = $derived(form?.lineasConteo ?? []);
  let resumen = $derived({
    total: resultado.length,
    con_ajuste: resultado.filter((/** @type {any} */ l) => l.ajuste).length,
    cuadradas: resultado.filter((/** @type {any} */ l) => !l.ajuste).length
  });
</script>

<!-- ============ LA REGLA DE ORO, ARRIBA ============ -->
<div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex items-start gap-space-md">
  <div class="w-10 h-10 rounded bg-surface-container flex items-center justify-center text-primary shrink-0">
    <span class="material-symbols-outlined text-[22px]">inventory</span>
  </div>
  <div class="flex flex-col">
    <span class="font-headline-sm text-headline-sm text-on-surface">
      Contar no corrige: produce un ajuste con su motivo
    </span>
    <p class="font-body-sm text-body-sm text-secondary mt-0.5 max-w-3xl">
      «El sistema dice 50 y tengo 48» no es un error del sistema: es un hecho nuevo que
      alguien tiene que explicar. Al cerrar, cada diferencia se escribe como un movimiento
      de ajuste —con quién contó y por qué— y la diferencia queda visible. Un conteo que
      sobreescribiera el saldo perdería lo único interesante que tiene.
    </p>
  </div>
</div>

{#if form?.error}
  <div class="bg-error-container/40 px-space-lg py-space-md rounded-xl flex items-start gap-space-md shadow-sm">
    <span class="material-symbols-outlined text-error text-[20px] shrink-0">error</span>
    <p class="font-body-md text-body-md text-on-surface">{form.error}</p>
  </div>
{/if}
{#if form?.hecho}
  <div class="bg-primary-fixed/40 px-space-lg py-space-md rounded-xl flex items-start gap-space-md shadow-sm">
    <span class="material-symbols-outlined text-primary text-[20px] shrink-0">check_circle</span>
    <p class="font-body-md text-body-md text-on-surface">{form.hecho}</p>
  </div>
{/if}

<!-- ============ FILA 1: ABRIR Y SESIONES ============ -->
<div class="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
  <section class="lg:col-span-4 bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md">
    <div>
      <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">Paso 1</span>
      <h2 class="font-headline-sm text-headline-sm text-on-surface mt-space-xs">Abrir conteo</h2>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5">
        Uno por ubicación a la vez: dos conteos abiertos producen dos verdades sobre lo
        mismo.
      </p>
    </div>

    <form method="POST" action="?/abrirConteo" use:enhance class="flex flex-col gap-space-md">
      <div class="flex flex-col gap-space-xs">
        <label for="ct-ubicacion" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Ubicación a contar <span class="text-error">*</span>
        </label>
        <div class="relative">
          <select
            id="ct-ubicacion"
            name="ubicacion"
            required
            class="w-full h-10 px-3 pr-9 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm appearance-none focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
          >
            {#each internas as u (u.id)}
              <option value={u.id} selected={u.id === ubicacionElegida}>{u.nombre}</option>
            {/each}
          </select>
          <span class="material-symbols-outlined absolute right-2.5 top-2.5 pointer-events-none text-secondary text-[20px]">
            arrow_drop_down
          </span>
        </div>
      </div>

      <!-- El auditor responsable: el sistema guarda quién contó, y es quien está
           usando la pantalla. No se puede elegir a otra persona. -->
      <div class="flex flex-col gap-space-xs" data-sin-dato="auditor-elegible">
        <span class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Responsable del conteo
        </span>
        <div class="h-10 px-3 flex items-center bg-surface-container-low rounded font-body-md text-body-md text-secondary">
          quien lo abre, que sos vos
        </div>
      </div>

      <button
        type="submit"
        class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-headline-sm text-body-md font-medium shadow-sm transition-colors flex items-center justify-center gap-space-xs"
      >
        <span class="material-symbols-outlined text-[18px]">lock</span>
        <span>Abrir conteo físico</span>
      </button>
    </form>
  </section>

  <section class="lg:col-span-8 bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg flex items-center justify-between gap-space-md">
      <div>
        <h2 class="font-headline-sm text-headline-sm text-on-surface">Sesiones de conteo</h2>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5">
          Un conteo cerrado no se puede modificar: sus números ya produjeron ajustes.
        </p>
      </div>
      <span class="font-label-numeric text-body-sm text-secondary bg-surface-container px-2 py-0.5 rounded">
        {(conteos ?? []).length}
      </span>
    </div>

    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-space-lg">Ubicación</th>
            <th class="py-2.5 px-space-lg w-28">Estado</th>
            <th class="py-2.5 px-space-lg w-44">Abierto</th>
            <th class="py-2.5 px-space-lg text-right w-24">Líneas</th>
          </tr>
        </thead>
        <tbody>
          {#if (conteos ?? []).length === 0}
            <tr>
              <td colspan="4" class="py-space-lg px-space-lg font-body-sm text-body-sm text-secondary">
                Todavía no se contó ninguna ubicación.
              </td>
            </tr>
          {/if}
          {#each conteos ?? [] as c (c.id)}
            <tr class="hover:bg-surface-container-low/40 transition-colors">
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">
                {c.ubicacion}
              </td>
              <td class="py-space-md px-space-lg">
                <span
                  class="px-2 py-0.5 rounded font-table-header text-table-header uppercase {c.estado ===
                  'borrador'
                    ? 'bg-tertiary-container/40 text-tertiary'
                    : 'bg-surface-container text-secondary'}"
                >
                  {c.estado === 'borrador' ? 'En progreso' : 'Cerrado'}
                </span>
              </td>
              <td class="py-space-md px-space-lg font-label-numeric text-body-sm text-secondary">
                {fecha(c.iniciado_en)}
              </td>
              <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-on-surface">
                {c.lineas}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
</div>

<!-- ============ FILA 2: EL CONTEO ABIERTO ============ -->
{#each abiertos as abierto (abierto.id)}
  <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg flex flex-wrap items-center justify-between gap-space-md bg-tertiary-container/10">
      <div class="flex items-center gap-space-md">
        <div class="w-10 h-10 rounded bg-tertiary-container/40 flex items-center justify-center text-tertiary shrink-0">
          <span class="material-symbols-outlined text-[22px]">edit_note</span>
        </div>
        <div class="flex flex-col">
          <div class="flex items-center gap-space-xs flex-wrap">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">
              Conteo de {abierto.ubicacion}
            </h2>
            <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-tertiary-container/40 text-tertiary">
              En progreso
            </span>
          </div>
          <span class="font-body-sm text-body-sm text-secondary">
            Abierto el {fecha(abierto.iniciado_en)} · {abierto.lineas}
            {abierto.lineas === 1 ? 'material anotado' : 'materiales anotados'}
          </span>
        </div>
      </div>

      <!-- El cierre, separado y notorio: es lo que escribe los ajustes. -->
      <form method="POST" action="?/cerrarConteo" use:enhance>
        <input type="hidden" name="conteo" value={abierto.id} />
        <button
          type="submit"
          class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-headline-sm text-body-md font-medium shadow-sm transition-colors flex items-center gap-space-xs"
        >
          <span class="material-symbols-outlined text-[18px]">verified</span>
          <span>Cerrar el conteo y escribir los ajustes</span>
        </button>
      </form>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-space-lg p-space-lg">
      <!-- Anotación rápida -->
      <form
        method="POST"
        action="?/anotarConteo"
        use:enhance
        class="lg:col-span-5 flex flex-col gap-space-md max-w-[540px]"
      >
        <input type="hidden" name="conteo" value={abierto.id} />
        <h3 class="font-headline-sm text-body-md text-on-surface font-semibold">
          Anotar lo que se contó
        </h3>

        <div class="flex flex-col gap-space-xs">
          <label for="ct-material-{abierto.id}" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Material <span class="text-error">*</span>
          </label>
          <select
            id="ct-material-{abierto.id}"
            name="material"
            required
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
          >
            <option value="">Elegí un material…</option>
            {#each materiales as m (m.id)}
              <option value={m.codigo}>{m.codigo} · {m.nombre}</option>
            {/each}
          </select>
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="ct-cantidad-{abierto.id}" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Cuánto hay de verdad <span class="text-error">*</span>
          </label>
          <div class="relative flex items-center">
            <input
              id="ct-cantidad-{abierto.id}"
              name="cantidad"
              type="number"
              step="0.001"
              min="0"
              required
              placeholder="0"
              class="w-full h-10 pl-3 pr-10 bg-surface-container-lowest text-on-surface font-label-numeric text-body-md rounded shadow-sm text-right focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span class="material-symbols-outlined absolute right-2.5 text-secondary text-[18px]">
              qr_code_scanner
            </span>
          </div>
          <span class="font-body-sm text-body-sm text-secondary">
            Lo contado, no lo que debería haber. La diferencia la calcula el sistema al
            cerrar.
          </span>
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="ct-motivo-{abierto.id}" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Motivo de la diferencia <span class="text-secondary font-normal opacity-75">(si hay)</span>
          </label>
          <input
            id="ct-motivo-{abierto.id}"
            name="motivo"
            placeholder="faltaban cinco en el estante"
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm placeholder:text-secondary/60 focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <span class="font-body-sm text-body-sm text-secondary">
            Sin motivo, el ajuste queda marcado como diferencia sin explicar. Eso se
            registra tal cual.
          </span>
        </div>

        <button
          type="submit"
          class="h-10 px-space-lg bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-md text-body-md font-medium transition-colors flex items-center justify-center gap-space-xs"
        >
          <span class="material-symbols-outlined text-[18px]">add_task</span>
          <span>Anotar línea</span>
        </button>
      </form>

      <!--
        La lista de lo ya anotado. La API devuelve CUÁNTAS líneas tiene el conteo,
        no cuáles: para mostrarlas haría falta un endpoint que todavía no existe.
        Queda la tabla con lo que sí se sabe.
      -->
      <div class="lg:col-span-7 flex flex-col gap-space-sm" data-sin-dato="lineas-del-conteo-abierto">
        <h3 class="font-headline-sm text-body-md text-on-surface font-semibold">
          Líneas anotadas en este conteo
        </h3>
        <div class="rounded-lg overflow-hidden border border-outline-variant/30">
          <table class="w-full text-left">
            <thead>
              <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
                <th class="py-2.5 px-space-md">Material</th>
                <th class="py-2.5 px-space-md text-right w-28">Contado</th>
                <th class="py-2.5 px-space-md text-right w-28">Sistema</th>
                <th class="py-2.5 px-space-md text-right w-28">Diferencia</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colspan="4" class="py-space-lg px-space-md font-body-sm text-body-sm text-secondary">
                  {abierto.lineas === 0
                    ? 'Todavía no se anotó ningún material.'
                    : `Hay ${abierto.lineas} material(es) anotados. El detalle se ve al cerrar el conteo: la API todavía no expone las líneas de un conteo en borrador.`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="font-body-sm text-body-sm text-secondary">
          Se puede anotar el mismo material dos veces: la segunda corrige la primera
          mientras el conteo siga abierto.
        </p>
      </div>
    </div>
  </section>
{/each}

<!-- ============ FILA 3: RESULTADO DEL CIERRE ============ -->
{#if resultado.length}
  <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg flex flex-wrap items-center justify-between gap-space-md">
      <div>
        <h2 class="font-headline-sm text-headline-sm text-on-surface">Resultado del conteo</h2>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5">
          Las líneas que cuadraron aparecen también: un conteo que solo muestra diferencias
          no deja ver cuánto se revisó.
        </p>
      </div>
      <div class="flex items-center gap-space-md">
        <div class="flex flex-col items-end">
          <span class="font-table-header text-table-header text-secondary uppercase">Revisadas</span>
          <span class="font-headline-md text-headline-md text-on-surface tabular-nums">{resumen.total}</span>
        </div>
        <div class="flex flex-col items-end">
          <span class="font-table-header text-table-header text-secondary uppercase">Cuadraron</span>
          <span class="font-headline-md text-headline-md text-primary tabular-nums">{resumen.cuadradas}</span>
        </div>
        <div class="flex flex-col items-end">
          <span class="font-table-header text-table-header text-tertiary uppercase">Con ajuste</span>
          <span class="font-headline-md text-headline-md text-tertiary tabular-nums">{resumen.con_ajuste}</span>
        </div>
      </div>
    </div>

    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-space-lg">Material</th>
            <th class="py-2.5 px-space-lg text-right w-32">Contado</th>
            <th class="py-2.5 px-space-lg text-right w-36">Decía el sistema</th>
            <th class="py-2.5 px-space-lg text-right w-32">Diferencia</th>
            <th class="py-2.5 px-space-lg w-44">Resultado</th>
          </tr>
        </thead>
        <tbody>
          {#each resultado as l, i (i)}
            {@const dif = Number(l.diferencia)}
            <tr class="transition-colors {dif !== 0 ? 'bg-tertiary-container/10' : 'hover:bg-surface-container-low/40'}">
              <td class="py-space-md px-space-lg font-label-code text-label-code text-on-surface font-semibold">
                {l.material}
              </td>
              <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-on-surface">
                {l.contado}
              </td>
              <td class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums text-secondary">
                {l.segun_sistema}
              </td>
              <td
                class="py-space-md px-space-lg text-right font-label-numeric text-body-md tabular-nums font-semibold {dif ===
                0
                  ? 'text-secondary'
                  : dif < 0
                    ? 'text-error'
                    : 'text-tertiary'}"
              >
                {l.diferencia}
              </td>
              <td class="py-space-md px-space-lg">
                {#if l.ajuste}
                  <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-tertiary-container/40 text-tertiary">
                    Ajuste escrito
                  </span>
                {:else}
                  <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-surface-container text-secondary">
                    Cuadró
                  </span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="px-space-lg py-space-md bg-surface-container-low/40 flex flex-wrap items-center justify-between gap-space-md">
      <p class="font-body-sm text-body-sm text-secondary max-w-2xl">
        Cada ajuste quedó como un movimiento con su dirección: lo que sobra entra a la
        ubicación y lo que falta sale de ella. La existencia ya lo refleja, porque se
        calcula sumando el libro.
      </p>
      <button
        type="button"
        disabled
        data-sin-dato="exportar-acta"
        class="h-9 px-space-md bg-surface-container-lowest text-outline rounded font-body-sm text-body-sm font-medium shadow-sm inline-flex items-center gap-1"
        title="Pendiente: todavía no hay un acta exportable"
      >
        <span class="material-symbols-outlined text-[16px]">file_download</span>
        <span>Exportar acta</span>
      </button>
    </div>
  </section>
{:else if cerrados.length}
  <section class="bg-surface-container-low/40 p-space-lg rounded-xl flex items-start gap-space-sm">
    <span class="material-symbols-outlined text-secondary text-[20px] mt-0.5">history</span>
    <p class="font-body-sm text-body-sm text-secondary">
      Hay {cerrados.length} conteo(s) cerrado(s). El detalle de sus líneas se ve al momento
      de cerrarlos; la API todavía no permite volver a consultarlo después.
    </p>
  </section>
{/if}
