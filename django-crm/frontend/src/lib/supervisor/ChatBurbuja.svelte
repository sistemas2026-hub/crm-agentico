<script>
  /**
   * LA BURBUJA DEL SUPERVISOR NOC
   * ==============================
   *
   * Pertenece a esta pantalla y a ninguna otra: no es un chat generico ni
   * una pagina aparte. Lo que decide --que sesion, que es un duplicado, como
   * se lee el hilo-- vive en lib/supervisor/chat-sesion.js, probado aparte.
   *
   * LA CONVERSACION NO VIVE ACA
   * ---------------------------
   * No hay localStorage ni sessionStorage, y es a proposito: lo que el
   * navegador guarda se pierde en otra maquina, en otro navegador y en una
   * ventana privada, y ademas le miente al modelo -- la pantalla mostraria
   * un hilo que el motor no tiene. El hilo vive en PostgreSQL, del lado del
   * motor, y se recupera con GET al abrir.
   */
  import { onMount } from 'svelte';
  import { aBurbujas, esDuplicado } from './chat-sesion.js';

  let abierta = $state(false);
  //  EL PANEL GRANDE. En la burbuja chica una respuesta con evidencia se lee
  //  por una ventanita, y las del Supervisor traen varias observaciones.
  let expandida = $state(false);
  //  EL HILO AL QUE SE ENGANCHA CADA MENSAJE (08/10/2026).
  //
  //  Hasta hoy no se mandaba, y el backend ABRE UNA CONVERSACION NUEVA cuando
  //  no lo recibe ('operaciones/chat.py::abrir' siempre crea). O sea que cada
  //  pregunta empezaba de cero y el Supervisor no recordaba la anterior: en
  //  pantalla el hilo se veia continuo porque las burbujas se acumulan en el
  //  navegador, pero del otro lado no habia memoria. Se nota al pedir algo en
  //  dos pasos -- "quiero delegarte una tarea" / "si, esa"-- que es justo como
  //  se delega.
  /** @type {string | null} */
  let conversacionId = $state(null);
  /** @type {Array<{id: string, rol: 'usuario'|'supervisor', texto: string, cuando: string|null}>} */
  let burbujas = $state([]);
  let borrador = $state('');
  let enviando = $state(false);
  let cargando = $state(false);
  /** @type {string} */
  let error = $state('');
  let historialPedido = false;
  //  $state y no un 'let' pelado: en runes, 'bind:this' sobre una variable no
  //  reactiva no se asigna de forma fiable, y el sintoma seria que el hilo no
  //  baja solo -- un fallo mudo, de los que no dan error en ningun lado.
  /** @type {HTMLDivElement | undefined} */
  let hilo = $state();

  const hayHilo = $derived(burbujas.length > 0);

  /**
   * Empieza una conversacion nueva. Vacia lo que se ve Y suelta el hilo.
   *
   * SOLTAR EL HILO ES LA MITAD QUE IMPORTA. Si solo se vaciaran las burbujas,
   * el proximo mensaje seguiria enganchado a la conversacion anterior y el
   * Supervisor seguiria leyendo lo que la pantalla ya no muestra -- el
   * malentendido mas caro posible en un boton que se llama "limpiar".
   *
   * NO BORRA NADA DEL SERVIDOR. Lo conversado queda guardado y auditado; lo
   * que cambia es desde donde se sigue. Un boton de la pantalla no es el lugar
   * para destruir un registro.
   */
  function limpiar() {
    if (enviando) return;
    burbujas = [];
    conversacionId = null;
    borrador = '';
    error = '';
    //  Se marca como ya pedido para que no reaparezca el hilo viejo si la
    //  burbuja se cierra y se vuelve a abrir.
    historialPedido = true;
  }

  async function recuperarHistorial() {
    //  Una sola vez por carga de pagina. Abrir y cerrar la burbuja tres
    //  veces no son tres consultas: el hilo ya esta en memoria y lo que
    //  falte llega con el proximo envio.
    if (historialPedido) return;
    historialPedido = true;
    cargando = true;
    error = '';
    try {
      const resp = await fetch('/api/supervisor-noc/chat');
      const datos = await resp.json();
      if (!resp.ok) throw new Error(datos.error || 'No se pudo recuperar la conversacion.');
      burbujas = aBurbujas(datos.mensajes);
      conversacionId = datos.conversacion_id ?? null;
    } catch (/** @type {any} */ e) {
      //  Se permite reintentar: sin esto, un fallo de red al abrir dejaria
      //  la burbuja vacia para siempre, pareciendo que no hay conversacion.
      historialPedido = false;
      error = e?.message || 'No se pudo recuperar la conversacion.';
    } finally {
      cargando = false;
      alFinal();
    }
  }

  function alternar() {
    abierta = !abierta;
    if (abierta) recuperarHistorial();
  }

  function alFinal() {
    //  Despues de que Svelte pinte.
    queueMicrotask(() => {
      if (hilo) hilo.scrollTop = hilo.scrollHeight;
    });
  }

  async function enviar() {
    const texto = borrador.trim();
    if (!texto || enviando) return;
    if (esDuplicado(texto, burbujas, enviando)) return;

    //  El mensaje se pinta YA, y el borrador NO se borra hasta que el envio
    //  salio bien. Si falla, lo escrito sigue en la caja: perder un parrafo
    //  largo por un corte de red es la peor forma de fallar de un chat.
    const propio = { id: `local-${Date.now()}`, rol: /** @type {const} */ ('usuario'),
                     texto, cuando: new Date().toISOString() };
    burbujas = [...burbujas, propio];
    enviando = true;
    error = '';
    alFinal();

    try {
      const resp = await fetch('/api/supervisor-noc/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        //  Con el id, el Supervisor sigue el MISMO hilo y ve lo anterior.
        //  Sin el --cuando se acaba de limpiar-- el backend abre uno nuevo,
        //  que es exactamente lo que "limpiar" tiene que significar.
        body: JSON.stringify(conversacionId
          ? { mensaje: texto, conversacion_id: conversacionId }
          : { mensaje: texto })
      });
      const datos = await resp.json();
      if (!resp.ok) throw new Error(datos.error || 'El Supervisor no respondio.');

      //  El id del hilo con el que contesto: si se acaba de limpiar, este es
      //  el de la conversacion nueva que el backend abrio.
      if (datos.conversacion_id) conversacionId = datos.conversacion_id;

      const respuesta = (datos.respuesta ?? '').trim();
      if (respuesta) {
        burbujas = [...burbujas, { id: `r-${Date.now()}`, rol: 'supervisor',
                                   texto: respuesta, cuando: new Date().toISOString() }];
      } else if (datos.pausada) {
        error = 'Esta conversacion esta en pausa: la esta atendiendo una persona.';
      }
      borrador = '';
    } catch (/** @type {any} */ e) {
      //  Se saca la burbuja optimista: el turno NO quedo en el motor, y
      //  dejarla pintada haria creer que si. El texto vuelve al borrador.
      burbujas = burbujas.filter((b) => b.id !== propio.id);
      borrador = texto;
      error = e?.message || 'No se pudo contactar al Supervisor.';
    } finally {
      enviando = false;
      alFinal();
    }
  }

  /** @param {KeyboardEvent} ev */
  function alTeclear(ev) {
    //  Enter envia, Shift+Enter hace salto de linea. Es lo que espera
    //  cualquiera que haya usado un chat.
    if (ev.key === 'Enter' && !ev.shiftKey) {
      ev.preventDefault();
      enviar();
    }
  }

  onMount(() => {
    //  El hilo se trae al montar, no al abrir: asi el contador del boton
    //  puede decir que hay conversacion antes de que nadie la abra.
    recuperarHistorial();
  });
