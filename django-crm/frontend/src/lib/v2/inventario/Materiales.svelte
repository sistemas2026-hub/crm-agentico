<script>
  /**
   * Materiales: el maestro del catálogo.
   *
   * DOS PREGUNTAS DISTINTAS, DOS PESTAÑAS
   *     Materiales   «¿qué cosas maneja esta empresa?»   -- esto
   *     Existencias  «¿cuánto tenemos y dónde está?»     -- el libro
   * La segunda cambia todo el día y la primera casi nunca. Mezclarlas es lo que
   * vuelve ilegible un módulo de inventario.
   *
   * TRES CAMPOS SE BLOQUEAN CUANDO EL MATERIAL YA TIENE MOVIMIENTOS
   *     código   es lo que aparece en las actas y en los registros viejos
   *     clase    un consumible que pasa a serializado deja movimientos sin serie
   *     unidad   si antes medía metros y ahora midiera unidades, TODO el libro
   *              cambia de significado sin que ningún movimiento se toque
   * El nombre y la categoría se corrigen siempre: son descriptivos.
   *
   * Y EL BLOQUEO DE ACÁ ES SOLO UNA AYUDA. La regla vive en el servidor, que
   * rechaza el cambio aunque el PATCH llegue a mano. Deshabilitar un campo en la
   * pantalla no protege de nada por sí solo.
   *
   * UN MATERIAL NO SE BORRA. Se da de baja: sus movimientos lo referencian y son
   * los que explican una existencia.
   */
  import { enhance } from '$app/forms';

  /** @type {{ catalogo: any[], form: any }} */
  let { catalogo, form } = $props();

  let editando = $state('');
  let codigo = $state('');
  let nombre = $state('');
  let categoria = $state('');
  let clase = $state('consumible');
  let unidad = $state('unidades');
  /** Del material que se está editando: de esto dependen los bloqueos. */
  let conMovimientos = $state(false);
  let verBajas = $state(false);

  const CLASES = [
    { id: 'consumible', texto: 'Consumible', ayuda: 'Se cuenta en unidades enteras. Un conector y medio no existe.' },
    { id: 'bobina', texto: 'Bobina', ayuda: 'Se fracciona: la fibra se consume en metros con decimales.' },
    { id: 'serializado', texto: 'Serializado', ayuda: 'Cada unidad es un aparato con número de serie único.' },
    { id: 'terminal', texto: 'Terminal', ayuda: 'Equipo de red que se instala en el cliente.' }
  ];

  let activos = $derived((catalogo ?? []).filter((m) => m.activo));
  let bajas = $derived((catalogo ?? []).filter((m) => !m.activo));
  let mostrados = $derived(verBajas ? (catalogo ?? []) : activos);

  function nuevo() {
    editando = '';
    codigo = '';
    nombre = '';
    categoria = '';
    clase = 'consumible';
    unidad = 'unidades';
    conMovimientos = false;
  }

  /** @param {any} m */
  function editar(m) {
    editando = m.id;
    codigo = m.codigo;
    nombre = m.nombre;
    categoria = m.categoria ?? '';
    clase = m.clase;
    unidad = m.unidad;
    conMovimientos = m.tiene_movimientos === true;
  }

  const MOTIVO = 'Este campo no puede modificarse porque el material ya tiene movimientos registrados.';

  let ayudaClase = $derived(CLASES.find((c) => c.id === clase)?.ayuda ?? '');
</script>

<!-- ============ QUÉ ES ESTA PESTAÑA ============ -->
<div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex items-start gap-space-md">
  <div class="w-10 h-10 rounded bg-surface-container flex items-center justify-center text-primary shrink-0">
    <span class="material-symbols-outlined text-[22px]">inventory_2</span>
  </div>
  <div class="flex flex-col">
    <span class="font-headline-sm text-headline-sm text-on-surface">
      Qué cosas maneja esta empresa
    </span>
    <p class="font-body-sm text-body-sm text-secondary mt-0.5 max-w-3xl">
      El catálogo es el maestro: define qué materiales existen y cómo se cuentan.
      <strong>Existencias</strong> contesta otra pregunta —cuánto hay y dónde— y cambia
      todo el día; esto casi nunca. Cada empresa tiene el suyo.
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

