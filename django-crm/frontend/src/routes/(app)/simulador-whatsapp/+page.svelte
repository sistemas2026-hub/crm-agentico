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
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import TrazaDelTurno from '$lib/components/manual/TrazaDelTurno.svelte';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import { esperarTraza } from '$lib/components/manual/traza.js';

  /** @type {{ data: any }} */
  let { data } = $props();
  let casos = $state(data.casos ?? []);

  /**
   * LA TRAZA DE CADA TURNO (12/11/2026), por id del mensaje del agente.
   *
   * El simulador pasa por atender_turno() --lo que cli/evaluar.py no hace--
   * pero mostraba solo la respuesta: qué herramientas llamó el agente, a qué
   * área derivó y qué falló había que ir a buscarlo a la base. Va en un mapa
   * aparte y no dentro de cada burbuja porque el hilo se REEMPLAZA cada pocos
   * segundos con lo que hay en la conversación (traerNuevos): pegada a la
   * burbuja, la traza desaparecería en el siguiente sondeo.
   *
   * @type {Record<string, any>}
   */
  let trazas = $state({});

  let telefono = $state('3001234567');
  let mensajes = $state([]);
  let entrada = $state('');
  let enviando = $state(false);
  let verificado = $state(false);
  let cerrada = $state(false);
  /**
   * Que area quedo atendiendo, tal como la devuelve el motor ('rol_activo').
   *
   * La cabecera dice "cliente_final" porque ese es el rol de ENTRADA, pero una
   * conversacion cambia de area a mitad de turno y desde afuera eso no se veia
   * sin abrir la base. Los tres bugs de derivacion del 08 y 09/09/2026 se
   * notaban aca de inmediato: saber que quien escribio "dejame pasarte con
   * ventas" ERA ventas convierte un texto raro en un bug evidente.
   */
  let rolActivo = $state('');
  let rolActivoNombre = $state('');

  /** La conversacion en curso, para poder preguntar si llego algo nuevo. */
  let conversacionActual = $state('');
  /** Un error de red que no vive en la conversacion: se muestra aparte. */
  let error = $state('');

  function reiniciar() {
    trazas = {};
    mensajes = [];
    verificado = false;
    cerrada = false;
    rolActivo = '';
    rolActivoNombre = '';
    conversacionActual = '';
    error = '';
  }

  /**
   * Trae lo que haya llegado a la conversacion desde afuera de esta pantalla:
   * la respuesta que un colaborador escribio desde el ticket.
   *
   * En WhatsApp de verdad ese mensaje viaja por el canal y aparece solo en el
   * celular del cliente. Aca el "celular" es esta pantalla, y nadie le avisa
   * -- habia que recargar, y probando una conversacion a dos manos eso hace
   * perder el hilo justo cuando se quiere mirar.
   *
   * Se preguntan los mensajes enteros y se dibujan los que no se vieron: no
   * hay orden de llegada que mantener ni estado que sincronizar, y una
   * consulta que falla se resuelve sola en la siguiente.
   */
  async function traerNuevos() {
    if (!conversacionActual || enviando) return;
    try {
      const resp = await fetch(
        `/api/simulador-whatsapp?conversacion=${encodeURIComponent(conversacionActual)}`
      );
      if (!resp.ok) return;
      const datos = await resp.json();
      const hilo = datos.mensajes ?? [];
      if (!hilo.length) return;
      // Se REEMPLAZA el hilo con lo que hay en la conversacion, en vez de ir
      // agregando lo que falta. La conversacion es la que manda: llevar una
      // copia aparte y una lista de "ya visto" obliga a mantener las dos en
      // fase, y en cuanto un mensaje entra por otro lado --el colaborador
      // desde el ticket-- dejan de coincidir. Asi no hay nada que sincronizar.
      mensajes = hilo.map((/** @type {any} */ m) => ({
        rol: m.rol === 'user' ? 'usuario' : 'asistente',
        texto: m.texto,
        conversacionId: conversacionActual,
        mensajeId: m.id,
        casoMarcado: m.caso_marcado
      }));
      if (datos.cerrada) cerrada = true;
      // Solo si vino y solo si no lo sabemos ya: el sondeo corre cada pocos
      // segundos y una respuesta sin el dato no puede borrar lo que la
      // ultima respuesta del motor si dijo.
      if (datos.rol_activo) {
        rolActivo = datos.rol_activo;
        if (!rolActivoNombre) rolActivoNombre = datos.rol_activo;
      }
    } catch {
      // Silencio a proposito: corre cada pocos segundos.
    }
  }

  // Cada 4 segundos mientras haya una conversacion abierta. Es una pantalla
  // de prueba que se mira mientras se usa, asi que no hace falta nada mas
  // fino -- y lo mas fino (una conexion abierta) es infraestructura que este
  // caso no justifica.
  $effect(() => {
    if (!conversacionActual) return;
    const reloj = setInterval(traerNuevos, 4000);
    return () => clearInterval(reloj);
  });

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando || !telefono.trim()) return;

    mensajes.push({ rol: 'usuario', texto });
    error = '';
    entrada = '';
    enviando = true;
    // Si la conversacion anterior se habia cerrado, escribir de nuevo abre
    // una nueva de forma transparente (mismo numero) -- ver cerrar_conversacion.
    cerrada = false;

    try {
      const resp = await fetch('/api/simulador-whatsapp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telefono: telefono.trim(), mensaje: texto })
      });
      const datos = await resp.json();
      if (resp.ok) {
        conversacionActual = datos.conversacion_id || conversacionActual;
        // Una respuesta vacia significa que hay una persona atendiendo y el
        // asistente se callo a proposito (ver api.py). No se dibuja nada:
        // una burbuja en blanco parece un error y no lo es.
        if ((datos.respuesta ?? '').trim()) {
          mensajes.push({
            rol: 'asistente',
            texto: datos.respuesta,
            conversacionId: datos.conversacion_id,
            mensajeId: datos.mensaje_id,
            casoMarcado: null
          });
        }
        if (datos.mensaje_id && datos.conversacion_id && datos.mensaje_usuario_id) {
          // Sin await: la traza llega un instante después de la respuesta y
          // la conversación no tiene por qué esperarla.
          cargarTraza(datos.mensaje_id, datos.conversacion_id, datos.mensaje_usuario_id);
        }
        verificado = !!datos.verificado;
        cerrada = !!datos.cerrada;
        // Solo si vino: los caminos de escalada y de conversacion pausada
        // devuelven antes y no lo traen. Pisarlo con '' ahi borraria de la
        // pantalla el area que si estaba atendiendo.
        if (datos.rol_activo) {
          rolActivo = datos.rol_activo;
          rolActivoNombre = datos.rol_activo_nombre || datos.rol_activo;
        }
      } else {
        error = datos.error || 'El asistente no pudo responder.';
      }
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo contactar al asistente.';
    } finally {
      enviando = false;
    }
  }

  /**
   * @param {string} mensajeId  la respuesta del agente bajo la que se dibuja
   * @param {string} conversacion
   * @param {string} desde      el mensaje del cliente que abrió el turno
   */
  async function cargarTraza(mensajeId, conversacion, desde) {
    trazas = { ...trazas, [mensajeId]: 'cargando' };
    const traza = await esperarTraza((url) => fetch(url), conversacion, desde);
    trazas = { ...trazas, [mensajeId]: traza };
  }

  // --- Reproducir una conversación real ------------------------------------
  //
  // /simulador-whatsapp?reproducir=<id de conversación> (12/11/2026). Trae lo
  // que escribió el cliente (solo texto, redactado) y lo reenvía, uno por uno,
  // a una conversación NUEVA. El identificador no es un teléfono a propósito:
  // uno inventado podría ser el de un cliente real, y el motor lo buscaría.
  /** @type {string[]} */
  let pendientes = $state([]);
  let reproduciendo = $state(false);
  let origenReproduccion = $state('');

  onMount(() => {
    const id = page.url.searchParams.get('reproducir');
    if (id) prepararReproduccion(id);
  });

  /** @param {string} id */
  async function prepararReproduccion(id) {
    error = '';
    try {
      const resp = await fetch(`/api/simulador-whatsapp/reproduccion?conversacion=${encodeURIComponent(id)}`);
      const datos = await resp.json();
      if (!resp.ok) {
        error = datos.error || 'No se pudo leer la conversación a reproducir.';
        return;
      }
      if (!(datos.mensajes ?? []).length) {
        error = 'Esa conversación no tiene mensajes de texto del cliente para reproducir.';
        return;
      }
      reiniciar();
      telefono = `reproduccion-${crypto.randomUUID().slice(0, 8)}`;
      pendientes = datos.mensajes;
      origenReproduccion = id;
    } catch {
      error = 'No se pudo contactar al asistente.';
    }
  }

  async function enviarSiguiente() {
    const [siguiente, ...resto] = pendientes;
    if (siguiente === undefined || enviando) return;
    pendientes = resto;
    entrada = siguiente;
    await enviar();
  }

  async function enviarTodos() {
    reproduciendo = true;
    try {
      while (pendientes.length && reproduciendo && !error) await enviarSiguiente();
    } finally {
      reproduciendo = false;
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
    Debajo de cada respuesta, lo que hizo el agente: herramientas, área a la que derivó y errores.
  {/snippet}
</PageHeader>

{#if origenReproduccion}
  <div class="reproduccion" role="status">
    <div>
      <b>Reproduciendo una conversación real</b>
      — lo que escribió el cliente, redactado, en una conversación simulada nueva.
      <a href="/conversaciones/{origenReproduccion}">Ver la original</a>
    </div>
    <div class="reproduccion-acciones">
      <span class="v2-sub">{pendientes.length} mensaje(s) por enviar</span>
      <button class="v2-btn v2-btn-sm" type="button" onclick={enviarSiguiente}
        disabled={enviando || pendientes.length === 0}>Enviar el siguiente</button>
      {#if reproduciendo}
        <button class="v2-btn v2-btn-sm" type="button" onclick={() => (reproduciendo = false)}>Detener</button>
      {:else}
        <button class="v2-btn v2-btn-primary v2-btn-sm" type="button" onclick={enviarTodos}
          disabled={enviando || pendientes.length === 0}>Enviar todos</button>
      {/if}
    </div>
  </div>
{/if}

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
      {#if rolActivo}
        <span class="agente-activo" title="Area que atiende ahora. El proximo mensaje del cliente entra directo aca ('rol_efectivo').">
          Atiende: <strong>{rolActivoNombre}</strong>
          {#if rolActivo !== rolActivoNombre}<code>{rolActivo}</code>{/if}
        </span>
      {/if}
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
        <div class="chat-burbuja chat-{m.rol}">
          <div>{m.texto}</div>
          {#if m.rol === 'asistente' && m.mensajeId && trazas[m.mensajeId]}
            <TrazaDelTurno traza={trazas[m.mensajeId]} />
          {/if}
          {#if m.rol === 'asistente' && casos.length > 0}
            <MarcarEjemplo
              conversacionId={m.conversacionId}
              mensajeId={m.mensajeId}
              casoInicial={m.casoMarcado}
              {casos}
            />
          {/if}
        </div>
      {/each}
      {#if enviando}
        <div class="chat-burbuja chat-asistente chat-escribiendo" aria-label="Escribiendo…">
          <span class="punto"></span><span class="punto"></span><span class="punto"></span>
        </div>
      {/if}
      {#if cerrada && !enviando}
        <div class="chat-cerrada">Conversación finalizada — si el cliente vuelve a escribir, se abre una nueva.</div>
      {/if}
      <!-- Fuera del hilo a propósito: el hilo se refresca con lo que hay en la
           conversación, y un error de red no está ahí. Dentro, desaparecería
           solo a los pocos segundos. -->
      {#if error}
        <div class="chat-burbuja chat-error">{error}</div>
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
    border-bottom: 1px solid var(--v2-line);
  }
  .fila-telefono label {
    font-size: 13px;
    color: var(--v2-slate);
    white-space: nowrap;
  }
  .fila-telefono input {
    max-width: 180px;
  }
  .agente-activo {
    font-size: 0.85rem;
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
    border: 1px solid var(--v2-line-strong);
    white-space: nowrap;
  }
  .agente-activo code {
    font-size: 0.78rem;
    opacity: 0.7;
    margin-left: 0.25rem;
  }

  .estado-verificacion {
    margin-left: auto;
    font-size: 13px;
    color: var(--v2-rust);
  }
  .estado-verificacion.ok {
    color: var(--v2-moss);
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
    color: var(--v2-slate);
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
    background: var(--v2-ember);
    color: var(--v2-on-ember);
  }
  .chat-asistente {
    align-self: flex-start;
    background: var(--v2-line-soft);
  }
  .chat-error {
    align-self: flex-start;
    background: color-mix(in srgb, var(--v2-rust) 10%, var(--v2-card));
    color: var(--v2-rust);
  }
  .chat-cerrada {
    align-self: center;
    font-size: 12px;
    color: var(--v2-slate);
    padding: 4px 10px;
    border-top: 1px dashed var(--v2-line);
    border-bottom: 1px dashed var(--v2-line);
    margin: 4px 0;
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
  .reproduccion {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px 16px;
    max-width: 720px;
    margin-bottom: 12px;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    border: 1px solid var(--v2-line-strong);
    background: var(--v2-paper);
  }
  .reproduccion-acciones {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .chat-form {
    display: flex;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-line);
  }
  .chat-form input {
    flex: 1;
  }
</style>
