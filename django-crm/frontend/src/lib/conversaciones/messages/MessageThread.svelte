<script>
  /**
   * El hilo de la conversación: los mensajes agrupados por día, sus adjuntos y
   * su estado de entrega.
   *
   * POR QUÉ EL SCROLL VIVE ACÁ
   * --------------------------
   * `hiloEl` es el elemento que scrollea, así que el efecto que lo sigue tiene
   * que estar donde está el elemento. Pero quien ENVÍA es la página: al mandar
   * un mensaje hay que bajar al final aunque el que mira estuviera leyendo
   * arriba, porque ahí la intención es evidente. Por eso este componente
   * exporta `alFinal()` y el padre lo llama con `bind:this` — es la misma
   * llamada que antes era local, no una señal nueva.
   */
  import { TriangleAlert, RotateCcw, Paperclip, Lock } from '@lucide/svelte';
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import { autorDe, burbujaClase, extension, hora, ENTREGA_TEXTO } from '../formato.js';

  let {
    /** El hilo ya agrupado por día: {tipo:'dia'|'msg'} */
    hilo,
    /** Cuántos mensajes hay. Dispara el autoscroll; se pasa aparte de `hilo`
        porque `hilo` incluye los separadores de día. */
    cantidadMensajes,
    conversacionId,
    /** El nombre del cliente, para rotular SU lado del hilo. La referencia
        maestra pone el nombre sobre la burbuja que entra; el hilo no lo tiene
        por mensaje --`autor_nombre` es de quien ATIENDE-- asi que llega de la
        conversacion. Vacio cae en 'Cliente', que sigue siendo cierto. */
    nombreCliente = '',
    casos = [],
    /** Se está enviando y la IA responde: muestra los tres puntitos. */
    escribiendo = false,
    reintentando = null,
    onReintentar
  } = $props();

  /** Si debajo de la burbuja hay algo que decir: el estado de entrega, el
      aviso de que no llego, o el control de marcar como ejemplo. Se pregunta
      antes de dibujar el pie para no dejar un renglon vacio con margen --que
      es lo que separa un hilo prolijo de uno con huecos. */
  const conPie = (/** @type {any} */ m) =>
    !!(m.sinEntregar ||
       m.estado_entrega === 'fallido' ||
       (m.rol === 'assistant' && (m.estado_entrega || casos.length > 0)));

  /** @type {HTMLElement | undefined} */
  let hiloEl = $state();

  export const alFinal = (suave = false) => {
    if (!hiloEl) return;
    hiloEl.scrollTo({ top: hiloEl.scrollHeight, behavior: suave ? 'smooth' : 'auto' });
  };

  /** Bajar al final SIN preguntar si estaba mirando el final.
      La usa el padre cuando uno mismo envía: da por vistos los `n` mensajes
      —con lo que el efecto de abajo no vuelve a decidir— y baja igual. Antes
      esto era `ultimoVisto = mensajes.length` escrito desde la página, cuando
      las dos cosas vivían en el mismo archivo. */
  export const forzarAlFinal = (/** @type {number} */ n) => {
    ultimoVisto = n;
    requestAnimationFrame(() => alFinal(true));
  };

  /** Si quien mira ya estaba abajo. Con un margen de 120 px porque nadie deja
      el scroll exactamente al final, y porque una burbuja a medio entrar
      cuenta como "estaba mirando el final". */
  const estabaAlFinal = () =>
    !hiloEl || hiloEl.scrollHeight - hiloEl.clientHeight - hiloEl.scrollTop < 120;

  /** Si el que mira está pegado abajo. Se recuerda EN EL SCROLL y no se
      pregunta en el momento de reajustar: cuando el contenedor cambia de alto,
      `scrollTop` ya quedó viejo y preguntarlo entonces contesta "no estaba al
      final" aunque lo estuviera. */
  let pegadoAbajo = $state(true);
  const alScrollear = () => (pegadoAbajo = estabaAlFinal());

  /* EL HILO CAMBIA DE ALTO DESPUÉS DE HABER BAJADO AL FINAL, y sin esto se
     queda donde estaba -- o sea, dejando el último mensaje abajo del borde.
     Pasa en los dos casos normales: cuando el resumen de escalada termina de
     armarse y empuja al hilo hacia abajo, y cuando cambia el tamaño de la
     ventana. Medido el 21/09/2026 a 390x844 después de acotar el resumen: el
     hilo quedaba en scrollTop 163 de 197, con el último mensaje cortado por el
     compositor.
     Sólo se re-ancla a quien estaba pegado abajo: al que subió a leer algo de
     hace dos semanas, cambiar de tamaño la ventana no tiene por qué
     arrancárselo de la vista. Misma regla que el efecto de arriba. */
  $effect(() => {
    if (!hiloEl) return;
    const observador = new ResizeObserver(() => {
      if (pegadoAbajo) alFinal();
    });
    observador.observe(hiloEl);
    return () => observador.disconnect();
  });

  // Al abrir la conversacion, y en cada cambio del hilo.
  //
  // La condicion NO es "siempre": si alguien subio a leer lo que paso hace
  // dos semanas y entra un mensaje nuevo, arrastrarlo al fondo le quita de
  // la vista justo lo que estaba leyendo. Solo se sigue al que ya estaba
  // mirando el final. Cuando uno MISMO envia se fuerza aparte (ver enviar()):
  // ahi la intencion es evidente.
  let ultimoVisto = $state(0);
  $effect(() => {
    const n = cantidadMensajes;
    if (n === ultimoVisto) return;
    const primeraVez = ultimoVisto === 0;
    const seguir = primeraVez || estabaAlFinal();
    ultimoVisto = n;
    if (seguir) {
      // Un tick despues: el efecto corre antes de que el DOM tenga la burbuja
      // nueva, asi que scrollHeight todavia seria el de antes.
      requestAnimationFrame(() => alFinal(!primeraVez));
    }
  });
