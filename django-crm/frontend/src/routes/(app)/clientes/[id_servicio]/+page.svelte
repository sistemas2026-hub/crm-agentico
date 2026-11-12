<script>
  /*
   * La ficha del cliente por su servicio (12/11/2026). Ver +page.server.js.
   *
   * Cada bloque dice tres cosas distintas y las dice distinto: «no hay»
   * (lista vacía), «no se pudo leer» (el sistema no contestó) y «no es para
   * tu rol» (null del backend). Mezclarlas haría pasar un fallo por un
   * cliente sin historia.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { CASE_STATUS_LABEL } from '$lib/v2/enums.js';
  import {
    tonoDeEstado,
    rotuloDeOrden,
    diaLegible,
    instanteLegible,
    quienVa
  } from '$lib/v2/hilo-del-cliente.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  let cliente = $derived(data.contexto?.cliente ?? null);
  let equipo = $derived(data.contexto?.equipo ?? null);
  let titulo = $derived(cliente?.nombre ? `${cliente.nombre} · servicio ${data.servicio}` : `Servicio ${data.servicio}`);

  /** Los campos de la persona, en el orden en que se leen. Los que el motor no
   *  entregó para este rol, no se dibujan: el criterio vive allá. */
  const CAMPOS_CLIENTE = [
    ['estado', 'Estado'],
    ['plan', 'Plan'],
    ['localidad', 'Localidad'],
    ['cedula', 'Cédula'],
    ['telefono', 'Teléfono'],
    ['direccion', 'Dirección']
  ];
</script>

<svelte:head><title>{titulo}</title></svelte:head>

