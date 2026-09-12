<script>
  /**
   * Un ADMIN describe una API nueva en el chat; el rol 'configuracion_guiada'
   * del motor la sondea de verdad (nunca inventa que un filtro funciona,
   * ver tenants/rapilink.config.yaml) y arma un borrador. Las propuestas
   * quedan PENDIENTES a la derecha hasta que alguien las aprueba o rechaza
   * -- nunca se activan solas, ni siquiera si las armo el mismo ADMIN que
   * esta charlando.
   *
   * Mismo patron que /simulador-whatsapp (chat) y /manual (lista con
   * aprobar/descartar), combinados en una sola pantalla porque las dos
   * mitades son parte del mismo flujo: sondear y decidir.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { toast } from 'svelte-sonner';

  /** @type {{ data: any }} */
  let { data } = $props();

  let mensajes = $state([]);
  let entrada = $state('');
  let enviando = $state(false);

  // Copia local mutable -- aprobar/rechazar actualiza la pantalla al toque,
  // mismo criterio que 'revisiones' en /manual.
  let propuestas = $state(data.propuestas ?? []);
  const pendientes = $derived(propuestas.filter((p) => p.estado === 'pendiente'));
  const resueltas = $derived(propuestas.filter((p) => p.estado !== 'pendiente'));
  let verResueltas = $state(false);
  /** @type {Record<string, boolean>} */
  let resolviendo = $state({});

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando) return;

    mensajes.push({ rol: 'usuario', texto });
    entrada = '';
    enviando = true;

    try {
      const resp = await fetch('/api/configuracion-guiada', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto })
      });
      const datos = await resp.json();
      if (resp.ok) {
        mensajes.push({ rol: 'asistente', texto: datos.respuesta });
        // El turno pudo haber generado una propuesta nueva -- se recarga la
        // lista en vez de tratar de adivinar la forma exacta desde el chat.
        await recargarPropuestas();
      } else {
        mensajes.push({ rol: 'error', texto: datos.error || 'El asistente no pudo responder.' });
      }
    } catch (/** @type {any} */ err) {
      mensajes.push({ rol: 'error', texto: err?.message || 'No se pudo contactar al asistente.' });
    } finally {
      enviando = false;
    }
  }

  async function recargarPropuestas() {
    try {
      const resp = await fetch('/api/configuracion-guiada/propuestas');
      if (resp.ok) propuestas = (await resp.json()).propuestas;
    } catch {
      // Silencioso a proposito: el chat ya sigue andando, esto solo
      // refresca el panel lateral -- no vale la pena un toast por esto.
    }
  }

  async function resolver(/** @type {any} */ p, /** @type {'aprobar'|'rechazar'} */ accion) {
    resolviendo = { ...resolviendo, [p.id]: true };
    try {
      const resp = await fetch(`/api/configuracion-guiada/propuestas/${p.id}/${accion}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        toast.error(datos?.error || `No se pudo ${accion} la propuesta.`);
        return;
      }
      propuestas = propuestas.map((x) => (x.id === p.id ? { ...x, estado: datos.estado } : x));
      toast.success(accion === 'aprobar' ? 'Herramienta agregada al catálogo.' : 'Propuesta rechazada.');
    } finally {
      resolviendo = { ...resolviendo, [p.id]: false };
    }
  }

  /** @param {SubmitEvent} evento */
  function alEnviar(evento) {
    evento.preventDefault();
    enviar();
  }
</script>

<PageHeader title="Conectar sistema nuevo">
  {#snippet sub()}
    Describí la API que querés conectar -- el asistente la sondea de verdad antes de proponer nada.
    Ninguna herramienta se activa sin que la apruebes acá.
  {/snippet}
</PageHeader>

{#if data.error}
  <p class="aviso-error">⚠️ {data.error}</p>
{:else}
  <div class="dos-columnas">
    <div class="chat">
      <div class="chat-mensajes">
        {#if mensajes.length === 0}
          <p class="chat-vacio">
            Contale al asistente qué API querés conectar: la URL base, si necesita autenticación
            (y con qué nombre guardaste la clave en Secretos), y qué datos te interesan.
          </p>
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
          placeholder="Ej: quiero conectar la API de facturación de..."
          disabled={enviando}
        />
        <button class="v2-btn v2-btn-primary" type="submit" disabled={enviando}>Enviar</button>
      </form>
    </div>

    <div class="panel-propuestas">
      <div class="v2-label">
        Propuestas pendientes
        <span class="v2-muted">({pendientes.length})</span>
      </div>

      {#if pendientes.length === 0}
        <p class="v2-sub" style="margin-bottom:16px">
          Ninguna todavía. Van a aparecer acá apenas el asistente termine de sondear algo.
        </p>
      {:else}
        <div class="propuestas-lista">
          {#each pendientes as p (p.id)}
            <div class="v2-card propuesta-card">
              <div class="propuesta-nombre">{p.herramienta_propuesta?.nombre || '(sin nombre)'}</div>
              <div class="v2-sub" style="margin:4px 0">{p.descripcion_pedido}</div>
              <div class="propuesta-detalle v2-sub">
                <code>{p.herramienta_propuesta?.tipo}</code> ·
                {p.herramienta_propuesta?.base_url}{p.herramienta_propuesta?.endpoint}
              </div>
              <div class="propuesta-meta v2-sub">
                {relativeTime(p.creado_en)} · propuesto por {p.propuesto_por}
              </div>
              <div class="propuesta-acciones">
                <button type="button" class="v2-btn v2-btn-sm" disabled={resolviendo[p.id]}
                  onclick={() => resolver(p, 'aprobar')}>
                  Aprobar
                </button>
                <button type="button" class="v2-btn v2-btn-sm" disabled={resolviendo[p.id]}
                  onclick={() => resolver(p, 'rechazar')}>
                  Rechazar
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      {#if resueltas.length > 0}
        <button type="button" class="v2-btn v2-btn-sm" style="margin-top:8px"
          onclick={() => (verResueltas = !verResueltas)}>
          {verResueltas ? 'Ocultar' : 'Ver'} {resueltas.length} resuelta{resueltas.length === 1 ? '' : 's'}
        </button>
        {#if verResueltas}
          <div class="propuestas-lista" style="margin-top:8px">
            {#each resueltas as p (p.id)}
              <div class="v2-card propuesta-card propuesta-resuelta">
                <div class="propuesta-nombre">
                  {p.herramienta_propuesta?.nombre || '(sin nombre)'}
                  <Pill tone={p.estado === 'aprobada' ? 'moss' : 'clay'}>{p.estado}</Pill>
                </div>
                <div class="v2-sub" style="margin:4px 0">{p.descripcion_pedido}</div>
                {#if p.motivo_rechazo}
                  <div class="v2-sub"><b>Motivo:</b> {p.motivo_rechazo}</div>
                {/if}
                <div class="propuesta-meta v2-sub">
                  revisado por {p.revisado_por} · {relativeTime(p.revisado_en)}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .dos-columnas {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
    gap: 24px;
    align-items: start;
  }
  @container (max-width: 720px) {
    .dos-columnas {
      grid-template-columns: 1fr;
    }
  }
  .chat {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 220px);
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
    max-width: 60ch;
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
    0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
    30% { opacity: 1; transform: translateY(-2px); }
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
  .panel-propuestas {
    border-left: 1px solid var(--v2-border, #e5e5e5);
    padding-left: 20px;
  }
  .propuestas-lista {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .propuesta-card {
    padding: 12px;
  }
  .propuesta-nombre {
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .propuesta-detalle code {
    font-size: 12px;
  }
  .propuesta-meta {
    margin-top: 6px;
    font-size: 12px;
  }
  .propuesta-acciones {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }
  .propuesta-resuelta {
    opacity: 0.75;
  }
</style>