</script>


<!-- ══════════════════════════════════════════════════════════════════════════
     EL HILO, CONTRA LA REFERENCIA MAESTRA

     Pantalla: «Dexter Operations - Human Control State (Assigned to Me)»
     (`c427b43a84534a489891f111217439a4`), que SPEC/BANDEJA_STITCH_REFERENCIAS.md
     declara referencia maestra del hilo. Medido sobre su marcado, no a ojo.

     LA DIFERENCIA DE FONDO con lo que había acá: el rótulo de autor y la hora
     viven FUERA de la burbuja --encima-- y el estado de entrega vive DEBAJO.
     Antes los tres estaban adentro, y la burbuja terminaba siendo una ficha
     con cuatro renglones de metadato alrededor de una frase de una línea. Con
     el metadato afuera, la burbuja vuelve a ser sólo lo que se dijo.
     ══════════════════════════════════════════════════════════════════════════ -->

{#snippet adjuntos(/** @type {any} */ m)}
  <!-- Lo que el cliente mandó junto al mensaje. Para un ISP la foto de las
       luces del router dice en un segundo lo que al cliente le cuesta tres
       mensajes explicar: va EN el hilo, donde la mandó, no en una lista
       aparte al final. -->
  {#each m.adjuntos ?? [] as a (a.id)}
    {#if a.tipo === 'image'}
      <a class="adjunto" href="/api/media/{a.id}" target="_blank" rel="noreferrer">
        <img src="/api/media/{a.id}" alt={a.descripcion || 'Foto del cliente'} loading="lazy" />
      </a>
    {:else if a.tipo === 'audio' || a.tipo === 'voice'}
      <!-- svelte-ignore a11y_media_has_caption -->
      <audio class="adjunto-audio" controls src="/api/media/{a.id}"></audio>
    {:else}
      <!-- Documento: nombre, tipo y peso, y un botón que dice qué hace. Antes
           decía "document · 428 KB", que no alcanza para saber si vale la
           pena abrirlo. -->
      <a class="adjunto-doc" href="/api/media/{a.id}" target="_blank" rel="noreferrer">
        <Paperclip size={15} />
        <span class="adjunto-doc-datos">
          <b>{a.descripcion || a.tipo || 'archivo'}</b>
          <span class="v2-muted v2-num">
            {extension(a)} · {Math.round(a.bytes / 1024)} KB
          </span>
        </span>
        <span class="adjunto-abrir">Abrir</span>
      </a>
    {/if}
  {/each}
{/snippet}

<div class="hilo" bind:this={hiloEl} onscroll={alScrollear}>
  <div class="chat-mensajes">
    {#each hilo as item (item.clave)}
      {#if item.tipo === 'dia'}
        <!-- El separador de día es una FICHA CENTRADA, no un renglón con dos
             filetes. La referencia lo dibuja así, y el motivo se ve al
             apilarlos: los filetes a los lados se confundían con el riel del
             evento de sistema, que sí es una línea que cruza. Dos separadores
             distintos tienen que verse distintos. -->
        <div class="dia"><span class="dia-chip">{item.texto}</span></div>
      {:else if item.m.rol === 'nota'}
        {@const autor = autorDe(item.m)}
        <!-- LA NOTA INTERNA NO SE PARECE A UN MENSAJE, y ahora tampoco ocupa
             su lugar: va de lado a lado, con candado y con el rótulo que dice
             a quién NO le llega. Es la mitad visual de la garantía; la otra
             mitad es que la ruta que la guarda no toca el canal. -->
        <div class="nota">
          <div class="nota-cabeza">
            <span class="nota-rotulo">
              <Lock size={12} /> Nota interna · sólo el equipo
            </span>
            <span class="nota-meta v2-num">
              {hora(item.m.creado_en)}{autor.quien ? ` · ${autor.quien}` : ''}
            </span>
          </div>
          {#if item.m.contenido}
            <p class="nota-texto">{item.m.contenido}</p>
          {/if}
          {@render adjuntos(item.m)}
        </div>
      {:else if burbujaClase(item.m.rol) === 'chat-otro'}
        <!-- Un renglón del hilo que no es un mensaje de nadie: un rol que esta
             pantalla no representa como conversación. La referencia lo pone
             como un riel que cruza, sin burbuja y sin lado, porque no tiene
             autor con quien hablar.

             OJO con lo que NO cae acá: los mensajes de origen 'sistema' SÍ
             salieron al cliente --son las respuestas automáticas de una
             conversación en pausa-- y siguen siendo burbujas. Pintarlos como
             un evento diría que no se le escribió a nadie, y se le escribió. -->
        <div class="evento">
          <span class="evento-texto v2-num">
            {hora(item.m.creado_en)} · {item.m.contenido}
          </span>
        </div>
      {:else}
        {@const autor = autorDe(item.m)}
        {@const sale = item.m.rol === 'assistant'}
        <div
          class="msg {sale ? 'msg-sale' : 'msg-entra'} {autor.clase}"
          class:msg-apagado={item.m.estado_entrega === 'descartado'}
        >
          <!-- QUIÉN escribió esto, dicho con palabras y no sólo con un color
               (D30). `rol` 'assistant' cubre por igual a la IA, a una persona
               y a las filas históricas sin origen: las tres se veían como si
               las hubiera escrito Dexter.

               El cliente lleva su nombre en texto llano y los demás una ficha
               con punto: es la misma distinción que hace la referencia --lo
               que ENTRA es una persona, lo que SALE es un sistema o un puesto
               de trabajo. -->
          <div class="msg-cabeza">
            {#if autor.clase === 'a-cliente'}
              <span class="msg-quien">{nombreCliente || autor.etiqueta}</span>
            {:else}
              <span class="msg-chip">
                <span class="msg-punto" aria-hidden="true"></span>{autor.etiqueta}
              </span>
            {/if}
            <span class="msg-hora v2-num">{hora(item.m.creado_en)}</span>
          </div>

          <div class="burbuja" class:sin-entregar={item.m.sinEntregar}>
            <!-- Un mensaje sin texto Y sin adjunto que se pueda dibujar no
                 puede quedar como una burbuja vacía: llegó algo (una
                 ubicación, un contacto, un sticker) que esta pantalla todavía
                 no representa. Decirlo es mejor que un hueco, que se lee como
                 un error de la aplicación. -->
            {#if item.m.contenido}
              <!-- Los saltos de línea que respeta `pre-wrap` son los DEL
                   MENSAJE, así que la regla va acá y no en la burbuja: en la
                   burbuja, el salto y la sangría del propio marcado contaban
                   como texto. -->
              <div class="burbuja-texto">{item.m.contenido}</div>
            {:else if !(item.m.adjuntos ?? []).length}
              <div class="no-representable">
                <TriangleAlert size={12} />
                Mensaje de un tipo que todavía no mostramos acá — el cliente sí lo envió.
              </div>
            {/if}
            {@render adjuntos(item.m)}
          </div>

          {#if conPie(item.m)}
            <div class="msg-pie">
              <!-- Por qué no alcanza con 'sinEntregar': ése es el aviso del
                   POST, existe una sola vez y se pierde al recargar. El estado
                   viene de la base (messages.estado_entrega) y sobrevive. Se
                   muestran los dos porque el primero llega al instante y el
                   segundo tarda lo que tarde el acuse de Meta. -->
              {#if item.m.sinEntregar || item.m.estado_entrega === 'fallido'}
                <span class="pie-fallo">
                  <TriangleAlert size={11} />
                  No le llegó — {item.m.sinEntregar ||
                    item.m.error_entrega ||
                    'WhatsApp lo rechazó'}
                </span>
                <!-- Reintentar sin volver a escribir: el texto ya está en la
                     burbuja, y hacer que alguien lo tipee de nuevo después de
                     un fallo del canal es cobrarle a la persona equivocada. -->
                <button
                  type="button"
                  class="pie-reintentar"
                  onclick={() => onReintentar?.(item.m)}
                  disabled={reintentando === item.m.id}
                  aria-busy={reintentando === item.m.id}
                >
                  <RotateCcw size={11} />
                  {reintentando === item.m.id ? 'Reintentando…' : 'Reintentar'}
                </button>
              {:else if item.m.rol === 'assistant' && item.m.estado_entrega}
                <!-- NULL no dibuja nada: significa "no se sabe" (otro canal, o
                     anterior al registro), y un tilde inventado sobre un
                     mensaje del que no sabemos nada es peor que no decir
                     nada. -->
                <span class="entrega entrega-{item.m.estado_entrega}">
                  {ENTREGA_TEXTO[item.m.estado_entrega] ?? item.m.estado_entrega}
                </span>
              {/if}
              {#if item.m.rol === 'assistant' && casos.length > 0}
                <MarcarEjemplo
                  conversacionId={conversacionId}
                  mensajeId={item.m.id}
                  casoInicial={item.m.caso_marcado}
                  {casos}
                />
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    {/each}
    {#if escribiendo}
      <div class="msg msg-sale a-ia" aria-label="Escribiendo…">
        <div class="burbuja burbuja-escribiendo">
          <span class="punto"></span><span class="punto"></span><span class="punto"></span>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  /* El hilo es lo único que scrollea acá: el encabezado y el compositor
     quedan fijos, para no tener que bajar hasta el fondo para escribir. */
  .hilo {
    flex: 1;
    /* El piso del hilo. Era `min-height: 0`, que en una columna flex significa
       "puedo desaparecer": medido el 21/09/2026 a 390x844 quedaba en 28px
       porque el resumen de escalada, que no encogía, se llevaba 224. Los
       mensajes son de lo que trata esta pantalla; son lo último que cede, no
       lo primero. 140px son dos burbujas cortas. */
    min-height: 140px;
    overflow-y: auto;
    /* p-5 en la referencia. */
    padding: 20px;
  }

  /* space-y-4 en la referencia: 16px entre bloques, y cada bloque decide su
     lado y su ancho. `max-width` acá no: el ancho lo pone cada mensaje
     (`.msg`), porque la nota interna y el evento de sistema van de lado a
     lado y antes quedaban recortados a los 720px del contenedor. */
  .chat-mensajes {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ── el separador de día ────────────────────────────────────────────── */
  .dia {
    display: flex;
    justify-content: center;
    margin: 2px 0;
  }

  .dia-chip {
    padding: 2px 10px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-3);
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* ── el evento de sistema: un riel que cruza ────────────────────────── */
  .evento {
    align-self: stretch;
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 2px 0;
  }

  .evento::before,
  .evento::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--bandeja-borde);
  }

  .evento-texto {
    font-family: var(--bandeja-mono);
    font-size: 11px;
    font-weight: 500;
    color: var(--bandeja-texto-2);
    text-align: center;
  }

  /* ── el bloque de un mensaje ────────────────────────────────────────── */
  /* `max-w-xl` de la referencia = 36rem. Sobre 720px una frase corta quedaba
     estirada y una larga se leía como un párrafo de documento; 576 es el
     ancho con el que la referencia acomoda tres renglones. */
  .msg {
    display: flex;
    flex-direction: column;
    max-width: 36rem;
    min-width: 0;
  }

  /* LO QUE ENTRA A LA IZQUIERDA. Estuvo al revés hasta el 21/09/2026: el
     cliente a la derecha, que es la convención de la app del CLIENTE, no la
     de la consola de quien atiende. En cualquier consola de agente la
     columna izquierda se lee como "lo que entra". */
  .msg-entra {
    align-self: flex-start;
    align-items: flex-start;
  }

  .msg-sale {
    align-self: flex-end;
    align-items: flex-end;
  }

  /* D24: la IA la calculó, pero una persona tomó el control antes de que
     saliera. Se ve, apagada, porque forma parte de lo que pasó; pero no
     compite con lo que sí se envió. */
  .msg-apagado {
    opacity: 0.75;
  }

  /* ── la cabecera: quién y cuándo ────────────────────────────────────── */
  .msg-cabeza {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    padding: 0 4px;
    min-width: 0;
  }

  .msg-quien {
    font-size: 12px;
    font-weight: 600;
    color: var(--bandeja-texto);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .msg-hora {
    flex: none;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }

  /* La ficha de autor. El color NO es la señal: adentro va la palabra, y el
     punto es refuerzo -- un 8% de la gente no distingue violeta de azul, y un
     punto de color sin texto no dice QUÉ pasó. */
  .msg-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 1px 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .msg-punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .a-ia .msg-chip {
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
    color: var(--bandeja-ia);
  }

  .a-humano .msg-chip {
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
    color: var(--bandeja-humano);
  }

  /* Sistema y "origen no registrado" quedan en gris a propósito: ninguno de
     los dos es alguien con quien se pueda hablar, y el segundo además es la
     admisión de que no sabemos. Un color propio le daría una identidad que
     justamente no tiene; el filete punteado dice "esto no está confirmado". */
  .a-sin-registro .msg-chip {
    border-style: dashed;
    border-color: var(--bandeja-borde-fuerte);
  }

  /* ── la burbuja ─────────────────────────────────────────────────────────
     SUPERFICIE Y FILETE, NUNCA RELLENO SÓLIDO. Los seis valores salen del
     `tailwind.config` de la referencia:

        cliente   #FFFFFF sobre #E2E8F0
        Dexter IA #F5F3FF sobre #DDD6FE
        operador  #EFF6FF sobre #BFDBFE

     Tipografía: 12px sobre interlínea 1.625 (`text-xs leading-relaxed`),
     padding 12 y radio 4. */
  .burbuja {
    padding: 12px;
    border-radius: var(--bandeja-radio-sm);
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto);
    font-size: 12px;
    line-height: 1.625;
    /* El texto se lee de izquierda a derecha también del lado que sale: lo
       que se alinea a la derecha es el bloque, no el renglón. */
    text-align: left;
    max-width: 100%;
    min-width: 0;
  }

  .burbuja-texto {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  /* Que el cliente se vea igual que la superficie base no puede ser una
     coincidencia de la cascada: se declara. */
  .a-cliente .burbuja {
    background: var(--bandeja-superficie);
    border-color: var(--bandeja-borde);
  }

  .a-ia .burbuja {
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
  }

  .a-humano .burbuja {
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
  }

  /* Una respuesta automática de una conversación en pausa SÍ salió al
     cliente, así que es una burbuja -- pero no la escribió ni la IA ni una
     persona, y por eso no lleva ninguno de los dos colores. */
  .a-sistema .burbuja {
    background: var(--bandeja-superficie-suave);
    border-color: var(--bandeja-borde);
  }

  /* Las filas anteriores a la migración 202609161600_origen_de_mensajes no
     tienen origen y no se puede reconstruir. Inventarlo sería peor que
     dibujarlo distinto. */
  .a-sin-registro .burbuja {
    border-style: dashed;
    border-color: var(--bandeja-borde-fuerte);
  }

  /* Una respuesta guardada que nunca salió tiene que verse distinta de una
     entregada. El aviso del pie desaparece al rato; la burbuja se queda. */
  .burbuja.sin-entregar {
    outline: 1px solid var(--v2-rust);
    outline-offset: -1px;
  }

  /* ── el pie: qué pasó con el envío ──────────────────────────────────── */
  .msg-pie {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 4px;
    padding: 0 4px;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }

  .entrega-leido {
    color: var(--bandeja-ok);
    font-weight: 600;
  }

  .pie-fallo {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--bandeja-error);
    font-weight: 600;
  }

  /* El reintento es un control chico dentro de una línea de metadato, no un
     botón del CRM: con `.v2-btn` medía 26px de alto y desequilibraba el pie
     de la burbuja. La referencia lo pone como una ficha de 9,5px. */
  .pie-reintentar {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 6px;
    border: 1px solid var(--bandeja-error-borde);
    border-radius: 3px;
    background: var(--bandeja-error-fondo);
    color: var(--bandeja-error);
    font-family: inherit;
    font-size: 9.5px;
    font-weight: 600;
    cursor: pointer;
  }

  .pie-reintentar:disabled {
    opacity: 0.6;
    cursor: default;
  }

  /* ── la nota interna ────────────────────────────────────────────────── */
  .nota {
    align-self: stretch;
    max-width: 100%;
    padding: 12px;
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    border: 1px solid var(--bandeja-aviso-borde);
  }

  .nota-cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 4px;
  }

  .nota-rotulo {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-nota);
  }

  .nota-rotulo :global(svg) {
    flex: none;
  }

  .nota-meta {
    flex: none;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-nota);
  }

  .nota-texto {
    margin: 0;
    font-size: 12px;
    line-height: 1.625;
    color: var(--bandeja-texto);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  /* ── multimedia recibida ────────────────────────────────────────────── */
  .no-representable {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-style: italic;
    color: var(--v2-slate);
  }

  .adjunto-doc {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-top: 6px;
    padding: 8px 10px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    color: inherit;
    text-decoration: none;
  }

  .adjunto-doc:hover {
    border-color: var(--v2-slate);
  }

  .adjunto-doc-datos {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    font-size: 12px;
  }

  .adjunto-doc-datos b {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .adjunto-abrir {
    margin-left: auto;
    font-size: 11.5px;
    font-weight: 650;
    color: var(--v2-ember);
    flex: none;
  }

  /* La foto ocupa el ancho de la burbuja y se abre a tamaño completo al hacer
     clic. Alto acotado: una foto vertical de teléfono empujaría el resto del
     hilo fuera de la pantalla. */
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

  /* ── escribiendo ────────────────────────────────────────────────────── */
  .burbuja-escribiendo {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 13px 16px;
  }

  .burbuja-escribiendo .punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--bandeja-ia);
    opacity: 0.35;
    animation: chat-parpadeo 1.2s infinite ease-in-out;
  }

  .burbuja-escribiendo .punto:nth-child(2) {
    animation-delay: 0.2s;
  }

  .burbuja-escribiendo .punto:nth-child(3) {
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

  /* En un teléfono 36rem es más que la pantalla, así que el bloque manda y el
     lado se sigue leyendo por el borde del que nace. El aire de 20px se baja
     a 14: a 390px de ancho, 40px de padding lateral eran el 10% del hilo. */
  @media (max-width: 760px) {
    .hilo {
      padding: 14px;
    }
    .msg {
      max-width: 92%;
    }
  }
</style>
