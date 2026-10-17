<script>
  /**
   * Planes de venta: que planes del catalogo TECNICO de WispHub se ofrecen
   * de verdad a un prospecto nuevo, y en que ZONAS reales (nodos de red de
   * la empresa) cada uno. El agente 'ventas' nunca muestra el catalogo
   * tecnico completo (trae variantes duplicadas y nombres legacy pensados
   * para facturar clientes existentes) -- solo lo que queda tildado aca.
   *
   * El catalogo de la izquierda se trae EN VIVO de WispHub cada vez que se
   * abre esta pantalla (no es un cache): asi nunca se arma la lista curada
   * contra un plan que ya no existe o un nombre que cambio.
   *
   * Las ZONAS no se escriben a mano (20/08/2026, cambio importante): un
   * barrio real puede caer en mas de una zona de red, y el texto libre no
   * podia representarlo ni mantenerse sincronizado con la realidad (ver
   * incidente "doña manuela"). El catalogo localidad -> zona se sincroniza
   * bajo demanda con el boton de abajo, recorriendo el proveedor entero --
   * las opciones de zona en la tabla de planes salen de ESE catalogo ya
   * sincronizado, no de una llamada aparte.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import { relativeTime, count } from '$lib/v2/format.js';
  import { enhance } from '$app/forms';
  import { Check, Search, RefreshCw } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /** @typedef {{ marcado: boolean, zonas: Set<number> }} EstadoPlan */

  /** Zonas reales distintas presentes en el catalogo ya sincronizado --
   * de ahi salen las opciones de la tabla de planes, sin pedirle nada
   * mas a WispHub. */
  let zonasDisponibles = $derived.by(() => {
    /** @type {Map<number, { zona_id: number, zona_nombre: string }>} */
    const mapa = new Map();
    for (const loc of data.localidades ?? []) {
      for (const z of loc.zonas ?? []) {
        if (!mapa.has(z.zona_id)) mapa.set(z.zona_id, { zona_id: z.zona_id, zona_nombre: z.zona_nombre });
      }
    }
    return [...mapa.values()].sort((a, b) => a.zona_nombre.localeCompare(b.zona_nombre));
  });

  function estadoInicial() {
    /** @type {Record<string, EstadoPlan>} */
    const mapa = {};
    for (const p of data.planesVenta ?? []) {
      mapa[p.nombre_wisphub] = { marcado: true, zonas: new Set(p.zonas ?? []) };
    }
    return mapa;
  }

  let seleccion = $state(estadoInicial());
  let filtro = $state('');
  let filtroLocalidad = $state('');
  let guardando = $state(false);
  let sincronizando = $state(false);

  /**
   * De que herramienta sale el listado de planes y de cual el precio.
   * Viene del motor (`marcas_precio`), no de un nombre fijo en esta
   * pantalla: es un dato del proveedor de CADA empresa.
   */
  const marcas = $derived(data.marcasPrecio ?? { listado: null, detalle: null });
  const yaElegidas = $derived(Boolean(marcas.listado && marcas.detalle));

  /**
   * Las candidatas salen del catalogo del tenant. Cuando el motor rechaza
   * por "falta elegir" manda la lista en el propio error, y esa gana: es la
   * que el motor acaba de ver, no la de cuando se cargo la pantalla.
   */
  const candidatas = $derived(
    form?.faltaElegir && (form?.herramientas ?? []).length
      ? form.herramientas
      : (data.herramientas ?? [])
  );

  /** Abre los dos selectores cuando ya hay marcas y alguien quiere cambiarlas. */
  let eligiendo = $state(false);

  let visibles = $derived(
    filtro.trim()
      ? (data.catalogo ?? []).filter((/** @type {any} */ p) =>
          (p.nombre ?? '').toLowerCase().includes(filtro.trim().toLowerCase())
        )
      : (data.catalogo ?? [])
  );

  let localidadesVisibles = $derived(
    filtroLocalidad.trim()
      ? (data.localidades ?? []).filter((/** @type {any} */ l) =>
          (l.localidad ?? '').toLowerCase().includes(filtroLocalidad.trim().toLowerCase())
        )
      : (data.localidades ?? [])
  );

  /** @param {string} nombre */
  function estadoDe(nombre) {
    return seleccion[nombre] ?? { marcado: false, zonas: new Set() };
  }

  /** @param {string} nombre */
  function alternar(nombre) {
    const actual = estadoDe(nombre);
    seleccion = { ...seleccion, [nombre]: { ...actual, marcado: !actual.marcado } };
  }

  /** @param {string} nombre @param {number} zonaId */
  function alternarZona(nombre, zonaId) {
    const actual = estadoDe(nombre);
    const nuevas = new Set(actual.zonas);
    if (nuevas.has(zonaId)) nuevas.delete(zonaId);
    else nuevas.add(zonaId);
    seleccion = { ...seleccion, [nombre]: { ...actual, zonas: nuevas } };
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
          zonas: [...s.zonas]
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

  const sincronizandoAction = () => {
    sincronizando = true;
    return async (/** @type {any} */ { update }) => {
      await update();
      sincronizando = false;
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
    {:else}
      <div class="v2-card" style="padding:14px 16px;margin-bottom:16px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div>
            <b style="font-size:13px">Localidades sincronizadas</b>
            <p class="v2-sub" style="font-size:12px;margin:6px 0 0;line-height:1.5">
              Barrios y localidades reales, con las zonas de red donde cada uno tiene clientes --
              se arma recorriendo WispHub entero, nunca escribiendo a mano. El asistente usa esto
              para saber si hay cobertura en un barrio sin pegarle a WispHub en cada mensaje.
              {#if data.localidadesActualizadoEn}
                Última actualización: {relativeTime(data.localidadesActualizadoEn)}.
              {:else}
                Todavía no se sincronizó nunca.
              {/if}
            </p>
          </div>
          <form
            method="POST"
            action="?/sincronizar"
            use:enhance={sincronizandoAction}
            style="flex:none"
          >
            <button
              class="v2-btn v2-btn-sm"
              type="submit"
              disabled={sincronizando || !data.can_edit}
            >
              <span class:pv-girando={sincronizando}><RefreshCw size={13} /></span>
              {sincronizando ? 'Sincronizando…' : 'Actualizar localidades'}
            </button>
          </form>
        </div>

        {#if form?.error && form?.action === 'sincronizar'}
          <p class="v2-error" style="font-size:12px;margin-top:10px">{form.error}</p>
        {/if}
        {#if form?.sincronizado}
          <p class="pv-ok" style="margin-top:10px"><Check size={12} /> Localidades actualizadas</p>
        {/if}

        <!--
          EL PRECIO DE CADA PLAN, en su propia acción y no como parte de la de
          arriba: recorre otro catálogo y tarda distinto. Mezclarlas haría que
          actualizar los barrios saliera a pedir 50 precios sin que nadie lo
          pidiera.

          Hace falta porque el listado de planes NO trae el precio —verificado
          contra la API: devuelve id, nombre y tipo— y el precio vive en el
          detalle, uno por uno.
        -->
        <div style="margin-top:14px;border-top:1px solid var(--v2-border);padding-top:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
            <div>
              <strong style="font-size:13px">Precio de cada plan</strong>
              <p style="font-size:12px;color:var(--v2-slate);margin:2px 0 0">
                {#if (data.precios ?? []).length}
                  {data.precios.length} planes con precio.
                  {#if data.preciosActualizadoEn}
                    Última actualización: {data.preciosActualizadoEn}.
                  {/if}
                {:else}
                  Todavía no se sincronizó ninguno. Sin esto, un plan alto no pesa al
                  repartir el trabajo del día.
                {/if}
              </p>
            </div>
            {#if yaElegidas && !eligiendo}
              <form method="POST" action="?/precios" use:enhance style="flex:none">
                <input type="hidden" name="listado" value={marcas.listado} />
                <input type="hidden" name="detalle" value={marcas.detalle} />
                <button class="v2-btn v2-btn-sm" type="submit" disabled={!data.can_edit}>
                  <RefreshCw size={13} /> Actualizar precios
                </button>
              </form>
            {/if}
          </div>

          {#if yaElegidas && !eligiendo}
            <p style="font-size:11px;color:var(--v2-slate);margin:8px 0 0">
              El listado sale de <code>{marcas.listado}</code> y el precio de
              <code>{marcas.detalle}</code>.
              {#if data.can_edit}
                <button type="button" class="pv-enlace" onclick={() => (eligiendo = true)}>
                  Cambiar
                </button>
              {/if}
            </p>
          {:else}
            <!--
              DE DONDE SALEN LOS PRECIOS SE ELIGE ACA, no en un YAML.

              Son dos llamadas distintas al proveedor: una devuelve los ids de
              los planes, la otra el precio de uno. Hasta el 07/10/2026 esto
              solo se podia marcar editando `tenants/<slug>.config.yaml` y
              cargandolo entero -- y cargarlo entero en produccion habria
              apagado la vision y borrado configuracion creada desde esta
              misma interfaz. Un ISP nuevo con otro proveedor lo configura
              aca, sin una sesion de codigo (CLAUDE.md 3.3).
            -->
            <form method="POST" action="?/precios" use:enhance style="margin-top:10px">
              <p style="font-size:12px;color:var(--v2-slate);margin:0 0 8px">
                Elegí de qué herramienta sale cada cosa. Son dos llamadas
                distintas: el listado da los planes, el detalle da el precio
                de cada uno.
              </p>
              <div class="pv-elegir">
                <label>
                  <span>Listado de planes</span>
                  <select name="listado" required>
                    <option value="" disabled selected={!marcas.listado}>Elegí una…</option>
                    {#each candidatas as h (h.nombre)}
                      <option value={h.nombre} selected={h.nombre === marcas.listado}>
                        {h.nombre}
                      </option>
                    {/each}
                  </select>
                </label>
                <label>
                  <span>Detalle con el precio</span>
                  <select name="detalle" required>
                    <option value="" disabled selected={!marcas.detalle}>Elegí una…</option>
                    {#each candidatas as h (h.nombre)}
                      <option value={h.nombre} selected={h.nombre === marcas.detalle}>
                        {h.nombre}
                      </option>
                    {/each}
                  </select>
                </label>
              </div>
              <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
                <button class="v2-btn v2-btn-sm" type="submit" disabled={!data.can_edit}>
                  <RefreshCw size={13} /> Guardar y actualizar precios
                </button>
                {#if yaElegidas}
                  <button type="button" class="v2-btn v2-btn-sm v2-btn-ghost"
                          onclick={() => (eligiendo = false)}>
                    Cancelar
                  </button>
                {/if}
              </div>
            </form>
          {/if}

          {#if form?.error && form?.action === 'precios'}
            <p class="v2-error" style="font-size:12px;margin-top:10px">{form.error}</p>
          {/if}
          {#if form?.preciosHecho}
            <p class="pv-ok" style="margin-top:10px"><Check size={12} /> {form.preciosHecho}</p>
          {/if}
        </div>

        {#if (data.localidades ?? []).length}
          <div class="pv-filtro" style="margin-top:12px">
            <Search size={14} style="color:var(--v2-slate)" />
            <input
              class="v2-input"
              type="text"
              placeholder="Buscar una localidad…"
              bind:value={filtroLocalidad}
              style="border:0;box-shadow:none;padding-left:6px"
            />
          </div>
          <div class="pv-tabla-scroll">
            <table class="pv-tabla">
              <thead>
                <tr>
                  <th>Localidad</th>
                  <th>Zona(s)</th>
                  <th style="text-align:right">Clientes</th>
                </tr>
              </thead>
              <tbody>
                {#each localidadesVisibles as loc (loc.localidad)}
                  <tr>
                    <td style="font-size:12.5px">{loc.localidad}</td>
                    <td style="font-size:11.5px">
                      {(loc.zonas ?? []).map((/** @type {any} */ z) => z.zona_nombre).join(', ') || '—'}
                    </td>
                    <td style="text-align:right" class="v2-num">{count(loc.n_clientes)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>

      {#if data.errorCatalogo}
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
                  <th>Zonas donde se ofrece</th>
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
                        {#if zonasDisponibles.length}
                          <div style="display:flex;flex-wrap:wrap;gap:6px">
                            {#each zonasDisponibles as z (z.zona_id)}
                              <label class="pv-chip" class:pv-chip-activo={est.zonas.has(z.zona_id)}>
                                <input
                                  type="checkbox"
                                  checked={est.zonas.has(z.zona_id)}
                                  disabled={!data.can_edit}
                                  onchange={() => alternarZona(plan.nombre, z.zona_id)}
                                  style="display:none"
                                />
                                {z.zona_nombre}
                              </label>
                            {/each}
                          </div>
                          <span class="v2-sub" style="font-size:11px">
                            Vacío = cualquier zona con cobertura
                          </span>
                        {:else}
                          <span class="v2-sub" style="font-size:11.5px">
                            Sincronizá las localidades para elegir zonas
                          </span>
                        {/if}
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

          {#if form?.error && form?.action === 'guardar'}
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
  .pv-tabla-scroll {
    max-height: 320px;
    overflow-y: auto;
    overflow-x: auto;
    border: 1px solid var(--v2-border, #e2e2e2);
    border-radius: 8px;
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
  .pv-chip {
    display: inline-flex;
    align-items: center;
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid var(--v2-border, #e2e2e2);
    font-size: 11px;
    cursor: pointer;
    user-select: none;
    color: var(--v2-slate);
  }
  .pv-chip-activo {
    background: color-mix(in oklab, var(--v2-moss, #2f9e44) 14%, transparent);
    border-color: var(--v2-moss, #2f9e44);
    color: var(--v2-ink, inherit);
    font-weight: 550;
  }
  .pv-girando {
    animation: pv-spin 0.9s linear infinite;
  }
  @keyframes pv-spin {
    to {
      transform: rotate(360deg);
    }
  }
  /* Los dos selectores del precio: en columna, para que a 390px cada
     etiqueta siga arriba de su control y nada quede cortado. */
  .pv-elegir {
    display: grid;
    gap: 10px;
    grid-template-columns: 1fr;
  }
  @media (min-width: 560px) {
    .pv-elegir { grid-template-columns: 1fr 1fr; }
  }
  .pv-elegir label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .pv-elegir label span {
    font-size: 11px;
    color: var(--v2-slate);
  }
  .pv-elegir select {
    font-size: 12px;
    padding: 6px 8px;
    border: 1px solid var(--v2-border);
    border-radius: 6px;
    background: var(--v2-card, #fff);
    color: inherit;
    width: 100%;
    min-width: 0;
  }
  .pv-enlace {
    background: none;
    border: 0;
    padding: 0;
    font: inherit;
    color: var(--v2-link, #2563eb);
    cursor: pointer;
    text-decoration: underline;
  }
</style>
