<script>
  /**
   * Buscar un aparato: la funcionalidad que justifica todo el módulo.
   *
   * Portada de la pantalla "Buscar aparato" de Stitch.
   *
   * QUIÉN LO TUVO, DÓNDE ESTÁ, CUÁNDO SALIÓ Y POR QUÉ
   * Con un solo libro es una consulta ordenada por fecha, y es la diferencia entre
   * este módulo y un contador de conectores. La historia se muestra completa,
   * incluidos los movimientos que quedaron en conflicto: que un intento no haya
   * ocurrido también es parte de lo que pasó.
   *
   * EL PUNTERO SE COMPARA CONTRA EL LIBRO, Y SI DIFIEREN SE DICE
   * `UbicacionDeActivo` es un atajo para no recorrer el libro en cada pantalla, y
   * el sistema lo reconstruye para compararlo. Si no coinciden, manda el libro. Un
   * dato guardado que nadie puede verificar es exactamente lo que este módulo
   * evita, y este aviso es lo que lo vuelve verificable.
   *
   * LO QUE EL DISEÑO PIDE Y NO EXISTE
   * «Ejecutar reconciliación del libro» y «exportar acta». El primero no se pone
   * como botón: la reconciliación no es una acción que alguien dispare desde acá —
   * el puntero se corrige registrando el movimiento que falta—. Las series de
   * ejemplo del diseño tampoco: serían enlaces a números que no están en la base.
   */

  /** @type {{ consulta: any, serieConsultada: string }} */
  let { consulta, serieConsultada } = $props();

  /** @param {string|null} iso */
  function fecha(iso) {
    return iso ? iso.slice(0, 16).replace('T', ' ') : '—';
  }

  const ICONO_TIPO = {
    entrada: 'input',
    compra: 'receipt_long',
    despacho: 'local_shipping',
    traslado: 'swap_horiz',
    devolucion: 'assignment_return',
    consumo: 'home_work',
    ajuste: 'tune',
    baja: 'delete_forever'
  };
</script>

<section class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-md">
  <div class="flex items-start justify-between gap-space-md flex-wrap">
    <div>
      <div class="flex items-center gap-space-xs">
        <span class="material-symbols-outlined text-primary text-[20px]">manage_search</span>
        <h2 class="font-headline-md text-headline-md text-on-surface">Buscar un aparato</h2>
      </div>
      <p class="font-body-sm text-body-sm text-secondary mt-0.5 max-w-2xl">
        Quién lo tuvo, dónde está, cuándo salió y por qué. Un equipo con número no puede
        quedar «en algún lado».
      </p>
    </div>
  </div>

  <form method="GET" class="flex flex-wrap items-end gap-space-md">
    <input type="hidden" name="ver" value="serie" />
    <div class="flex flex-col gap-space-xs flex-1 min-w-[280px] max-w-md">
      <label for="se-serie" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
        Número de serie
      </label>
      <div class="relative flex items-center">
        <input
          id="se-serie"
          name="serie"
          required
          value={serieConsultada ?? ''}
          placeholder="HWTCA6FB5263"
          class="w-full h-10 pl-9 pr-3 bg-surface-container-lowest text-on-surface font-label-code text-label-code uppercase tracking-wider rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <span class="material-symbols-outlined absolute left-2.5 text-secondary text-[18px]">
          barcode_scanner
        </span>
      </div>
    </div>
    <button
      type="submit"
      class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-headline-sm text-body-md font-medium shadow-sm transition-colors flex items-center gap-space-xs"
    >
      <span class="material-symbols-outlined text-[18px]">search</span>
      <span>Buscar</span>
    </button>
  </form>
</section>

