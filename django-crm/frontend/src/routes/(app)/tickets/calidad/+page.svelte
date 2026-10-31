<script>
  /**
   * Calidad de la atención (28/10/2026).
   *
   * Lo que contestaron los clientes en la encuesta de WhatsApp que les llega al
   * cerrarse su caso. Cuatro preguntas, en el orden en que las hace quien
   * coordina: ¿cómo nos califican?, ¿está mejorando?, ¿quién necesita apoyo?, y
   * ¿qué casos hay que mirar ya?
   *
   * Los números vienen calculados del motor (nunca los suma un modelo). Una
   * persona o un área sin respuestas muestra «—», no cero: cero sería una nota
   * pésima que nadie puso. Y con menos de 5 respuestas se avisa que el número
   * todavía dice poco: dos encuestas malas no definen a nadie.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { shortDate } from '$lib/v2/format.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  let r = $derived(data.resumen);
  const area = (/** @type {string | null} */ a) => (a ? (data.etiquetasArea?.[a] ?? a) : '');
  let total = $derived(r?.total ?? null);
  const POCAS = 5;

  const tonoDe = (/** @type {number | null} */ p) =>
    p == null ? 'slate' : p >= 4 ? 'moss' : p >= 3 ? 'clay' : 'rust';
  const tonoSatisfaccion = (/** @type {number | null} */ s) =>
    s == null ? 'slate' : s >= 85 ? 'moss' : s >= 70 ? 'clay' : 'rust';
  const pct = (/** @type {number | null} */ v) => (v == null ? '—' : `${Math.round(v)}%`);
  const nota = (/** @type {number | null} */ v) => (v == null ? '—' : v.toFixed(1).replace('.', ','));

  let maxOpcion = $derived(Math.max(1, ...(r?.opciones ?? []).map((/** @type {any} */ o) => o.cantidad)));
  let paraRevisar = $derived((r?.recientes ?? []).filter((/** @type {any} */ x) => (x.puntaje ?? 5) <= 2));
</script>

