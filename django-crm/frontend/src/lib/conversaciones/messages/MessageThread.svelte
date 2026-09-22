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
  import { TriangleAlert, RotateCcw, Paperclip } from '@lucide/svelte';
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import { autorDe, burbujaClase, extension, hora, ENTREGA_TEXTO } from '../formato.js';

  let {
    /** El hilo ya agrupado por día: {tipo:'dia'|'msg'} */
    hilo,
    /** Cuántos mensajes hay. Dispara el autoscroll; se pasa aparte de `hilo`
        porque `hilo` incluye los separadores de día. */
    cantidadMensajes,
    conversacionId,
    casos = [],
    /** Se está enviando y la IA responde: muestra los tres puntitos. */
    escribiendo = false,
    reintentando = null,
    onReintentar
  } = $props();

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

<div class="hilo" bind:this={hiloEl} onscroll={alScrollear}>
  <div class="chat-mensajes">
    {#each hilo as item (item.clave)}
      {#if item.tipo === 'dia'}
        <div class="dia"><span>{item.texto}</span></div>
      {:else}
        {@const autor = autorDe(item.m)}
        <div
          class="chat-burbuja {burbujaClase(item.m.rol)} {autor.clase}"
          class:sin-entregar={item.m.sinEntregar}
        >
          <!-- QUIEN escribio esto, dicho con palabras y no solo con un color
               (D30). Antes la burbuja se clasificaba por `rol`, y `rol`
               'assistant' cubre por igual a la IA, a una persona y a las filas
               historicas sin origen: las tres se veian como si las hubiera
               escrito Dexter.

               El cliente no lleva rotulo: su burbuja ya esta del otro lado y
               es el unico que no puede confundirse con nadie. -->
          {#if autor.clase !== 'a-cliente'}
            <div class="autor">
              <span class="autor-punto" aria-hidden="true"></span>{autor.etiqueta}
            </div>
          {/if}
          <!-- Un mensaje sin texto Y sin adjunto que se pueda dibujar no
               puede quedar como una burbuja vacía: llegó algo (una
               ubicación, un contacto, un sticker) que esta pantalla todavía
               no representa. Decirlo es mejor que un hueco, que se lee como
               un error de la aplicación. -->
          {#if item.m.contenido}
            <!-- Los saltos de línea que respeta `pre-wrap` son los DEL MENSAJE,
                 así que la regla va acá y no en la burbuja. Estando en la
                 burbuja, el salto y la sangría del propio marcado contaban
                 como texto: medido el 21/09/2026, un mensaje de un renglón
                 ocupaba 128px de los cuales 60 eran líneas en blanco de la
                 plantilla. Se notó al subir la interlínea a 1,6. -->
            <div class="chat-texto">{item.m.contenido}</div>
          {:else if !(item.m.adjuntos ?? []).length}
            <div class="no-representable">
              <TriangleAlert size={12} />
              Mensaje de un tipo que todavía no mostramos acá — el cliente sí lo envió.
            </div>
          {/if}
          <!-- Lo que el cliente mando junto al mensaje. Para un ISP la foto
               de las luces del router dice en un segundo lo que al cliente
               le cuesta tres mensajes explicar: va EN el hilo, donde la
               mandó, no en una lista aparte al final. -->
          {#each item.m.adjuntos ?? [] as a (a.id)}
            {#if a.tipo === 'image'}
              <a class="adjunto" href="/api/media/{a.id}" target="_blank" rel="noreferrer">
                <img src="/api/media/{a.id}" alt={a.descripcion || 'Foto del cliente'} loading="lazy" />
              </a>
            {:else if a.tipo === 'audio' || a.tipo === 'voice'}
              <!-- svelte-ignore a11y_media_has_caption -->
              <audio class="adjunto-audio" controls src="/api/media/{a.id}"></audio>
            {:else}
              <!-- Documento: nombre, tipo y peso, y un botón que dice qué
                   hace. Antes decía "document · 428 KB", que no alcanza para
                   saber si vale la pena abrirlo. -->
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

          <!-- Por qué no alcanza con 'sinEntregar': ese es el aviso del
               POST, existe una sola vez y se pierde al recargar. El estado
               viene de la base (messages.estado_entrega) y sobrevive. Se
               muestran los dos porque el primero llega al instante y el
               segundo tarda lo que tarde el acuse de Meta. -->
          {#if item.m.sinEntregar || item.m.estado_entrega === 'fallido'}
            <div class="no-llego">
              <TriangleAlert size={12} />
              <span>
                No le llegó al cliente — {item.m.sinEntregar ||
                  item.m.error_entrega ||
                  'WhatsApp lo rechazó'}
              </span>
              <!-- Reintentar sin volver a escribir: el texto ya está en la
                   burbuja, y hacer que alguien lo tipee de nuevo después de
                   un fallo del canal es cobrarle a la persona equivocada. -->
              <button
                type="button"
                class="v2-btn v2-btn-sm reintentar"
                onclick={() => onReintentar?.(item.m)}
                disabled={reintentando === item.m.id}
                aria-busy={reintentando === item.m.id}
              >
                <RotateCcw size={12} />
                {reintentando === item.m.id ? 'Reintentando…' : 'Reintentar'}
              </button>
            </div>
          {:else if item.m.rol === 'assistant' && item.m.estado_entrega}
            <!-- NULL no dibuja nada: significa "no se sabe" (otro canal, o
                 anterior al registro), y un tilde inventado sobre un mensaje
                 del que no sabemos nada es peor que no decir nada. -->
            <div class="entrega entrega-{item.m.estado_entrega}">
              {ENTREGA_TEXTO[item.m.estado_entrega] ?? item.m.estado_entrega}
            </div>
          {/if}
          <div class="chat-hora v2-num">{hora(item.m.creado_en)}</div>
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
    {/each}
    {#if escribiendo}
      <div class="chat-burbuja chat-asistente chat-escribiendo" aria-label="Escribiendo…">
        <span class="punto"></span><span class="punto"></span><span class="punto"></span>
      </div>
    {/if}
  </div>
</div>


<style>
  /* ── quién escribió (D30) ─────────────────────────────────────────────── */
  /* El rótulo va SIEMPRE con palabra. El color solo no alcanza: un 8% de la
     gente no distingue violeta de azul, y un punto de color sin texto no dice
     QUÉ pasó. El punto es refuerzo, no la señal. */
  .autor {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-bottom: 4px;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }

  .autor-punto {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .a-ia .autor {
    color: var(--bandeja-ia);
  }

  .a-humano .autor {
    color: var(--bandeja-humano);
  }

  .a-nota .autor {
    color: var(--bandeja-nota);
  }

  /* Sistema y "origen no registrado" quedan en gris a propósito: ninguno de
     los dos es alguien con quien se pueda hablar, y el segundo además es la
     admisión de que no sabemos. Un color propio le daría una identidad que
     justamente no tiene. */
  .a-sistema .autor,
  .a-sin-registro .autor {
    color: var(--bandeja-texto-3);
  }

  /* El hilo es lo único que scrollea acá: el encabezado y el compositor
     quedan fijos, para no tener que bajar hasta el fondo para escribir. */
  .hilo {
    flex: 1;
    /* El piso del hilo. Era `min-height: 0`, que en una columna flex significa
       "puedo desaparecer": medido el 21/09/2026 a 390x844 quedaba en 28px
       porque el resumen de escalada, que no encogía, se llevaba 224. Los
       mensajes son de lo que trata esta pantalla; son lo último que cede, no
       lo primero. Quien cede ahora es el resumen (`.brief { min-height: 0 }`,
       con scroll propio). 140px son dos burbujas cortas: suficiente para que
       el hilo siga siendo un hilo. */
    min-height: 140px;
    overflow-y: auto;
    padding: 14px 16px;
  }
  /* ── entrega y multimedia recibida ──────────────────────────────────── */
  .entrega {
    font-size: 10.5px;
    color: var(--v2-slate);
    text-align: right;
    margin-top: 2px;
  }
  .entrega-leido {
    color: var(--v2-moss);
    font-weight: 600;
  }
  .reintentar {
    margin-left: auto;
    flex: none;
  }
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
  .chat-mensajes {
    display: flex;
    flex-direction: column;
    gap: 14px;
    max-width: 720px;
  }
  .dia {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 6px 0;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    color: var(--bandeja-texto-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .dia::before,
  .dia::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--bandeja-borde);
  }

  /* ── las burbujas ──────────────────────────────────────────────────────
     SUPERFICIE Y FILETE, NUNCA RELLENO SÓLIDO.

     Hasta el 21/09/2026 esto era un chat genérico: el cliente iba en un
     rectángulo azul saturado con texto blanco y radio 12, y la respuesta en
     un gris. Los tres valores salían de `var(--v2-accent, #2563eb)`,
     `var(--v2-surface-2, #f1f1f1)` y `var(--v2-border, #e5e5e5)` -- y
     NINGUNA de esas tres variables existe (medido: 0 definiciones en
     v2.css). O sea que el hilo se pintaba enteramente con los colores de
     respaldo, por fuera del sistema congelado.

     La referencia (Human Control State, medida en el HTML de Stitch) usa
     radio 4, padding 12, 12,5px sobre interlínea 1,6, y distingue por
     SUPERFICIE + FILETE de 1px:

        cliente   #FFFFFF sobre #E2E8F0
        Dexter IA #F5F3FF sobre #DDD6FE
        operador  #EFF6FF sobre #BFDBFE

     Los seis valores ya estaban en `bandeja.css` desde la Fase 1 --salen
     del tailwind.config del diseño canónico-- y el hilo era el único lugar
     que no los usaba.

     El color NO es la señal: el rótulo de autor (D30) sigue arriba de cada
     burbuja, con palabra y punto. La superficie sólo refuerza. */
  .chat-burbuja {
    padding: 12px;
    border-radius: var(--bandeja-radio-sm);
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto);
    max-width: 80%;
    font-size: 12.5px;
    line-height: 1.6;
  }

  .chat-texto {
    white-space: pre-wrap;
  }

  /* EL CLIENTE VA A LA IZQUIERDA. Estaba al revés: el cliente a la derecha
     y quien atiende a la izquierda, que es la convención de la app de
     mensajería del CLIENTE, no la de una consola de quien atiende. En la
     referencia, y en cualquier consola de agente, uno lee la columna
     izquierda como "lo que entra" y la derecha como "lo que sale". */
  .chat-usuario {
    align-self: flex-start;
  }
  .chat-asistente {
    align-self: flex-end;
  }
  .chat-otro {
    align-self: center;
    background: transparent;
    border: 1px dashed var(--bandeja-borde-fuerte);
    font-style: italic;
    color: var(--bandeja-texto-2);
  }

  /* Quién habla, por superficie. Va por AUTOR (`a-*`, D30) y no por rol:
     `rol = assistant` cubre por igual a la IA y a una persona, y ésa es
     justo la distinción que el hilo tiene que hacer visible. */
  .a-ia {
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
  }
  .a-humano {
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
  }

  /* LA NOTA INTERNA NO SE PARECE A UN MENSAJE, y por eso su regla vive DESPUÉS
     de `.chat-burbuja` y no antes: las dos son selectores de una clase, así
     que gana la última del archivo. Estaba arriba, y cuando `.chat-burbuja`
     pasó a fijar superficie y filete propios le habría borrado el ámbar y el
     borde punteado -- una nota interna con la misma cara que un mensaje
     enviado es exactamente lo que este bloque existe para impedir. Mismo
     mecanismo que la colisión de `.activa` en la cola: en un `<style>` de
     Svelte, el orden ES la especificidad. */
  .chat-nota {
    align-self: stretch;
    max-width: 100%;
    background: var(--bandeja-nota-fondo);
    border: 1px dashed var(--bandeja-aviso-borde);
    color: var(--bandeja-texto);
  }
  .chat-nota::before {
    content: 'Nota interna · no la ve el cliente';
    display: block;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-nota);
    margin-bottom: 4px;
  }

  .chat-hora {
    margin-top: 6px;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }
  /* Una respuesta guardada que nunca salio tiene que verse distinta de una
     entregada. El aviso de arriba desaparece al rato; la burbuja se queda. */
  .chat-burbuja.sin-entregar {
    outline: 1px solid var(--v2-rust);
    outline-offset: -1px;
  }
  /* La foto ocupa el ancho de la burbuja y se abre a tamano completo al
     hacer clic. Alto acotado: una foto vertical de telefono empujaria el
     resto del hilo fuera de la pantalla. */
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
  .no-llego {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
    padding-top: 5px;
    border-top: 1px solid color-mix(in srgb, var(--v2-rust) 35%, transparent);
    font-size: 11px;
    color: var(--v2-rust);
    line-height: 1.35;
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
</style>
