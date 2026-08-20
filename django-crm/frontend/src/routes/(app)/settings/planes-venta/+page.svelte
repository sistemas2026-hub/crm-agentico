<script>
  /**
   * Planes de venta: que planes del catalogo TECNICO de WispHub se ofrecen
   * de verdad a un prospecto nuevo, y en que localidades cada uno. El
   * agente 'ventas' nunca muestra el catalogo tecnico completo (trae
   * variantes duplicadas y nombres legacy pensados para facturar clientes
   * existentes) -- solo lo que queda tildado aca.
   *
   * El catalogo de la izquierda se trae EN VIVO de WispHub cada vez que se
   * abre esta pantalla (no es un cache): asi nunca se arma la lista curada
   * contra un plan que ya no existe o un nombre que cambio.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import { enhance } from '$app/forms';
  import { Check, Search } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /** @typedef {{ marcado: boolean, localidades: string }} EstadoPlan */

  function estadoInicial() {
    /** @type {Record<string, EstadoPlan>} */
    const mapa = {};
    for (const p of data.planesVenta ?? []) {
      mapa[p.nombre_wisphub] = { marcado: true, localidades: (p.localidades ?? []).join(', ') };
    }
    return mapa;
  }

  let seleccion = $state(estadoInicial());
  let filtro = $state('');
  let guardando = $state(false);

  let visibles = $derived(
    filtro.trim()
      ? (data.catalogo ?? []).filter((/** @type {any} */ p) =>
          (p.nombre ?? '').toLowerCase().includes(filtro.trim().toLowerCase())
        )
      : (data.catalogo ?? [])
  );

  /** @param {string} nombre */
  function estadoDe(nombre) {
    return seleccion[nombre] ?? { marcado: false, localidades: '' };
  }

  /** @param {string} nombre */
  function alternar(nombre) {
    const actual = estadoDe(nombre);
    seleccion = { ...seleccion, [nombre]: { ...actual, marcado: !actual.marcado } };
  }

  /** @param {string} nombre @param {string} valor */
  function cambiarLocalidades(nombre, valor) {
    const actual = estadoDe(nombre);
    seleccion = { ...seleccion, [nombre]: { ...actual, localidades: valor } };
  }

  let cantidadSeleccionada = $derived(
    Object.values(seleccion).filter((/** @type {EstadoPlan} */ s) => s.marcado).length
  );

  let datosParaEnviar = $derived(
    JSON.stringify(
      Object.entries(seleccion)
        .filter(([, /** @type {EstadoPlan} */ s]) => s.marcado)
        .map(([nombre, /** @type {EstadoPlan} */ s]) => ({
          nombre_wisphub: nombre,
          localidades: s.localidades
            .split(',')
            .map((/** @type {string} */ l) => l.trim())
            .filter(Boolean)
        }))
    )
  );

  const guardandoAction = () => {
    guardando = true;
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
      guardando = false;
    };
  };
</script>

