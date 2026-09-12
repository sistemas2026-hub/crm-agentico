<script>
  /**
   * Pagina del asistente de IA. Habla con el motor de crm-agentico (repo
   * aparte) via el proxy server-side en /api/asistente -- este componente
   * nunca conoce la URL real del motor ni su auth, solo llama a su propio
   * origen (sin CORS, sin exponer nada al browser).
   *
   * Primer corte: un solo rol ('soporte'), sin streaming, sin historial
   * persistido entre recargas de pagina -- el motor si mantiene su propia
   * sesion en memoria del lado del proceso (ver nucleo/canales/api.py).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';

  let mensajes = $state([]);
  let entrada = $state('');
  let enviando = $state(false);

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando) return;

    mensajes.push({ rol: 'usuario', texto });
    entrada = '';
    enviando = true;

    try {
      const resp = await fetch('/api/asistente', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto })
      });
      const datos = await resp.json();
      mensajes.push(
        resp.ok
          ? { rol: 'asistente', texto: datos.respuesta }
          : { rol: 'error', texto: datos.error || 'El asistente no pudo responder.' }
      );
    } catch (/** @type {any} */ err) {
      mensajes.push({ rol: 'error', texto: err?.message || 'No se pudo contactar al asistente.' });
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

<PageHeader title="Asistente">
  {#snippet sub()}
    Pregunta por clientes, tickets o casos -- por ejemplo: "¿hay casos en estado asignado?"
  {/snippet}
</PageHeader>

<div class="chat">
  <div class="chat-mensajes">
    {#if mensajes.length === 0}
      <p class="chat-vacio">Escribi un mensaje para empezar.</p>
    {/if}
    {#each mensajes as m}
      <div class="chat-burbuja chat-{m.rol}">{m.texto}</div>
    {/each}
    {#if enviando}
      <div class="chat-burbuja chat-asistente chat-pensando">Pensando…</div>
    {/if}
  </div>

  <form class="chat-form" onsubmit={alEnviar}>
    <input
      class="v2-input"
      type="text"
      bind:value={entrada}
      placeholder="Escribi tu mensaje…"
      disabled={enviando}
    />
    <button class="v2-btn v2-btn-primary" type="submit" disabled={enviando}>Enviar</button>
  </form>
</div>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 160px);
    max-width: 720px;
  }
  .chat-mensajes {
    flex: 1;
    overflow-y: auto;
    padding: 16px 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .chat-vacio {
    color: var(--v2-muted, #888);
    font-size: 14px;
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
  .chat-error {
    align-self: flex-start;
    background: #fee2e2;
    color: #991b1b;
  }
  .chat-pensando {
    opacity: 0.6;
    font-style: italic;
  }
  .chat-form {
    display: flex;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-border, #e5e5e5);
  }
  .chat-form input {
    flex: 1;
  }
</style>
