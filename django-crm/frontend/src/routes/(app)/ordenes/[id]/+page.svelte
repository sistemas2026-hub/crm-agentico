<script>
  /*
   * La página de una orden de campo (12/11/2026). Ver +page.server.js.
   *
   * LA LÍNEA DE TIEMPO NO SE REORDENA (CLAUDE.md §12): se dibuja en el orden en
   * que el backend la entrega, que es el orden en que LLEGÓ cada reporte. Un
   * AVANCE sin INICIO es válido y se muestra como anomalía arriba de todo, con
   * el texto que arma el backend: la regla vive en un solo lugar.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import {
    tonoDeEstado,
    rotuloDeOrden,
    diaLegible,
    instanteLegible
  } from '$lib/v2/hilo-del-cliente.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  let o = $derived(data.orden);
  let seg = $derived(data.seguimiento);
  let mat = $derived(data.materiales);

  /** Los bloques del material, con el rótulo con que se leen. */
  const BLOQUES_MATERIAL = [
    ['consumido', 'Consumido'],
    ['devuelto', 'Devuelto'],
    ['otros', 'Otros movimientos']
  ];

  /** @param {string} id */
  const archivo = (id) => `/api/supervisor-noc/evidencias/${id}/archivo`;
</script>

<svelte:head><title>{rotuloDeOrden(o.numero)} · {o.tipo}</title></svelte:head>

