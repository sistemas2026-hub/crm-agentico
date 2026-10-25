<script>
  import { page } from '$app/state';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import FilterBar from '$lib/v2/components/FilterBar.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { count, shortAge } from '$lib/v2/format.js';
  import {
    PRIORITY_TONE,
    CASE_STATUS_TONE,
    CASE_PRIORITY_LABEL,
    CASE_STATUS_LABEL
  } from '$lib/v2/enums.js';
  import { LifeBuoy, Plus, MessageCircle, Server, PenLine } from '@lucide/svelte';
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import { origenDelTicket } from '$lib/v2/ticket-origen.js';

  /** @type {{ data: any, form?: any }} */
  let { data, form } = $props();

  //  Si no se pudo tomar -- otra persona lo tomo primero -- la fila que se ve
  //  ya esta vieja: se recarga la cola ademas de mostrar el motivo.
  const alTomar = () => async (/** @type {any} */ { result, update }) => {
    await update();
    if (result.type === 'failure') await invalidateAll();
  };

  let tickets = $derived(data.tickets);
  let totals = $derived(data.totals);

  /**
   * How the first-reply clock stands.
   *
   * The deadline arrives from the server, where it is walked through the org's
   * business calendar and pushed forward by any time the ticket spent waiting
   * on the customer. Recomputing it here from `opened_at + hours`, which is
   * what the mock did, would put a second, quietly different answer on the
   * same screen.
   *
   * A progress bar only means something while there is still time on the
   * clock. Past the deadline a bar pinned at 100% says nothing about how bad
   * it is, so we stop drawing one and say how far over it went instead.
   *
   * @param {any} t
   */
  function responsePressure(t) {
    if (t.first_response_at) {
      const took =
        (new Date(t.first_response_at).getTime() - new Date(t.opened_at).getTime()) / 6e4;
      return { state: 'met', label: `Respondido a los ${fmtMins(took)}`, tone: 'moss' };
    }
    if (!t.first_response_deadline) {
      return { state: 'none', label: 'Sin objetivo', tone: 'slate' };
    }
    const now = Date.now();
    const opened = new Date(t.opened_at).getTime();
    const due = new Date(t.first_response_deadline).getTime();
    if (now >= due) {
      return { state: 'breached', label: `Venció hace ${fmtMins((now - due) / 6e4)}`, tone: 'rust' };
    }
    const pct = Math.max(0, Math.min(100, Math.round(((now - opened) / (due - opened)) * 100)));
    return {
      state: 'running',
      pct,
      label: `Vence en ${fmtMins((due - now) / 6e4)}`,
      // Fibra: rojo SOLO cuando ya vencio; ambar desde el 75 %; antes, el
      // color de accion. Hasta el 23/10/2026 se ponia rojo al 75 % sin
      // haber vencido, y rojo dejaba de querer decir "vencido".
      tone: pct >= 75 ? 'clay' : 'ember'
    };
  }

  /** @param {number} m */
  function fmtMins(m) {
    const n = Math.max(0, Math.round(m));
    if (n < 60) return `${n} min`;
    if (n < 1440) return `${Math.round(n / 60)} h`;
    const d = Math.round(n / 1440);
    return d === 1 ? '1 día' : `${d} días`;
  }

  const TONE_VAR = {
    moss: 'var(--v2-moss)',
    rust: 'var(--v2-rust)',
    clay: 'var(--v2-clay)',
    slate: 'var(--v2-slate)',
    ember: 'var(--v2-ember)'
  };

  const VISTAS = [
    { clave: 'todos', etiqueta: 'Todos' },
    { clave: 'mios', etiqueta: 'Míos' },
    { clave: 'sin_asignar', etiqueta: 'Sin asignar' }
  ];

  /**
   * Reescribe UN parametro sobre la URL actual y vuelve a la primera pagina.
   * Cambiar de vista, de area o de orden CONSERVA los filtros ya puestos:
   * perder el filtro de estado por pasar a "Míos" obligaria a ponerlo de
   * nuevo cada vez. El 'offset' se descarta: la pagina 7 de "Todos" no existe
   * en "Míos".
   */
  function hrefCon(/** @type {string} */ clave, /** @type {string|null} */ valor) {
    const p = new URLSearchParams(page.url.searchParams);
    p.delete('offset');
    if (valor === null) p.delete(clave);
    else p.set(clave, valor);
    const q = p.toString();
    return q ? `?${q}` : '?';
  }

  /** El nombre visible de un area interna ('soporte_tecnico' -> 'Soporte Técnico'). */
  let etiquetaDeArea = $derived(
    Object.fromEntries(
      [...(data.selectorAreas ?? []), ...(data.areas ?? [])].map((/** @type {any} */ a) => [
        a.nombre,
        a.etiqueta
      ])
    )
  );

  const ORIGEN_ICONO = { whatsapp: MessageCircle, wisphub: Server, manual: PenLine };

  /**
   * Con el orden "vence primero", la cola se parte en tres tramos que se leen
   * de un vistazo. El tramo lo decide el MISMO reloj que dibuja la barra
   * (responsePressure, con el vencimiento que calcula el servidor), no otro
   * calculo: si el tramo y la barra no coincidieran, la pantalla se
   * contradiria en la misma fila. Dentro de cada tramo se respeta el orden
   * que mando el servidor.
   */
  let grupos = $derived.by(() => {
    if (data.orden !== 'vence') return [{ clave: 'todos', etiqueta: '', filas: tickets }];
    /** @type {Record<string, any[]>} */
    const tramos = { urg: [], aten: [], ok: [] };
    for (const t of tickets) {
      const p = responsePressure(t);
      const clave = p.state === 'breached' ? 'urg'
        : p.state === 'running' && p.pct >= 75 ? 'aten' : 'ok';
      tramos[clave].push(t);
    }
    return [
      { clave: 'urg', etiqueta: 'Vencieron', filas: tramos.urg },
      { clave: 'aten', etiqueta: 'Por vencer', filas: tramos.aten },
      { clave: 'ok', etiqueta: 'En plazo o respondidos', filas: tramos.ok }
    ].filter((g) => g.filas.length);
  });

  /**
   * El nombre del caso viene como "Asunto · Cliente · #id8" desde el
   * asistente. La cola necesita leer el asunto de un vistazo, y el id solo
   * cuando hay que cruzarlo con la conversacion -- asi que va abajo, chico.
   *
   * Los casos viejos traen el formato anterior ("WhatsApp <numero> - <id8>"):
   * se parten por el mismo criterio (el ultimo tramo es el identificador) y
   * siguen legibles, sin migrar ni tocar una sola fila existente.
   */
  function partirAsunto(/** @type {string} */ nombre) {
    const limpio = (nombre ?? '').trim();
    const tramos = limpio.split(' · ');
    if (tramos.length > 1 && tramos[tramos.length - 1].startsWith('#')) {
      // El cliente baja a la linea secundaria y NO se descarta: la columna
      // 'Cuenta' esta vacia en todo caso que llega por conversacion (se crean
      // sin account), asi que borrarlo de aca lo borraria de la pantalla.
      return {
        principal: tramos[0],
        cliente: tramos.slice(1, -1).join(' · '),
        id: tramos[tramos.length - 1]
      };
    }
    // Formato viejo: "WhatsApp 573001234567 - a1b2c3d4"
    const viejo = limpio.match(/^WhatsApp\s+(\S+)\s+-\s+(\S+)$/);
    if (viejo) return { principal: `Conversación de ${viejo[1]}`, cliente: '', id: `#${viejo[2]}` };
    return { principal: limpio || 'Sin asunto', cliente: '', id: '' };
  }

