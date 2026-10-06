<script>
  /**
   * Ubicaciones: dónde puede estar el material.
   *
   * POR QUÉ EXISTE ESTA PANTALLA
   * El endpoint estaba desde el primer día; el botón, no. Sin una bodega no hay
   * dónde registrar una entrada, así que el inventario quedaba trabado antes de
   * empezar: el catálogo se podía llenar y «Registrar entrada» no tenía destino.
   * Lo encontró alguien tratando de usarlo, no una prueba.
   *
   * TRES TIPOS, Y SOLO DOS SE CREAN ACÁ
   *     bodega    el depósito de la empresa. Una empresa con tres municipios
   *               tiene tres, y traslada material entre ellas.
   *     vehículo  en una cuadrilla el material vive en la camioneta y no en la
   *               mochila de una persona, y esa distinción cambia a quién se le
   *               pide cuenta.
   *     técnico   la custodia de alguien. NO se crea acá y el servidor lo
   *               rechaza: nace sola la primera vez que se le despacha material,
   *               para que no pueda quedar una custodia sin dueño ni dos para la
   *               misma persona.
   *
   * Por eso la lista muestra las tres pero el formulario ofrece dos: esconder
   * las custodias haría pensar que el material de los técnicos no está en
   * ningún lado.
   */
  import { enhance } from '$app/forms';

  /** @type {{ ubicaciones: any[], form: any }} */
  let { ubicaciones, form } = $props();

  let abierto = $state(false);
  let nombre = $state('');
  let tipo = $state('bodega');

  const TIPOS = [
    { id: 'bodega', texto: 'Bodega', ayuda: 'Un depósito de la empresa.' },
    {
      id: 'vehiculo',
      texto: 'Vehículo',
      ayuda: 'Una camioneta de cuadrilla: el material viaja con ella, no con una persona.'
    }
  ];

  const ICONO = {
    bodega: 'warehouse',
    vehiculo: 'local_shipping',
    tecnico: 'person'
  };

  const NOMBRE_TIPO = {
    bodega: 'Bodega',
    vehiculo: 'Vehículo',
    tecnico: 'Custodia'
  };

  /** Las de la empresa primero; las custodias al final, que son muchas. */
  let ordenadas = $derived(
    [...(ubicaciones ?? [])].sort((a, b) => {
      const peso = (u) => (u.tipo === 'tecnico' ? 1 : 0);
      if (peso(a) !== peso(b)) return peso(a) - peso(b);
      return String(a.nombre ?? '').localeCompare(String(b.nombre ?? ''));
    })
  );

  let internas = $derived(ordenadas.filter((u) => u.tipo !== 'tecnico'));
  let custodias = $derived(ordenadas.filter((u) => u.tipo === 'tecnico'));

  function nueva() {
    abierto = true;
    nombre = '';
    tipo = 'bodega';
  }
</script>

