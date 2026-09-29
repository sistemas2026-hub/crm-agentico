<script>
  /**
   * Trasladar: mover material entre ubicaciones internas.
   *
   * Portada de la pantalla "Trasladar" de Stitch. Es la operación más simple del
   * módulo y la que hace útil tener más de una bodega: sin traslado, dos bodegas
   * son dos sistemas separados.
   *
   * SE VALIDA ANTES, COMO EL DESPACHO, porque tampoco ocurrió todavía: el origen
   * y el destino no pueden ser el mismo, y una serie no sale de donde no está.
   *
   * LO QUE EL DISEÑO PIDE Y NO EXISTE
   * «Capacidad de tránsito», un número de protocolo de custodia, el tipo de
   * transporte y el validador de carga. Quedan con `—`. El botón de escaneo
   * rápido tampoco: el campo de serie ya acepta un lector, así que la tarjeta
   * queda como la nota que lo dice y no como un botón que no hace nada.
   */
  import { enhance } from '$app/forms';

  /** @type {{ materiales: any[], internas: any[], existencias: any[], form: any }} */
  let { materiales, internas, existencias, form } = $props();

  // svelte-ignore state_referenced_locally
  // Es a propósito: se quiere el valor INICIAL. Los props de esta pantalla no
  // cambian sin una recarga --vienen del load-- y lo que sigue es una elección
  // del usuario, que no debe volver al primer elemento cuando el padre repinta.
  let origen = $state(internas[0]?.id ?? '');
  // svelte-ignore state_referenced_locally
  // Es a propósito: se quiere el valor INICIAL. Los props de esta pantalla no
  // cambian sin una recarga --vienen del load-- y lo que sigue es una elección
  // del usuario, que no debe volver al primer elemento cuando el padre repinta.
  let destino = $state(internas[1]?.id ?? internas[0]?.id ?? '');
  let lineas = $state([{ n: 1, material: '', cantidad: '', serie: '' }]);
  let siguiente = 2;

  function invertir() {
    const antes = origen;
    origen = destino;
    destino = antes;
  }

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

  /** @param {string} codigo @param {string} ubicacionId */
  function disponible(codigo, ubicacionId) {
    const bloque = existencias.find((b) => b.ubicacion.id === ubicacionId);
    if (!bloque) return null;
    return bloque.materiales.find((m) => m.codigo === codigo) ?? null;
  }

  let mismoSitio = $derived(origen !== '' && origen === destino);
  let nombreOrigen = $derived(internas.find((u) => u.id === origen)?.nombre ?? '');
  let nombreDestino = $derived(internas.find((u) => u.id === destino)?.nombre ?? '');

  const NOMBRE_CLASE = { consumible: 'Consumible', bobina: 'Bobina', serializado: 'Serializado' };

  /** @param {string} valor @param {string} clase */
  function cantidad(valor, clase) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return valor;
    return clase === 'bobina' ? n.toFixed(3) : String(Math.round(n * 1000) / 1000);
  }
</script>

<!-- ============ TIRA DE CONTEXTO ============ -->
<div class="grid grid-cols-1 md:grid-cols-4 gap-space-md w-full">
  <div class="bg-surface-container-lowest p-space-md rounded flex items-center justify-between shadow-sm">
    <div class="flex flex-col min-w-0">
      <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">Sale de</span>
      <span class="font-headline-sm text-headline-sm text-on-surface truncate">
        {nombreOrigen || '—'}
      </span>
    </div>
    <div class="w-9 h-9 rounded bg-surface-container flex items-center justify-center shrink-0">
      <span class="material-symbols-outlined text-primary text-[20px]">warehouse</span>
    </div>
  </div>

  <div class="bg-surface-container-lowest p-space-md rounded flex items-center justify-between shadow-sm">
    <div class="flex flex-col min-w-0">
      <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">Entra a</span>
      <span class="font-headline-sm text-headline-sm text-on-surface truncate">
        {nombreDestino || '—'}
      </span>
    </div>
    <div class="w-9 h-9 rounded bg-surface-container flex items-center justify-center shrink-0">
      <span class="material-symbols-outlined text-secondary text-[20px]">swap_horiz</span>
    </div>
  </div>

  <div class="bg-surface-container-lowest p-space-md rounded flex items-center justify-between shadow-sm">
    <div class="flex flex-col min-w-0">
      <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">Líneas cargadas</span>
      <span class="font-headline-sm text-headline-sm text-on-surface tabular-nums">
        {lineas.filter((l) => l.material).length}
      </span>
    </div>
    <div class="w-9 h-9 rounded bg-surface-container flex items-center justify-center shrink-0">
      <span class="material-symbols-outlined text-secondary text-[20px]">format_list_bulleted</span>
    </div>
  </div>

  <!-- Capacidad de tránsito: el sistema no modela capacidad de ningún vehículo. -->
  <div class="bg-surface-container-lowest p-space-md rounded flex items-center justify-between shadow-sm" data-sin-dato="capacidad-de-transito">
    <div class="flex flex-col min-w-0">
      <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">Capacidad de tránsito</span>
      <span class="font-headline-sm text-headline-sm text-on-surface truncate">—</span>
    </div>
    <div class="w-9 h-9 rounded bg-surface-container flex items-center justify-center shrink-0">
      <span class="material-symbols-outlined text-secondary text-[20px]">verified_user</span>
    </div>
  </div>
