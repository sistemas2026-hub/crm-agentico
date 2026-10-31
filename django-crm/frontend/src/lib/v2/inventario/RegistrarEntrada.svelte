<script>
  /**
   * Registrar entrada: material que ENTRA al sistema sin una compra registrada.
   *
   * Portada de la pantalla "Registrar entrada" del proyecto de Stitch. Dos
   * columnas: el formulario a la izquierda (540px, como el diseño) y el contexto
   * operativo a la derecha.
   *
   * EL BUSCADOR DE MATERIAL ES UN COMBO DE VERDAD, NO UN SELECT
   * El diseño pide un campo de búsqueda con un desplegable que muestra el código,
   * el nombre y la clase de cada material. Se replica con estado local: filtrar
   * por código o nombre es lo que hace usable un catálogo de cien materiales, y
   * un `<select>` nativo no lo permite. El valor que viaja al servidor es el
   * código, en un campo oculto.
   *
   * LO QUE EL DISEÑO PIDE Y NO EXISTE
   * Las tres métricas de la derecha (entradas de hoy, entradas sin factura,
   * porcentaje a bodega), el gráfico de la semana y el historial de entradas: no
   * hay endpoint para ninguno. Quedan puestos, vacíos y marcados. Un gráfico con
   * barras inventadas es peor que uno vacío: parece información.
   */
  import { enhance } from '$app/forms';

  /** @type {{ materiales: any[], internas: any[], form: any }} */
  let { materiales, internas, form } = $props();

  let busqueda = $state('');
  let abierto = $state(false);
  /** El material elegido, entero: de él salen la clase, la unidad y el código. */
  let elegido = $state(/** @type {any} */ (null));

  let filtrados = $derived(
    busqueda.trim() === ''
      ? materiales
      : materiales.filter((m) => {
          const q = busqueda.toLowerCase();
          return (
            (m.codigo ?? '').toLowerCase().includes(q) ||
            (m.nombre ?? '').toLowerCase().includes(q)
          );
        })
  );

  const NOMBRE_CLASE = {
    consumible: 'Consumible',
    bobina: 'Bobina',
    serializado: 'Serializado'
  };

  /** Lo que el diseño muestra debajo del campo, según la clase del material. */
  const AYUDA_CLASE = {
    consumible: 'Se cuenta por piezas completas. Una fracción se trunca hacia abajo: inventar media unidad es peor que perderla.',
    bobina: 'Admite decimales: la fibra se consume en metros y una bobina se fracciona.',
    serializado: 'Cada unidad es un aparato con número de serie. La cantidad es 1 y la serie es obligatoria.'
  };

  const TAG_CANTIDAD = {
    consumible: 'Entero (unidades)',
    bobina: 'Decimal (metros)',
    serializado: '1 unidad automática'
  };

  let esSerializado = $derived(elegido?.es_serializado === true);

  /**
   * Si se cargan VARIAS series de una.
   *
   * Un lote de 50 ONT eran 50 envios del formulario. El backend ya lo soportaba
   * --la clave de idempotencia de una entrada incluye la serie, asi que 50
   * series con la misma factura son 50 claves distintas-- y lo unico que
   * faltaba era ofrecerlo.
   */
  let varias = $state(false);
  let series = $state('');

  /** Cuantas series se leen de lo pegado, sin contar repetidas ni vacias. */
  let cuantas = $derived(
    new Set(
      series
        .split(/[\s,;]+/)
        .map((x) => x.trim().toUpperCase())
        .filter(Boolean)
    ).size
  );

  /** Las que estan dos veces en la propia lista: el error mas comun al copiar. */
  let repetidasAhora = $derived.by(() => {
    const vistas = new Set();
    const repes = new Set();
    for (const x of series
      .split(/[\s,;]+/)
      .map((y) => y.trim().toUpperCase())
      .filter(Boolean)) {
      if (vistas.has(x)) repes.add(x);
      vistas.add(x);
    }
    return [...repes];
  });
  let clase = $derived(elegido?.clase ?? 'consumible');

  /** @param {any} m */
  function elegir(m) {
    elegido = m;
    busqueda = `${m.codigo} · ${m.nombre}`;
    abierto = false;
  }

  function limpiar() {
    elegido = null;
    busqueda = '';
    abierto = false;
  }
</script>