<div class="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-space-lg">
  <section class="bg-surface-container-lowest rounded-lg shadow-sm overflow-hidden">
    <div class="flex items-center justify-between gap-space-md p-space-lg pb-space-md">
      <div>
        <h3 class="font-title-md text-title-md text-on-surface">Ubicaciones</h3>
        <p class="font-body-sm text-body-sm text-secondary">
          {internas.length}
          {internas.length === 1 ? 'de la empresa' : 'de la empresa'} ·
          {custodias.length}
          {custodias.length === 1 ? 'custodia' : 'custodias'}
        </p>
      </div>
      <button
        type="button"
        onclick={nueva}
        class="h-9 px-space-md bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-body-sm text-body-sm font-medium shadow-sm transition-colors inline-flex items-center gap-1"
      >
        <span class="material-symbols-outlined text-[16px]">add</span>
        Ubicación nueva
      </button>
    </div>

    <div class="w-full overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr
            class="bg-surface-container-low text-secondary font-table-header text-table-header uppercase"
          >
            <th class="py-2.5 px-space-lg w-16"></th>
            <th class="py-2.5 px-space-lg">Nombre</th>
            <th class="py-2.5 px-space-lg w-40">Tipo</th>
          </tr>
        </thead>
        <tbody>
          {#if ordenadas.length === 0}
            <tr>
              <td
                colspan="3"
                class="py-space-lg px-space-lg font-body-md text-body-md text-secondary"
              >
                Todavía no hay ninguna ubicación. Hasta que exista al menos una bodega no se
                puede registrar una entrada: el material tiene que entrar a algún lado.
              </td>
            </tr>
          {/if}
          {#each ordenadas as u (u.id)}
            <tr class="transition-colors hover:bg-surface-container-low/40">
              <td class="py-space-md px-space-lg">
                <div
                  class="w-10 h-10 rounded bg-surface-container flex items-center justify-center text-secondary"
                >
                  <span class="material-symbols-outlined text-[18px]">
                    {ICONO[u.tipo] ?? 'place'}
                  </span>
                </div>
              </td>
              <td class="py-space-md px-space-lg font-body-md text-body-md text-on-surface">
                {u.nombre}
              </td>
              <td class="py-space-md px-space-lg">
                <span
                  class="px-2 py-0.5 rounded font-body-sm text-body-sm bg-surface-container text-secondary"
                >
                  {NOMBRE_TIPO[u.tipo] ?? u.tipo}
                </span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if custodias.length}
      <p class="px-space-lg py-space-md font-body-sm text-body-sm text-secondary">
        Las custodias no se crean ni se borran a mano: aparecen solas la primera vez que se
        le despacha material a una persona, y quedan para siempre porque sus movimientos
        las referencian.
      </p>
    {/if}
  </section>

  {#if abierto}
    <aside class="bg-surface-container-lowest rounded-lg shadow-sm p-space-lg h-fit">
      <h3 class="font-title-md text-title-md text-on-surface flex items-center gap-2 mb-space-md">
        <span class="material-symbols-outlined text-primary text-[20px]">add_circle</span>
        Ubicación nueva
      </h3>

      <form method="POST" action="?/ubicacion" use:enhance class="flex flex-col gap-space-md">
        <div>
          <label for="ubi-nombre" class="block font-body-sm text-body-sm text-on-surface mb-1">
            NOMBRE <span class="text-error">*</span>
          </label>
          <input
            id="ubi-nombre"
            name="nombre"
            bind:value={nombre}
            required
            placeholder="Bodega Principal"
            class="w-full h-10 px-space-md bg-surface-container-low rounded font-body-md text-body-md text-on-surface"
          />
          <p class="font-body-sm text-body-sm text-secondary mt-1">
            Es lo que se elige en Registrar entrada, Despachar y Trasladar.
          </p>
        </div>

        <div>
          <label for="ubi-tipo" class="block font-body-sm text-body-sm text-on-surface mb-1">
            TIPO <span class="text-error">*</span>
          </label>
          <select
            id="ubi-tipo"
            name="tipo"
            bind:value={tipo}
            class="w-full h-10 px-space-md bg-surface-container-low rounded font-body-md text-body-md text-on-surface"
          >
            {#each TIPOS as t (t.id)}
              <option value={t.id}>{t.texto}</option>
            {/each}
          </select>
          <p class="font-body-sm text-body-sm text-secondary mt-1">
            {TIPOS.find((t) => t.id === tipo)?.ayuda ?? ''}
          </p>
        </div>

        <p class="font-body-sm text-body-sm text-secondary">
          La custodia de un técnico no se crea acá: aparece sola cuando se le despacha
          material.
        </p>

        {#if form?.error}
          <p class="font-body-sm text-body-sm text-on-error-container bg-error-container/40 rounded px-space-md py-2">
            {form.error}
          </p>
        {/if}

        <div class="flex items-center gap-space-sm">
          <button
            type="submit"
            class="h-10 px-space-lg bg-primary-container text-on-primary-container rounded font-body-sm text-body-sm font-medium transition-colors"
          >
            Dar de alta
          </button>
          <button
            type="button"
            onclick={() => (abierto = false)}
            class="h-10 px-space-md text-secondary rounded font-body-sm text-body-sm transition-colors hover:bg-surface-container-low"
          >
            Cancelar
          </button>
        </div>
      </form>
    </aside>
  {/if}
</div>