<PageHeader title="Planes de venta">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if data.huboRespuesta}
      {cantidadSeleccionada} plan{cantidadSeleccionada === 1 ? '' : 'es'} ofrecido{cantidadSeleccionada ===
      1
        ? ''
        : 's'} a prospectos nuevos
    {:else}
      El asistente no responde
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:920px">
    {#if !data.huboRespuesta}
      <div class="v2-card" style="padding:20px 22px">
        <b style="font-size:13px">No se pudo leer la configuración</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          El motor no está respondiendo. Si otras pantallas de ajustes tampoco cargan, es el motor.
        </p>
      </div>
    {:else if data.errorCatalogo}
      <div class="v2-card" style="padding:20px 22px">
        <b style="font-size:13px">No se pudo traer el catálogo de WispHub</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          {data.errorCatalogo}
        </p>
      </div>
    {:else}
      <div class="v2-card" style="padding:14px 16px;margin-bottom:16px">
        <div style="display:flex;gap:10px;align-items:flex-start">
          <div>
            <b style="font-size:13px">Por qué esta lista existe aparte del catálogo de WispHub</b>
            <p class="v2-sub" style="font-size:12px;margin:6px 0 0;line-height:1.5">
              El catálogo técnico trae variantes duplicadas y nombres viejos pensados para facturar
              clientes existentes — no para vender. Un prospecto nunca ve el catálogo completo, solo
              lo que quede tildado acá. Dejar todo destildado no rompe nada: el agente de ventas le
              va a decir que todavía no hay planes cargados para su zona, y va a ofrecer pasar el
              caso a un colaborador — nunca muestra el catálogo técnico.
            </p>
          </div>
        </div>
      </div>

      <form
        method="POST"
        action="?/guardar"
        use:enhance={guardandoAction}
        style="display:flex;flex-direction:column;gap:12px"
      >
        <input type="hidden" name="datos" value={datosParaEnviar} />

        <div class="pv-filtro">
          <Search size={14} style="color:var(--v2-slate)" />
          <input
            class="v2-input"
            type="text"
            placeholder="Buscar un plan por nombre…"
            bind:value={filtro}
            style="border:0;box-shadow:none;padding-left:6px"
          />
        </div>

        <div class="v2-card" style="padding:0;overflow:hidden">
          <table class="pv-tabla">
            <thead>
              <tr>
                <th style="width:36px"></th>
                <th>Plan (WispHub)</th>
                <th>Localidades donde se ofrece</th>
              </tr>
            </thead>
            <tbody>
              {#each visibles as plan (plan.id ?? plan.nombre)}
                {@const est = estadoDe(plan.nombre)}
                <tr class:pv-fila-marcada={est.marcado}>
                  <td>
                    <input
                      type="checkbox"
                      checked={est.marcado}
                      disabled={!data.can_edit}
                      onchange={() => alternar(plan.nombre)}
                    />
                  </td>
                  <td style="font-size:12.5px">{plan.nombre}</td>
                  <td>
                    {#if est.marcado}
                      <input
                        class="v2-input"
                        type="text"
                        placeholder="Vacío = cualquier localidad con cobertura"
                        value={est.localidades}
                        disabled={!data.can_edit}
                        oninput={(e) =>
                          cambiarLocalidades(plan.nombre, /** @type {HTMLInputElement} */ (e.target).value)}
                        style="font-size:12px;padding:6px 9px"
                      />
                    {:else}
                      <span class="v2-sub" style="font-size:11.5px">—</span>
                    {/if}
                  </td>
                </tr>
              {:else}
                <tr>
                  <td colspan="3" style="text-align:center;padding:24px">
                    <span class="v2-sub" style="font-size:12.5px">
                      {filtro ? 'Ningún plan coincide con la búsqueda.' : 'WispHub no devolvió planes.'}
                    </span>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

        {#if form?.error}
          <p class="v2-error" style="font-size:12px">{form.error}</p>
        {/if}
        {#if form?.guardado}
          <p class="pv-ok"><Check size={12} /> Guardado</p>
        {/if}

        {#if data.can_edit}
          <button
            class="v2-btn v2-btn-primary v2-btn-sm"
            type="submit"
            disabled={guardando}
            style="align-self:flex-start"
          >
            {guardando ? 'Guardando…' : 'Guardar lista de planes'}
          </button>
        {/if}
      </form>
    {/if}
  </div>
</div>

<style>
  .pv-filtro {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 10px;
    border: 1px solid var(--v2-border, #e2e2e2);
    border-radius: 8px;
    background: var(--v2-surface, #fff);
    max-width: 360px;
  }
  .pv-tabla {
    width: 100%;
    border-collapse: collapse;
  }
  .pv-tabla th {
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    color: var(--v2-slate);
    padding: 10px 12px;
    border-bottom: 1px solid var(--v2-border, #e2e2e2);
  }
  .pv-tabla td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--v2-border, #eee);
    vertical-align: middle;
  }
  .pv-tabla tr:last-child td {
    border-bottom: none;
  }
  .pv-fila-marcada {
    background: color-mix(in oklab, var(--v2-moss, #2f9e44) 6%, transparent);
  }
  .pv-ok {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 0;
    font-size: 11.5px;
    color: var(--v2-moss);
    font-weight: 550;
  }
</style>
