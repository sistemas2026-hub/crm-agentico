<script>
  import { untrack } from 'svelte';
  import { invalidate } from '$app/navigation';
  import { enhance } from '$app/forms';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import {
    TriangleAlert,
    ChevronDown,
    ArrowRight,
    ArrowLeft,
    CircleCheck,
    CircleX,
    Send,
    Phone,
    User,
    PanelRight,
    X,
    Paperclip
  } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  // untrack: la conversacion/hilo/caso se mutan localmente despues (enviar(),
  // la asignacion) -- capturar el valor inicial es lo que se quiere, no
  // seguir a `data` en cada re-render (mismo patron que goals/[id]/edit).
  //
  // Este componente se REMONTA por completo al pasar de una conversacion a
  // otra -- ver el {#key abierta} en +layout.svelte -- asi que este
  // untrack corre de nuevo, fresco, en cada chat. Se probaron dos versiones
  // de un $effect que resincronizaba sin remontar (para evitar el parpadeo),
  // pero en pruebas reales (grabaciones de Jam, agosto 2026) el panel se
  // quedaba mostrando la conversacion anterior pese al effect -- se volvio a
  // este enfoque, mas simple y con la garantia estructural de Svelte de que
  // un componente remontado siempre arranca de cero.
  let conversacion = $state(untrack(() => data.conversacion));
  let mensajes = $state(untrack(() => data.mensajes ?? []));
  let caso = $state(untrack(() => data.caso));
  let owners = $state(untrack(() => data.owners ?? []));
  let herramientas = $state(untrack(() => data.herramientas ?? []));
  let casos = $state(untrack(() => data.casos ?? []));

  let entrada = $state('');
  let enviando = $state(false);
  let error = $state('');
  /** Solo se usa por debajo de 1240px, donde la columna de contexto no cabe
      al lado y pasa a abrirse como panel. */
  let contextoAbierto = $state(false);

  // --- atender: sacar el caso de "Sin atender" sin pasar por el chat -------
  // 'atendida' hoy se calcula sola en cuanto alguien responde de verdad
  // (ver nucleo/persistencia/db.py::ultima_actividad) -- esto es el camino
  // manual para cuando el caso se resolvio por telefono, en persona, o por
  // otro canal, y no corresponde mandarle un mensaje al cliente solo para
  // que el calculo lo cuente. Sin desmarcar a proposito: ver
  // marcar_atendida() en el motor.
  let atendida = $state(untrack(() => !!data.conversacion?.atendida));
  let marcandoAtendida = $state(false);
  let errorAtender = $state('');

  async function marcarAtendida() {
    if (marcandoAtendida || atendida) return;
    marcandoAtendida = true;
    errorAtender = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/atender`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caso_id: conversacion.caso_id ?? null })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorAtender = datos.error || 'No se pudo guardar.';
        return;
      }
      atendida = true;
      // El servidor toma el ticket a nombre de quien dio "Atender" (ver el
      // proxy) -- reflejarlo ya mismo en "Asignado a", sin esperar a que
      // alguien reabra el ticket para verlo.
      if (datos.asignado) asignadoA = datos.asignado.id;
      // Sin esto, la lista de la izquierda (+layout.svelte, otro load())
      // no se entera hasta el proximo sondeo -- hasta 8s despues. Con
      // invalidate() se refresca al instante, apenas se guarda.
      invalidate('app:conversaciones');
    } catch (/** @type {any} */ err) {
      errorAtender = err?.message || 'No se pudo guardar.';
    } finally {
      marcandoAtendida = false;
    }
  }

  // --- sondeo: mensajes nuevos sin recargar (para cuando WhatsApp real este
  // integrado y el cliente escriba mientras esta pantalla esta abierta) ----
  // Todavia no hay WebSocket -- sondea cada pocos segundos mientras la
  // pestaña esta visible (una de fondo no gasta pedidos). Nunca REEMPLAZA
  // 'mensajes': solo agrega lo que no estaba, para no perder ni duplicar los
  // push() optimistas de enviar().
  async function sondearMensajesNuevos() {
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/mensajes`);
      if (!resp.ok) return;
      const datos = await resp.json();
      const ahora = Date.now();
      for (const m of datos.mensajes ?? []) {
        if (!m.id || mensajes.some((loc) => loc.id === m.id)) continue;
        // Evita duplicar un mensaje que ESTA pestaña ya empujo de forma
        // optimista (sin id todavia) y que el sondeo recien ahora trae con
        // su id real -- match por rol + contenido + reciente.
        const esEcoDeOptimista = mensajes.some(
          (loc) =>
            !loc.id &&
            loc.rol === m.rol &&
            loc.contenido === m.contenido &&
            ahora - new Date(loc.creado_en).getTime() < 15000
        );
        if (!esEcoDeOptimista) mensajes.push(m);
      }

      // La conversacion tambien cambia sin que esta pestaña lo sepa -- se
      // puede escalar (o alguien mas la atiende/asigna el ticket) DESPUES
      // de que esta pantalla ya cargo. 'conversacion' se reemplaza entera
      // (no hay push() locales sobre ella como si hay en 'mensajes', asi que
      // no hay nada que perder). 'atendida' sigue la misma logica -- salvo
      // que este a mitad de guardarse desde ESTA pestaña ahora mismo, para
      // no pisar el propio click con una respuesta vieja del sondeo.
      if (datos.conversacion) conversacion = datos.conversacion;
      if (!marcandoAtendida) atendida = !!datos.conversacion?.atendida;
    } catch {
      // un sondeo que falla no tiene que avisar nada -- se reintenta solo.
    }
  }

  $effect(() => {
    const intervalo = setInterval(() => {
      if (document.visibilityState === 'visible') sondearMensajesNuevos();
    }, 5000);
    // Igual que en +layout.svelte: sin esto, volver a esta pestaña despues
    // de estar en otra espera hasta el proximo tick (y los navegadores
    // frenan los timers de pestañas de fondo) para notar algo nuevo. Dos
    // señales (visibilitychange + focus de ventana), no una -- entre las
    // dos es dificil que ninguna dispare al volver.
    const alVolver = () => sondearMensajesNuevos();
    document.addEventListener('visibilitychange', alVolver);
    window.addEventListener('focus', alVolver);
    return () => {
      clearInterval(intervalo);
      document.removeEventListener('visibilitychange', alVolver);
      window.removeEventListener('focus', alVolver);
    };
  });

  // --- conservar: sacar la conversacion de la purga por retencion ----------
  // Distinto de marcar un ejemplo: eso dice "esta respuesta fue buena" y
  // alimenta el manual; esto dice "no la borres todavia" -- un reclamo, un
  // incidente. Justo lo que NO hay que copiar como ejemplo.
  let conservada = $state(untrack(() => !!data.conversacion?.conservar));
  let motivoConservar = $state(untrack(() => data.conversacion?.conservar_motivo ?? ''));
  let pidiendoMotivo = $state(false);
  let guardandoConservar = $state(false);
  let errorConservar = $state('');

  async function guardarConservar(/** @type {boolean} */ valor) {
    if (guardandoConservar) return;
    // El motivo es obligatorio al conservar: dentro de seis meses nadie va a
    // saber si la marca sigue teniendo sentido sin el.
    if (valor && !motivoConservar.trim()) {
      pidiendoMotivo = true;
      return;
    }
    guardandoConservar = true;
    errorConservar = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/conservar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conservar: valor, motivo: motivoConservar.trim() })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorConservar = datos.error || 'No se pudo guardar.';
        return;
      }
      conservada = valor;
      if (!valor) motivoConservar = '';
      pidiendoMotivo = false;
    } catch (/** @type {any} */ err) {
      errorConservar = err?.message || 'No se pudo guardar.';
    } finally {
      guardandoConservar = false;
    }
  }

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (c) => CANAL_LABEL[c] ?? c;
  const canalTone = (c) => (c === 'whatsapp' ? 'moss' : 'slate');
  const estadoTone = (e) => (e === 'abierta' ? 'clay' : 'slate');

  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');

  // Mismo criterio que la lista del layout: un telefono o un uuid no dan
  // iniciales, y diez digitos seguidos no se leen.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    const d = v.replace(/\D/g, '');
    if (esTelefono(v) && d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    return v;
  }

  let asignadoA = $state(caso?.assignee_id ?? '');
  let ownerActual = $derived(owners.find((o) => o.id === asignadoA) ?? null);
  let listaAbierta = $state(false);
  /** @type {HTMLFormElement} */
  let formularioAsignar = $state();

  /** El esquema admite user|assistant|tool|system; solo los dos primeros
   *  aparecen hoy (nucleo/persistencia/db.py solo registra esos), pero un
   *  rol inesperado cae en un estilo neutro en vez de romper el render. */
  const burbujaClase = (rol) =>
    rol === 'user' ? 'chat-usuario' : rol === 'assistant' ? 'chat-asistente' : 'chat-otro';

  // Una vez que hay ticket, la caja deja de simular al cliente para que
  // conteste el bot -- pasa a ser la respuesta de la persona que tomo el
  // caso, tal cual la escribe, sin pasar por el modelo. El cliente del otro
  // lado no deberia notar el cambio de quien le esta escribiendo.
  //
  // Se deriva de caso_id, no de si el panel del ticket (caso) cargo bien:
  // si BottleCRM esta caido en ese momento, la conversacion sigue escalada
  // igual y no hay que volver a simular al cliente por eso.
  let escalada = $derived(!!conversacion.caso_id);

  /** Clave de dia local, para agrupar el hilo. */
  function diaDe(/** @type {string} */ iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toDateString();
  }

  function etiquetaDia(/** @type {string} */ iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const hoy = new Date();
    const ayer = new Date();
    ayer.setDate(hoy.getDate() - 1);
    if (d.toDateString() === hoy.toDateString()) return 'Hoy';
    if (d.toDateString() === ayer.toDateString()) return 'Ayer';
    return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'long' }).format(d);
  }

  function hora(/** @type {string} */ iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' }).format(d);
  }

  /** El hilo con separadores de dia intercalados: un chat largo sin ellos
      obliga a pasar el mouse por cada burbuja para ubicarse en el tiempo. */
  let hilo = $derived.by(() => {
    const salida = [];
    let dia = null;
    for (const m of mensajes) {
      const d = diaDe(m.creado_en);
      if (d !== dia) {
        salida.push({ tipo: 'dia', clave: `d-${d}-${salida.length}`, texto: etiquetaDia(m.creado_en) });
        dia = d;
      }
      salida.push({ tipo: 'msg', clave: `m-${salida.length}`, m });
    }
    return salida;
  });

  // --- copiloto documental -------------------------------------------------
  // Lo que dice la documentacion interna sobre lo ultimo que pregunto el
  // cliente. Recupera, no genera: son fragmentos reales con su procedencia, y
  // el agente decide que hacer con ellos. Cuesta un embedding, no una llamada
  // al modelo.
  let sugerencias = $state([]);
  let buscandoDocs = $state(false);
  let errorDocs = $state('');
  let mejorSimilitud = $state(null);
  let docsAbierto = $state(false);
  let expandido = $state(null);
  let copiado = $state(null);
  // La ultima pregunta del cliente es la mejor consulta de arranque; si no
  // sirve, el agente la reescribe.
  let consultaDocs = $state(
    untrack(() => [...(data.mensajes ?? [])].reverse().find((m) => m.rol === 'user')?.contenido ?? '')
  );

  async function buscarDocs() {
    const texto = consultaDocs.trim();
    if (!texto || buscandoDocs) return;
    buscandoDocs = true;
    errorDocs = '';
    expandido = null;
    try {
      const resp = await fetch('/api/sugerencias', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto })
      });
      const datos = await resp.json();
      if (resp.ok) {
        sugerencias = datos.sugerencias ?? [];
        mejorSimilitud = datos.mejor_similitud ?? null;
      } else {
        errorDocs = datos.error || 'No se pudo consultar la documentacion.';
      }
    } catch (/** @type {any} */ err) {
      errorDocs = err?.message || 'No se pudo consultar la documentacion.';
    } finally {
      buscandoDocs = false;
    }
  }

  /** Busca la primera vez que se abre el panel, no al cargar la pagina: si
      nadie lo mira, no se gasta el embedding. */
  function alAbrirDocs(/** @type {Event} */ ev) {
    docsAbierto = /** @type {HTMLDetailsElement} */ (ev.currentTarget).open;
    if (docsAbierto && sugerencias.length === 0 && !buscandoDocs && !errorDocs) buscarDocs();
  }

  /** @param {SubmitEvent} ev */
  function alBuscarDocs(ev) {
    ev.preventDefault();
    buscarDocs();
  }

  /**
   * Copiar, nunca insertar en el compositor: la documentacion esta escrita en
   * lenguaje interno y mandarsela cruda a un cliente seria peor que no
   * tenerla. El agente lee y redacta.
   *
   * @param {string} texto
   * @param {number} i
   */
  async function copiarFragmento(texto, i) {
    try {
      await navigator.clipboard.writeText(texto);
      copiado = i;
      setTimeout(() => (copiado = null), 1600);
    } catch {
      // Portapapeles bloqueado (sin https o sin permiso). El texto esta a la
      // vista para seleccionarlo a mano; no hay nada que avisar.
    }
  }

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando) return;

    entrada = '';
    enviando = true;
    error = '';

    if (escalada) {
      // Una sola burbuja: lo que el agente escribio ES la respuesta, no hay
      // nada que "contestar" del otro lado.
      const burbuja = {
        rol: 'assistant',
        contenido: texto,
        creado_en: new Date().toISOString(),
        /** @type {string|null} */ sinEntregar: null
      };
      mensajes.push(burbuja);
      try {
        const resp = await fetch(`/api/conversaciones/${conversacion.id}/humano`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mensaje: texto })
        });
        const datos = await resp.json();
        if (!resp.ok) {
          error = datos.error || 'No se pudo guardar la respuesta.';
        } else if (datos.aviso) {
          // Se guardo pero NO salio por el canal. El caso mas comun es la
          // ventana de 24 h de WhatsApp. Va marcado en la burbuja y no solo
          // como error suelto: dentro de un rato el aviso de arriba ya no
          // esta, y la burbuja sigue ahi pareciendo entregada.
          burbuja.sinEntregar = datos.aviso;
          error = datos.aviso;
        }
      } catch (/** @type {any} */ err) {
        error = err?.message || 'No se pudo guardar la respuesta.';
      } finally {
        enviando = false;
      }
      return;
    }

    mensajes.push({ rol: 'user', contenido: texto, creado_en: new Date().toISOString() });
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mensaje: texto,
          usuario_externo: conversacion.usuario_externo,
          rol_efectivo: conversacion.rol_efectivo,
          canal: conversacion.canal
        })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        error = datos.error || 'El asistente no pudo responder.';
        return;
      }
      mensajes.push({
        rol: 'assistant',
        contenido: datos.respuesta,
        creado_en: new Date().toISOString(),
        id: datos.mensaje_id,
        caso_marcado: null
      });
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo contactar al asistente.';
    } finally {
      enviando = false;
    }
  }

  /** @param {SubmitEvent} evento */
  function alEnviar(evento) {
    evento.preventDefault();
    enviar();
  }