<div class="grid grid-cols-1 xl:grid-cols-12 gap-space-xl items-start">
  <!-- ============ COLUMNA IZQUIERDA: EL FORMULARIO ============ -->
  <div class="xl:col-span-7 flex flex-col items-center">
    <div class="w-full max-w-[540px] flex flex-col gap-space-lg">
      <!-- Cabecera del módulo -->
      <div class="flex flex-col gap-1 bg-surface-container-lowest p-space-lg rounded-xl shadow-sm">
        <div class="flex items-center justify-between gap-space-sm">
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-container text-secondary text-body-sm font-label-numeric font-medium uppercase tracking-wider">
            <span class="material-symbols-outlined text-[15px]">input</span>
            Ingreso externo
          </span>
        </div>
        <h2 class="font-headline-sm text-headline-sm text-on-surface mt-space-xs font-semibold">
          Registrar entrada
        </h2>
        <p class="font-body-sm text-body-sm text-secondary">
          Usá esta operación cuando un material entra al inventario sin una compra
          registrada: un equipo retirado de la casa de un cliente, o un lote que llegó
          sin papeles. Es el único movimiento sin origen, y ese hueco es la frontera del
          sistema.
        </p>
      </div>

      <!-- El formulario -->
      <form
        method="POST"
        action="?/entrada"
        use:enhance
        class="flex flex-col gap-space-lg bg-surface-container-lowest p-space-lg rounded-xl shadow-sm"
      >
        <!-- Campo 1: material -->
        <div class="flex flex-col gap-space-xs">
          <div class="flex items-center justify-between gap-space-sm">
            <span class="font-table-header text-table-header text-on-surface uppercase tracking-wider flex items-center gap-1">
              Material
              <span class="text-error font-bold">*</span>
            </span>
            {#if elegido}
              <span class="px-2 py-0.5 rounded bg-surface-container text-secondary font-label-numeric text-body-sm font-medium">
                {NOMBRE_CLASE[clase] ?? clase}
              </span>
            {/if}
          </div>

          <div class="relative">
            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-secondary">
              <span class="material-symbols-outlined text-[18px]">search</span>
            </div>
            <input
              type="text"
              autocomplete="off"
              bind:value={busqueda}
              onfocus={() => (abierto = true)}
              oninput={() => {
                abierto = true;
                elegido = null;
              }}
              placeholder="Buscar por código o nombre"
              class="w-full h-10 pl-9 pr-9 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none placeholder:text-secondary/60"
            />
            <button
              type="button"
              onclick={() => (abierto = !abierto)}
              class="absolute inset-y-0 right-0 pr-3 flex items-center text-secondary hover:text-on-surface"
              aria-label="Ver el catálogo"
            >
              <span class="material-symbols-outlined text-[18px]">unfold_more</span>
            </button>
          </div>

          <!-- El código es lo que viaja: la API acepta el código o el id. -->
          <input type="hidden" name="material" value={elegido?.codigo ?? ''} />

          {#if abierto}
            <div class="flex flex-col gap-1 p-1 bg-surface-container-lowest rounded-xl shadow-md mt-1 max-h-72 overflow-y-auto">
              {#if filtrados.length === 0}
                <p class="px-3 py-2 font-body-sm text-body-sm text-secondary">
                  Ningún material del catálogo coincide con «{busqueda}».
                </p>
              {/if}
              {#each filtrados as m (m.id)}
                <button
                  type="button"
                  onclick={() => elegir(m)}
                  class="w-full text-left px-3 py-2 text-body-sm text-on-surface hover:bg-surface-container-low rounded flex items-center justify-between gap-space-sm"
                >
                  <span class="font-label-code">{m.codigo} · {m.nombre}</span>
                  {#if m.es_serializado}
                    <span class="text-body-sm text-primary font-medium bg-primary-fixed px-1.5 py-0.5 rounded shrink-0">
                      Serializado
                    </span>
                  {:else}
                    <span class="text-body-sm text-secondary bg-surface-container px-1.5 py-0.5 rounded shrink-0">
                      {NOMBRE_CLASE[m.clase] ?? m.clase}
                    </span>
                  {/if}
                </button>
              {/each}
            </div>
          {/if}

          {#if elegido}
            <p class="font-body-sm text-body-sm text-secondary flex items-start gap-1">
              <span class="material-symbols-outlined text-[15px] text-secondary shrink-0">inventory</span>
              <span>
                <span class="font-medium text-on-surface">{NOMBRE_CLASE[clase] ?? clase}</span>.
                {AYUDA_CLASE[clase] ?? ''}
              </span>
            </p>
          {/if}
        </div>

        <!-- Campo 2: cantidad, o serie si el material es serializado -->
        <div class="flex flex-col gap-space-xs">
          <div class="flex items-center justify-between gap-space-sm">
            <span class="font-table-header text-table-header text-on-surface uppercase tracking-wider flex items-center gap-1">
              {esSerializado ? 'Número de serie' : 'Cantidad ingresada'}
              <span class="text-error font-bold">*</span>
            </span>
            <span class="font-label-code text-body-sm text-secondary">
              {TAG_CANTIDAD[clase] ?? 'Entero (unidades)'}
            </span>
          </div>

          {#if esSerializado}
            <!--
              UNA O VARIAS. Una recepcion real no trae un equipo: trae una caja.
              Cargarlos de a uno eran cincuenta envios de este formulario.
            -->
            <div class="flex items-center gap-space-sm">
              <button
                type="button"
                onclick={() => (varias = false)}
                class="h-8 px-space-md rounded font-body-sm text-body-sm transition-colors {!varias
                  ? 'bg-primary-fixed text-on-primary-fixed'
                  : 'bg-surface-container-low text-secondary hover:bg-surface-container'}"
              >
                Una serie
              </button>
              <button
                type="button"
                onclick={() => (varias = true)}
                class="h-8 px-space-md rounded font-body-sm text-body-sm transition-colors {varias
                  ? 'bg-primary-fixed text-on-primary-fixed'
                  : 'bg-surface-container-low text-secondary hover:bg-surface-container'}"
              >
                Varias series
              </button>
            </div>

            {#if varias}
              <textarea
                name="series"
                bind:value={series}
                rows="8"
                required
                placeholder={`CDTC505AEA5F\nCDTC505AEA60\nCDTC505AEA61`}
                class="w-full px-3 py-2 bg-surface-container-lowest text-on-surface font-label-code text-label-code uppercase tracking-wider rounded shadow-sm focus:outline-none placeholder:text-secondary/60"
              ></textarea>
              <div class="flex items-center justify-between gap-space-sm font-body-sm text-body-sm">
                <span class="text-secondary">
                  Una por línea. También sirve separadas por coma.
                </span>
                <span class="text-on-surface font-label-numeric">
                  {cuantas}
                  {cuantas === 1 ? 'serie' : 'series'}
                </span>
              </div>

              {#if repetidasAhora.length}
                <!--
                  Se avisa ANTES de enviar: pegar dos veces la misma serie es el
                  error mas comun al copiar de una factura, y el rechazo del
                  servidor se lee como «ya esta en otra custodia», que asusta
                  sin motivo.
                -->
                <div class="flex items-start gap-2 p-2 bg-error-container/40 rounded text-body-sm text-on-error-container">
                  <span class="material-symbols-outlined text-[16px] shrink-0">content_copy</span>
                  <span>
                    {repetidasAhora.length === 1 ? 'Esta serie está' : 'Estas series están'}
                    dos veces en la lista y se {repetidasAhora.length === 1
                      ? 'va a cargar una sola vez'
                      : 'van a cargar una sola vez'}:
                    <span class="font-label-code">{repetidasAhora.join(', ')}</span>
                  </span>
                </div>
              {/if}

              <div class="flex items-start gap-2 p-2 bg-surface-container-low rounded text-body-sm text-secondary">
                <span class="material-symbols-outlined text-primary text-[16px] shrink-0">info</span>
                <span>
                  Cada serie entra por separado. Si alguna ya figura en otra custodia, esa
                  se informa y <strong>las demás entran igual</strong>. Con varias series la
                  referencia de origen es obligatoria: es lo que evita duplicar la
                  recepción entera si se envía dos veces.
                </span>
              </div>
            {:else}
              <div class="relative">
                <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-secondary">
                  <span class="material-symbols-outlined text-[18px]">barcode_scanner</span>
                </div>
                <input
                  name="serie"
                  required
                  placeholder="HWTCA6FB5263"
                  class="w-full h-10 pl-9 pr-3 bg-surface-container-lowest text-on-surface font-label-code text-label-code uppercase tracking-wider rounded shadow-sm focus:outline-none placeholder:text-secondary/60"
                />
              </div>
              <div class="flex items-start gap-2 p-2 bg-surface-container-low rounded text-body-sm text-secondary">
                <span class="material-symbols-outlined text-primary text-[16px] shrink-0">info</span>
                <span>
                  En un equipo serializado la cantidad es 1. Si esa serie ya figura en otra
                  custodia, la entrada lo va a decir: un aparato no puede estar en dos
                  lugares.
                </span>
              </div>
            {/if}
            <!-- La cantidad no se pide: un aparato es uno. -->
            <input type="hidden" name="cantidad" value="1" />
          {:else}
            <div class="relative">
              <input
                name="cantidad"
                type="number"
                step={clase === 'bobina' ? '0.001' : '1'}
                min={clase === 'bobina' ? '0.001' : '1'}
                required
                placeholder={clase === 'bobina' ? '500.00' : '0'}
                class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-label-numeric text-body-md rounded shadow-sm focus:outline-none placeholder:text-secondary/60"
              />
              <div class="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-secondary text-body-sm font-label-numeric">
                {elegido?.unidad ?? ''}
              </div>
            </div>
            <p class="font-body-sm text-body-sm text-secondary">
              Ingresá la cantidad física contada al momento de la recepción.
            </p>
          {/if}
        </div>

        <!-- Campo 3: ubicación de destino -->
        <div class="flex flex-col gap-space-xs">
          <span class="font-table-header text-table-header text-on-surface uppercase tracking-wider flex items-center gap-1">
            Ubicación de destino
            <span class="text-error font-bold">*</span>
          </span>
          <div class="relative">
            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-secondary">
              <span class="material-symbols-outlined text-[18px]">warehouse</span>
            </div>
            <select
              name="ubicacion_destino"
              required
              class="w-full h-10 pl-9 pr-9 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm appearance-none focus:outline-none cursor-pointer"
            >
              {#each internas as u (u.id)}
                <option value={u.id}>{u.nombre}</option>
              {/each}
            </select>
            <div class="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-secondary">
              <span class="material-symbols-outlined text-[18px]">expand_more</span>
            </div>
          </div>
          <p class="font-body-sm text-body-sm text-secondary">
            Lugar físico donde el material queda disponible para despacharse.
          </p>
        </div>

        <!-- Campo 4: referencia de origen -->
        <div class="flex flex-col gap-space-xs">
          <div class="flex items-center justify-between gap-space-sm">
            <span class="font-table-header text-table-header text-on-surface uppercase tracking-wider">
              Referencia de origen
            </span>
            <span class="text-body-sm font-label-numeric text-secondary bg-surface-container-low px-1.5 py-0.5 rounded">
              Opcional
            </span>
          </div>
          <div class="relative">
            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-secondary">
              <span class="material-symbols-outlined text-[18px]">tag</span>
            </div>
            <input
              name="origen_ref"
              placeholder="FAC-001"
              class="w-full h-10 pl-9 pr-3 bg-surface-container-lowest text-on-surface font-label-code text-body-md uppercase rounded shadow-sm focus:outline-none placeholder:text-secondary/60"
            />
          </div>
          <div class="flex items-start gap-2 bg-surface-container-low p-space-sm rounded">
            <span class="material-symbols-outlined text-secondary text-[16px] shrink-0 mt-0.5">help_outline</span>
            <p class="font-body-sm text-body-sm text-secondary leading-tight">
              Una referencia evita duplicar la misma entrada. Sin referencia el sistema no
              puede saber si un segundo registro es el mismo hecho, así que la entrada se
              guarda igual —el material ya llegó— pero queda marcada como no protegida.
            </p>
          </div>
        </div>

        <div class="pt-space-sm flex items-center justify-end gap-space-md">
          <button
            type="button"
            onclick={limpiar}
            class="h-10 px-4 bg-surface-container text-on-surface hover:bg-surface-container-high rounded font-body-md text-body-md font-medium transition-colors"
          >
            Restablecer
          </button>
          <button
            type="submit"
            class="h-10 px-5 bg-primary-container hover:bg-primary text-on-primary rounded font-body-md text-body-md font-medium flex items-center gap-2 shadow-sm transition-colors"
          >
            <span class="material-symbols-outlined text-[18px]">add_box</span>
            <span>Registrar entrada</span>
          </button>
        </div>
      </form>

      <!--
        EL RESULTADO DE UN LOTE, LINEA POR LINEA.
        No alcanza con «se registro»: en una recepcion de cincuenta importa
        cuales NO entraron y por que, porque esas hay que buscarlas.
      -->
      {#if form?.lote}
        {@const L = form.lote}
        <div class="w-full flex flex-col gap-space-sm p-space-md rounded-xl bg-surface-container-lowest shadow-sm">
          <div class="flex items-start gap-space-md">
            <div class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined text-primary text-[20px]">
                {L.fallaron.length ? 'rule' : 'check_circle'}
              </span>
            </div>
            <div class="flex flex-col gap-0.5 flex-1 min-w-0">
              <span class="font-headline-sm text-body-md font-semibold text-on-surface">
                Entraron {L.entraron} de {L.total}
              </span>
              <p class="font-body-sm text-body-sm text-secondary">
                La existencia de esa ubicación ya lo refleja: se calcula sumando el libro.
              </p>
            </div>
          </div>

          {#if L.repetidas.length}
            <p class="font-body-sm text-body-sm text-secondary pl-11">
              {L.repetidas.length === 1 ? 'Una serie venía' : `${L.repetidas.length} series venían`}
              repetida{L.repetidas.length === 1 ? '' : 's'} en la lista y se cargó una sola
              vez cada una:
              <span class="font-label-code">{L.repetidas.join(', ')}</span>
            </p>
          {/if}

          {#if L.fallaron.length}
            <div class="pl-11 flex flex-col gap-1">
              <span class="font-body-sm text-body-sm text-on-surface">
                {L.fallaron.length === 1 ? 'Esta no entró' : `Estas ${L.fallaron.length} no entraron`}:
              </span>
              {#each L.fallaron as f (f.serie)}
                <div class="flex items-start gap-2 font-body-sm text-body-sm">
                  <span class="font-label-code text-on-surface shrink-0">{f.serie}</span>
                  <span class="text-secondary">{f.motivo}</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}

      <!-- El resultado, cuando hay uno -->
      {#if form?.hecho}
        <div class="w-full flex items-start gap-space-md p-space-md rounded-xl bg-surface-container-lowest shadow-sm">
          <div class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-primary text-[20px]">check_circle</span>
          </div>
          <div class="flex flex-col gap-0.5 flex-1 min-w-0">
            <span class="font-headline-sm text-body-md font-semibold text-on-surface">
              {form.hecho}
            </span>
            <p class="font-body-sm text-body-sm text-secondary">
              La existencia de esa ubicación ya lo refleja: se calcula sumando el libro, no
              hay contador que actualizar.
            </p>
          </div>
        </div>
      {/if}
    </div>
  </div>

  <!-- ============ COLUMNA DERECHA: CONTEXTO ============ -->
  <div class="xl:col-span-5 flex flex-col gap-space-lg">
    <!-- Las reglas que aplican al registrar una entrada. Texto, no datos. -->
    <div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md">
      <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
        Qué valida una entrada
      </span>
      <div class="grid grid-cols-1 gap-space-sm">
        <div class="p-space-sm rounded bg-surface-container-low flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-primary text-[18px] shrink-0 mt-0.5">verified</span>
          <div class="flex flex-col min-w-0">
            <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
              El destino es obligatorio
            </span>
            <span class="font-body-sm text-body-sm text-secondary">
              Nada entra a un limbo: una entrada dice a qué ubicación llega. El origen, en
              cambio, queda vacío a propósito — el material viene de afuera del sistema.
            </span>
          </div>
        </div>
        <div class="p-space-sm rounded bg-surface-container-low flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-tertiary text-[18px] shrink-0 mt-0.5">lock_clock</span>
          <div class="flex flex-col min-w-0">
            <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
              Una serie está en un solo lugar
            </span>
            <span class="font-body-sm text-body-sm text-secondary">
              Si el número ya figura en otra custodia, el sistema lo dice y nombra dónde
              está, en vez de aceptar dos veces el mismo aparato.
            </span>
          </div>
        </div>
        <div class="p-space-sm rounded bg-surface-container-low flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-secondary text-[18px] shrink-0 mt-0.5">straighten</span>
          <div class="flex flex-col min-w-0">
            <span class="font-headline-sm text-body-sm font-semibold text-on-surface">
              Las bobinas se fraccionan
            </span>
            <span class="font-body-sm text-body-sm text-secondary">
              Admiten decimales (845.500 m). Un consumible, no: 2.7 conectores se guarda
              como 2, truncado hacia abajo.
            </span>
          </div>
        </div>
      </div>
    </div>

    <!--
      TRES INDICADORES QUE EL DISEÑO PIDE Y LA API NO TIENE.
      Harían falta entradas filtradas por fecha y por presencia de compra; ese
      endpoint no existe. Quedan con `—`: un número inventado acá se leería como
      actividad real del día.
    -->
    <div class="grid grid-cols-3 gap-space-md" data-sin-dato="metricas-de-entrada">
      <div class="h-[72px] bg-surface-container-lowest p-space-sm rounded-xl shadow-sm flex flex-col justify-between">
        <span class="font-table-header text-table-header text-secondary uppercase truncate">Entradas hoy</span>
        <span class="font-headline-md text-headline-md text-on-surface tabular-nums">—</span>
      </div>
      <div class="h-[72px] bg-surface-container-lowest p-space-sm rounded-xl shadow-sm flex flex-col justify-between">
        <span class="font-table-header text-table-header text-secondary uppercase truncate">Sin factura</span>
        <span class="font-headline-md text-headline-md text-tertiary tabular-nums">—</span>
      </div>
      <div class="h-[72px] bg-surface-container-lowest p-space-sm rounded-xl shadow-sm flex flex-col justify-between">
        <span class="font-table-header text-table-header text-secondary uppercase truncate">A bodega</span>
        <span class="font-headline-md text-headline-md text-primary tabular-nums">—</span>
      </div>
    </div>

    <!--
      El gráfico del diseño, con su marco y sin barras. Las del diseño eran
      dibujadas: no hay serie temporal de entradas en la API. Un gráfico vacío se
      lee como «falta el dato»; uno con barras inventadas, como información.
    -->
    <div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md" data-sin-dato="flujo-de-entrada-semanal">
      <div class="flex items-start justify-between gap-space-sm">
        <div class="flex flex-col">
          <span class="font-table-header text-table-header text-secondary uppercase tracking-wider">
            Flujo de entrada por depósito
          </span>
          <span class="font-body-sm text-body-sm text-secondary">Semana actual</span>
        </div>
        <span class="px-2 py-0.5 rounded bg-surface-container text-body-sm font-label-code text-secondary">
          sin dato
        </span>
      </div>
      <div class="w-full pt-2">
        <svg class="w-full h-24 overflow-visible text-secondary" viewBox="0 0 420 90" role="img" aria-label="Sin datos para graficar">
          <line stroke="currentColor" stroke-dasharray="2 2" stroke-opacity="0.1" x1="0" x2="420" y1="20" y2="20" />
          <line stroke="currentColor" stroke-dasharray="2 2" stroke-opacity="0.1" x1="0" x2="420" y1="50" y2="50" />
          <line stroke="currentColor" stroke-opacity="0.15" x1="0" x2="420" y1="80" y2="80" />
          <text x="210" y="48" text-anchor="middle" class="fill-secondary" style="font-size:11px">
            todavía no hay serie de entradas para graficar
          </text>
        </svg>
        <div class="flex items-center justify-between text-body-sm font-label-code text-secondary pt-1 px-1">
          <span>LUN</span><span>MAR</span><span>MIÉ</span><span>JUE</span>
          <span>VIE</span><span>SÁB</span><span>DOM</span>
        </div>
      </div>
      <div class="flex items-center gap-space-lg pt-1 text-body-sm text-secondary">
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-primary"></span>
          <span>Bodegas</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-secondary-container"></span>
          <span>Vehículos</span>
        </div>
      </div>
    </div>

    <!--
      El historial de entradas del diseño. La API no expone «las últimas
      entradas»: los movimientos se consultan por ubicación o por serie. Queda la
      tabla con su encabezado y el estado vacío diciendo qué falta.
    -->
    <div class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden" data-sin-dato="historial-de-entradas">
      <div class="p-space-md flex items-center justify-between gap-space-sm">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-secondary text-[18px]">history</span>
          <span class="font-headline-sm text-body-md font-semibold text-on-surface">
            Últimas entradas
          </span>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-body-sm">
          <thead class="bg-surface-container-low text-secondary font-table-header uppercase text-table-header tracking-wider">
            <tr>
              <th class="py-2 px-space-md font-semibold">Código</th>
              <th class="py-2 px-space-md font-semibold">Destino</th>
              <th class="py-2 px-space-md font-semibold text-right">Cantidad</th>
              <th class="py-2 px-space-md font-semibold">Referencia</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colspan="4" class="py-space-md px-space-md font-body-sm text-body-sm text-secondary">
                Todavía no se puede listar: la API consulta movimientos por ubicación o por
                serie, no las últimas entradas. Mientras tanto, la pestaña Existencias
                muestra el resultado de cada una.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