{#if consulta?.noExiste}
  <section class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex items-start gap-space-md">
    <div class="w-10 h-10 rounded bg-surface-container flex items-center justify-center text-secondary shrink-0">
      <span class="material-symbols-outlined text-[22px]">rule_folder</span>
    </div>
    <div class="flex flex-col gap-space-xs">
      <h3 class="font-headline-sm text-headline-sm text-on-surface">
        <span class="font-label-code text-label-code">{serieConsultada}</span> no está en el
        sistema
      </h3>
      <p class="font-body-md text-body-md text-secondary max-w-2xl">
        No es un error de consulta: esa serie nunca entró al inventario de esta empresa. Si
        el aparato está físicamente en una bodega, la forma de incorporarlo es registrar su
        entrada.
      </p>
      <a
        href="?ver=entrada"
        class="mt-space-xs h-9 px-space-md self-start bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-sm text-body-sm font-medium transition-colors inline-flex items-center gap-space-xs"
      >
        <span class="material-symbols-outlined text-[16px]">add_box</span>
        Registrar su entrada
      </a>
    </div>
  </section>
{:else if consulta?.error}
  <section class="bg-error-container/40 rounded-xl shadow-sm p-space-lg flex items-start gap-space-md">
    <span class="material-symbols-outlined text-error text-[20px] shrink-0">error</span>
    <p class="font-body-md text-body-md text-on-surface">
      No se pudo consultar. Reintentá: esto no significa que la serie no exista.
    </p>
  </section>
{:else if consulta}
  {#each consulta.activos as a (a.serie + a.material.codigo)}
    <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
      <!-- Ficha del aparato -->
      <div class="p-space-lg flex flex-wrap items-start justify-between gap-space-md">
        <div class="flex items-start gap-space-md">
          <div class="w-12 h-12 rounded bg-surface-container flex items-center justify-center text-primary shrink-0">
            <span class="material-symbols-outlined text-[24px]">router</span>
          </div>
          <div class="flex flex-col">
            <h3 class="font-label-code text-headline-sm text-on-surface font-semibold tracking-tight">
              {a.serie}
            </h3>
            <span class="font-body-md text-body-md text-secondary">{a.material.nombre}</span>
            <span class="font-label-code text-label-code text-secondary mt-0.5">
              {a.material.codigo}
            </span>
          </div>
        </div>

        <div class="flex flex-col items-end gap-space-xs">
          <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
            Ahora está en
          </span>
          <span class="font-headline-sm text-headline-sm text-on-surface text-right">
            {a.donde_esta}
          </span>
        </div>
      </div>

      {#if !a.cuadra_con_el_libro}
        <div class="mx-space-lg mb-space-lg bg-error-container/40 p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-error text-[18px] shrink-0 mt-0.5">
            compare_arrows
          </span>
          <div class="flex flex-col">
            <span class="font-headline-sm text-body-sm font-semibold text-error">
              El índice de posición y el libro no coinciden
            </span>
            <p class="font-body-sm text-body-sm text-on-surface mt-0.5">
              Lo que manda es el libro, que está abajo. El índice es un atajo para no
              recorrerlo en cada pantalla, y cuando difiere se arregla registrando el
              movimiento que falta — no editando el índice.
            </p>
          </div>
        </div>
      {/if}

      <!-- La historia -->
      <div class="px-space-lg pb-space-lg">
        <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
          Por dónde pasó
        </span>
        <ol class="flex flex-col gap-0 mt-space-md">
          {#each a.historia as h, i (i)}
            <li class="flex items-stretch gap-space-md">
              <!-- La línea de tiempo -->
              <div class="flex flex-col items-center shrink-0">
                <div
                  class="w-8 h-8 rounded-full flex items-center justify-center {h.estado === 'aceptado'
                    ? 'bg-surface-container text-primary'
                    : 'bg-error-container text-error'}"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {ICONO_TIPO[h.tipo] ?? 'circle'}
                  </span>
                </div>
                {#if i < a.historia.length - 1}
                  <div class="w-px flex-1 bg-outline-variant/40 my-1"></div>
                {/if}
              </div>

              <div class="flex flex-col pb-space-md min-w-0">
                <div class="flex items-center gap-space-sm flex-wrap">
                  <span class="font-label-numeric text-body-sm text-secondary tabular-nums">
                    {fecha(h.en)}
                  </span>
                  <span class="font-headline-sm text-body-md text-on-surface font-semibold capitalize">
                    {h.tipo}
                  </span>
                  {#if h.estado !== 'aceptado'}
                    <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-error-container text-error">
                      {h.estado}
                    </span>
                  {/if}
                </div>
                <span class="font-body-sm text-body-sm text-secondary">
                  {#if h.desde}desde {h.desde}{/if}
                  {#if h.desde && h.hacia}&nbsp;→&nbsp;{/if}
                  {#if h.hacia}
                    hacia {h.hacia}
                  {:else}
                    <span class="text-on-surface-variant">
                      → fuera de custodia (instalado en la casa de un cliente, o dado de
                      baja)
                    </span>
                  {/if}
                </span>
                {#if h.motivo}
                  <span class="font-body-sm text-body-sm text-secondary italic mt-0.5">{h.motivo}</span>
                {/if}
              </div>
            </li>
          {/each}
        </ol>

        {#if a.historia.length === 0}
          <p class="font-body-sm text-body-sm text-secondary mt-space-sm">
            El aparato está dado de alta pero todavía no tiene movimientos.
          </p>
        {/if}
      </div>

      <div class="px-space-lg py-space-md bg-surface-container-low/40 flex flex-wrap items-center justify-between gap-space-md">
        <p class="font-body-sm text-body-sm text-secondary max-w-2xl">
          Esta historia es el libro, no un resumen: cada línea es un movimiento que alguien
          registró, y nada se edita ni se borra.
        </p>
        <button
          type="button"
          disabled
          data-sin-dato="exportar-acta-del-aparato"
          class="h-9 px-space-md bg-surface-container-lowest text-outline rounded font-body-sm text-body-sm font-medium shadow-sm inline-flex items-center gap-1"
          title="Pendiente: todavía no hay un acta exportable"
        >
          <span class="material-symbols-outlined text-[16px]">file_download</span>
          <span>Exportar acta</span>
        </button>
      </div>
    </section>
  {/each}
{:else}
  <section class="bg-surface-container-low/60 rounded-xl p-space-lg flex items-start gap-space-md">
    <span class="material-symbols-outlined text-secondary text-[20px] mt-0.5">info</span>
    <div class="flex flex-col gap-space-xs">
      <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
        Escribí un número de serie para empezar
      </span>
      <p class="font-body-sm text-body-sm text-secondary max-w-2xl">
        Sirve para cualquier equipo que el sistema conozca: una ONT, un router. El campo
        acepta un lector de código de barras, así que se puede apuntar al aparato en vez de
        tipear el número.
      </p>
    </div>
  </section>
{/if}