<div class="grid grid-cols-1 xl:grid-cols-12 gap-space-lg items-start">
  <!-- ============ LA LISTA ============ -->
  <section class="xl:col-span-7 bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
    <div class="p-space-lg flex flex-wrap items-center justify-between gap-space-md">
      <div>
        <h2 class="font-headline-sm text-headline-sm text-on-surface">Catálogo</h2>
        <p class="font-body-sm text-body-sm text-secondary mt-0.5">
          {activos.length} en uso{bajas.length ? ` · ${bajas.length} dados de baja` : ''}
        </p>
      </div>
      <div class="flex items-center gap-space-sm">
        {#if bajas.length}
          <button
            type="button"
            onclick={() => (verBajas = !verBajas)}
            class="h-9 px-space-md rounded font-body-sm text-body-sm font-medium transition-colors {verBajas
              ? 'bg-primary-fixed text-on-primary-fixed'
              : 'bg-surface-container-low text-secondary hover:bg-surface-container'}"
          >
            {verBajas ? 'Ocultar los dados de baja' : 'Ver los dados de baja'}
          </button>
        {/if}
        <button
          type="button"
          onclick={nuevo}
          class="h-9 px-space-md bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors inline-flex items-center gap-1"
        >
          <span class="material-symbols-outlined text-[16px]">add</span>
          Material nuevo
        </button>
      </div>
    </div>

    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase">
            <th class="py-2.5 px-space-lg w-44">Código</th>
            <th class="py-2.5 px-space-lg">Material</th>
            <th class="py-2.5 px-space-lg w-32">Clase</th>
            <th class="py-2.5 px-space-lg w-28">Unidad</th>
            <th class="py-2.5 px-space-lg w-40">Estado</th>
            <th class="py-2.5 px-space-lg w-48"></th>
          </tr>
        </thead>
        <tbody>
          {#if mostrados.length === 0}
            <tr>
              <td colspan="6" class="py-space-lg px-space-lg font-body-md text-body-md text-secondary">
                Todavía no hay materiales en el catálogo. Hasta que exista al menos uno no
                se puede registrar una entrada ni despachar nada: los formularios eligen
                de acá.
              </td>
            </tr>
          {/if}
          {#each mostrados as m (m.id)}
            <tr
              class="transition-colors {m.activo
                ? 'hover:bg-surface-container-low/40'
                : 'bg-surface-container-low/40'}"
            >
              <td class="py-space-md px-space-lg font-label-code text-label-code font-semibold {m.activo ? 'text-on-surface' : 'text-secondary'}">
                {m.codigo}
              </td>
              <td class="py-space-md px-space-lg">
                <span class="font-body-md text-body-md {m.activo ? 'text-on-surface' : 'text-secondary'}">
                  {m.nombre}
                </span>
                {#if m.categoria}
                  <span class="font-body-sm text-body-sm text-secondary block">{m.categoria}</span>
                {/if}
              </td>
              <td class="py-space-md px-space-lg">
                <span class="px-2 py-0.5 rounded font-body-sm text-body-sm bg-surface-container text-secondary">
                  {CLASES.find((c) => c.id === m.clase)?.texto ?? m.clase}
                </span>
              </td>
              <td class="py-space-md px-space-lg font-body-sm text-body-sm text-secondary">
                {m.unidad}
              </td>
              <td class="py-space-md px-space-lg">
                {#if !m.activo}
                  <span class="px-2 py-0.5 rounded font-table-header text-table-header uppercase bg-surface-container text-secondary">
                    Dado de baja
                  </span>
                {:else if m.tiene_movimientos}
                  <span
                    class="inline-flex items-center gap-1 font-body-sm text-body-sm text-secondary"
                    title="Su código, su clase y su unidad ya no se pueden cambiar"
                  >
                    <span class="material-symbols-outlined text-[14px]">lock</span>
                    con movimientos
                  </span>
                {:else}
                  <span class="font-body-sm text-body-sm text-secondary">sin movimientos</span>
                {/if}
              </td>
              <td class="py-space-md px-space-lg">
                <div class="flex items-center gap-space-xs justify-end">
                  <button
                    type="button"
                    onclick={() => editar(m)}
                    class="h-8 px-space-md bg-surface-container-lowest hover:bg-surface-container text-on-surface rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors"
                  >
                    Editar
                  </button>
                  <form method="POST" action="?/materialEstado" use:enhance>
                    <input type="hidden" name="material_id" value={m.id} />
                    <input type="hidden" name="activo" value={m.activo ? 'false' : 'true'} />
                    <button
                      type="submit"
                      class="h-8 px-space-md bg-surface-container-lowest rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors {m.activo
                        ? 'text-secondary hover:text-error hover:bg-error-container/30'
                        : 'text-primary hover:bg-primary-fixed/40'}"
                      title={m.activo
                        ? 'Deja de ofrecerse en operaciones nuevas. No se borra: sigue explicando los movimientos que lo usaron'
                        : 'Vuelve a ofrecerse en las operaciones'}
                    >
                      {m.activo ? 'Dar de baja' : 'Reactivar'}
                    </button>
                  </form>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="px-space-lg py-space-md bg-surface-container-low/40">
      <p class="font-body-sm text-body-sm text-secondary">
        Un material nunca se borra. Dar de baja lo saca de los formularios de despacho,
        entrada, traslado, reserva, compra y plantillas, y lo deja intacto en los
        registros viejos y en las existencias.
      </p>
    </div>
  </section>

  <!-- ============ ALTA Y EDICIÓN ============ -->
  <section class="xl:col-span-5">
    <form
      method="POST"
      action="?/material"
      use:enhance
      class="bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col gap-space-md max-w-[520px]"
    >
      <input type="hidden" name="material_id" value={editando} />

      <div class="flex items-center gap-space-xs">
        <span class="material-symbols-outlined text-primary text-[20px]">
          {editando ? 'edit' : 'add_circle'}
        </span>
        <h2 class="font-headline-sm text-headline-sm text-on-surface">
          {editando ? `Editar ${codigo}` : 'Material nuevo'}
        </h2>
      </div>

      {#if editando && conMovimientos}
        <!--
          El aviso va ARRIBA y no solo en cada campo: quien viene a corregir algo
          tiene que entender la regla antes de encontrarse tres campos apagados.
        -->
        <div class="bg-surface-container-low p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-secondary text-[18px] shrink-0">lock</span>
          <p class="font-body-sm text-body-sm text-on-surface">
            Este material ya tiene movimientos registrados, así que su <strong>código</strong>,
            su <strong>clase</strong> y su <strong>unidad</strong> quedaron fijos. El nombre y
            la categoría se pueden corregir igual.
          </p>
        </div>
      {/if}

      <div class="flex flex-col gap-space-xs">
        <label for="mat-codigo" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Código <span class="text-error">*</span>
        </label>
        <input
          id="mat-codigo"
          name="codigo"
          bind:value={codigo}
          required
          readonly={conMovimientos}
          placeholder="CON-SC-APC"
          title={conMovimientos ? MOTIVO : 'Se guarda en mayúsculas'}
          class="h-10 px-3 font-label-code text-label-code uppercase rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary {conMovimientos
            ? 'bg-surface-container-low text-secondary cursor-not-allowed'
            : 'bg-surface-container-lowest text-on-surface'}"
        />
        <span class="font-body-sm text-body-sm text-secondary">
          {#if conMovimientos}
            {MOTIVO}
          {:else}
            Es lo que se escribe en las pantallas. Se guarda en mayúsculas y es único en
            esta empresa — otra empresa puede usar el mismo.
          {/if}
        </span>
      </div>

      <div class="flex flex-col gap-space-xs">
        <label for="mat-nombre" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Nombre <span class="text-error">*</span>
        </label>
        <input
          id="mat-nombre"
          name="nombre"
          bind:value={nombre}
          required
          placeholder="Conector SC/APC monomodo"
          class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <div class="flex flex-col gap-space-xs">
        <label for="mat-categoria" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Categoría <span class="text-secondary font-normal opacity-75">(opcional)</span>
        </label>
        <input
          id="mat-categoria"
          name="categoria"
          bind:value={categoria}
          placeholder="Conectividad"
          class="h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <span class="font-body-sm text-body-sm text-secondary">
          Agrupa las filas en Existencias. Se puede cambiar siempre.
        </span>
      </div>

      <div class="flex flex-col gap-space-xs">
        <label for="mat-clase" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Clase <span class="text-error">*</span>
        </label>
        <select
          id="mat-clase"
          name="clase"
          bind:value={clase}
          disabled={conMovimientos}
          title={conMovimientos ? MOTIVO : ''}
          class="h-10 px-3 rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary {conMovimientos
            ? 'bg-surface-container-low text-secondary cursor-not-allowed'
            : 'bg-surface-container-lowest text-on-surface cursor-pointer'}"
        >
          {#each CLASES as c (c.id)}
            <option value={c.id}>{c.texto}</option>
          {/each}
        </select>
        <!-- Un `select` deshabilitado no se envía, así que el valor viaja igual. -->
        {#if conMovimientos}
          <input type="hidden" name="clase" value={clase} />
        {/if}
        <span class="font-body-sm text-body-sm text-secondary">
          {conMovimientos ? MOTIVO : ayudaClase}
        </span>
      </div>

      <div class="flex flex-col gap-space-xs">
        <label for="mat-unidad" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
          Unidad <span class="text-error">*</span>
        </label>
        <input
          id="mat-unidad"
          name="unidad"
          bind:value={unidad}
          required
          readonly={conMovimientos}
          placeholder="unidades"
          title={conMovimientos ? MOTIVO : ''}
          class="h-10 px-3 font-body-md text-body-md rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary {conMovimientos
            ? 'bg-surface-container-low text-secondary cursor-not-allowed'
            : 'bg-surface-container-lowest text-on-surface'}"
        />
        <span class="font-body-sm text-body-sm text-secondary">
          {#if conMovimientos}
            {MOTIVO}
          {:else}
            Cómo se cuenta: unidades, m, kg. Es lo que se lee en cada existencia.
          {/if}
        </span>
      </div>

      {#if clase === 'serializado' && !editando}
        <div class="bg-surface-container-low p-space-md rounded flex items-start gap-space-sm">
          <span class="material-symbols-outlined text-primary text-[18px] shrink-0">info</span>
          <p class="font-body-sm text-body-sm text-on-surface">
            Acá se crea el <strong>tipo</strong> de equipo, no los aparatos. Cada número de
            serie nace cuando ese equipo entra al inventario, en Registrar entrada o en una
            compra.
          </p>
        </div>
      {/if}

      <div class="flex items-center justify-end gap-space-sm pt-space-xs">
        {#if editando}
          <button
            type="button"
            onclick={nuevo}
            class="h-10 px-space-md bg-surface-container-lowest hover:bg-surface-container text-secondary rounded font-body-sm text-body-sm font-medium transition-colors"
          >
            Cancelar
          </button>
        {/if}
        <button
          type="submit"
          class="h-10 px-space-lg bg-primary-container hover:bg-primary text-on-primary rounded font-headline-sm text-body-md font-medium shadow-sm transition-colors flex items-center gap-space-xs"
        >
          <span class="material-symbols-outlined text-[18px]">save</span>
          <span>{editando ? 'Guardar los cambios' : 'Dar de alta'}</span>
        </button>
      </div>
    </form>
  </section>
</div>