</script>

<nav class="migas" aria-label="Ruta">
  <a href="/">Inicio</a><span aria-hidden="true">›</span><span aria-current="page">Tickets</span>
</nav>

<PageHeader title="Tickets">
  {#snippet sub()}
    {#if data.sinAreaPropia}
      Tu usuario todavía no tiene un área asignada.
    {:else}
      <span class="v2-num">{count(totals.open)}</span> abiertos
      {#if data.conteosVista?.sin_asignar != null}
        &middot; <span class="v2-num">{count(data.conteosVista.sin_asignar)}</span> sin asignar
      {/if}
      &middot; <span class="v2-num">{count(totals.awaiting_reply)}</span> sin primera respuesta
    {/if}
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-primary" href="/tickets/new"><Plus /> Nuevo ticket</a>
  {/snippet}
</PageHeader>

<!-- Approvals and Analytics were buttons in this header that went nowhere.
     They are sibling pages, so they belong in a tab strip that also tells you
     which one you are on. -->
<SectionTabs set="tickets" />

{#if data.sinAreaPropia}
  <div class="aviso-sin-area">
    <p><b>Tu usuario todavía no tiene un área asignada.</b></p>
    <p>
      Por eso no se muestra ninguna cola: los tickets se organizan por área, y sin
      una definida no hay forma de saber cuáles te corresponden. Pedile a quien
      administra la plataforma que te asigne un área desde <b>Agentes</b>.
    </p>
  </div>
{:else}
  <!-- La barra de la cola: de quien, que area, y en que orden. Las tres viajan
       por la URL, asi un enlace a "sin asignar de Soporte, vence primero"
       sigue diciendo lo mismo al abrirlo. -->
  {#if form?.error}
    <p class="aviso-accion" role="alert">{form.error}</p>
  {/if}
  <div class="barra-cola">
    <div class="vistas" role="group" aria-label="De quién">
      {#each VISTAS as v (v.clave)}
        {@const n = v.clave === 'todos' ? totals.open : data.conteosVista?.[v.clave]}
        <a
          class="vista"
          href={hrefCon('vista', v.clave === 'todos' ? null : v.clave)}
          aria-current={data.vista === v.clave ? 'page' : undefined}
        >
          {v.etiqueta}
          {#if n != null}<span class="v2-num">{count(n)}</span>{/if}
        </a>
      {/each}
    </div>

    {#if data.soloMiArea}
      <span class="area-fija">Área: <b>{etiquetaDeArea[data.areaElegida] ?? data.areaElegida}</b></span>
    {:else if (data.selectorAreas ?? []).length > 1}
      <!-- Un formulario GET y no un menu armado a mano: funciona sin JS, se
           puede compartir el enlace que deja, y conserva los demas filtros
           (los campos ocultos). Con JS se envia solo al elegir. -->
      <form method="GET" class="area-form">
        {#each [...page.url.searchParams.entries()] as [k, val] (k + val)}
          {#if k !== 'area' && k !== 'offset'}<input type="hidden" name={k} value={val} />{/if}
        {/each}
        <label for="area-cola">Área</label>
        <select
          id="area-cola"
          name="area"
          class="v2-input area-select"
          value={data.areaElegida}
          onchange={(e) => e.currentTarget.form?.requestSubmit()}
        >
          {#each data.selectorAreas as a (a.nombre)}
            <option value={a.nombre}>{a.etiqueta}{a.total != null ? ` (${a.total})` : ''}</option>
          {/each}
        </select>
        <noscript><button class="v2-btn v2-btn-sm" type="submit">Ver</button></noscript>
      </form>
    {/if}

    <div class="orden" role="group" aria-label="Orden">
      <span class="orden-rotulo">Orden</span>
      <a class="vista" href={hrefCon('orden', null)} aria-current={data.orden === 'vence' ? 'page' : undefined}
        >Vence primero</a
      >
      <a class="vista" href={hrefCon('orden', 'recientes')}
        aria-current={data.orden === 'recientes' ? 'page' : undefined}>Más recientes</a
      >
    </div>
  </div>

{#if page.url.search}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">Estos números describen la cola filtrada.</p>
{/if}
{#if data.deOtrasAreas > 0}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">
    En esta página {data.deOtrasAreas === 1 ? 'hay 1 ticket de otra área asignado' : `hay ${data.deOtrasAreas} tickets de otra área asignados`}
    a vos: los ves porque son tuyos, y cuentan en su área.
  </p>
{/if}


<FilterBar
  page="tickets"
  url={page.url}
  people={data.people}
  tags={data.tags}
  meId={data.meId}
  buscar
  buscarEtiqueta="Buscar por cliente, asunto o n.º de ticket"
  meta="Los objetivos de primera respuesta vienen de las horas de SLA de cada ticket"
/>

<div class="v2-scroll">
  {#if tickets.length === 0}
    <!-- An empty queue is good news, so it does not read like a failure. -->
    <EmptyState
      title={data.showAll ? 'Todavía no hay tickets acá' : 'La cola está despejada'}
      body={data.showAll
        ? 'Todavía no escaló ninguna conversación. Los casos llegan acá solos cuando el asistente pasa una a una persona.'
        : 'Nada está esperando a tu equipo ahora mismo. Los tickets cerrados y rechazados siguen acá. Simplemente no estorban.'}
    >
      {#snippet icon()}<LifeBuoy size={21} />{/snippet}
      {#snippet actions()}
        {#if !data.showAll}
          <a class="v2-btn" href="/tickets?all=1">Mostrar los cerrados también</a>
        {/if}
        <a class="v2-btn" href="/solutions">Base de conocimiento</a>
      {/snippet}
    </EmptyState>
  {:else}
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <!-- El plazo va PRIMERO (23/10/2026): con "vence primero" es lo que
                 decide que se abre a continuacion. Cliente, numero y area
                 bajaron a la segunda linea del asunto, que es donde se leen
                 junto con lo que pide el cliente. -->
            <th style="width:160px">Primera respuesta</th>
            <th>Asunto</th>
            <th>Origen</th>
            <th>Prioridad</th>
            <th>Estado</th>
            <th>Responsable</th>
          </tr>
        </thead>
        <tbody>
          {#each grupos as g (g.clave)}
            {#if g.etiqueta}
              <tr class="tramo" data-tramo={g.clave}>
                <td colspan="6"><i aria-hidden="true"></i>{g.etiqueta} <span class="v2-num">{g.filas.length}</span></td>
              </tr>
            {/if}
            {#each g.filas as t (t.id)}
              {@const p = responsePressure(t)}
              {@const asunto = partirAsunto(t.name)}
              {@const origen = origenDelTicket(t)}
              {@const OrigenIcono = ORIGEN_ICONO[origen.clave]}
              <!-- La fila entera abre el ticket, no solo el asunto: ver
                   .v2-row-click en v2.css y el clic que no hacia nada. -->
              <tr class="v2-row-click">
                <!-- Kept on a phone: a running first-reply clock is the one
                     thing in this queue that decides what to open next. -->
                <td data-m="meta">
                  <span class="plazo-texto v2-num" style="color:{TONE_VAR[p.tone]}">{p.label}</span>
                  {#if p.state === 'running' || p.state === 'breached'}
                    <span class="plazo-pista" aria-hidden="true"
                      ><i style="width:{p.state === 'breached' ? 100 : p.pct}%;background:{TONE_VAR[p.tone]}"></i></span
                    >
                  {/if}
                </td>
                <td data-m="title">
                  <a class="v2-row-link" href="/tickets/{t.id}">
                    <span class="v2-table-primary">{asunto.principal}</span>
                  </a>
                  <span class="asunto-id">
                    {#if t.external_client_name || asunto.cliente}{t.external_client_name || asunto.cliente} &middot; {/if}
                    {#if t.external_ticket_id}<span class="v2-num">#{t.external_ticket_id}</span>
                    {:else if asunto.id}<span class="v2-num">{asunto.id}</span>{/if}
                    {#if t.area && etiquetaDeArea[t.area]} &middot; {etiquetaDeArea[t.area]}{/if}
                    &middot; hace {shortAge(t.opened_at)}
                  </span>
                </td>
                <td data-m="hide">
                  <span class="origen" data-origen={origen.clave}><OrigenIcono size={13} />{origen.etiqueta}</span>
                </td>
                <td><Pill tone={PRIORITY_TONE[t.priority]}>{CASE_PRIORITY_LABEL[t.priority] ?? t.priority}</Pill></td>
                <!-- EL ESTADO DEL PROVEEDOR, y la divergencia cuando la hay.
                     El equipo trabaja con los estados de WispHub (Nuevo / En
                     Progreso / Cerrado); los de Dexter son otros y mostrarlos
                     solos obligaba a traducir de cabeza. Pero no se reemplaza a
                     ciegas: cuando el proveedor ya cerro y en Dexter sigue
                     abierto --12 casos el 07/10/2026-- esa diferencia es el
                     dato, y se dice. -->
                <td data-m="tag">
                  {#if t.external_status}
                    <Pill tone={CASE_STATUS_TONE[t.status]}>{t.external_status}</Pill>
                    {#if t.status !== 'Closed' && t.external_status === 'Cerrado'}
                      <span class="divergencia">abierto en Dexter</span>
                    {/if}
                  {:else}
                    <Pill tone={CASE_STATUS_TONE[t.status]}>{CASE_STATUS_LABEL[t.status] ?? t.status}</Pill>
                  {/if}
                </td>
                <td data-m="hide">
                  {#if t.assignee}
                    <!-- Con nombre, no solo la inicial: una 'D' sola no
                         distingue a dos personas del equipo cuyo nombre empieza
                         igual. Y si hay mas de un asignado se dice. -->
                    <span class="asignado">
                      <Avatar name={t.assignee} size={22} />
                      <span class="asignado-nombre">{t.assignee}</span>
                      {#if t.assignee_count > 1}
                        <span class="asignado-mas">+{t.assignee_count - 1}</span>
                      {/if}
                    </span>
                  {:else}
                    <span class="asignado">
                      <span class="v2-muted" style="font-size:12.5px">Sin asignar</span>
                      <!-- En cada fila sin responsable: si se ve, se puede
                           tomar. Quien reparte ve todo; un colaborador solo
                           ve lo sin asignar de SU area. Lo decide el backend
                           ('/tomar/'), no este boton. -->
                      <form method="POST" action="?/asignarme" use:enhance={alTomar} class="asignarme">
                        <input type="hidden" name="id" value={t.id} />
                        <button class="v2-btn v2-btn-sm" type="submit">Asignarme</button>
                      </form>
                    </span>
                  {/if}
                </td>
              </tr>
            {/each}
          {/each}
        </tbody>
      </table>
    </div>
    <!-- El pie dice QUE TRAMO se esta viendo y, si hay mas, como llegar.
         Antes decia "Mostrando 25 de 47" y ahi terminaba: los otros 22 no
         tenian camino. -->
    <div class="pie-cola v2-pad">
      <p class="v2-sub" style="font-size:12px;margin:0">
        Mostrando <span class="v2-num">{data.paginacion.desde}</span>–<span
          class="v2-num">{data.paginacion.hasta}</span>
        de <span class="v2-num">{count(data.paginacion.total)}</span>
        {#if !data.showAll}
          · <a href="/tickets?all=1" style="color:inherit">incluir cerrados</a>
        {:else}
          · <a href="/tickets" style="color:inherit">solo abiertos</a>
        {/if}
      </p>
      {#if data.paginacion.previa || data.paginacion.siguiente}
        <nav class="paginas" aria-label="Paginación de la cola">
          <!-- Numerada y no solo Anterior/Siguiente: con 24 paginas, llegar
               al final a saltos de uno son 23 clics. La ultima SIEMPRE esta
               a la vista. -->
          {#if data.paginacion.previa}
            <a class="v2-btn v2-btn-sm" href={data.paginacion.previa}>Anterior</a>
          {:else}
            <span class="v2-btn v2-btn-sm pag-off">Anterior</span>
          {/if}
          {#each data.paginacion.numeros as p}
            {#if p === null}
              <span class="pag-hueco" aria-hidden="true">…</span>
            {:else if p.actual}
              <span class="v2-btn v2-btn-sm pag-actual" aria-current="page">{p.n}</span>
            {:else}
              <a class="v2-btn v2-btn-sm" href={p.url}>{p.n}</a>
            {/if}
          {/each}
          {#if data.paginacion.siguiente}
            <a class="v2-btn v2-btn-sm" href={data.paginacion.siguiente}>Siguiente</a>
          {:else}
            <span class="v2-btn v2-btn-sm pag-off">Siguiente</span>
          {/if}
        </nav>
      {/if}
    </div>
  {/if}
</div>
{/if}

<style>
  /* ── la barra de la cola (23/10/2026) ──────────────────────────────── */
  .barra-cola {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 16px;
    padding: 14px var(--v2-pad) 4px;
  }
  .vistas,
  .orden {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .orden {
    margin-left: auto;
  }
  .orden-rotulo {
    font-size: 12.5px;
    color: var(--v2-slate);
    margin-right: 2px;
  }
  .vista {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 34px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid var(--v2-line-strong);
    background: var(--v2-card);
    color: var(--v2-ink);
    font-size: 12.5px;
    font-weight: 600;
    text-decoration: none;
  }
  .vista:hover {
    border-color: var(--v2-ember);
  }
  .vista[aria-current='page'] {
    background: var(--v2-ink);
    border-color: var(--v2-ink);
    color: var(--v2-paper);
  }
  .area-form {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    color: var(--v2-slate);
  }
  .area-select {
    width: auto;
    min-height: 34px;
    padding: 4px 10px;
    font-size: 13px;
  }
  .area-fija {
    font-size: 13px;
    color: var(--v2-slate);
  }
  .area-fija b {
    color: var(--v2-ink);
    font-weight: 650;
  }
  /* Los tramos de "vence primero": una fila de cabecera por grupo, del color
     de lo que dice. */
  .tramo td {
    height: auto;
    padding: 8px 14px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--v2-slate);
    background: color-mix(in srgb, var(--v2-paper) 60%, var(--v2-card));
  }
  .tramo i {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: 1px;
    background: currentColor;
  }
  .tramo[data-tramo='urg'] td {
    color: var(--v2-rust);
  }
  .tramo[data-tramo='aten'] td {
    color: var(--v2-clay);
  }
  .plazo-texto {
    display: block;
    font-size: 12px;
    font-weight: 650;
    white-space: nowrap;
  }
  .plazo-pista {
    display: block;
    width: 120px;
    max-width: 100%;
    height: 4px;
    margin-top: 5px;
    border-radius: 999px;
    background: var(--v2-line-soft);
    overflow: hidden;
  }
  .plazo-pista i {
    display: block;
    height: 100%;
    border-radius: 999px;
  }
  .origen {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    font-weight: 650;
    padding: 3px 9px;
    border-radius: 999px;
    white-space: nowrap;
    color: var(--v2-origen-ink);
    background: var(--v2-origen);
  }
  .origen[data-origen='whatsapp'] {
    color: var(--v2-ember-text);
    background: var(--v2-ember-soft);
  }
  /* Encima de la capa que hace clicable toda la fila (.v2-row-click). */
  .asignarme {
    position: relative;
    z-index: 1;
    display: inline-flex;
  }
  .pie-cola {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 24px;
  }
  .paginas {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
  }
  /* La actual no es un enlace: lleva a donde ya estas. Se marca y no se pulsa. */
  .pag-actual {
    font-weight: 600;
    background: var(--v2-ember-soft);
    border-color: var(--v2-ember);
    cursor: default;
  }
  /* Los extremos se muestran apagados en vez de desaparecer: si el boton se
     va, los numeros se corren y el siguiente clic cae en otro lado. */
  .pag-off {
    opacity: 0.4;
    cursor: default;
  }
  .pag-hueco {
    padding: 0 2px;
    color: var(--v2-slate);
  }
  .divergencia {
    display: block;
    margin-top: 2px;
    font-size: 11px;
    color: var(--v2-slate);
  }
  .asignado {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
  }
  .asignado-nombre {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 140px;
  }
  .asignado-mas {
    color: var(--v2-slate);
    font-size: 11px;
  }
  .asunto-id {
    display: block;
    font-size: 11px;
    color: var(--v2-slate);
    margin-top: 1px;
  }
  .aviso-sin-area {
    max-width: 62ch;
    margin: 16px 0 22px;
    padding: 14px 16px;
    border: 1px solid var(--v2-line, #e3e4e1);
    border-left: 3px solid var(--v2-clay, #a8560b);
    border-radius: 8px;
    background: var(--v2-card, #fff);
    font-size: 13px;
    line-height: 1.55;
  }
  .aviso-sin-area p {
    margin: 0;
  }
  .aviso-accion {
    margin: 12px 0 0;
    padding: 10px 14px;
    border: 1px solid var(--v2-line);
    border-left: 3px solid var(--v2-clay);
    border-radius: 8px;
    background: var(--v2-card);
    font-size: 13px;
  }
  .aviso-sin-area p + p {
    margin-top: 6px;
    color: var(--v2-slate);
  }
  .migas {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 14px 0 2px;
    font-size: 12px;
    color: var(--v2-slate);
  }
  .migas a {
    color: inherit;
    text-decoration: none;
  }
  .migas a:hover {
    color: var(--v2-ink, #1c1f21);
    text-decoration: underline;
  }
</style>
