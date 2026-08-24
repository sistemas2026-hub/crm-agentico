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
    CASE_STATUS_LABEL,
    CASE_TYPE_LABEL
  } from '$lib/v2/enums.js';
  import { LifeBuoy, Wrench, Receipt, Building2, Network, UserRound,
           PackageOpen } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

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
      return { state: 'met', label: `Cumplido en ${fmtMins(took)}`, tone: 'moss' };
    }
    if (!t.first_response_deadline) {
      return { state: 'none', label: 'Sin objetivo', tone: 'slate' };
    }
    const now = Date.now();
    const opened = new Date(t.opened_at).getTime();
    const due = new Date(t.first_response_deadline).getTime();
    if (now >= due) {
      return { state: 'breached', label: `${fmtMins((now - due) / 6e4)} de más`, tone: 'rust' };
    }
    const pct = Math.max(0, Math.min(100, Math.round(((now - opened) / (due - opened)) * 100)));
    return {
      state: 'running',
      pct,
      label: `${fmtMins((due - now) / 6e4)} restantes`,
      tone: pct >= 75 ? 'rust' : pct >= 50 ? 'clay' : 'slate'
    };
  }

  /** @param {number} m */
  function fmtMins(m) {
    const n = Math.max(0, Math.round(m));
    if (n < 60) return `${n}m`;
    if (n < 1440) return `${Math.round(n / 60)}h`;
    return `${Math.round(n / 1440)}d`;
  }

  const TONE_VAR = {
    moss: 'var(--v2-moss)',
    rust: 'var(--v2-rust)',
    clay: 'var(--v2-clay)',
    slate: 'var(--v2-slate)'
  };
  /**
   * Catalogo GENERICO de iconos. La empresa elige cual le toca a cada area
   * (campo 'icono' de su config); la pantalla solo sabe dibujarlos.
   *
   * Es la misma linea que separa 'nombre' de 'etiqueta': el vocabulario es
   * del producto, la eleccion es de la empresa. Un icono que se llamara
   * "soporte" en vez de "llave" volveria a meter el organigrama de un ISP
   * dentro del CSS del otro.
   */
  const ICONOS = {
    llave: Wrench,
    factura: Receipt,
    edificio: Building2,
    red: Network,
    persona: UserRound,
    caja: PackageOpen
  };

  /**
   * Color de un area cuando su config no declara uno.
   *
   * Se deriva del nombre, no de la posicion en la lista: asi el color de un
   * area no cambia porque alguien reordeno la config o declaro una nueva
   * arriba. Un tono que baila entre recargas no sirve para reconocer nada.
   */
  function colorDeArea(/** @type {any} */ a) {
    if (a.color) return a.color;
    let h = 0;
    for (const c of a.nombre ?? '') h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h} 52% 46%)`;
  }

  const VISTAS = [
    { clave: 'todos', etiqueta: 'Todos' },
    { clave: 'mios', etiqueta: 'Mis asignados' },
    { clave: 'sin_asignar', etiqueta: 'Sin asignar' }
  ];

  /**
   * Cambiar de vista CONSERVA los filtros ya puestos -- se reescribe un solo
   * parametro sobre la URL actual en vez de armar una nueva. Perder el filtro
   * de estado por pasar a "Mis asignados" obligaria a ponerlo de nuevo cada
   * vez, y ensena que la sub-navegacion pisa el trabajo anterior.
   */
  function hrefVista(/** @type {string} */ clave) {
    const p = new URLSearchParams(page.url.searchParams);
    if (clave === 'todos') p.delete('vista');
    else p.set('vista', clave);
    return `?${p.toString()}`;
  }

  /** Iniciales, para un area sin icono declarado. */
  const iniciales = (/** @type {string} */ etiqueta) =>
    (etiqueta ?? '')
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join('');

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

{#if !data.areaElegida}
  <!-- La pantalla NO arranca con todos los tickets mezclados. Arranca
       diciendo donde esta la carga, que es la pregunta que alguien se hace al
       abrirla: ¿que area esta desbordada? Recien despues se entra a una. -->
  <nav class="migas" aria-label="Ruta">
    <a href="/">Inicio</a><span aria-hidden="true">›</span><span aria-current="page">Tickets</span>
  </nav>

  <PageHeader title="Tickets">
    {#snippet sub()}Elegí un área para ver su cola.{/snippet}
  </PageHeader>

  <h2 class="titulo-seccion">Tickets por área</h2>

  <div class="areas-grilla">
    {#each data.areas ?? [] as a (a.nombre)}
      {@const Icono = ICONOS[a.icono]}
      <a
        class="area-tarjeta"
        href="/tickets?area={encodeURIComponent(a.nombre)}"
        style="--area-color: {colorDeArea(a)}"
      >
        <span class="area-marca" aria-hidden="true">
          {#if Icono}
            <Icono size={17} strokeWidth={1.9} />
          {:else}
            <span class="area-iniciales">{iniciales(a.etiqueta)}</span>
          {/if}
        </span>
        <span class="area-nombre">{a.etiqueta}</span>
        <span class="area-total v2-num">{a.total}</span>
        <span class="area-detalle">
          <!-- Apagados cuando son cero: un "0 urgentes" en rojo grita algo
               que no esta pasando. -->
          <span class="marca urgente" class:hay={a.urgentes > 0}
            >{a.urgentes} urgente{a.urgentes === 1 ? '' : 's'}</span
          >
          <span class="marca espera" class:hay={a.sin_respuesta > 0}
            >{a.sin_respuesta} sin respuesta</span
          >
        </span>
        {#if a.sin_asignar > 0}
          <span class="area-sin-asignar">{a.sin_asignar} sin asignar</span>
        {/if}
      </a>
    {/each}
  </div>

  {#if data.sinAreaPropia}
    <div class="aviso-sin-area">
      <p><b>Tu usuario todavía no tiene un área asignada.</b></p>
      <p>
        Por eso no se muestra ninguna cola: los tickets se organizan por área, y sin
        una definida no hay forma de saber cuáles te corresponden. Pedile a quien
        administra la plataforma que te asigne un área desde <b>Agentes</b>.
      </p>
    </div>
  {:else if !(data.areas ?? []).length}
    <p class="v2-sub" style="padding:0 0 18px">
      No se pudieron leer las áreas del asistente. Abajo está la cola sin agrupar.
    </p>
  {/if}
{:else}
  {@const actual = (data.areas ?? []).find((/** @type {any} */ x) => x.nombre === data.areaElegida)}
  <nav class="migas" aria-label="Ruta">
    <a href="/">Inicio</a><span aria-hidden="true">›</span>
    {#if data.soloMiArea}
      <span>Tickets</span><span aria-hidden="true">›</span>
    {:else}
      <a href="/tickets">Tickets</a><span aria-hidden="true">›</span>
    {/if}
    <span aria-current="page">{actual?.etiqueta ?? 'Área'}</span>
  </nav>

  <PageHeader title={actual?.etiqueta ?? 'Área'}>
    {#snippet sub()}
      <span class="v2-num">{actual?.total ?? 0}</span> en total &middot;
      <span class="v2-num">{actual?.urgentes ?? 0}</span> urgentes &middot;
      <span class="v2-num">{actual?.sin_asignar ?? 0}</span> sin asignar &middot;
      <span class="v2-num">{actual?.sin_respuesta ?? 0}</span> sin respuesta &middot;
      <span class="v2-num">{actual?.en_progreso ?? 0}</span> en progreso
    {/snippet}
    {#snippet actions()}
      {#if !data.soloMiArea}
        <a class="v2-btn v2-btn-sm" href="/tickets">&larr; Volver a áreas</a>
      {/if}
    {/snippet}
  </PageHeader>

  <!-- Los tres cortes que alguien hace sobre su propia cola, y que no son un
       filtro mas: "que me toca a mi" y "que no le toca a nadie" son las dos
       preguntas con las que se abre el dia. Viajan por la URL para que un
       enlace a "sin asignar de Soporte" siga diciendo lo mismo al abrirlo. -->
  <nav class="v2-tabs sub-nav" aria-label="Vista del área">
    {#each VISTAS as v (v.clave)}
      <a
        href={hrefVista(v.clave)}
        aria-current={(page.url.searchParams.get('vista') ?? 'todos') === v.clave
          ? 'page'
          : undefined}
      >
        {v.etiqueta}
        {#if v.clave !== 'todos' && data.conteosVista?.[v.clave]}
          <span class="v2-tab-count v2-num">{data.conteosVista[v.clave]}</span>
        {/if}
      </a>
    {/each}
  </nav>
{/if}

{#if !data.sinAreaPropia && (data.areaElegida || !(data.areas ?? []).length)}
{#if page.url.search}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">Estos números describen la cola filtrada.</p>
{/if}

<!-- Approvals and Analytics were buttons in this header that went nowhere.
     They are sibling pages, so they belong in a tab strip that also tells you
     which one you are on. -->
<SectionTabs set="tickets" />

<FilterBar
  page="tickets"
  url={page.url}
  people={data.people}
  tags={data.tags}
  meId={data.meId}
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
            <th>Asunto</th>
            <th>Prioridad</th>
            <th>Estado</th>
            <th>Tipo</th>
            <th>Cuenta</th>
            <th>Asignado a</th>
            <th class="v2-r">Antigüedad</th>
            <th style="width:130px">Primera respuesta</th>
          </tr>
        </thead>
        <tbody>
          {#each tickets as t (t.id)}
            {@const p = responsePressure(t)}
            {@const asunto = partirAsunto(t.name)}
            <tr>
              <td data-m="title">
                <a class="v2-row-link" href="/tickets/{t.id}">
                  <span class="v2-table-primary">{asunto.principal}</span>
                </a>
                {#if asunto.id}
                  <span class="asunto-id">
                    {#if asunto.cliente}{asunto.cliente} &middot; {/if}Ticket {asunto.id}
                    &middot; WhatsApp
                  </span>
                {/if}
              </td>
              <td><Pill tone={PRIORITY_TONE[t.priority]}>{CASE_PRIORITY_LABEL[t.priority] ?? t.priority}</Pill></td>
              <td data-m="tag"><Pill tone={CASE_STATUS_TONE[t.status]}>{CASE_STATUS_LABEL[t.status] ?? t.status}</Pill></td>
              <!-- Nullable on the model and null on plenty of rows, so it says
                   so rather than printing an empty cell. -->
              <!-- Traducido como el resto de la fila. El valor viaja en
                   ingles porque es el enum del CRM ('Question' / 'Incident' /
                   'Problem'); dejarlo crudo era la unica palabra en ingles de
                   una pantalla en espanol. El mapa ya existia en enums.js y
                   esta columna no lo usaba. -->
              <td class="v2-muted" data-m="hide" style="font-size:12.5px">
                {CASE_TYPE_LABEL[t.case_type] ?? t.case_type ?? '—'}
              </td>
              <td class="v2-muted" style="font-size:12.5px">
                {#if t.account}
                  <a class="v2-row-link" href="/accounts/{t.account.id}">{t.account.name}</a>
                {:else}
                  Sin cuenta
                {/if}
              </td>
              <td data-m="hide">
                {#if t.assignee}
                  <!-- Con nombre, no solo la inicial: una 'D' sola no
                       distingue a dos personas del equipo cuyo nombre empieza
                       igual, que es justo cuando hace falta saber a quien le
                       toca. Y si hay mas de un asignado se dice, en vez de
                       mostrar al primero como si fuera el unico. -->
                  <span class="asignado">
                    <Avatar name={t.assignee} size={22} />
                    <span class="asignado-nombre">{t.assignee}</span>
                    {#if t.assignee_count > 1}
                      <span class="asignado-mas">+{t.assignee_count - 1}</span>
                    {/if}
                  </span>
                {:else}
                  <span class="v2-muted" style="font-size:12.5px">Sin asignar</span>
                {/if}
              </td>
              <td class="v2-r v2-num v2-muted" data-m="meta">{shortAge(t.opened_at)}</td>
              <!-- Kept on a phone, unlike the other trailing columns: a running
                   first-reply clock is the one thing in this queue that decides
                   what to open next. It takes its own line so the meter has a
                   width to fill. -->
              <td data-m="bar">
                {#if p.state === 'running'}
                  <div style="display:flex;align-items:center;gap:8px">
                    <span
                      style="flex:1;height:4px;border-radius:3px;background:var(--v2-line);overflow:hidden;display:block"
                    >
                      <i
                        style="display:block;height:100%;width:{p.pct}%;background:{TONE_VAR[
                          p.tone
                        ]}"
                      ></i>
                    </span>
                    <span class="v2-num" style="font-size:11px;color:{TONE_VAR[p.tone]}"
                      >{p.label}</span
                    >
                  </div>
                {:else}
                  <span class="v2-num" style="font-size:11.5px;color:{TONE_VAR[p.tone]}"
                    >{p.label}</span
                  >
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{tickets.length}</span> de
      <span class="v2-num">{count(totals.count)}</span>
      {#if !data.showAll}
        · <a href="/tickets?all=1" style="color:inherit">incluir cerrados</a>
      {:else}
        · <a href="/tickets" style="color:inherit">solo abiertos</a>
      {/if}
    </p>
  {/if}
</div>
{/if}

<style>
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
    color: var(--v2-muted, #8a9196);
    font-size: 11px;
  }
  .asunto-id {
    display: block;
    font-size: 11px;
    color: var(--v2-muted, #8a9196);
    margin-top: 1px;
  }
  /* Grilla fluida: en pantallas chicas las tarjetas se reacomodan solas, sin
     puntos de corte escritos a mano. */
  .areas-grilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(205px, 1fr));
    gap: 12px;
    padding: 14px 0 22px;
  }
  .area-tarjeta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 14px 16px 15px;
    border: 1px solid var(--v2-line, #e3e4e1);
    border-radius: 10px;
    background: var(--v2-card, #fff);
    text-decoration: none;
    color: inherit;
    transition:
      border-color 0.12s,
      transform 0.12s;
  }
  .area-tarjeta:hover {
    border-color: var(--area-color);
    transform: translateY(-1px);
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
  .aviso-sin-area p + p {
    margin-top: 6px;
    color: var(--v2-muted, #6b7378);
  }
  .migas {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 14px 0 2px;
    font-size: 12px;
    color: var(--v2-muted, #8a9196);
  }
  .migas a {
    color: inherit;
    text-decoration: none;
  }
  .migas a:hover {
    color: var(--v2-ink, #1c1f21);
    text-decoration: underline;
  }
  .titulo-seccion {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--v2-muted, #6b7378);
    margin: 4px 0 0;
  }
  .sub-nav {
    margin-bottom: 4px;
  }
  /* El color del area se aplica a la marca, no a la tarjeta entera: cinco
     tarjetas de fondo saturado compiten entre si y ninguna resalta. */
  .area-marca {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    margin-bottom: 6px;
    border-radius: 8px;
    color: var(--area-color);
    background: color-mix(in srgb, var(--area-color) 13%, transparent);
  }
  .area-iniciales {
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }
  .area-nombre {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--v2-muted, #6b7378);
  }
  .area-total {
    font-size: 26px;
    font-weight: 700;
    line-height: 1.15;
  }
  .area-detalle {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 11.5px;
    margin-top: 2px;
  }
  .marca {
    color: var(--v2-muted, #8a9196);
  }
  .marca.urgente.hay {
    color: var(--v2-rust, #e8590c);
    font-weight: 600;
  }
  .marca.espera.hay {
    color: var(--v2-clay, #a8560b);
    font-weight: 600;
  }
  .area-sin-asignar {
    font-size: 11px;
    color: var(--v2-muted, #8a9196);
    margin-top: 3px;
  }
</style>
