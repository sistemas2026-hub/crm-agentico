<script>
  import { untrack } from 'svelte';
  import { Select } from 'bits-ui';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { TriangleAlert, ChevronDown, ArrowRight } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  // untrack: la conversacion/hilo/caso se mutan localmente despues (enviar(),
  // la asignacion) -- capturar el valor inicial es lo que se quiere, no
  // seguir a `data` en cada re-render (mismo patron que goals/[id]/edit).
  let conversacion = $state(untrack(() => data.conversacion));
  let mensajes = $state(untrack(() => data.mensajes ?? []));
  let caso = $state(untrack(() => data.caso));
  let owners = $state(untrack(() => data.owners ?? []));

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
  /** @type {HTMLFormElement} */
  let formularioAsignar;

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
        creado_en: new Date().toISOString()
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
        <Select.Root
          type="single"
          value={asignadoA}
          onValueChange={(v) => {
            asignadoA = v;
            formularioAsignar.requestSubmit();
          }}
        >
          <Select.Trigger class="v2-btn asignado-trigger">
            {#if ownerActual}
              <Avatar name={ownerActual.name} size={18} />
              <span>{ownerActual.name}</span>
            {:else}
              <span class="v2-muted">Sin asignar</span>
            {/if}
            <ChevronDown size={14} style="margin-left:auto;opacity:0.6" />
          </Select.Trigger>
          <Select.Portal>
            <Select.Content class="asignado-content" sideOffset={4}>
              <Select.Viewport>
                <Select.Item value="" label="Sin asignar" class="asignado-item">
                  <span class="v2-muted">Sin asignar</span>
                </Select.Item>
                {#each owners as o (o.id)}
                  <Select.Item value={o.id} label={o.name} class="asignado-item">
                    <Avatar name={o.name} size={18} />
                    <span>{o.name}</span>
                  </Select.Item>
                {/each}
              </Select.Viewport>
            </Select.Content>
          </Select.Portal>
        </Select.Root>
      </form>
    </div>

    <a class="v2-btn v2-btn-sm caso-link" href="/tickets/{caso.id}">
      Ver ticket completo <ArrowRight size={14} />
    </a>
  </div>
{/if}

<div class="v2-scroll v2-pad" style="padding-top:12px">
  <div class="chat-mensajes">
    {#each mensajes as m}
      <div class="chat-burbuja {burbujaClase(m.rol)}">
        <div>{m.contenido}</div>
        <div class="chat-hora">{relativeTime(m.creado_en)}</div>
      </div>
    {/each}
    {#if enviando && !escalada}
      <div class="chat-burbuja chat-asistente chat-pensando">Pensando…</div>
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
  :global(.asignado-trigger) {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 160px;
  }
  :global(.asignado-content) {
    background: var(--v2-surface, #fff);
    border: 1px solid var(--v2-border, #e5e5e5);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 6px;
    min-width: 200px;
    z-index: 50;
  }
  :global(.asignado-item) {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 10px;
    border-radius: 7px;
    font-size: 13.5px;
    cursor: pointer;
    outline: none;
  }
  :global(.asignado-item[data-highlighted]) {
    background: var(--v2-surface-2, #f1f1f1);
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
  .chat-pensando {
    opacity: 0.6;
    font-style: italic;
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