</div>

<!-- ============ VALIDACIONES ============ -->
<div class="flex flex-col gap-space-xs w-full">
  {#if mismoSitio}
    <div class="bg-error-container text-on-error-container px-space-lg py-space-md rounded flex items-start gap-space-md shadow-sm">
      <span class="material-symbols-outlined text-error text-[20px] shrink-0 mt-0.5">error_outline</span>
      <div class="flex flex-col flex-1 min-w-0">
        <span class="font-headline-sm text-body-md font-semibold text-error">
          El origen y el destino son la misma ubicación
        </span>
        <p class="font-body-md text-body-md text-on-error-container mt-0.5">
          Eso no es un traslado. Elegí dos ubicaciones distintas, o usá el botón de
          invertir.
        </p>
      </div>
    </div>
  {/if}

  {#if form?.error}
    <!--
      Cuando una serie no está en el origen, el mensaje del servidor nombra la
      custodia donde figura. Viaja entero, igual que en el despacho.
    -->
    <div class="bg-surface-container-highest px-space-lg py-space-md rounded flex items-start gap-space-md shadow-sm border-l-4 border-error">
      <span class="material-symbols-outlined text-error text-[20px] shrink-0 mt-0.5">lock_person</span>
      <div class="flex flex-col flex-1 min-w-0">
        <span class="font-headline-sm text-body-md font-semibold text-on-surface">
          El traslado no se registró
        </span>
        <p class="font-body-md text-body-md text-on-surface-variant mt-0.5">{form.error}</p>
      </div>
    </div>
  {/if}

  {#if form?.hecho}
    <div class="bg-primary-fixed/40 px-space-lg py-space-md rounded flex items-start gap-space-md shadow-sm">
      <span class="material-symbols-outlined text-primary text-[20px] shrink-0 mt-0.5">check_circle</span>
      <p class="font-body-md text-body-md text-on-surface">{form.hecho}</p>
    </div>
  {/if}
</div>

<form method="POST" action="?/traslado" use:enhance class="grid grid-cols-1 lg:grid-cols-12 gap-space-lg w-full items-start">
  <!-- ============ COLUMNA IZQUIERDA: LA RUTA ============ -->
  <div class="lg:col-span-4 flex flex-col gap-space-lg">
    <div class="bg-surface-container-lowest p-space-xl rounded shadow-sm flex flex-col gap-space-lg max-w-[540px] w-full">
      <div>
        <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
          Parámetros de ruta
        </span>
        <h2 class="font-headline-md text-headline-md text-on-surface mt-space-xs">
          Puntos de transferencia
        </h2>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5">
          De dónde sale y a dónde va. Las dos son ubicaciones internas: para entregarle a
          un técnico está el despacho.
        </p>
      </div>

      <div class="flex flex-col gap-space-md">
        <div class="flex flex-col gap-space-xs">
          <label for="tr-origen" class="font-table-header text-table-header text-secondary uppercase">
            Ubicación origen <span class="text-error">*</span>
          </label>
          <div class="relative">
            <select
              id="tr-origen"
              name="ubicacion_origen"
              bind:value={origen}
              required
              class="w-full h-10 px-space-md pr-10 bg-surface-container-lowest text-on-surface rounded appearance-none font-body-md text-body-md focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
            >
              {#each internas as u (u.id)}
                <option value={u.id}>{u.nombre}</option>
              {/each}
            </select>
            <span class="material-symbols-outlined absolute right-3 top-2.5 text-secondary pointer-events-none text-[20px]">
              unfold_more
            </span>
          </div>
        </div>

        <div class="flex items-center justify-center my-0.5">
          <button
            type="button"
            onclick={invertir}
            class="w-8 h-8 rounded-full bg-surface-container-low hover:bg-surface-container flex items-center justify-center text-secondary transition-colors"
            title="Invertir origen y destino"
          >
            <span class="material-symbols-outlined text-[18px]">sync_alt</span>
          </button>
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="tr-destino" class="font-table-header text-table-header text-secondary uppercase">
            Ubicación destino <span class="text-error">*</span>
          </label>
          <div class="relative">
            <select
              id="tr-destino"
              name="ubicacion_destino"
              bind:value={destino}
              required
              class="w-full h-10 px-space-md pr-10 bg-surface-container-lowest text-on-surface rounded appearance-none font-body-md text-body-md focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
            >
              {#each internas as u (u.id)}
                <option value={u.id}>{u.nombre}</option>
              {/each}
            </select>
            <span class="material-symbols-outlined absolute right-3 top-2.5 text-secondary pointer-events-none text-[20px]">
              unfold_more
            </span>
          </div>
        </div>

        <div class="flex flex-col gap-space-xs pt-space-xs">
          <label for="tr-motivo" class="font-table-header text-table-header text-secondary uppercase">
            Motivo <span class="text-secondary opacity-75 font-normal">(opcional)</span>
          </label>
          <input
            id="tr-motivo"
            name="motivo"
            placeholder="reparto semanal"
            class="w-full h-10 px-space-md bg-surface-container-lowest text-on-surface placeholder:text-secondary rounded font-body-md text-body-md focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
          />
          <span class="font-body-sm text-body-sm text-secondary">
            Queda en cada movimiento del traslado.
          </span>
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="tr-referencia" class="font-table-header text-table-header text-secondary uppercase">
            N° de hoja de ruta <span class="text-secondary opacity-75 font-normal">(opcional)</span>
          </label>
          <input
            id="tr-referencia"
            name="referencia"
            placeholder="HR-0884"
            class="w-full h-10 px-space-md bg-surface-container-lowest text-on-surface placeholder:text-secondary rounded font-label-code text-label-code focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
          />
          <span class="font-body-sm text-body-sm text-secondary">
            Con número, reenviar el formulario no traslada dos veces.
          </span>
        </div>
      </div>

      <!--
        Los metadatos de la orden que pide el diseño. La fecha es real; el
        validador de carga y el tipo de transporte no existen en el sistema.
      -->
      <div class="bg-surface-container-low p-space-md rounded flex flex-col gap-space-xs font-body-sm text-body-sm text-secondary">
        <div class="flex justify-between items-center gap-space-sm">
          <span>Se registra al enviar:</span>
          <span class="font-label-numeric text-on-surface">ahora</span>
        </div>
        <div class="flex justify-between items-center gap-space-sm" data-sin-dato="validador-de-carga">
          <span>Validador de carga:</span>
          <span class="font-body-sm text-on-surface">—</span>
        </div>
        <div class="flex justify-between items-center gap-space-sm" data-sin-dato="tipo-de-transporte">
          <span>Tipo de transporte:</span>
          <span class="font-body-sm text-on-surface">—</span>
        </div>
      </div>
    </div>

    <div class="bg-surface-container-lowest p-space-lg rounded shadow-sm max-w-[540px] w-full flex flex-col gap-space-sm">
      <span class="font-headline-sm text-body-md font-semibold text-on-surface flex items-center gap-space-xs">
        <span class="material-symbols-outlined text-[18px] text-primary">qr_code_scanner</span>
        Lectura de series
      </span>
      <p class="font-body-sm text-body-sm text-secondary">
        Los campos de serie de la tabla aceptan un lector de código de barras: se apunta al
        equipo y el número entra solo. Un aparato serializado se traslada de a uno, con su
        número, porque el sistema tiene que poder decir después dónde está cada uno.
      </p>
    </div>
  </div>

  <!-- ============ COLUMNA DERECHA: LOS MATERIALES ============ -->
  <div class="lg:col-span-8 flex flex-col gap-space-lg">
    <div class="bg-surface-container-lowest rounded shadow-sm overflow-hidden">
      <div class="p-space-lg flex items-center justify-between gap-space-md flex-wrap">
        <div>
          <h3 class="font-headline-sm text-headline-sm text-on-surface">Materiales a trasladar</h3>
          <p class="font-body-sm text-body-sm text-secondary mt-0.5">
            La columna de la derecha dice cuánto hay en {nombreOrigen || 'el origen'} ahora
            mismo.
          </p>
        </div>
        <button
          type="button"
          onclick={agregar}
          class="h-9 px-4 bg-surface-container-lowest hover:bg-surface-container text-on-surface font-body-sm text-body-sm font-medium rounded shadow-sm transition-colors flex items-center gap-1.5"
        >
          <span class="material-symbols-outlined text-[18px] text-primary">add_circle</span>
          <span>Agregar material</span>
        </button>
      </div>

      <div class="w-full overflow-x-auto">
        <table class="w-full text-left">
          <thead>
            <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
              <th class="py-2.5 px-space-md tracking-wider">Material</th>
              <th class="py-2.5 px-space-md tracking-wider w-32">Tipo</th>
              <th class="py-2.5 px-space-md tracking-wider w-56">Cantidad o serie</th>
              <th class="py-2.5 px-space-md tracking-wider text-right w-48">Disponible en origen</th>
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
                </td>

                <td class="py-3 px-space-md">
                  {#if m}
                    <span class="px-2 py-0.5 rounded bg-surface-container text-secondary font-label-numeric text-body-sm">
                      {NOMBRE_CLASE[m.clase] ?? m.clase}
                    </span>
                  {:else}
                    <span class="font-body-sm text-body-sm text-secondary">—</span>
                  {/if}
                </td>

                <td class="py-3 px-space-md">
                  {#if m?.es_serializado}
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
                    <input type="hidden" name="cantidad" value="1" />
                  {:else}
                    <div class="flex items-center gap-2">
                      <input
                        name="cantidad"
                        type="number"
                        step={m?.clase === 'bobina' ? '0.001' : '1'}
                        min="0.001"
                        class="w-28 h-9 px-2.5 text-right font-label-numeric text-body-md bg-surface-container-lowest text-on-surface rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                      <span class="font-body-sm text-body-sm text-secondary">{m?.unidad ?? ''}</span>
                      <input type="hidden" name="serie" value="" />
                    </div>
                  {/if}
                </td>

                <td class="py-3 px-space-md text-right">
                  {#if !linea.material}
                    <span class="font-body-sm text-body-sm text-secondary">—</span>
                  {:else if disp === null}
                    <span class="font-body-sm text-body-sm text-tertiary">
                      sin movimientos en el origen
                    </span>
                  {:else}
                    <span
                      class="font-label-numeric text-body-md font-medium tabular-nums {Number(disp.existencia) <= 0
                        ? 'text-error'
                        : 'text-on-surface'}"
                    >
                      {cantidad(disp.existencia, disp.clase)} {disp.unidad}
                    </span>
                  {/if}
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
    </div>

    <!-- Pie de acción -->
    <div class="flex flex-wrap items-center justify-between gap-space-md p-space-md bg-surface-container-lowest rounded shadow-sm">
      <div class="flex items-start gap-space-sm text-secondary max-w-xl">
        <span class="material-symbols-outlined text-[18px] text-primary shrink-0">info</span>
        <span class="font-body-sm text-body-sm">
          Un traslado no cambia cuánto hay en la empresa: cambia dónde está. La existencia
          del origen baja y la del destino sube por el mismo movimiento.
        </span>
      </div>
      <button
        type="submit"
        disabled={mismoSitio}
        class="h-10 px-space-xl font-headline-sm text-body-md font-medium rounded-lg shadow-sm transition-colors flex items-center gap-space-xs {mismoSitio
          ? 'bg-surface-container text-outline'
          : 'bg-primary-container hover:bg-primary text-on-primary'}"
      >
        <span class="material-symbols-outlined text-[20px]">outbound</span>
        <span>Trasladar</span>
      </button>
    </div>
  </div>
</form>