</script>

<div class="snoc-chat">
  {#if abierta}
    <section class="snoc-chat-panel" class:snoc-chat-grande={expandida}
             aria-label="Chat con el Supervisor NOC">
      <header class="snoc-chat-cabecera">
        <div>
          <p class="snoc-chat-titulo">Supervisor NOC</p>
          <p class="snoc-chat-sub">Pregunta sobre la operacion de hoy</p>
        </div>
        <div style="display:flex; gap:2px; flex-shrink:0; align-items:center;">
          <!-- Solo si hay algo que limpiar: un boton que no hace nada enseña
               a desconfiar de los botones. -->
          {#if hayHilo}
            <button type="button" class="snoc-chat-cerrar" onclick={limpiar}
                    disabled={enviando}
                    title="Empezar una conversación nueva. Lo conversado queda guardado."
                    aria-label="Empezar una conversación nueva">&#8635;</button>
          {/if}
          <button type="button" class="snoc-chat-cerrar"
                  onclick={() => (expandida = !expandida)}
                  title={expandida ? 'Achicar' : 'Expandir'}
                  aria-label={expandida ? 'Achicar el chat' : 'Expandir el chat'}
          >{expandida ? '⤡' : '⤢'}</button>
          <button type="button" class="snoc-chat-cerrar" onclick={alternar}
                  aria-label="Cerrar el chat">&times;</button>
        </div>
      </header>

      <div class="snoc-chat-hilo" bind:this={hilo}>
        {#if cargando}
          <p class="snoc-chat-aviso">Recuperando la conversacion...</p>
        {:else if !hayHilo}
          <p class="snoc-chat-aviso">
            Todavia no hay conversacion. Pregunta lo que necesites saber de la
            operacion: que revisar primero, que paso con un ticket, que esta
            en riesgo hoy.
          </p>
        {/if}

        {#each burbujas as b (b.id)}
          <div class="snoc-chat-msg snoc-chat-{b.rol}">
            <p>{b.texto}</p>
          </div>
        {/each}

        {#if enviando}
          <div class="snoc-chat-msg snoc-chat-supervisor snoc-chat-pensando">
            <p>Revisando la operacion...</p>
          </div>
        {/if}
      </div>

      {#if error}
        <p class="snoc-chat-error" role="alert">{error}</p>
      {/if}

      <div class="snoc-chat-caja">
        <textarea
          bind:value={borrador}
          onkeydown={alTeclear}
          rows="2"
          placeholder="Escribe tu pregunta..."
          aria-label="Mensaje para el Supervisor NOC"
        ></textarea>
        <button type="button" onclick={enviar} disabled={enviando || !borrador.trim()}>
          {enviando ? 'Enviando' : 'Enviar'}
        </button>
      </div>
    </section>
  {/if}

  <button type="button" class="snoc-chat-boton" onclick={alternar}
          aria-expanded={abierta}
          aria-label={abierta ? 'Cerrar el chat del Supervisor' : 'Abrir el chat del Supervisor'}>
    {#if abierta}&times;{:else}Preguntar{/if}
    {#if !abierta && hayHilo}<span class="snoc-chat-punto" aria-hidden="true"></span>{/if}
  </button>
</div>

<style>
  .snoc-chat {
    position: fixed;
    right: 1.5rem;
    bottom: 1.5rem;
    z-index: 60;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.75rem;
  }

  .snoc-chat-boton {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.85rem 1.4rem;
    border: none;
    border-radius: var(--snoc-r-full, 999px);
    background: var(--snoc-primary, #2b5cab);
    color: var(--snoc-on-primary, #fff);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 6px 20px rgb(0 0 0 / 22%);
  }
  .snoc-chat-boton:hover { filter: brightness(1.08); }
  .snoc-chat-boton:focus-visible { outline: 3px solid var(--snoc-primary-fixed-dim, #9ec1ff); outline-offset: 2px; }

  .snoc-chat-punto {
    width: 0.5rem; height: 0.5rem; border-radius: 50%;
    background: var(--snoc-primary-fixed, #cfe0ff);
  }

  .snoc-chat-panel {
    width: min(26rem, calc(100vw - 2rem));
    height: min(32rem, calc(100vh - 8rem));
    display: flex;
    flex-direction: column;
    background: var(--snoc-surface, #fff);
    color: var(--snoc-on-surface, #1a1c1e);
    border: 1px solid var(--snoc-outline-variant, #c3c7cf);
    border-radius: var(--snoc-lg, 16px);
    box-shadow: 0 16px 48px rgb(0 0 0 / 26%);
    overflow: hidden;
  }
  /*  EXPANDIDA: casi toda la ventana, con margen para no pegarse a los bordes.
      Sigue teniendo tope --ocupa mucho, no todo-- asi que se ve que es un
      panel sobre el tablero y no otra pantalla.  */
  .snoc-chat-panel.snoc-chat-grande {
    width: min(68rem, calc(100vw - 2.5rem));
    height: calc(100vh - 7rem);
  }

  .snoc-chat-cabecera {
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; padding: 0.9rem 1.1rem;
    background: var(--snoc-primary-container, #d8e2ff);
    color: var(--snoc-on-secondary-container, #0f1b2d);
    border-bottom: 1px solid var(--snoc-outline-variant, #c3c7cf);
  }
  .snoc-chat-titulo { margin: 0; font-weight: 700; }
  .snoc-chat-sub { margin: 0.15rem 0 0; font-size: 0.8rem; opacity: 0.8; }
  .snoc-chat-cerrar {
    border: none; background: transparent; cursor: pointer;
    font-size: 1.5rem; line-height: 1; color: inherit; padding: 0 0.25rem;
  }

  .snoc-chat-hilo {
    flex: 1; overflow-y: auto; padding: 1rem;
    display: flex; flex-direction: column; gap: 0.6rem;
  }

  .snoc-chat-aviso {
    margin: 0; font-size: 0.85rem; line-height: 1.5;
    color: var(--snoc-on-surface-variant, #43474e);
  }

  .snoc-chat-msg {
    max-width: 85%; padding: 0.6rem 0.85rem;
    border-radius: var(--snoc-md, 12px);
    font-size: 0.9rem; line-height: 1.5;
  }
  .snoc-chat-msg p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }

  .snoc-chat-usuario {
    align-self: flex-end;
    background: var(--snoc-primary, #2b5cab);
    color: var(--snoc-on-primary, #fff);
    border-bottom-right-radius: 4px;
  }
  .snoc-chat-supervisor {
    align-self: flex-start;
    background: var(--snoc-primary-container, #d8e2ff);
    color: var(--snoc-on-secondary-container, #0f1b2d);
    border-bottom-left-radius: 4px;
  }
  .snoc-chat-pensando { opacity: 0.7; font-style: italic; }

  .snoc-chat-error {
    margin: 0; padding: 0.6rem 1.1rem; font-size: 0.85rem;
    background: var(--snoc-error-container, #ffdad6);
    color: var(--snoc-on-error-container, #410002);
  }

  .snoc-chat-caja {
    display: flex; gap: 0.5rem; padding: 0.75rem;
    border-top: 1px solid var(--snoc-outline-variant, #c3c7cf);
  }
  .snoc-chat-caja textarea {
    flex: 1; resize: none; font: inherit; font-size: 0.9rem;
    padding: 0.5rem 0.65rem;
    border: 1px solid var(--snoc-outline, #73777f);
    border-radius: var(--snoc-r, 8px);
    background: var(--snoc-surface, #fff);
    color: inherit;
  }
  .snoc-chat-caja button {
    align-self: flex-end;
    padding: 0.55rem 1rem; border: none;
    border-radius: var(--snoc-r, 8px);
    background: var(--snoc-primary, #2b5cab);
    color: var(--snoc-on-primary, #fff);
    font: inherit; font-weight: 600; cursor: pointer;
  }
  .snoc-chat-caja button:disabled { opacity: 0.5; cursor: default; }

  @media (prefers-reduced-motion: reduce) {
    .snoc-chat-boton { transition: none; }
  }
</style>
