<script>
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { TriangleAlert, ChevronDown, ArrowRight, CircleCheck, CircleX } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  // untrack: la conversacion/hilo/caso se mutan localmente despues (enviar(),
  // la asignacion) -- capturar el valor inicial es lo que se quiere, no
  // seguir a `data` en cada re-render (mismo patron que goals/[id]/edit).
  let conversacion = $state(untrack(() => data.conversacion));
  let mensajes = $state(untrack(() => data.mensajes ?? []));
  let caso = $state(untrack(() => data.caso));
  let owners = $state(untrack(() => data.owners ?? []));
  let herramientas = $state(untrack(() => data.herramientas ?? []));
  let casos = $state(untrack(() => data.casos ?? []));

  let entrada = $state('');
  let enviando = $state(false);
  let error = $state('');

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (c) => CANAL_LABEL[c] ?? c;
  const canalTone = (c) => (c === 'whatsapp' ? 'moss' : 'slate');
  const estadoTone = (e) => (e === 'abierta' ? 'clay' : 'slate');

  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');

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

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando) return;

    entrada = '';
    enviando = true;
    error = '';

    if (escalada) {
      // Una sola burbuja: lo que el agente escribio ES la respuesta, no hay
      // nada que "contestar" del otro lado.
      mensajes.push({ rol: 'assistant', contenido: texto, creado_en: new Date().toISOString() });
      try {
        const resp = await fetch(`/api/conversaciones/${conversacion.id}/humano`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mensaje: texto })
        });
        if (!resp.ok) {
          const datos = await resp.json();
          error = datos.error || 'No se pudo guardar la respuesta.';
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

<PageHeader title={conversacion.usuario_externo} record>
  {#snippet crumb()}<a href="/conversaciones">Conversaciones</a> ›{/snippet}
  {#snippet sub()}
    <Pill tone={canalTone(conversacion.canal)}>{canalLabel(conversacion.canal)}</Pill>
    <Pill tone={estadoTone(conversacion.estado)}>{conversacion.estado}</Pill>
    {#if conversacion.escalada_a_humano}
      <span class="v2-sub" style="color:var(--v2-rust);display:inline-flex;align-items:center;gap:4px">
        <TriangleAlert size={14} />
        {conversacion.motivo_escalamiento || 'Escalada a un humano'}
      </span>
    {/if}
  {/snippet}
</PageHeader>

{#if caso}
  <div class="caso-panel v2-pad">
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

{#if herramientas.length > 0}
  <details class="proceso v2-pad">
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

<div class="v2-scroll v2-pad" style="padding-top:12px">
  <div class="chat-mensajes">
    {#each mensajes as m}
      <div class="chat-burbuja {burbujaClase(m.rol)}">
        <div>{m.contenido}</div>
        <div class="chat-hora">{relativeTime(m.creado_en)}</div>
        {#if m.rol === 'assistant' && casos.length > 0}
          <MarcarEjemplo
            conversacionId={conversacion.id}
            mensajeId={m.id}
            casoInicial={m.caso_marcado}
            {casos}
          />
        {/if}
      </div>
    {/each}
    {#if enviando && !escalada}
      <div class="chat-burbuja chat-asistente chat-escribiendo" aria-label="Escribiendo…">
        <span class="punto"></span><span class="punto"></span><span class="punto"></span>
      </div>
    {/if}
  </div>

  {#if conversacion.estado === 'abierta'}
    {#if escalada}
      <p class="v2-sub" style="max-width:720px;font-size:12px;margin-bottom:6px">
        Estás respondiendo como agente humano — esto no pasa por el asistente.
      </p>
    {/if}
    {#if error}<p class="v2-error" style="max-width:720px">{error}</p>{/if}
    <form class="chat-form" onsubmit={alEnviar} style="max-width:720px">
      <input
        class="v2-input"
        type="text"
        bind:value={entrada}
        placeholder={escalada ? 'Escribí tu respuesta…' : 'Continuar la conversación…'}
        disabled={enviando}
      />
      <button class="v2-btn v2-btn-primary" type="submit" disabled={enviando}>Enviar</button>
    </form>
  {/if}
</div>

<style>
  .caso-panel {
    display: flex;
    align-items: center;
    gap: 28px;
    padding-top: 0;
    padding-bottom: 16px;
    flex-wrap: wrap;
  }
  .caso-campo {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .caso-campo > .v2-sub {
    font-size: 12px;
    white-space: nowrap;
  }
  .caso-link {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .proceso {
    padding-top: 0;
    padding-bottom: 14px;
    max-width: 720px;
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
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 160px;
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
  .chat-form {
    display: flex;
    gap: 8px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-border, #e5e5e5);
  }
  .chat-form input {
    flex: 1;
  }
</style>