<PageHeader title={titulo} record>
  {#snippet sub()}
    <span class="v2-sub">Todo lo que Dexter sabe de este cliente, por su servicio en el ISP.</span>
  {/snippet}
  {#snippet actions()}
    {#if data.contexto?.wisphub_perfil}
      <a class="v2-btn v2-btn-sm" href={data.contexto.wisphub_perfil} target="_blank" rel="noopener">Ver en WispHub</a>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad v2-split-wide pagina">
    <div class="columna">
      <!-- ── Conversaciones ─────────────────────────────────────────── -->
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Conversaciones</span></div>
        <div class="cuerpo">
          {#if data.motorSinRespuesta}
            <p class="v2-sub">No se pudieron leer las conversaciones: el asistente no respondió.</p>
          {:else if data.conversaciones === null}
            <p class="v2-sub">No se pudieron leer las conversaciones.</p>
          {:else if data.conversaciones.length === 0}
            <p class="v2-sub">Este cliente no tiene conversaciones identificadas.</p>
          {:else}
            <ul class="lineas">
              {#each data.conversaciones as c (c.id)}
                <li>
                  <a href="/conversaciones/{c.id}">{instanteLegible(c.creado_en)}</a>
                  <span class="v2-sub">{c.canal}{c.canal_operativo ? '' : ' (prueba)'} · {c.estado}</span>
                  {#if c.escalada_a_humano}<Pill tone="clay">pasó a una persona</Pill>{/if}
                  {#if c.etiqueta}<span class="v2-sub">· {c.etiqueta}</span>{/if}
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </section>

      <!-- ── Tickets ────────────────────────────────────────────────── -->
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Tickets</span></div>
        <div class="cuerpo">
          {#if data.tickets === null}
            <p class="v2-sub">{data.errorCrm ?? 'No se pudieron leer los tickets.'}</p>
          {:else if data.tickets.length === 0}
            <p class="v2-sub">Sin tickets que puedas abrir para este servicio.</p>
          {:else}
            <ul class="lineas">
              {#each data.tickets as t (t.id)}
                <li>
                  <a href="/tickets/{t.id}">{t.nombre}</a>
                  <span class="v2-sub">
                    {CASE_STATUS_LABEL?.[t.estado] ?? t.estado}{#if t.external_ticket_id} · #{t.external_ticket_id}{/if}
                    · {instanteLegible(t.creado_en)}
                  </span>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </section>

      <!-- ── Visitas de campo ───────────────────────────────────────── -->
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Visitas de campo</span></div>
        <div class="cuerpo">
          {#if data.ordenes === null}
            <p class="v2-sub">{data.errorCrm ?? 'No se pudieron leer las visitas.'}</p>
          {:else if data.ordenes.length === 0}
            <p class="v2-sub">Sin visitas de campo.</p>
          {:else}
            <ul class="lineas">
              {#each data.ordenes as o (o.id)}
                <li>
                  {#if o.puede_abrir}
                    <a href="/ordenes/{o.id}">{rotuloDeOrden(o.numero)}</a>
                  {:else}
                    <span>{rotuloDeOrden(o.numero)}</span>
                  {/if}
                  <span class="v2-sub">{o.tipo}</span>
                  <Pill tone={tonoDeEstado(o.estado_operativo)}>{o.estado_etiqueta}</Pill>
                  <span class="v2-sub">{quienVa(o)}{#if o.fecha} · {diaLegible(o.fecha)}{/if}</span>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </section>

      {#if data.solicitudes !== null}
        <!-- Solo para la gestión: null significa «no es para tu rol» y entonces
             el bloque no se dibuja, en vez de decir «sin solicitudes». -->
        <section class="v2-card">
          <div class="v2-card-head"><span class="v2-label">Solicitudes de instalación</span></div>
          <div class="cuerpo">
            {#if data.solicitudes.length === 0}
              <p class="v2-sub">Sin solicitudes atadas a los tickets de este servicio.</p>
            {:else}
              <ul class="lineas">
                {#each data.solicitudes as s (s.id)}
                  <li>
                    <a href="/instalaciones">{s.tipo_solicitud || 'Solicitud'}</a>
                    <span class="v2-sub">{s.estado_etiqueta}{#if s.plan_interesado} · {s.plan_interesado}{/if}{#if s.ticket_wisphub} · #{s.ticket_wisphub}{/if}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        </section>
      {/if}
    </div>

    <aside class="columna">
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">El cliente</span></div>
        {#if data.motorSinRespuesta}
          <p class="cuerpo v2-sub">No se pudo consultar el sistema del ISP.</p>
        {:else if !cliente}
          <p class="cuerpo v2-sub">El ISP no devolvió datos para este servicio.</p>
        {:else}
          <dl class="v2-kv cuerpo">
            <dt>Servicio</dt>
            <dd>{data.servicio}</dd>
            {#each CAMPOS_CLIENTE as [clave, rotulo] (clave)}
              {#if cliente[clave]}
                <dt>{rotulo}</dt>
                <dd>{cliente[clave]}</dd>
              {/if}
            {/each}
          </dl>
          {#if (cliente._ocultos ?? []).length}
            <p class="cuerpo v2-sub oculto">Oculto para tu área: {cliente._ocultos.join(', ')}.</p>
          {/if}
        {/if}
      </section>

      <section class="v2-card">
        <div class="v2-card-head">
          <span class="v2-label">El equipo</span>
          {#if data.contexto?.smartolt_ont}
            <a href={data.contexto.smartolt_ont} target="_blank" rel="noopener">SmartOLT</a>
          {/if}
        </div>
        {#if equipo}
          <dl class="v2-kv cuerpo">
            {#if equipo.onu_status}<dt>Estado</dt><dd>{equipo.onu_status}</dd>{/if}
            {#if equipo.onu_signal_1490}
              <dt>Potencia RX</dt>
              <dd>{equipo.onu_signal_1490}{#if equipo.onu_signal_1490_veredicto} · {equipo.onu_signal_1490_veredicto}{/if}</dd>
            {/if}
            {#if equipo.odb_name}<dt>Caja</dt><dd>{equipo.odb_name}</dd>{/if}
            {#if equipo.last_status_change}<dt>Último cambio</dt><dd>{equipo.last_status_change}</dd>{/if}
          </dl>
        {:else if data.contexto?.equipo_no_disponible === 'onu_no_vinculada'}
          <p class="cuerpo v2-sub">El ISP todavía no tiene cargado el serial del equipo.</p>
        {:else if data.contexto?.equipo_no_disponible === 'serial_desactualizado'}
          <p class="cuerpo v2-sub">El serial del ISP no existe en la OLT: probablemente le cambiaron el equipo.</p>
        {:else}
          <p class="cuerpo v2-sub">Sin datos del equipo.</p>
        {/if}
      </section>
    </aside>
  </div>
</div>

<style>
  .pagina {
    padding-top: 14px;
    padding-bottom: 24px;
  }
  .columna {
    display: grid;
    gap: 16px;
    align-content: start;
  }
  .cuerpo {
    padding: 12px 15px;
    margin: 0;
  }
  .lineas {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 7px;
    font-size: 12.5px;
  }
  .lineas li {
    display: flex;
    gap: 8px;
    align-items: baseline;
    flex-wrap: wrap;
  }
  .oculto {
    font-size: 11.5px;
    border-top: 1px solid var(--v2-line);
  }
  a {
    color: var(--v2-ember-text);
  }
</style>