<PageHeader title="{rotuloDeOrden(o.numero)} · {o.tipo}" record>
  {#snippet sub()}
    <span class="cabecera">
      <Pill tone={tonoDeEstado(o.estado_operativo)}>{o.estado_etiqueta}</Pill>
      <span class="v2-sub">Prioridad {o.prioridad}</span>
      {#if o.vuelta > 1}<span class="v2-sub">· vuelta {o.vuelta}</span>{/if}
    </span>
  {/snippet}
  {#snippet actions()}
    {#if o.caso}
      <a class="v2-btn v2-btn-sm" href="/tickets/{o.caso.id}">Ver ticket</a>
    {/if}
    {#await data.conversacion then conv}
      {#if conv}
        <a class="v2-btn v2-btn-sm" href="/conversaciones/{conv}">Ver conversación</a>
      {/if}
    {/await}
    {#if o.servicio}
      <a class="v2-btn v2-btn-sm" href="/clientes/{encodeURIComponent(o.servicio)}">Ficha del cliente</a>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad v2-split-wide pagina">
    <div class="columna">
      <!-- ── La línea de tiempo ─────────────────────────────────────── -->
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Seguimiento</span></div>
        <div class="cuerpo">
          {#if data.errorSeguimiento}
            <p class="v2-sub">{data.errorSeguimiento}</p>
          {:else if seg}
            {#each seg.avisos ?? [] as aviso, i (i)}
              <p class="anomalia" role="note"><strong>Anomalía:</strong> {aviso}</p>
            {/each}
            {#if seg.bloqueo_abierto}
              <p class="anomalia" role="note">
                <strong>Detenida</strong>{#if seg.bloqueo_abierto.abierto_en}
                  desde {instanteLegible(seg.bloqueo_abierto.abierto_en)}{/if}{#if seg.bloqueo_abierto.requiere_noc}
                  · espera al NOC{/if}.
              </p>
            {/if}
            {#if (seg.eventos ?? []).length === 0}
              <p class="v2-sub">Todavía no hay nada registrado en esta orden.</p>
            {:else}
              <ol class="v2-timeline">
                {#each seg.eventos as e, i (e.id)}
                  <li class="v2-event" class:latest={i === seg.eventos.length - 1}>
                    <div class="evento-titulo">{e.etiqueta}</div>
                    <div class="v2-event-meta">
                      {#if e.quien}{e.quien} · {/if}recibido {instanteLegible(e.recibido_en)}
                      {#if e.capturado_en_dispositivo}
                        · capturado {instanteLegible(e.capturado_en_dispositivo)}
                      {/if}
                    </div>
                    {#if e.estado_nuevo}
                      <div class="v2-sub detalle">
                        {#if e.estado_anterior}{e.estado_anterior} → {/if}{e.estado_nuevo}
                      </div>
                    {/if}
                    {#if (e.detalle ?? []).length}
                      <dl class="v2-kv detalle">
                        {#each e.detalle as d (d.id)}
                          <dt>{d.titulo}</dt>
                          <dd>{Array.isArray(d.valor) ? d.valor.join(', ') : (d.valor ?? '—')}</dd>
                        {/each}
                      </dl>
                    {/if}
                    {#if (e.evidencias ?? []).length}
                      <div class="fotos">
                        {#each e.evidencias as f (f.id)}
                          {#if f.disponible}
                            <a href={archivo(f.id)} target="_blank" rel="noopener">{f.nombre_original || 'Foto'}</a>
                          {:else}
                            <span class="v2-sub">{f.nombre_original || 'Foto'} (sin subir)</span>
                          {/if}
                        {/each}
                      </div>
                    {/if}
                  </li>
                {/each}
              </ol>
            {/if}
          {/if}
        </div>
      </section>

      <!-- ── El material ─────────────────────────────────────────────── -->
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Material</span></div>
        <div class="cuerpo">
          {#if data.errorMateriales}
            <p class="v2-sub">{data.errorMateriales}</p>
          {:else if !mat?.hay_algo}
            <p class="v2-sub">Esta orden no movió material.</p>
          {:else}
            {#each BLOQUES_MATERIAL as [clave, rotulo] (clave)}
              {#if (mat[clave] ?? []).length}
                <div class="v2-label sub-bloque">{rotulo}</div>
                <ul class="lineas">
                  {#each mat[clave] as m (m.id)}
                    <li>
                      <span>{m.material.nombre}</span>
                      <span class="v2-sub">{m.cantidad} {m.material.unidad}{#if m.serie} · serie {m.serie}{/if}</span>
                      {#if m.estado && m.estado !== 'confirmado'}<Pill tone="rust">{m.estado}</Pill>{/if}
                    </li>
                  {/each}
                </ul>
              {/if}
            {/each}
            {#if (mat.comprometido ?? []).length}
              <div class="v2-label sub-bloque">Reservado</div>
              <ul class="lineas">
                {#each mat.comprometido as r (r.id)}
                  <li>
                    <span>{r.material.nombre}</span>
                    <span class="v2-sub">{r.cantidad} {r.material.unidad} · {r.pendiente ? 'pendiente' : r.desenlace}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          {/if}
        </div>
      </section>
    </div>

    <aside class="columna">
      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">La visita</span></div>
        <dl class="v2-kv cuerpo">
          <dt>Cliente</dt>
          <dd>{o.cliente?.nombre ?? '—'}</dd>
          <dt>Dirección</dt>
          <dd>{o.cliente?.direccion ?? '—'}</dd>
          {#if o.zona}<dt>Zona</dt><dd>{o.zona}</dd>{/if}
          <dt>Día</dt>
          <dd>{diaLegible(o.fecha) ?? 'Sin programar'}</dd>
          {#if o.ventana_inicio}
            <dt>Franja</dt>
            <dd>{instanteLegible(o.ventana_inicio)} – {instanteLegible(o.ventana_fin)}</dd>
          {/if}
          {#if o.sla_vence_en}<dt>Vence</dt><dd>{instanteLegible(o.sla_vence_en)}</dd>{/if}
          {#if o.iniciada_en}<dt>Iniciada</dt><dd>{instanteLegible(o.iniciada_en)}</dd>{/if}
          {#if o.completada_campo_en}<dt>Completada</dt><dd>{instanteLegible(o.completada_campo_en)}</dd>{/if}
          {#if o.cerrada_en}<dt>Cerrada</dt><dd>{instanteLegible(o.cerrada_en)}</dd>{/if}
          {#if o.caso}
            <dt>Ticket</dt>
            <dd>
              <a href="/tickets/{o.caso.id}">{o.caso.nombre}</a>
              {#if o.caso.external_ticket_id}<span class="v2-sub"> · #{o.caso.external_ticket_id}</span>{/if}
            </dd>
          {/if}
          {#if o.servicio}<dt>Servicio</dt><dd>{o.servicio}</dd>{/if}
        </dl>
        {#if o.resumen}<p class="cuerpo resumen">{o.resumen}</p>{/if}
      </section>

      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Quién va</span></div>
        <div class="cuerpo">
          {#if (o.cuadrilla_integrantes ?? []).length === 0}
            <p class="v2-sub">Sin técnico asignado.</p>
          {:else}
            {#if o.cuadrilla}<p class="v2-sub">{o.cuadrilla}</p>{/if}
            <ul class="lineas">
              {#each o.cuadrilla_integrantes as p, i (i)}
                <li><span>{p.nombre}</span><span class="v2-sub">{p.rol}{p.es_principal ? ' · responsable' : ''}</span></li>
              {/each}
            </ul>
          {/if}
        </div>
      </section>

      <section class="v2-card">
        <div class="v2-card-head"><span class="v2-label">Evidencias</span></div>
        <div class="cuerpo">
          {#if (o.evidencias ?? []).length === 0}
            <p class="v2-sub">Sin evidencias.</p>
          {:else}
            <ul class="lineas">
              {#each o.evidencias as ev (ev.id)}
                <li>
                  {#if ev.estado === 'recibido' || ev.estado === 'verificado'}
                    <a href={archivo(ev.id)} target="_blank" rel="noopener">{ev.nombre || ev.requisito_id}</a>
                  {:else}
                    <span>{ev.nombre || ev.requisito_id}</span>
                  {/if}
                  <span class="v2-sub">{ev.de_un_reporte ? 'de un reporte' : ev.requisito_id} · {ev.estado}</span>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
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
  .cabecera {
    display: inline-flex;
    gap: 8px;
    align-items: center;
  }
  .cuerpo {
    padding: 12px 15px;
  }
  .anomalia {
    margin: 0 0 10px;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 12.5px;
    background: color-mix(in srgb, var(--v2-rust) 8%, transparent);
  }
  .evento-titulo {
    font-weight: 600;
    font-size: 13px;
  }
  .detalle {
    margin-top: 6px;
  }
  .fotos {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 6px;
    font-size: 12.5px;
  }
  .sub-bloque {
    margin: 10px 0 6px;
  }
  .sub-bloque:first-child {
    margin-top: 0;
  }
  .lineas {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 6px;
    font-size: 12.5px;
  }
  .lineas li {
    display: flex;
    gap: 8px;
    align-items: baseline;
    flex-wrap: wrap;
  }
  .resumen {
    margin: 0;
    font-size: 12.5px;
    border-top: 1px solid var(--v2-line);
  }
  a {
    color: var(--v2-ember-text);
  }
</style>