</script>

<!-- ── CENTRO: la conversación ────────────────────────────────────────────── -->
<section class="centro">
  <header class="centro-top">
    <a class="volver" href="/conversaciones" aria-label="Volver a la lista">
      <ArrowLeft size={16} />
    </a>

    {#if conversacion.nombre_cliente}
      <Avatar name={conversacion.nombre_cliente} size={32} />
    {:else if esTelefono(conversacion.usuario_externo)}
      <span class="ident" aria-hidden="true"><Phone size={15} /></span>
    {:else if !conversacion.usuario_externo || esUuid(conversacion.usuario_externo)}
      <span class="ident" aria-hidden="true"><User size={15} /></span>
    {:else}
      <Avatar name={conversacion.usuario_externo} size={32} />
    {/if}

    <div class="centro-quien">
      <h2>{conversacion.nombre_cliente || quien(conversacion.usuario_externo)}</h2>
      <div class="centro-meta">
        <Pill tone={canalTone(conversacion.canal)}>{canalLabel(conversacion.canal)}</Pill>
        <Pill tone={estadoTone(conversacion.estado)}>{conversacion.estado}</Pill>
      </div>
    </div>

    <!-- Solo aparece cuando la columna de contexto no cabe al lado. Ahí se
         abre como panel, no se pierde: el ticket y la documentación siguen a
         un clic. -->
    <button
      type="button"
      class="v2-btn v2-btn-sm contexto-toggle"
      onclick={() => (contextoAbierto = !contextoAbierto)}
      aria-expanded={contextoAbierto}
    >
      <PanelRight size={14} /> Contexto
    </button>
  </header>

  {#if conversacion.escalada_a_humano}
    <p class="aviso">
      <TriangleAlert size={14} />
      {conversacion.motivo_escalamiento || 'Escalada a un humano'}
      {#if conversacion.necesita_atencion_humana}
        {#if !atendida}
          <button
            type="button"
            class="v2-btn v2-btn-sm aviso-atender"
            onclick={marcarAtendida}
            disabled={marcandoAtendida}
          >
            <CircleCheck size={13} />
            {marcandoAtendida ? 'Marcando…' : 'Atender'}
          </button>
        {:else}
          <span class="aviso-atendida">
            <CircleCheck size={13} /> Atendida
          </span>
        {/if}
      {/if}
      {#if errorAtender}<span class="aviso-mal">{errorAtender}</span>{/if}
    </p>
  {/if}

  <div class="hilo">
    <div class="chat-mensajes">
      {#each hilo as item (item.clave)}
        {#if item.tipo === 'dia'}
          <div class="dia"><span>{item.texto}</span></div>
        {:else}
          <div
            class="chat-burbuja {burbujaClase(item.m.rol)}"
            class:sin-entregar={item.m.sinEntregar}
          >
            <div>{item.m.contenido}</div>
            <!-- Lo que el cliente mando junto al mensaje. Para un ISP la foto
                 de las luces del router dice en un segundo lo que al cliente
                 le cuesta tres mensajes explicar: va EN el hilo, donde la
                 mandó, no en una lista aparte al final. -->
            {#each item.m.adjuntos ?? [] as a (a.id)}
              {#if a.tipo === 'image'}
                <a class="adjunto" href="/api/media/{a.id}" target="_blank" rel="noreferrer">
                  <img src="/api/media/{a.id}" alt={a.descripcion || 'Foto del cliente'} loading="lazy" />
                </a>
              {:else if a.tipo === 'audio' || a.tipo === 'voice'}
                <!-- svelte-ignore a11y_media_has_caption -->
                <audio class="adjunto-audio" controls src="/api/media/{a.id}"></audio>
              {:else}
                <a class="adjunto-otro" href="/api/media/{a.id}" target="_blank" rel="noreferrer">
                  <Paperclip size={13} />
                  {a.tipo || 'archivo'} · <span class="v2-num">{Math.round(a.bytes / 1024)} KB</span>
                </a>
              {/if}
            {/each}

            {#if item.m.sinEntregar}
              <div class="no-llego">
                <TriangleAlert size={12} />
                No le llegó al cliente — {item.m.sinEntregar}
              </div>
            {/if}
            <div class="chat-hora v2-num">{hora(item.m.creado_en)}</div>
            {#if item.m.rol === 'assistant' && casos.length > 0}
              <MarcarEjemplo
                conversacionId={conversacion.id}
                mensajeId={item.m.id}
                casoInicial={item.m.caso_marcado}
                {casos}
              />
            {/if}
          </div>
        {/if}
      {/each}
      {#if enviando && !escalada}
        <div class="chat-burbuja chat-asistente chat-escribiendo" aria-label="Escribiendo…">
          <span class="punto"></span><span class="punto"></span><span class="punto"></span>
        </div>
      {/if}
    </div>
  </div>

  {#if conversacion.estado === 'abierta'}
    <div class="pie">
      {#if error}<p class="v2-error" style="margin:0 0 6px">{error}</p>{/if}
      <form class="compositor" onsubmit={alEnviar}>
        <textarea
          class="compositor-texto"
          bind:value={entrada}
          rows="2"
          placeholder={escalada ? 'Escribí tu respuesta…' : 'Continuar la conversación…'}
          disabled={enviando}
          onkeydown={(e) => {
            // Enter envia, Shift+Enter hace salto de linea: es lo que la mano
            // ya espera de un chat.
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
        ></textarea>
        <div class="compositor-pie">
          <span class="compositor-nota">
            {#if escalada}
              Le llega al cliente tal cual, sin pasar por el asistente
            {:else}
              Responde el asistente
            {/if}
            · <kbd class="v2-kbd">Enter</kbd> envía
          </span>
          <button class="v2-btn v2-btn-primary" type="submit" disabled={enviando || !entrada.trim()}>
            <Send size={14} />{enviando ? 'Enviando…' : 'Enviar'}
          </button>
        </div>
      </form>
    </div>
  {/if}
</section>

<!-- ── DERECHA: el contexto de la conversación ────────────────────────────
     Todo lo que ayuda a contestar pero no es la conversación: el ticket, qué
     hizo el asistente y qué dice la documentación. Antes vivía apilado encima
     del hilo y lo empujaba fuera de la vista. -->
{#if contextoAbierto}
  <!-- Fondo para cerrar el panel al hacer clic afuera. Solo existe mientras el
       panel está desplegado sobre el hilo. -->
  <button
    type="button"
    class="info-fondo"
    aria-label="Cerrar contexto"
    onclick={() => (contextoAbierto = false)}
  ></button>
{/if}

<aside class="info" class:abierto={contextoAbierto} aria-label="Contexto de la conversación">
  <button
    type="button"
    class="v2-btn v2-btn-sm info-cerrar"
    onclick={() => (contextoAbierto = false)}
  >
    <X size={14} /> Cerrar
  </button>

  {#if caso}
  <div class="caso-panel">
    <div class="caso-campo">
      <span class="v2-sub">Etiqueta</span>
      {#if conversacion.etiqueta}
        <Pill tone={etiquetaTone(conversacion.etiqueta)}>{etiquetaLabel(conversacion.etiqueta)}</Pill>
      {:else}
        <span class="v2-muted">Sin clasificar</span>
      {/if}
    </div>

    <div class="caso-campo">
      <span class="v2-sub">Asignado a</span>
      <form
        method="POST"
        action="?/asignar"
        bind:this={formularioAsignar}
        use:enhance={() => ({ update }) => update({ reset: false })}
      >
        <input type="hidden" name="caso_id" value={caso.id} />
        <input type="hidden" name="assigned_to" value={asignadoA} />
        <div class="asignado-picker">
          <button
            type="button"
            class="v2-btn asignado-trigger"
            onclick={() => (listaAbierta = !listaAbierta)}
          >
            {#if ownerActual}
              <Avatar name={ownerActual.name} size={18} />
              <span>{ownerActual.name}</span>
            {:else}
              <span class="v2-muted">Sin asignar</span>
            {/if}
            <ChevronDown size={14} style="margin-left:auto;opacity:0.6" />
          </button>
          {#if listaAbierta}
            <!-- Fondo invisible: cerrar al hacer clic afuera, patron estandar
                 sin depender de ninguna libreria de popover. -->
            <button
              type="button"
              class="asignado-fondo"
              aria-label="Cerrar"
              onclick={() => (listaAbierta = false)}
            ></button>
            <ul class="asignado-content">
              <li>
                <button
                  type="button"
                  class="asignado-item"
                  onclick={() => {
                    asignadoA = '';
                    listaAbierta = false;
                    formularioAsignar.requestSubmit();
                  }}
                >
                  <span class="v2-muted">Sin asignar</span>
                </button>
              </li>
              {#each owners as o (o.id)}
                <li>
                  <button
                    type="button"
                    class="asignado-item"
                    onclick={() => {
                      asignadoA = o.id;
                      listaAbierta = false;
                      formularioAsignar.requestSubmit();
                    }}
                  >
                    <Avatar name={o.name} size={18} />
                    <span>{o.name}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </form>
    </div>

    <a class="v2-btn v2-btn-sm caso-link" href="/tickets/{caso.id}">
      Ver ticket completo <ArrowRight size={14} />
    </a>
  </div>
  {/if}

  <!-- Conservar. Va arriba de todo y fuera de cualquier plegable: es una
       decisión sobre si esta conversación va a seguir existiendo, y hay que
       poder verla sin abrir nada. -->
  <div class="conservar" class:activa={conservada}>
    <label class="conservar-linea">
      <input
        type="checkbox"
        checked={conservada}
        disabled={guardandoConservar}
        onchange={(e) => guardarConservar(/** @type {HTMLInputElement} */ (e.currentTarget).checked)}
      />
      <span>
        <b>Conservar</b>
        <span class="v2-muted">— no borrar al vencer la retención</span>
      </span>
    </label>

    {#if pidiendoMotivo && !conservada}
      <div class="conservar-motivo">
        <input
          class="v2-input"
          type="text"
          bind:value={motivoConservar}
          placeholder="¿Por qué? Ej: reclamo en curso"
          onkeydown={(e) => { if (e.key === 'Enter') guardarConservar(true); }}
        />
        <button
          class="v2-btn v2-btn-sm"
          type="button"
          disabled={guardandoConservar || !motivoConservar.trim()}
          onclick={() => guardarConservar(true)}
        >
          Guardar
        </button>
      </div>
    {:else if conservada && motivoConservar}
      <p class="conservar-nota">{motivoConservar}</p>
    {/if}

    {#if errorConservar}<p class="conservar-mal">{errorConservar}</p>{/if}
  </div>

  {#if herramientas.length > 0}
  <details class="proceso">
    <summary class="proceso-resumen">
      Ver proceso
      <span class="v2-muted">
        ({herramientas.length} paso{herramientas.length === 1 ? '' : 's'}{#if herramientas.some((h) => h.es_escritura)}, con escritura{/if})
      </span>
    </summary>
    <ol class="proceso-lista">
      {#each herramientas as h}
        <li class="proceso-item">
          {#if h.exito}
            <CircleCheck size={15} style="color:var(--v2-moss);flex:none" />
          {:else}
            <CircleX size={15} style="color:var(--v2-rust);flex:none" />
          {/if}
          <span class="proceso-nombre">{h.herramienta}</span>
          {#if h.n_registros !== null}
            <span class="v2-muted">{h.n_registros} resultado{h.n_registros === 1 ? '' : 's'}</span>
          {/if}
          {#if h.codigo_error}
            <span class="v2-muted" title={h.codigo_error}>{h.codigo_error.split(':')[0]}</span>
          {/if}
          <span class="v2-muted proceso-duracion">{h.duracion_ms} ms</span>
        </li>
      {/each}
    </ol>
  </details>
  {/if}

  <!-- Copiloto documental. Mismo patron plegable que "Ver proceso": es ayuda
       lateral, no el contenido de la pantalla. -->
  <details class="docs" ontoggle={alAbrirDocs}>
  <summary class="proceso-resumen">
    Documentación
    <span class="v2-muted">
      {#if sugerencias.length}
        ({sugerencias.length} fragmento{sugerencias.length === 1 ? '' : 's'})
      {:else}
        (buscar en las guías internas)
      {/if}
    </span>
  </summary>

  <form class="docs-buscar" onsubmit={alBuscarDocs}>
    <input
      class="v2-input"
      type="text"
      bind:value={consultaDocs}
      placeholder="¿Qué necesitás buscar?"
      aria-label="Buscar en la documentación interna"
    />
    <button class="v2-btn v2-btn-sm" type="submit" disabled={buscandoDocs}>Buscar</button>
  </form>

  {#if buscandoDocs}
    <p class="v2-muted docs-nota">Buscando…</p>
  {:else if errorDocs}
    <p class="docs-nota docs-malo">{errorDocs}</p>
  {:else if sugerencias.length === 0}
    <p class="v2-muted docs-nota">
      La documentación no cubre esta consulta.
      {#if mejorSimilitud !== null}
        Lo más parecido quedó en <span class="v2-num">{mejorSimilitud}</span>, por debajo del umbral.
      {/if}
    </p>
  {:else}
    {#each sugerencias as s, i}
      <article class="doc" class:abierto={expandido === i}>
        <button
          type="button"
          class="doc-head"
          onclick={() => (expandido = expandido === i ? null : i)}
          aria-expanded={expandido === i}
        >
          <span class="doc-codigo v2-num">{s.codigo || '—'}{#if s.version} v{s.version}{/if}</span>
          <span class="doc-titulo">{s.titulo || 'Sin título'}</span>
        </button>
        <p class="doc-texto">{s.contenido}</p>
        <div class="doc-pie">
          <button
            class="v2-btn v2-btn-sm"
            type="button"
            onclick={() => copiarFragmento(s.contenido, i)}
          >
            {copiado === i ? 'Copiado' : 'Copiar'}
          </button>
        </div>
      </article>
    {/each}
  {/if}
  </details>
</aside>

<style>
  /* ── columna del centro: la conversación ────────────────────────────── */
  .centro {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .centro-top {
    flex: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--v2-line);
  }
  .centro-quien {
    min-width: 0;
  }
  .centro-top h2 {
    margin: 0;
    font-size: 14.5px;
    font-weight: 640;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .centro-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 3px;
  }
  .ident {
    flex: none;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }
  /* Volver sólo tiene sentido cuando la lista no está al lado. */
  .volver {
    display: none;
    color: var(--v2-slate);
  }
  .aviso {
    flex: none;
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    padding: 8px 16px;
    font-size: 12.5px;
    color: var(--v2-rust);
    background: color-mix(in srgb, var(--v2-rust) 6%, transparent);
    border-bottom: 1px solid var(--v2-line);
  }
  .aviso-atender {
    margin-left: auto;
    flex: none;
  }
  .aviso-atendida {
    margin-left: auto;
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--v2-moss, #15803d);
    font-weight: 600;
  }
  .aviso-mal {
    flex: none;
    color: var(--v2-rust);
  }
  /* El hilo es lo único que scrollea acá: el encabezado y el compositor
     quedan fijos, para no tener que bajar hasta el fondo para escribir. */
  .hilo {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 16px;
  }
  .pie {
    flex: none;
    padding: 0 16px 14px;
  }

  /* ── columna de la derecha: el contexto ─────────────────────────────── */
  .info {
    width: 310px;
    flex: none;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 16px 20px;
    border-left: 1px solid var(--v2-line);
  }
  /* Por encima de 1240px la columna está siempre a la vista: ni botón para
     abrirla, ni botón para cerrarla, ni fondo que interceptar. */
  .contexto-toggle,
  .info-cerrar,
  .info-fondo {
    display: none;
  }
  .info-fondo {
    position: fixed;
    inset: 0;
    z-index: 55;
    background: rgba(28, 25, 23, 0.18);
    border: 0;
    padding: 0;
    cursor: default;
  }
  @media (max-width: 1240px) {
    .info-fondo {
      display: block;
    }
  }

  /* En la columna angosta los campos del ticket se apilan; en fila no
     entraban ni el nombre del responsable. */
  .caso-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }
  .caso-campo {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
  }
  .caso-campo > .v2-sub {
    font-size: 11.5px;
    white-space: nowrap;
  }
  .caso-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    align-self: flex-start;
  }
  .proceso,
  .docs {
    padding: 14px 0 0;
  }

  /* ── conservar ──────────────────────────────────────────────────────── */
  /* Sin recuadro mientras está apagada: es una casilla más, no una alerta.
     Al encenderla toma superficie, porque a partir de ahí sí es un estado
     que hay que poder ver de un vistazo. */
  .conservar {
    padding: 0 0 14px;
    border-bottom: 1px solid var(--v2-line-soft);
  }
  .conservar.activa {
    background: var(--v2-line-soft);
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 14px;
    border-bottom: 0;
  }
  .conservar-linea {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12.5px;
    line-height: 1.4;
    cursor: pointer;
  }
  .conservar-linea input {
    margin-top: 2px;
    flex: none;
    accent-color: var(--v2-ink);
  }
  .conservar-motivo {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }
  .conservar-motivo input {
    flex: 1;
    min-width: 0;
    font-size: 12.5px;
  }
  .conservar-nota {
    margin: 6px 0 0 22px;
    font-size: 11.5px;
    color: var(--v2-slate);
    line-height: 1.4;
  }
  .conservar-mal {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--v2-rust);
  }

  /* ── copiloto documental ────────────────────────────────────────────── */
  .docs-buscar {
    display: flex;
    gap: 6px;
    margin: 10px 0 4px;
  }
  .docs-buscar input {
    flex: 1;
    min-width: 0;
    font-size: 13px;
  }
  .docs-nota {
    font-size: 12.5px;
    line-height: 1.5;
    margin: 8px 0 0;
  }
  .docs-malo {
    color: var(--v2-rust);
  }
  /* Sin tarjeta: son citas de un documento, no objetos que se manipulan. */
  .doc {
    border-top: 1px solid var(--v2-line-soft);
    padding: 9px 0;
  }
  .doc-head {
    display: flex;
    flex-direction: column;
    gap: 1px;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    padding: 0;
    font: inherit;
    color: inherit;
    cursor: pointer;
  }
  .doc-codigo {
    font-size: 10.5px;
    color: var(--v2-slate);
  }
  .doc-titulo {
    font-size: 12.5px;
    font-weight: 620;
    letter-spacing: -0.01em;
    line-height: 1.35;
  }
  .doc-head:hover .doc-titulo {
    text-decoration: underline;
  }
  .doc-texto {
    font-size: 12.2px;
    color: var(--v2-slate);
    line-height: 1.5;
    margin: 5px 0 0;
    white-space: pre-wrap;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  /* Abierto: el fragmento entero, con su propio scroll para que un documento
     largo no empuje el hilo fuera de la vista. */
  .doc.abierto .doc-texto {
    display: block;
    max-height: 320px;
    overflow-y: auto;
  }
  .doc-pie {
    display: flex;
    justify-content: flex-end;
    margin-top: 6px;
  }
  .proceso-resumen {
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
    user-select: none;
  }
  .proceso-resumen .v2-muted {
    font-weight: 400;
  }
  .proceso-lista {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .proceso-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    padding: 4px 0;
  }
  .proceso-nombre {
    font-family: var(--v2-mono, monospace);
  }
  .proceso-duracion {
    margin-left: auto;
  }
  .asignado-picker {
    position: relative;
  }
  .asignado-trigger {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }
  /* Fondo invisible a pantalla completa: clic afuera cierra la lista. Es el
     patron sin dependencias -- ver por que se saco bits-ui mas arriba. */
  .asignado-fondo {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: transparent;
    border: none;
    cursor: default;
    padding: 0;
  }
  .asignado-content {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--v2-surface, #fff);
    border: 1px solid var(--v2-border, #e5e5e5);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 6px;
    min-width: 200px;
    z-index: 50;
    list-style: none;
    margin: 0;
  }
  .asignado-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border-radius: 7px;
    font-size: 13.5px;
    cursor: pointer;
    background: none;
    border: none;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }
  .asignado-item:hover,
  .asignado-item:focus-visible {
    background: var(--v2-surface-2, #f1f1f1);
    outline: none;
  }

  .chat-mensajes {
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 720px;
  }
  .dia {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 6px 0;
    color: var(--v2-slate);
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .dia::before,
  .dia::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--v2-line);
  }
  .chat-burbuja {
    padding: 10px 14px;
    border-radius: 12px;
    max-width: 80%;
    white-space: pre-wrap;
    font-size: 14px;
    line-height: 1.4;
  }
  .chat-usuario {
    align-self: flex-end;
    background: var(--v2-accent, #2563eb);
    color: white;
  }
  .chat-asistente {
    align-self: flex-start;
    background: var(--v2-surface-2, #f1f1f1);
  }
  .chat-otro {
    align-self: center;
    background: transparent;
    border: 1px dashed var(--v2-border, #e5e5e5);
    font-style: italic;
    opacity: 0.75;
  }
  .chat-hora {
    margin-top: 4px;
    font-size: 11px;
    opacity: 0.65;
  }
  /* Una respuesta guardada que nunca salio tiene que verse distinta de una
     entregada. El aviso de arriba desaparece al rato; la burbuja se queda. */
  .chat-burbuja.sin-entregar {
    outline: 1px solid var(--v2-rust);
    outline-offset: -1px;
  }
  /* La foto ocupa el ancho de la burbuja y se abre a tamano completo al
     hacer clic. Alto acotado: una foto vertical de telefono empujaria el
     resto del hilo fuera de la pantalla. */
  .adjunto {
    display: block;
    margin-top: 6px;
    border-radius: 8px;
    overflow: hidden;
    line-height: 0;
  }
  .adjunto img {
    display: block;
    width: 100%;
    max-height: 320px;
    object-fit: cover;
  }
  .adjunto-audio {
    display: block;
    width: 100%;
    margin-top: 6px;
    height: 34px;
  }
  .adjunto-otro {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
    font-size: 11.5px;
    color: inherit;
    opacity: 0.85;
  }

  .no-llego {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
    padding-top: 5px;
    border-top: 1px solid color-mix(in srgb, var(--v2-rust) 35%, transparent);
    font-size: 11px;
    color: var(--v2-rust);
    line-height: 1.35;
  }
  .chat-escribiendo {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 13px 16px;
  }
  .chat-escribiendo .punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.35;
    animation: chat-parpadeo 1.2s infinite ease-in-out;
  }
  .chat-escribiendo .punto:nth-child(2) {
    animation-delay: 0.2s;
  }
  .chat-escribiendo .punto:nth-child(3) {
    animation-delay: 0.4s;
  }
  @keyframes chat-parpadeo {
    0%,
    60%,
    100% {
      opacity: 0.3;
      transform: translateY(0);
    }
    30% {
      opacity: 1;
      transform: translateY(-2px);
    }
  }
  .compositor {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-line);
  }
  .compositor-texto {
    width: 100%;
    resize: vertical;
    min-height: 44px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    padding: 9px 11px;
    background: var(--v2-card);
    color: var(--v2-ink);
    font-family: inherit;
    font-size: calc(var(--v2-fs) - 0.5px);
    line-height: 1.4;
  }
  .compositor-texto:focus {
    outline: 2px solid var(--v2-ember);
    outline-offset: -1px;
    border-color: transparent;
  }
  .compositor-texto:disabled {
    background: var(--v2-line-soft);
    color: var(--v2-slate);
    cursor: not-allowed;
  }
  .compositor-pie {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .compositor-nota {
    font-size: 11.5px;
    color: var(--v2-slate);
  }

  /* Debajo de 1240px las tres columnas ahogan el hilo. El contexto deja de
     estar fijo al lado y pasa a abrirse con el botón del encabezado -- no
     desaparece: el ticket y la documentación siguen estando a un clic. */
  @media (max-width: 1240px) {
    .contexto-toggle {
      display: inline-flex;
      margin-left: auto;
      flex: none;
    }
    .info {
      display: none;
    }
    .info.abierto {
      display: block;
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: min(340px, 88vw);
      z-index: 60;
      background: var(--v2-paper);
      box-shadow: -8px 0 24px rgba(0, 0, 0, 0.12);
    }
    .info-cerrar {
      display: inline-flex;
      margin-bottom: 12px;
    }
  }
  /* Y debajo de 1000px la lista deja de estar al lado (ver el layout), así que
     hace falta una forma de volver. */
  @media (max-width: 1000px) {
    .volver {
      display: grid;
      place-items: center;
    }
  }
</style>
