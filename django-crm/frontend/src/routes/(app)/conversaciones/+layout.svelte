<script>
  /**
   * Bandeja de conversaciones — la mesa de trabajo.
   *
   * TRES COLUMNAS, NO DOS PANTALLAS
   * Antes esto eran dos rutas separadas: una lista, y al hacer clic, una
   * pantalla aparte. Atender una bandeja no funciona asi: se entra, se
   * contesta, se pasa a la siguiente. Con dos pantallas cada salto cuesta un
   * "volver" y se pierde de vista que mas hay esperando.
   *
   * Por eso la lista vive en el layout y acompaña siempre:
   *   izquierda   quienes escribieron (esta columna)
   *   centro      la conversacion abierta            -> [id]/+page.svelte
   *   derecha     el ticket, el proceso, la documentacion   -> idem
   *
   * Las URLs no cambian: /conversaciones/<id> sigue siendo un enlace que se
   * puede compartir y abrir directo.
   *
   * COMO SE LEE  (la regla de v2.css: ember marca lo que te necesita o
   * aquello sobre lo que podes actuar, nunca cromo)
   *   Sin atender   escalada y NADIE del equipo escribio todavia. Es el unico
   *                 estado que pide algo, y el unico con ember.
   *   En curso      escalada y ya contestada por una persona. Sigue abierta
   *                 pero no espera a nadie -> clay, quieto.
   *   (sin marca)   el bot la esta resolviendo solo. Es el caso normal: una
   *                 pildora por fila para decir "todo bien" es ruido.
   *
   * Las pestanas, el buscador y el filtro trabajan sobre lo ya cargado: la
   * bandeja entra en una pagina y filtrar del lado del cliente es instantaneo,
   * sin un viaje de red por cada clic.
   */
  import { page } from '$app/state';
  import { invalidate } from '$app/navigation';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { MessagesSquare, TriangleAlert, Search, X, Phone, User } from '@lucide/svelte';

  /** @type {{ data: any, children: import('svelte').Snippet }} */
  let { data, children } = $props();

  let conversaciones = $derived(data.conversaciones ?? []);
  let abierta = $derived(page.params.id ?? null);

  // Sondeo: mientras esta pestaña esta abierta, revisa cada pocos segundos
  // si hay algo nuevo (un chat que nadie tenia, un mensaje que cambio el
  // "ultimo_mensaje" de una fila) -- para cuando WhatsApp real este
  // integrado y un cliente escriba sin que nadie tenga que recargar. Solo
  // si la pestaña esta visible: una de fondo no gasta pedidos al motor.
  // Todavia no hay WebSocket, esto es sondeo simple.
  //
  // El intervalo NO alcanza solo: si la pestaña estuvo de fondo (otra
  // pestaña, otra app), el intervalo de 8s puede haber estado corriendo
  // igual pero cada disparo se descartaba por el chequeo de arriba -- al
  // volver, el proximo disparo real puede tardar hasta 8s mas (y los
  // navegadores frenan los timers de pestañas de fondo, asi que puede ser
  // bastante mas). El listener de 'visibilitychange' sondea AL INSTANTE
  // apenas la pestaña vuelve a estar visible, en vez de esperar al proximo
  // tick -- confirmado en vivo (agosto 2026): sin esto, dos pestañas
  // (conversaciones + simulador) no mostraban el mensaje nuevo en minutos.
  $effect(() => {
    const intervalo = setInterval(() => {
      if (document.visibilityState === 'visible') invalidate('app:conversaciones');
    }, 8000);
    // Dos señales, no una: 'visibilitychange' no siempre alcanza (algunos
    // navegadores/arreglos de ventana no la disparan de forma confiable
    // segun como se cambia de pestaña o ventana). 'focus' de la ventana es
    // una segunda red -- entre las dos, es dificil que ninguna dispare al
    // volver.
    const alVolver = () => invalidate('app:conversaciones');
    document.addEventListener('visibilitychange', alVolver);
    window.addEventListener('focus', alVolver);
    return () => {
      clearInterval(intervalo);
      document.removeEventListener('visibilitychange', alVolver);
      window.removeEventListener('focus', alVolver);
    };
  });

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (/** @type {string} */ c) => CANAL_LABEL[c] ?? c;

  // Un color por etiqueta, no toda la taxonomia hardcodeada -- si el tenant
  // agrega una categoria nueva en conversaciones.etiquetas, cae en 'ink' en
  // vez de romper.
  const ETIQUETA_TONE = {
    soporte_tecnico: 'clay',
    facturacion: 'moss',
    comercial: 'slate',
    queja: 'rust'
  };
  const etiquetaTone = (/** @type {string} */ e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (/** @type {string} */ e) => (e ? e.replaceAll('_', ' ') : '');

  /** Escalada, necesita atencion humana ahora, y sin que nadie del equipo
      haya escrito: pide algo. 'necesita_atencion_humana' es independiente
      de 'escalada_a_humano' -- toda escalada crea ticket y pausa el bot
      igual, pero no toda escalada exige entrar ya mismo (ver
      nucleo/seguimiento/escalamiento.py). */
  const pendiente = (/** @type {any} */ c) =>
    c.escalada_a_humano && c.necesita_atencion_humana && !c.atendida;

  const AUTOR = { user: 'Cliente', assistant: 'Asistente', humano: 'Vos', tool: 'Herramienta' };

  // Quien escribe por WhatsApp se identifica con un telefono, y quien prueba
  // desde el CRM con un uuid. Ninguno de los dos tiene iniciales: initials()
  // devuelve '3' o 'B', un circulo con una letra que no significa nada. Un
  // icono dice mas y no finge ser un nombre.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);

  /** '3007778899' -> '300 777 8899'. Diez digitos seguidos no se leen. */
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    const d = v.replace(/\D/g, '');
    if (esTelefono(v) && d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    return v;
  }

  let filtro = $state('todas');
  let busqueda = $state('');

  let pendientes = $derived(conversaciones.filter(pendiente).length);
  let escaladas = $derived(conversaciones.filter((/** @type {any} */ c) => c.escalada_a_humano).length);

  let pestanas = $derived([
    { id: 'todas', label: 'Todas', n: conversaciones.length },
    { id: 'pendientes', label: 'Sin atender', n: pendientes, urge: true },
    { id: 'escaladas', label: 'Escaladas', n: escaladas },
    { id: 'bot', label: 'Asistente', n: conversaciones.length - escaladas }
  ]);

  let visibles = $derived.by(() => {
    let lista = conversaciones;
    if (filtro === 'pendientes') lista = lista.filter(pendiente);
    else if (filtro === 'escaladas') lista = lista.filter((/** @type {any} */ c) => c.escalada_a_humano);
    else if (filtro === 'bot') lista = lista.filter((/** @type {any} */ c) => !c.escalada_a_humano);

    const q = busqueda.trim().toLowerCase();
    if (!q) return lista;
    return lista.filter((/** @type {any} */ c) =>
      [c.usuario_externo, c.ultimo_mensaje, c.etiqueta, c.caso_manual, c.motivo_escalamiento]
        .filter(Boolean)
        .some((campo) => String(campo).toLowerCase().includes(q))
    );
  });
</script>

<PageHeader title="Conversaciones">
  {#snippet sub()}
    {#if pendientes > 0}
      <span class="v2-num">{pendientes}</span>
      {pendientes === 1 ? 'espera' : 'esperan'} a una persona · <span class="v2-num"
        >{conversaciones.length}</span
      > en total
    {:else}
      <span class="v2-num">{conversaciones.length}</span>
      {conversaciones.length === 1 ? 'conversación' : 'conversaciones'}, ninguna esperando
    {/if}
  {/snippet}
</PageHeader>

<div class="mesa">
  <aside class="columna" class:hay-abierta={abierta} aria-label="Conversaciones">
    {#if !data.error && conversaciones.length > 0}
      <!-- Pestanas de estado. Nunca ember en la activa: "donde estoy" no es una
           accion. El contador de "Sin atender" si lo lleva, porque ese numero
           es trabajo sin tomar. -->
      <nav class="tabs" aria-label="Filtrar por estado">
        {#each pestanas as t (t.id)}
          <button
            type="button"
            class="tab"
            aria-current={filtro === t.id ? 'true' : undefined}
            onclick={() => (filtro = t.id)}
          >
            {t.label}
            <span class="tab-n v2-num" class:urge={t.urge && t.n > 0}>{t.n}</span>
          </button>
        {/each}
      </nav>

      <label class="buscar">
        <Search size={14} />
        <input
          type="text"
          bind:value={busqueda}
          placeholder="Buscar cliente o mensaje…"
          aria-label="Buscar conversaciones"
        />
        {#if busqueda}
          <button
            type="button"
            class="limpiar"
            onclick={() => (busqueda = '')}
            aria-label="Limpiar"
          >
            <X size={13} />
          </button>
        {/if}
      </label>
    {/if}

    <div class="lista">
      {#if data.error}
        <div class="hueco">
          <EmptyState title="No se pudo cargar la bandeja" body={data.error}>
            {#snippet icon()}<TriangleAlert size={21} />{/snippet}
          </EmptyState>
        </div>
      {:else if conversaciones.length === 0}
        <div class="hueco">
          <EmptyState
            title="Todavía no hay conversaciones"
            body="Acá van a aparecer los chats de WhatsApp con tus clientes."
          >
            {#snippet icon()}<MessagesSquare size={21} />{/snippet}
          </EmptyState>
        </div>
      {:else if visibles.length === 0}
        <div class="hueco">
          <EmptyState
            title="Nada acá"
            body={busqueda
              ? `Ninguna coincide con «${busqueda}».`
              : 'No hay conversaciones en este estado.'}
          >
            {#snippet icon()}<Search size={20} />{/snippet}
          </EmptyState>
        </div>
      {:else}
        {#each visibles as c (c.id)}
          <a
            class="fila"
            class:pide={pendiente(c)}
            class:activa={c.id === abierta}
            href="/conversaciones/{c.id}"
            aria-current={c.id === abierta ? 'page' : undefined}
          >
            {#if c.nombre_cliente}
              <Avatar name={c.nombre_cliente} size={30} />
            {:else if esTelefono(c.usuario_externo)}
              <span class="ident" aria-hidden="true"><Phone size={14} /></span>
            {:else if !c.usuario_externo || esUuid(c.usuario_externo)}
              <span class="ident" aria-hidden="true"><User size={14} /></span>
            {:else}
              <Avatar name={c.usuario_externo} size={30} />
            {/if}

            <div class="cuerpo">
              <div class="alta">
                <span class="quien">{c.nombre_cliente || quien(c.usuario_externo)}</span>
                <span class="cuando v2-num">{shortAge(c.actualizado_en)}</span>
              </div>

              <p class="avance">
                {#if c.ultimo_rol && c.ultimo_rol !== 'user'}
                  <span class="avance-quien">{AUTOR[c.ultimo_rol] ?? c.ultimo_rol}:</span>
                {/if}
                {c.ultimo_mensaje || 'Sin mensajes todavía'}
              </p>

              <!-- Solo se dibuja si hay algo que decir. "El bot la está
                   llevando" es el caso normal: ponerle una píldora a cada fila
                   agrega una línea y un rectángulo por conversación para no
                   informar nada. -->
              {#if c.escalada_a_humano || c.etiqueta || c.caso_manual}
                <div class="baja">
                  {#if pendiente(c)}
                    <span class="marca" title={c.motivo_escalamiento || 'Escalada a un humano'}>
                      Sin atender
                    </span>
                  {:else if c.escalada_a_humano}
                    <Pill tone="clay" dot>En curso</Pill>
                  {/if}

                  {#if c.etiqueta}
                    <Pill tone={etiquetaTone(c.etiqueta)}>{etiquetaLabel(c.etiqueta)}</Pill>
                  {/if}

                  <!-- De qué es la conversación, no si escaló: lo asigna el
                       asistente en cada turno y existe también en las que
                       resolvió solo (ver supabase/202608180923_caso_conversacion.sql).
                       Va en tono neutro para que no compita con la píldora
                       de estado, que es la que pide una acción. -->
                  {#if c.caso_manual}
                    <Pill tone="ink">{etiquetaLabel(c.caso_manual)}</Pill>
                  {/if}
                </div>
              {/if}

              <span class="canal">{canalLabel(c.canal)}</span>
            </div>
          </a>
        {/each}
      {/if}
    </div>
  </aside>

  <!-- 'abierta' (el id de la URL) como key: [id]/+page.svelte inicializa su
       estado local con $state(untrack(...)) a proposito (para que enviar()
       no se pise con una relectura reactiva mientras se escribe), y ese
       mismo untrack hace que SvelteKit, al reusar este componente entre una
       conversacion y otra, se quede mostrando la anterior -- confirmado con
       grabaciones reales (Jam, agosto 2026): sin esto el panel no actualiza
       NUNCA, solo cambia la URL. Se probo resincronizar con un $effect en
       vez de esto (evitaba el parpadeo de remontar), pero en las mismas
       pruebas grabadas el effect no alcanzaba a aplicar el cambio a tiempo.
       La key fuerza a Svelte a destruir y recrear el componente -- unico
       mecanismo que garantiza la reinicializacion, al costo de un
       parpadeo breve. Solo envuelve el hijo, no <aside> de arriba: la
       lista de conversaciones NO se remonta al cambiar de chat. -->
  {#key abierta}
    {@render children()}
  {/key}
</div>

<style>
  /* La mesa ocupa lo que queda bajo el encabezado y no scrollea: cada columna
     maneja su propio desborde, para que leer un hilo largo no arrastre la
     lista fuera de la vista. */
  .mesa {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: stretch;
    border-top: 1px solid var(--v2-line);
  }
  .columna {
    width: 330px;
    flex: none;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--v2-line);
  }

  /* ── pestañas + buscador ────────────────────────────────────────────── */
  .tabs {
    display: flex;
    align-items: center;
    gap: 1px;
    padding: 8px 10px 0;
    border-bottom: 1px solid var(--v2-line);
    flex: none;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 7px 7px 8px;
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    font: inherit;
    font-size: 11.8px;
    font-weight: 550;
    color: var(--v2-slate);
    cursor: pointer;
    white-space: nowrap;
  }
  .tab:hover {
    color: var(--v2-ink);
  }
  /* Activa = peso y tinta. Ember marca lo que hay que hacer, no dónde estás. */
  .tab[aria-current='true'] {
    color: var(--v2-ink);
    font-weight: 640;
    border-bottom-color: var(--v2-ink);
  }
  .tab-n {
    font-size: 10px;
    font-weight: 650;
    color: var(--v2-slate);
    background: var(--v2-hover);
    border-radius: 20px;
    padding: 1px 5px;
  }
  /* El único número que sí es ember: trabajo que nadie tomó. */
  .tab-n.urge {
    color: #fff;
    background: var(--v2-ember);
  }
  :global(.dark) .tab-n.urge {
    color: #1c1917;
  }
  .buscar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
    margin: 9px 10px 3px;
    padding: 5px 9px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    background: var(--v2-card);
    color: var(--v2-slate);
  }
  .buscar:focus-within {
    border-color: var(--v2-slate);
  }
  .buscar input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--v2-ink);
    font: inherit;
    font-size: 12.5px;
    outline: none;
  }
  .limpiar {
    border: 0;
    background: none;
    color: var(--v2-slate);
    cursor: pointer;
    display: grid;
    place-items: center;
    padding: 0;
  }
  .limpiar:hover {
    color: var(--v2-ink);
  }

  /* ── filas ──────────────────────────────────────────────────────────── */
  .lista {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 4px 6px 10px;
  }
  .hueco {
    padding: 18px 10px;
  }
  .fila {
    display: flex;
    gap: 10px;
    padding: 9px 9px 10px;
    border-radius: 8px;
    color: inherit;
    text-decoration: none;
  }
  .fila:hover {
    background: var(--v2-hover);
  }
  /* La abierta se marca con la superficie, no con ember: "estoy acá" no es
     trabajo pendiente. */
  .fila.activa {
    background: var(--v2-line-soft);
  }
  /* Un tinte apenas perceptible, no un bloque. Lo que marca "sin atender" es
     el punto ember de abajo; el fondo solo tiene que hacer que la fila salte
     al pasar la vista, no gritar. */
  .fila.pide {
    background: color-mix(in srgb, var(--v2-ember) 5%, transparent);
  }
  .fila.pide:hover,
  .fila.pide.activa {
    background: color-mix(in srgb, var(--v2-ember) 9%, transparent);
  }
  /* Círculo para quien no tiene nombre: un teléfono o un uuid no dan iniciales. */
  .ident {
    flex: none;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }
  .fila.activa .ident {
    background: var(--v2-card);
  }
  .cuerpo {
    flex: 1;
    min-width: 0;
  }
  .alta {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .quien {
    font-weight: 620;
    font-size: 13px;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cuando {
    margin-left: auto;
    flex: none;
    font-size: 10.5px;
    color: var(--v2-slate);
  }
  /* Una sola línea: el preview orienta, no se lee. Dos líneas hacen que la
     altura de cada fila dependa de lo largo que fue el último mensaje. */
  .avance {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--v2-slate);
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .avance-quien {
    font-weight: 600;
    color: var(--v2-ink);
    opacity: 0.6;
  }
  .baja {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 6px;
  }
  .canal {
    display: block;
    margin-top: 4px;
    font-size: 10.5px;
    color: var(--v2-slate);
  }
  /* No es un Pill: Pill.svelte excluye ember a propósito porque ember no es
     "un estado en el que un registro está". Acá no describe un estado, marca
     trabajo sin tomar -- el mismo sentido que la tira .v2-next. */
  .marca {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11.2px;
    font-weight: 650;
    color: var(--v2-ember);
    white-space: nowrap;
  }
  .marca::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--v2-ember);
    flex: none;
  }

  /* En pantallas angostas no caben tres columnas al lado. La lista pasa a ser
     la pantalla, y abrir una conversación la reemplaza -- el comportamiento
     de dos pantallas de antes, que es el correcto en un teléfono. */
  @media (max-width: 1000px) {
    .columna {
      width: 100%;
      border-right: 0;
    }
    .columna.hay-abierta {
      display: none;
    }
  }
</style>
