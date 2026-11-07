<script>
  /**
   * Pagina del asistente de IA. Habla con el motor de crm-agentico (repo
   * aparte) via el proxy server-side en /api/asistente -- este componente
   * nunca conoce la URL real del motor ni su auth, solo llama a su propio
   * origen (sin CORS, sin exponer nada al browser).
   *
   * Sin streaming y sin historial persistido entre recargas -- el motor si
   * mantiene su propia sesion en memoria del lado del proceso (ver
   * nucleo/canales/api.py).
   *
   * ES TAMBIEN LA PANTALLA DE ENTRENAMIENTO  --  02/11/2026
   * -------------------------------------------------------
   * Decision del usuario: probar y corregir un agente se hace aca y no en el
   * simulador de WhatsApp. El simulador esta hecho para probar ESE canal --
   * numero de telefono, ventana de 24 h, verificacion de identidad-- y para
   * ensayar un agente interno eso es ruido.
   *
   * Tres cosas, y ninguna cambia como funcionaba esto para quien solo
   * pregunta:
   *
   *   elegir agente   solo ADMIN, y lo decide el servidor (+page.server.js):
   *                   hablarle a uno que no tenes asignado saltea el modelo
   *                   de asignaciones.
   *   adjuntar foto   solo si la empresa lo habilito. La mira el motor y lo
   *                   que entra al turno es el analisis en texto, rotulado
   *                   como lectura automatica -- el mismo camino de WhatsApp.
   *   corregir        el boton de la burbuja, que escribe una habilidad para
   *                   el agente que contesto.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import CorregirAgente from '$lib/components/manual/CorregirAgente.svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let mensajes = $state([]);
  let entrada = $state('');
  let enviando = $state(false);

  /** A que agente se le habla. Vacio = los que tengas asignados, como antes. */
  let rolElegido = $state('');
  /** La foto adjunta, como data URL. Se manda una sola vez y se limpia. */
  let foto = $state('');
  let nombreFoto = $state('');
  /** @type {HTMLInputElement | undefined} */
  let inputFoto = $state();

  const etiquetaDe = (/** @type {any} */ a) => {
    const partes = [a.area, a.cargo].filter(Boolean);
    return partes.length ? `${a.nombre} — ${partes.join(' · ')}` : a.nombre;
  };

  /** Tope del analizador del motor (8 MB). Se avisa ACA para no subir 20 MB
      por la red interna y que los rechace del otro lado. */
  const MAX_BYTES = 8 * 1024 * 1024;

  function elegirFoto(/** @type {Event} */ evento) {
    const archivo = /** @type {HTMLInputElement} */ (evento.target)?.files?.[0];
    if (!archivo) return;
    if (archivo.size > MAX_BYTES) {
      mensajes.push({
        rol: 'error',
        texto: `Esa foto pesa ${Math.round(archivo.size / 1024)} KB y el máximo son ${
          MAX_BYTES / 1024
        } KB.`
      });
      if (inputFoto) inputFoto.value = '';
      return;
    }
    const lector = new FileReader();
    lector.onload = () => {
      foto = String(lector.result ?? '');
      nombreFoto = archivo.name;
    };
    lector.readAsDataURL(archivo);
  }

  function quitarFoto() {
    foto = '';
    nombreFoto = '';
    if (inputFoto) inputFoto.value = '';
  }

  async function enviar() {
    const texto = entrada.trim();
    //  Con foto se puede mandar sin texto: la foto ES la pregunta.
    if ((!texto && !foto) || enviando) return;

    const fotoDelTurno = foto;
    const nombreDelTurno = nombreFoto;
    mensajes.push({ rol: 'usuario', texto, foto: fotoDelTurno, nombreFoto: nombreDelTurno });
    entrada = '';
    quitarFoto();
    enviando = true;

    try {
      const resp = await fetch('/api/asistente', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mensaje: texto,
          ...(rolElegido ? { rol: rolElegido } : {}),
          ...(fotoDelTurno ? { imagen: fotoDelTurno } : {})
        })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        mensajes.push({ rol: 'error', texto: datos.error || 'El asistente no pudo responder.' });
        return;
      }
      //  El aviso de la foto va APARTE y antes de la respuesta: que no se
      //  haya podido mirar no es lo que contesto el agente, y mezclarlos
      //  haria creer que el agente la vio.
      if (datos.aviso_foto) {
        mensajes.push({ rol: 'error', texto: `La foto no se analizó: ${datos.aviso_foto}` });
      }
      mensajes.push({ rol: 'asistente', texto: datos.respuesta });
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
      <div class="chat-burbuja chat-{m.rol}">
        {#if m.foto}
          <img class="chat-foto" src={m.foto} alt={m.nombreFoto || 'Foto adjunta'} />
        {/if}
        {#if m.texto}<div>{m.texto}</div>{/if}
        {#if m.rol === 'asistente'}
          <!-- Enseñarle lo que le faltó. Se le escribe al agente que
               contestó: el elegido, o el que resolvió tu perfil. -->
          <CorregirAgente rol={rolElegido || null} textoDeLaRespuesta={m.texto} />
        {/if}
      </div>
    {/each}
    {#if enviando}
      <div class="chat-burbuja chat-asistente chat-pensando">Pensando…</div>
    {/if}
  </div>

  {#if data.puedeElegir && data.agentes.length > 0}
    <div class="fila-agente">
      <label for="agente">Le habla a</label>
      <select id="agente" class="v2-input sel-agente" bind:value={rolElegido}>
        <option value="">Los agentes que tenés asignados</option>
        {#each data.agentes as a (a.nombre)}
          <option value={a.nombre}>{etiquetaDe(a)}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if foto}
    <div class="foto-pendiente">
      <img src={foto} alt={nombreFoto} />
      <span>{nombreFoto}</span>
      <button class="v2-btn v2-btn-sm" type="button" onclick={quitarFoto}>Quitar</button>
    </div>
  {/if}

  <form class="chat-form" onsubmit={alEnviar}>
    {#if data.fotoHabilitada}
      <input
        bind:this={inputFoto}
        id="foto"
        class="foto-input"
        type="file"
        accept="image/jpeg,image/png"
        onchange={elegirFoto}
        disabled={enviando}
      />
      <label
        class="v2-btn"
        for="foto"
        title="Adjuntar una foto (JPEG o PNG). La mira el motor y su lectura entra a la conversación."
      >
        📎
      </label>
    {/if}
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
  .chat-pensando {
    opacity: 0.6;
    font-style: italic;
  }
  .chat-form {
    display: flex;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-line);
  }
  .chat-form input[type='text'] {
    flex: 1;
  }
  .fila-agente {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--v2-line);
  }
  .fila-agente label {
    font-size: 13px;
    color: var(--v2-slate);
    white-space: nowrap;
  }
  .sel-agente {
    max-width: 320px;
  }
  .chat-foto {
    display: block;
    max-width: 240px;
    border-radius: 8px;
    margin-bottom: 6px;
  }
  .foto-pendiente {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 12px;
    color: var(--v2-slate);
  }
  .foto-pendiente img {
    width: 40px;
    height: 40px;
    object-fit: cover;
    border-radius: 6px;
  }
  /* Oculto pero accesible: el <label> es el botón visible. `display:none`
     lo sacaría del foco por teclado. */
  .foto-input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
    pointer-events: none;
  }
</style>
