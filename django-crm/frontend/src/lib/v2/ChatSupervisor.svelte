<script>
  /**
   * La burbuja de chat del Supervisor NOC IA.
   *
   * POR QUE ES UN COMPONENTE APARTE
   * '+page.svelte' del Supervisor NOC tiene 1.913 líneas y es de los archivos
   * que CLAUDE.md §2 marca como superficie de conflicto alta. La burbuja entra
   * con un import y una etiqueta; toda su lógica vive acá.
   *
   * LO QUE ESTE COMPONENTE NO SABE
   * No sabe qué es una situación, no decide qué herramientas hay y no arma
   * contexto. Manda un texto y muestra lo que vuelve. Si decidiera algo, habría
   * dos lugares donde buscar por qué el Supervisor contestó lo que contestó —
   * y uno de los dos estaría en el navegador, donde no se puede garantizar nada.
   *
   * @typedef {{ rol: 'humano' | 'supervisor' | 'error', texto: string,
   *             herramientas?: string[] }} Mensaje
   */

  /** @type {{ situacion?: string | null, caso?: string | null }} */
  let { situacion = null, caso = null } = $props();

  let abierto = $state(false);
  //  El chat a pantalla casi completa. Lo pidió el usuario y el motivo es
  //  práctico: en la burbuja chica, una respuesta de varias líneas obliga a
  //  leer por una ventanita, y las respuestas del Supervisor traen evidencia.
  let expandido = $state(false);
  /** @type {Mensaje[]} */
  let mensajes = $state([]);
  let texto = $state('');
  let enviando = $state(false);
  /** @type {string | null} */
  let conversacionId = $state(null);
  /** @type {string | null} */
  let contextoActual = $state(null);
  /** @type {HTMLDivElement | undefined} */
  let hilo = $state();

  //  El contexto con el que se abre: si la burbuja se monta desde una situación,
  //  el primer mensaje ya la lleva. Es lo que hace que "¿qué evidencia tenés?"
  //  se entienda sin repetir el código.
  const contextoInicial = $derived(situacion || caso || null);

  const SUGERENCIAS = [
    '¿Qué está pasando ahora?',
    '¿Qué situaciones siguen abiertas?',
    '¿Cuál es la más crítica?',
    '¿Qué información te falta?'
  ];

  async function enviar() {
    const pregunta = texto.trim();
    if (!pregunta || enviando) return;

    mensajes = [...mensajes, { rol: 'humano', texto: pregunta }];
    texto = '';
    enviando = true;
    //  Se baja al final DESPUÉS de pintar, no antes: si no, se baja a la altura
    //  que el hilo tenía sin el mensaje nuevo.
    setTimeout(alFinal, 0);

    try {
      const r = await fetch('/api/supervisor-noc/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mensaje: pregunta,
          conversacion_id: conversacionId,
          //  El contexto solo viaja en el PRIMER mensaje del hilo: después vive
          //  en la conversación del backend. Reenviarlo cada vez volvería a
          //  fijarlo y pisaría un cambio de tema hecho desde el chat.
          situacion: conversacionId ? undefined : situacion || undefined,
          caso: conversacionId ? undefined : caso || undefined
        })
      });
      const d = await r.json();

      if (!r.ok || d?.error) {
        mensajes = [
          ...mensajes,
          { rol: 'error', texto: d?.error ?? 'No se pudo enviar el mensaje.' }
        ];
      } else {
        conversacionId = d.conversacion_id ?? conversacionId;
        contextoActual = d?.contexto?.situacion ?? d?.contexto?.caso ?? null;
        mensajes = [
          ...mensajes,
          {
            rol: d.es_error ? 'error' : 'supervisor',
            texto: d.respuesta || '(sin respuesta)',
            herramientas: d.herramientas ?? []
          }
        ];
      }
    } catch {
      //  Un fallo de red se MUESTRA. Un hilo que se queda mudo deja a la persona
      //  sin saber si preguntar de nuevo.
      mensajes = [
        ...mensajes,
        { rol: 'error', texto: 'No hubo respuesta. Revisá la conexión y probá de nuevo.' }
      ];
    } finally {
      enviando = false;
      setTimeout(alFinal, 0);
    }
  }

  function alFinal() {
    if (hilo) hilo.scrollTop = hilo.scrollHeight;
  }

  /**
   * Vacía la conversación de la pantalla y empieza una nueva.
   *
   * SUELTA 'conversacionId' A PROPÓSITO. Si lo conservara, el backend seguiría
   * enganchando los mensajes nuevos al hilo viejo y "limpiar" sería solo dejar
   * de ver lo que el Supervisor sí sigue leyendo — el malentendido más caro
   * posible en un botón que se llama así.
   *
   * NO BORRA NADA DEL SERVIDOR. Lo conversado queda guardado y auditado; lo que
   * cambia es desde dónde se sigue. Un botón de la pantalla no es el lugar para
   * destruir un registro.
   */
  function limpiar() {
    if (enviando) return;
    mensajes = [];
    conversacionId = null;
    contextoActual = null;
    texto = '';
  }

  /** @param {KeyboardEvent} e */
  function alTeclado(e) {
    //  Enter envía; Shift+Enter hace salto de línea. Es lo que espera cualquiera
    //  que haya usado un chat.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  }
</script>

{#if !abierto}
  <button
    class="snoc-chat-burbuja"
    type="button"
    onclick={() => (abierto = true)}
    aria-label="Abrir el chat del Supervisor NOC"
    title="Preguntarle al Supervisor NOC"
  >
    <span aria-hidden="true">💬</span>
    <span class="snoc-chat-burbuja-txt">Supervisor</span>
  </button>
{:else}
  <section
    class="snoc-chat-panel"
    class:snoc-chat-expandido={expandido}
    aria-label="Chat del Supervisor NOC IA"
  >
    <header class="snoc-chat-cabecera">
      <div style="min-width:0;">
        <strong>Supervisor NOC IA</strong>
        {#if contextoActual || contextoInicial}
          <div class="snoc-mono-sm">Contexto: {contextoActual ?? contextoInicial}</div>
        {:else}
          <div class="snoc-mono-sm">Sin situación como contexto</div>
        {/if}
      </div>
      <div style="display:flex; gap:4px; flex-shrink:0;">
        <!-- Solo aparece si hay algo que limpiar: un botón que no hace nada
             enseña a desconfiar de los botones. -->
        {#if mensajes.length}
          <button
            class="snoc-btn"
            type="button"
            onclick={limpiar}
            disabled={enviando}
            aria-label="Empezar una conversación nueva"
            title="Empezar de cero. Lo conversado queda guardado; se sigue desde una conversación nueva."
          >
            ⟲
          </button>
        {/if}
        <button
          class="snoc-btn"
          type="button"
          onclick={() => (expandido = !expandido)}
          aria-label={expandido ? 'Achicar el chat' : 'Expandir el chat'}
          title={expandido ? 'Achicar' : 'Expandir'}
        >
          {expandido ? '⤡' : '⤢'}
        </button>
        <button
          class="snoc-btn"
          type="button"
          onclick={() => (abierto = false)}
          aria-label="Cerrar el chat"
        >
          ✕
        </button>
      </div>
    </header>

    <div class="snoc-chat-hilo" bind:this={hilo}>
      {#if mensajes.length === 0}
        <p class="snoc-mono-sm">
          Observo la operación de forma continua. Puedo contarte qué está pasando, por qué una
          situación me parece grave y qué información me falta. No ejecuto acciones.
        </p>
        <div class="snoc-chat-sugerencias">
          {#each SUGERENCIAS as s (s)}
            <button
              class="snoc-btn"
              type="button"
              onclick={() => {
                texto = s;
                enviar();
              }}
            >
              {s}
            </button>
          {/each}
        </div>
      {/if}

      {#each mensajes as m, i (i)}
        <div class="snoc-chat-msg snoc-chat-{m.rol}">
          <div class="snoc-chat-txt">{m.texto}</div>
          {#if m.herramientas && m.herramientas.length}
            <!-- De dónde salió. Una respuesta sin poder ver qué consultó es una
                 afirmación sin respaldo. -->
            <div class="snoc-mono-sm snoc-chat-fuentes">
              consultó: {m.herramientas.join(', ')}
            </div>
          {/if}
        </div>
      {/each}

      {#if enviando}
        <div class="snoc-chat-msg snoc-chat-supervisor">
          <div class="snoc-mono-sm">Consultando la operación…</div>
        </div>
      {/if}
    </div>

    <footer class="snoc-chat-pie">
      <textarea
        id="snoc-chat-texto"
        bind:value={texto}
        onkeydown={alTeclado}
        placeholder="Preguntale al Supervisor…"
        rows="2"
        maxlength="4000"
        disabled={enviando}
        aria-label="Mensaje para el Supervisor"
      ></textarea>
      <button
        class="snoc-btn snoc-btn-primario"
        type="button"
        onclick={enviar}
        disabled={enviando || !texto.trim()}
      >
        {enviando ? '…' : 'Enviar'}
      </button>
    </footer>
  </section>
{/if}

<style>
  /*  Los colores salen de los tokens de 'supervisor-noc.css' -- no hay ni un
      literal. Asi la burbuja sigue al tablero cuando cambie de tema, y en
      particular funciona en claro y en oscuro sin tocarla.  */
  .snoc-chat-burbuja {
    position: fixed;
    right: 1.25rem;
    bottom: 1.25rem;
    z-index: 40;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 1rem;
    border: 1px solid var(--snoc-outline);
    border-radius: 999px;
    background: var(--snoc-primary);
    color: var(--snoc-on-primary);
    box-shadow: var(--snoc-sombra);
    cursor: pointer;
    font: inherit;
  }
  .snoc-chat-burbuja:hover {
    background: var(--snoc-primary-container);
  }
  .snoc-chat-burbuja-txt {
    font-weight: 600;
  }

  .snoc-chat-panel {
    position: fixed;
    right: 1.25rem;
    bottom: 1.25rem;
    z-index: 40;
    display: flex;
    flex-direction: column;
    width: min(420px, calc(100vw - 2rem));
    /*  Alto acotado: un panel que crece sin tope tapa el tablero que la persona
        esta mirando, que es justo lo que no debe pasar.  */
    height: min(560px, calc(100vh - 3rem));
    border: 1px solid var(--snoc-outline);
    border-radius: 12px;
    background: var(--snoc-surface-container);
    color: var(--snoc-on-surface);
    box-shadow: var(--snoc-sombra);
    overflow: hidden;
  }
  /*  EXPANDIDO: casi toda la ventana, con margen para no pegarse a los bordes.
      En la burbuja chica una respuesta con evidencia se lee por una ventanita,
      y las del Supervisor traen varias observaciones. Sigue siendo 'fixed' y
      sigue teniendo tope: ocupa mucho, no todo, asi que el tablero de atras no
      desaparece del todo y se ve que es un panel y no otra pantalla.  */
  .snoc-chat-panel.snoc-chat-expandido {
    width: min(1100px, calc(100vw - 2.5rem));
    height: calc(100vh - 2.5rem);
    right: 1.25rem;
    bottom: 1.25rem;
  }
  .snoc-chat-cabecera {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.75rem;
    border-bottom: 1px solid var(--snoc-outline);
    background: var(--snoc-surface-container-high);
  }
  .snoc-chat-hilo {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .snoc-chat-sugerencias {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .snoc-chat-msg {
    padding: 0.55rem 0.7rem;
    border-radius: 10px;
    max-width: 92%;
  }
  .snoc-chat-humano {
    align-self: flex-end;
    background: var(--snoc-primary);
    color: var(--snoc-on-primary);
  }
  .snoc-chat-supervisor {
    align-self: flex-start;
    background: var(--snoc-surface-variant);
  }
  .snoc-chat-error {
    align-self: flex-start;
    background: var(--snoc-error);
    color: var(--snoc-on-error);
  }
  .snoc-chat-txt {
    /*  El Supervisor contesta separando hecho, hipotesis y recomendacion en
        lineas. 'pre-wrap' conserva esos saltos: sin el, todo el razonamiento
        queda en un parrafo y se pierde justamente la separacion.  */
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .snoc-chat-fuentes {
    margin-top: 0.3rem;
    opacity: 0.8;
  }
  .snoc-chat-pie {
    display: flex;
    gap: 0.5rem;
    align-items: flex-end;
    padding: 0.6rem;
    border-top: 1px solid var(--snoc-outline);
    background: var(--snoc-surface-container-high);
  }
  .snoc-chat-pie textarea {
    flex: 1;
    resize: none;
    font: inherit;
    padding: 0.45rem 0.55rem;
    border: 1px solid var(--snoc-outline);
    border-radius: 8px;
    background: var(--snoc-surface-container);
    color: var(--snoc-on-surface);
  }

  @media (max-width: 480px) {
    /*  En un telefono el panel ocupa el ancho util con su medianil, en vez de
        asomar por un costado.  */
    .snoc-chat-panel {
      right: 0.5rem;
      left: 0.5rem;
      width: auto;
      height: min(70vh, calc(100vh - 2rem));
    }
  }
</style>
