<script>
  /**
   * Hoy de la operacion. La cola, los tonos y el orden los arma el servidor
   * (lib/v2/hoy-operacion.js); aca solo se dibuja y se filtra.
   *
   * Solo el primer item lleva el boton de accion lleno: uno por pantalla. Si
   * todo es principal, nada lo es.
   */
  import {
    MessageCircle,
    Activity,
    ClipboardCheck,
    Boxes,
    LifeBuoy,
    Receipt,
    Columns3,
    CircleCheck,
    Users,
    TriangleAlert,
    ArrowRight,
    Radar
  } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  const ICONOS = {
    conversacion: MessageCircle,
    noc: Activity,
    instalacion: ClipboardCheck,
    bodega: Boxes,
    ticket: LifeBuoy,
    factura: Receipt,
    negociacion: Columns3,
    tarea: CircleCheck
  };

  const FILTROS = [
    { id: 'todo', label: 'Todo' },
    { id: 'urg', label: 'Vencido' },
    { id: 'aten', label: 'Necesita atención' },
    { id: 'neutro', label: 'Puede esperar' }
  ];

  let filtro = $state('todo');
  let visibles = $derived(filtro === 'todo' ? data.cola : data.cola.filter((i) => i.tono === filtro));
  let primero = $derived(data.cola[0]?.id);

  const cuantos = (id) => (id === 'todo' ? data.cola.length : data.conteos[id]);

  const hoy = new Intl.DateTimeFormat('es-CO', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'America/Bogota'
  }).format(new Date());
</script>