<PageHeader title="Calidad de la atención">
  {#snippet sub()}
    Lo que contestaron los clientes en la encuesta de WhatsApp al cerrarse su caso.
  {/snippet}
</PageHeader>

<SectionTabs set="tickets" />

{#if !data.puedeVer}
  <div class="v2-pad" style="padding-top:40px">
    <div class="v2-card" style="padding:20px 22px;max-width:520px;margin-inline:auto">
      <strong>Esta vista es para quien coordina al equipo.</strong>
      <p>La ven administración, supervisión y operaciones, porque muestra la calidad por persona.</p>
    </div>
  </div>
{:else}
  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="periodo" role="group" aria-label="Período">
      {#each data.periodos as d (d)}
        <a class="v2-btn v2-btn-sm" class:activo={d === data.dias} aria-current={d === data.dias ? 'true' : undefined}
          href={`?dias=${d}`}>Últimos {d} días</a>
      {/each}
      {#if data.desde}<span class="v2-sub">{shortDate(data.desde)} – {shortDate(data.hasta)}</span>{/if}
    </div>

    {#if !r}
      <div class="v2-card aviso">No se pudo leer la información de las encuestas. Probá recargar en un rato.</div>
    {:else if !r.activa && !total?.enviadas}
      <div class="v2-card aviso">
        <strong>La encuesta todavía no está encendida.</strong>
        <p>
          Para que salga al cerrar cada caso con chat: creá la plantilla «Encuesta de satisfacción» en
          Ajustes → WhatsApp → Plantillas, esperá a que Meta la apruebe, y encendé «Encuesta de
          satisfacción» en <a href="/settings/canales/whatsapp/mensajes">Mensajes automáticos</a>.
        </p>
      </div>
    {:else}
      <div class="v2-stats">
        <StatCard
          label="Satisfacción"
          value={pct(total.satisfaccion)}
          tone={tonoSatisfaccion(total.satisfaccion)}
          detail={`Respuestas con ${r.satisfecho_desde} o más, sobre 5`}
        />
        <StatCard label="Puntaje promedio" value={total.promedio == null ? '—' : `${nota(total.promedio)} / 5`}
          tone={tonoDe(total.promedio)} />
        <StatCard
          label="Respondidas"
          value={String(total.respondidas)}
          tone="ink"
          detail={total.enviadas ? `de ${total.enviadas} enviadas (${pct(total.tasa_respuesta)})` : 'Ninguna enviada'}
        />
        <StatCard label="Para revisar" value={String(paraRevisar.length)} tone={paraRevisar.length ? 'rust' : 'slate'}
          detail="Calificaciones de 1 o 2 entre las últimas" />
      </div>
    {/if}
  </div>

  {#if r && (r.activa || total?.enviadas)}
    <div class="v2-scroll">
      <div class="v2-pad" style="padding-bottom:32px">
        {#if total.respondidas > 0 && total.respondidas < POCAS}
          <p class="v2-sub" style="margin:0 0 14px;font-size:12.5px">
            Todavía hay pocas respuestas en este período: los porcentajes van a moverse mucho con cada una.
          </p>
        {/if}

        <div class="grilla">
          <div class="v2-card bloque">
            <div class="v2-label">Qué contestaron</div>
            {#if !r.opciones.length}
              <p class="v2-sub vacio">Nadie contestó todavía en este período.</p>
            {:else}
              {#each r.opciones as o (o.opcion)}
                <div class="barra">
                  <span class="barra-k">{o.opcion}</span>
                  <span class="barra-pista">
                    <i style="width:{(o.cantidad / maxOpcion) * 100}%;background:var(--v2-{tonoDe(o.puntaje)})"></i>
                  </span>
                  <span class="barra-v">{o.cantidad}</span>
                </div>
              {/each}
            {/if}
          </div>

          <div class="v2-card bloque">
            <div class="v2-label">Semana a semana</div>
            {#if !r.por_semana.length}
              <p class="v2-sub vacio">Sin encuestas en este período.</p>
            {:else}
              {#each r.por_semana as s (s.semana)}
                <div class="barra">
                  <span class="barra-k">Sem. {shortDate(s.semana)}</span>
                  <span class="barra-pista">
                    <i style="width:{((s.promedio ?? 0) / 5) * 100}%;background:var(--v2-{tonoDe(s.promedio)})"></i>
                  </span>
                  <span class="barra-v" title={`${s.respondidas} de ${s.enviadas} respondidas`}>{nota(s.promedio)}</span>
                </div>
              {/each}
              <p class="v2-hint" style="margin:8px 0 0">Puntaje promedio de cada semana, sobre 5.</p>
            {/if}
          </div>
        </div>

        {#each [{ titulo: 'Por persona', filas: r.por_responsable }, { titulo: 'Por área', filas: r.por_area.map((/** @type {any} */ f) => ({ ...f, nombre: f.clave ? area(f.clave) : f.nombre })) }] as tabla (tabla.titulo)}
          <div class="v2-card bloque" style="margin-top:18px">
            <div class="v2-label">{tabla.titulo}</div>
            <p class="v2-hint" style="margin:2px 0 10px">Primero las notas más bajas: son las que piden apoyo.</p>
            <div class="tabla" role="table">
              <div class="fila cabeza" role="row">
                <span role="columnheader">Nombre</span>
                <span role="columnheader">Respondidas</span>
                <span role="columnheader">Promedio</span>
                <span role="columnheader">Satisfacción</span>
              </div>
              {#each tabla.filas as f (f.clave)}
                <div class="fila" role="row">
                  <span role="cell">{f.nombre}</span>
                  <span role="cell">{f.respondidas} de {f.enviadas}{#if f.respondidas > 0 && f.respondidas < POCAS}<small>&nbsp;· pocas</small>{/if}</span>
                  <span role="cell"><Pill tone={tonoDe(f.promedio)}>{nota(f.promedio)}</Pill></span>
                  <span role="cell">{pct(f.satisfaccion)}</span>
                </div>
              {/each}
            </div>
          </div>
        {/each}

        <div class="v2-card bloque" style="margin-top:18px">
          <div class="v2-label">Últimas respuestas</div>
          {#if !r.recientes.length}
            <p class="v2-sub vacio">Nadie contestó todavía en este período.</p>
          {:else}
            <div class="recientes">
              {#each r.recientes as x (x.caso_id)}
                <a class="reciente" href={`/tickets/${x.caso_id}`}>
                  <Pill tone={tonoDe(x.puntaje)} dot>{x.opcion}</Pill>
                  <span>{x.responsable ?? 'Sin responsable'}{x.area ? ` · ${area(x.area)}` : ''}</span>
                  <span class="v2-sub">{shortDate(x.respondida_en)}</span>
                  <span aria-hidden="true">→</span>
                </a>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  .periodo {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
  }
  .periodo .activo {
    border-color: var(--v2-ember-line);
    background: var(--v2-ember-soft);
    color: var(--v2-ember-text);
  }
  .aviso {
    padding: 16px 18px;
    max-width: 640px;
    font-size: 13px;
  }
  .aviso p {
    margin: 6px 0 0;
    line-height: 1.5;
  }
  .grilla {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
  }
  @media (max-width: 760px) {
    .grilla {
      grid-template-columns: 1fr;
    }
  }
  .bloque {
    padding: 16px 18px;
  }
  .vacio {
    margin: 10px 0 0;
    font-size: 12.5px;
  }
  .barra {
    display: grid;
    grid-template-columns: 110px 1fr 40px;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
    font-size: 13px;
  }
  .barra-pista {
    height: 10px;
    border-radius: 999px;
    background: var(--v2-line-soft);
    overflow: hidden;
  }
  .barra-pista i {
    display: block;
    height: 100%;
    border-radius: 999px;
  }
  .barra-v {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .tabla {
    display: grid;
    font-size: 13px;
  }
  .fila {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr;
    gap: 10px;
    align-items: center;
    padding: 8px 0;
    border-top: 1px solid var(--v2-line-soft);
  }
  .fila.cabeza {
    border-top: 0;
    font-size: 11.5px;
    color: var(--v2-slate);
  }
  .fila small {
    color: var(--v2-slate);
  }
  .recientes {
    display: grid;
    margin-top: 8px;
  }
  .reciente {
    display: grid;
    grid-template-columns: auto 1fr auto auto;
    gap: 12px;
    align-items: center;
    padding: 9px 4px;
    border-top: 1px solid var(--v2-line-soft);
    color: inherit;
    text-decoration: none;
    font-size: 13px;
  }
  .reciente:first-child {
    border-top: 0;
  }
  .reciente:hover {
    background: var(--v2-hover);
  }
</style>
