<script>
  /**
   * Simula un remitente de WhatsApp para probar 'cliente_final' (el rol
   * orientado al cliente, no al colaborador) sin depender de la API real de
   * WhatsApp Business -- misma idea que cli/panel_pruebas.py, ahora dentro
   * de BottleCRM en vez de en una herramienta aparte.
   *
   * El telefono ES la identidad: cambiarlo simula a otro cliente escribiendo
   * de cero, y reinicia la conversacion (el motor arranca una sesion nueva
   * para cada 'identificador_sesion' que no haya visto antes).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';

  let telefono = $state('3001234567');
  let mensajes = $state([]);
  let entrada = $state('');
  let enviando = $state(false);
  let verificado = $state(false);

  function reiniciar() {
    mensajes = [];
    verificado = false;
  }

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando || !telefono.trim()) return;

    mensajes.push({ rol: 'usuario', texto });
    entrada = '';
    enviando = true;

    try {
      const resp = await fetch('/api/simulador-whatsapp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telefono: telefono.trim(), mensaje: texto })
      });
      const datos = await resp.json();
      if (resp.ok) {
        mensajes.push({ rol: 'asistente', texto: datos.respuesta });
        verificado = !!datos.verificado;
      } else {
        mensajes.push({ rol: 'error', texto: datos.error || 'El asistente no pudo responder.' });
      }
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

<PageHeader title="Simulador de WhatsApp">
  {#snippet sub()}
    Prueba al agente de atención al cliente (<code>cliente_final</code>) como si fueras un cliente escribiendo por WhatsApp.
  {/snippet}
</PageHeader>

<div class="simulador">
  <div class="fila-telefono">
    <label for="telefono">Número que simula escribir</label>
    <input
      id="telefono"
      class="v2-input"
      type="text"
      bind:value={telefono}
      placeholder="3001234567"
    />
    <button class="v2-btn" type="button" onclick={reiniciar}>Reiniciar conversación</button>
    {#if mensajes.length > 0}
      <span class="estado-verificacion" class:ok={verificado}>
        {verificado ? '✅ Verificado' : '🔒 No verificado'}
      </span>
    {/if}
  </div>

  <div class="chat">
    <div class="chat-mensajes">
      {#if mensajes.length === 0}
        <p class="chat-vacio">Escribí un mensaje como si fueras este cliente para empezar.</p>
      {/if}
      {#each mensajes as m}
        <div class="chat-burbuja chat-{m.rol}">{m.texto}</div>
      {/each}
      {#if enviando}
        <div class="chat-burbuja chat-asistente chat-escribiendo" aria-label="Escribiendo…">
          <span class="punto"></span><span class="punto"></span><span class="punto"></span>
        </div>
      {/if}
    </div>

    <form class="chat-form" onsubmit={alEnviar}>
      <input
        class="v2-input"
        type="text"
        bind:value={entrada}
        placeholder="Escribí como si fueras el cliente…"
        disabled={enviando}
      />
      <button class="v2-btn v2-btn-primary" type="submit" disabled={enviando}>Enviar</button>
    </form>
  </div>
</div>

<style>
  .simulador {
    display: flex;
    flex-direction: column;
    max-width: 720px;
  }
  .fila-telefono {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-bottom: 12px;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--v2-border, #e5e5e5);
  }
  .fila-telefono label {
    font-size: 13px;
    color: var(--v2-muted, #888);
    white-space: nowrap;
  }
  .fila-telefono input {
    max-width: 180px;
  }
  .estado-verificacion {
    margin-left: auto;
    font-size: 13px;
    color: #991b1b;
  }
  .estado-verificacion.ok {
    color: #15803d;
  }
  .chat {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 260px);
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
    padding-top: 12px;
    border-top: 1px solid var(--v2-border, #e5e5e5);
  }
  .chat-form input {
    flex: 1;
  }
</style>