<div class="v2-scroll">
  <div class="v2-pad hoy">
    <section class="v2-card cabecera" aria-labelledby="titulo-hoy">
      <div class="cabecera-texto">
        <span class="fecha">{hoy.charAt(0).toUpperCase() + hoy.slice(1)}</span>
        <h1 id="titulo-hoy" class="v2-page-title">Hoy</h1>
        <p class="frase">{data.resumen}</p>
      </div>
      <a class="v2-btn" href="/conversaciones">
        Abrir conversaciones <ArrowRight />
      </a>

      {#if data.dexter}
        <div class="franja">
          <div class="franja-celda franja-titulo">
            <span class="v2-label">Dexter ahora</span>
            <span class="agentes">
              <i class="punto-ok"></i>
              {data.dexter.agentesActivos}{#if data.dexter.agentesTotal != null}
                de {data.dexter.agentesTotal}{/if} agentes trabajando
            </span>
          </div>
          <div class="franja-celda">
            <span class="tile tile-accion"><MessageCircle /></span>
            <span><b class="v2-num">{data.dexter.activas}</b><small>conversaciones activas</small></span>
          </div>
          <div class="franja-celda">
            <span class="tile tile-aten"><Users /></span>
            <span><b class="v2-num" class:aten={data.dexter.esperanPersona > 0}>{data.dexter.esperanPersona}</b><small>esperan a una persona</small></span>
          </div>
          <div class="franja-celda">
            <span class="tile tile-accion"><CircleCheck /></span>
            <span><b class="v2-num">{data.dexter.atendidasHoy}</b><small>atendidas hoy</small></span>
          </div>
          <div class="franja-celda">
            <span class="tile" class:tile-urg={data.dexter.fallosHoy > 0}><TriangleAlert /></span>
            <span><b class="v2-num" class:urg={data.dexter.fallosHoy > 0}>{data.dexter.fallosHoy}</b><small>fallos de herramientas hoy</small></span>
          </div>
          <a class="franja-celda franja-enlace" href="/centro-mando"><Radar /> Centro de mando</a>
        </div>
      {/if}
    </section>

    {#if data.noLeidas.length}
      <p class="no-leidas" role="status">
        No se pudo leer {data.noLeidas.join(', ')}. Lo demás está al día.
      </p>
    {/if}

    <div class="columnas">
      <section class="cola" aria-labelledby="titulo-cola">
        <div class="cola-cabeza">
          <h2 id="titulo-cola" class="v2-section">Te necesita ahora</h2>
          <div class="filtros" role="group" aria-label="Filtrar por plazo">
            {#each FILTROS as f (f.id)}
              {#if f.id === 'todo' || cuantos(f.id) > 0}
                <button
                  type="button"
                  class="filtro"
                  data-tono={f.id}
                  aria-pressed={filtro === f.id}
                  onclick={() => (filtro = f.id)}
                >
                  {#if f.id !== 'todo'}<i class="punto"></i>{/if}
                  {f.label} <span class="v2-num">{cuantos(f.id)}</span>
                </button>
              {/if}
            {/each}
          </div>
        </div>

        {#each visibles as item (item.id)}
          {@const Icono = ICONOS[item.icono] ?? CircleCheck}
          <article class="v2-card tarjeta">
            <span class="origen-icono"><Icono /></span>
            <div class="tarjeta-cuerpo">
              <div class="tarjeta-meta">
                <span class="origen">{item.origen}</span>
                {#if item.cuando}<span class="v2-pill estado" data-tono={item.tono}><i class="v2-pill-dot"></i>{item.cuando}</span>{/if}
              </div>
              <a class="tarjeta-titulo" href={item.href}>{item.titulo}</a>
              {#if item.detalle}<p class="tarjeta-detalle">{item.detalle}</p>{/if}
              {#if item.plazo}
                <div class="plazo">
                  <span class="plazo-pista"
                    ><span
                      class="plazo-relleno"
                      data-nivel={item.plazo.uso >= 100 ? 'urg' : item.plazo.uso >= 75 ? 'aten' : 'ok'}
                      style="width:{item.plazo.uso}%"
                    ></span></span
                  >
                  <span class="v2-num plazo-texto" class:urg={item.plazo.uso >= 100}>{item.plazo.texto}</span>
                </div>
              {/if}
            </div>
            <a class="v2-btn" class:v2-btn-primary={item.id === primero} href={item.href}>{item.accion}</a>
          </article>
        {:else}
          <div class="v2-card vacio">
            <b>{filtro === 'todo' ? 'Nada te necesita ahora' : 'Nada en este filtro'}</b>
            <p>
              {filtro === 'todo'
                ? 'Sin clientes esperando, órdenes detenidas, instalaciones ni pedidos pendientes. Dexter sigue atendiendo.'
                : 'Probá con «Todo».'}
            </p>
          </div>
        {/each}

        {#if data.crmOcultos > 0}
          <p class="mas">
            <span class="v2-num">{data.crmOcultos}</span>
            {data.crmOcultos === 1 ? 'más espera' : 'más esperan'} en
            {#each data.crmFuentes as s, i (s.href)}<a href={s.href}>{s.count} {s.label}</a
              >{i < data.crmFuentes.length - 1 ? ', ' : '.'}{/each}
          </p>
        {/if}
      </section>

      <aside class="lateral" aria-label="Resumen">
        {#if data.porArea.length}
          <section class="v2-card panel" aria-labelledby="titulo-areas">
            <h2 id="titulo-areas" class="v2-section">Por área</h2>
            {#each data.porArea as a (a.id)}
              {@const Icono = ICONOS[a.icono] ?? CircleCheck}
              <a class="area" href={a.href}>
                <span class="origen-icono chico"><Icono /></span>
                <span class="area-texto"><b>{a.nombre}</b><small>{a.nota}</small></span>
                <span class="v2-num area-valor">{a.valor}</span>
              </a>
            {/each}
          </section>
        {/if}

        {#if data.luego.length}
          <section class="v2-card panel" aria-labelledby="titulo-luego">
            <h2 id="titulo-luego" class="v2-section">Más adelante esta semana</h2>
            {#each data.luego as l (l.id)}
              <div class="luego">
                <span class="luego-dia">{l.day}</span>
                <span class="luego-texto"><b>{l.title}</b>{#if l.meta}<small>{l.meta}</small>{/if}</span>
              </div>
            {/each}
          </section>
        {/if}
      </aside>
    </div>
  </div>
</div>

<style>
  .hoy {
    padding-top: 18px;
    padding-bottom: 32px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ── cabecera ─────────────────────────────────────────────────────────── */
  .cabecera {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 14px 20px;
    align-items: start;
    padding: 20px 22px 0;
    overflow: hidden;
  }
  .cabecera-texto {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  .fecha {
    font-size: 12.5px;
    color: var(--v2-slate);
  }
  .frase {
    margin: 2px 0 0;
    font-size: 15px;
    color: var(--v2-slate);
    max-width: 680px;
  }
  .cabecera :global(.v2-btn svg) {
    width: 15px;
    height: 15px;
  }
  .franja {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    margin: 4px -22px 0;
    border-top: 1px solid var(--v2-line-soft);
    background: color-mix(in srgb, var(--v2-paper) 45%, var(--v2-card));
  }
  .franja-celda {
    flex: 1 1 150px;
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 14px 18px;
    border-right: 1px solid var(--v2-line-soft);
    min-width: 0;
  }
  .franja-celda b {
    display: block;
    font-size: 21px;
    font-weight: 700;
    line-height: 1.15;
  }
  .franja-celda small {
    display: block;
    font-size: 12px;
    color: var(--v2-slate);
  }
  .franja-titulo {
    flex-direction: column;
    align-items: flex-start;
    gap: 3px;
  }
  .agentes {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 13.5px;
    font-weight: 600;
  }
  .punto-ok {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--v2-moss);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--v2-moss) 15%, transparent);
  }
  .tile {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    flex: none;
    display: grid;
    place-items: center;
    background: var(--v2-origen);
    color: var(--v2-origen-ink);
  }
  .tile :global(svg) {
    width: 17px;
    height: 17px;
  }
  .tile-accion {
    background: var(--v2-ember-soft);
    color: var(--v2-ember);
  }
  .tile-aten {
    background: color-mix(in srgb, var(--v2-clay) 12%, var(--v2-card));
    color: var(--v2-clay);
  }
  .tile-urg {
    background: color-mix(in srgb, var(--v2-rust) 10%, var(--v2-card));
    color: var(--v2-rust);
  }
  b.aten {
    color: var(--v2-clay);
  }
  b.urg {
    color: var(--v2-rust);
  }
  .franja-enlace {
    flex: 0 1 auto;
    gap: 7px;
    font-size: 13px;
    font-weight: 600;
    color: var(--v2-ember-text);
    text-decoration: none;
    border-right: 0;
  }
  .franja-enlace :global(svg) {
    width: 16px;
    height: 16px;
  }
  .franja-enlace:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .no-leidas {
    margin: 0;
    font-size: 13px;
    color: var(--v2-clay);
  }

  /* ── dos columnas ─────────────────────────────────────────────────────── */
  .columnas {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    align-items: flex-start;
  }
  .cola {
    flex: 999 1 520px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 9px;
  }
  .lateral {
    flex: 1 1 280px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .cola-cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    padding: 2px 2px 4px;
  }
  .filtros {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .filtro {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 34px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid var(--v2-line-strong);
    background: var(--v2-card);
    color: var(--v2-ink);
    font: inherit;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
  }
  .filtro[aria-pressed='true'] {
    background: var(--v2-ink);
    border-color: var(--v2-ink);
    color: var(--v2-paper);
  }
  .filtro .punto {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--v2-slate);
  }
  .filtro[data-tono='urg'] .punto {
    background: var(--v2-rust);
  }
  .filtro[data-tono='aten'] .punto {
    background: var(--v2-clay);
  }
  .filtro[aria-pressed='true'] .punto {
    background: currentColor;
  }

  /* ── tarjeta ──────────────────────────────────────────────────────────── */
  .tarjeta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px 16px;
    padding: 15px 16px;
    transition:
      border-color 0.15s ease,
      box-shadow 0.15s ease;
  }
  .tarjeta:hover {
    border-color: var(--v2-line-strong);
    box-shadow: var(--v2-shadow-lift);
  }
  .origen-icono {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    flex: none;
    align-self: flex-start;
    display: grid;
    place-items: center;
    background: var(--v2-origen);
    color: var(--v2-origen-ink);
  }
  .origen-icono :global(svg) {
    width: 19px;
    height: 19px;
  }
  .origen-icono.chico {
    width: 32px;
    height: 32px;
    border-radius: 9px;
  }
  .origen-icono.chico :global(svg) {
    width: 16px;
    height: 16px;
  }
  .tarjeta-cuerpo {
    flex: 1 1 280px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .tarjeta-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .origen {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--v2-slate);
  }
  .estado {
    color: var(--v2-slate);
    background: var(--v2-line-soft);
  }
  .estado .v2-pill-dot {
    background: currentColor;
  }
  .estado[data-tono='urg'] {
    color: var(--v2-rust);
    background: color-mix(in srgb, var(--v2-rust) 10%, var(--v2-card));
  }
  .estado[data-tono='aten'] {
    color: var(--v2-clay);
    background: color-mix(in srgb, var(--v2-clay) 12%, var(--v2-card));
  }
  .tarjeta-titulo {
    color: inherit;
    text-decoration: none;
    font-size: 15px;
    font-weight: 650;
    letter-spacing: -0.015em;
    line-height: 1.3;
  }
  .tarjeta-titulo:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .tarjeta-detalle {
    margin: 0;
    font-size: 13.5px;
    color: var(--v2-slate);
  }
  .plazo {
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 380px;
    margin-top: 3px;
  }
  .plazo-pista {
    flex: 1;
    height: 5px;
    border-radius: 999px;
    background: var(--v2-line-soft);
    overflow: hidden;
  }
  .plazo-relleno {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--v2-ember);
  }
  .plazo-relleno[data-nivel='aten'] {
    background: var(--v2-clay);
  }
  .plazo-relleno[data-nivel='urg'] {
    background: var(--v2-rust);
  }
  .plazo-texto {
    font-size: 12px;
    font-weight: 600;
    color: var(--v2-slate);
    white-space: nowrap;
  }
  .plazo-texto.urg {
    color: var(--v2-rust);
  }
  .tarjeta > .v2-btn {
    margin-left: auto;
  }

  .vacio {
    padding: 22px;
    text-align: center;
  }
  .vacio p {
    margin: 4px 0 0;
    font-size: 13.5px;
    color: var(--v2-slate);
  }
  .mas {
    margin: 6px 2px 0;
    font-size: 13px;
    color: var(--v2-slate);
  }
  .mas a {
    color: var(--v2-ember-text);
  }

  /* ── lateral ──────────────────────────────────────────────────────────── */
  .panel {
    padding: 16px 12px 8px;
  }
  .panel .v2-section {
    margin: 0 6px 8px;
  }
  .area {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 52px;
    padding: 8px 6px;
    border-radius: 10px;
    color: inherit;
    text-decoration: none;
  }
  .area + .area {
    border-top: 1px solid var(--v2-line-soft);
  }
  .area:hover {
    background: var(--v2-hover);
  }
  .area-texto {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    line-height: 1.25;
  }
  .area-texto b {
    font-size: 13.5px;
    font-weight: 600;
  }
  .area-texto small,
  .luego-texto small {
    font-size: 12px;
    color: var(--v2-slate);
  }
  .area-valor {
    font-size: 16px;
    font-weight: 700;
  }
  .luego {
    display: flex;
    gap: 12px;
    align-items: baseline;
    padding: 9px 6px;
  }
  .luego + .luego {
    border-top: 1px solid var(--v2-line-soft);
  }
  .luego-dia {
    width: 34px;
    flex: none;
    font-size: 12px;
    font-weight: 650;
    color: var(--v2-ember-text);
  }
  .luego-texto {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .luego-texto b {
    font-size: 13.5px;
    font-weight: 600;
  }

  @media (max-width: 768px) {
    .cabecera {
      grid-template-columns: 1fr;
    }
    .tarjeta > .v2-btn {
      margin-left: 0;
      width: 100%;
      justify-content: center;
    }
  }
</style>
