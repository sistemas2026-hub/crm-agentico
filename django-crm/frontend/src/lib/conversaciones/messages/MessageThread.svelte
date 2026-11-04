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
  import { TriangleAlert, RotateCcw, Paperclip, Lock, Check, CheckCheck, Clock, Bot, UserRound, User } from '@lucide/svelte';
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import CorregirAgente from '$lib/components/manual/CorregirAgente.svelte';
  import { autorDe, burbujaClase, extension, hora, ENTREGA_TEXTO } from '../formato.js';
  import { partirMensaje, resumir } from './analisis-imagen.js';
  import { agruparMensajes } from './agrupar.js';

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
    onReintentar,
    /** Ver las conversaciones anteriores del chat (21/10/2026). Lo dibuja el
        elemento {tipo:'mas'} que arma lib/conversaciones/chat.js. */
    onVerAnteriores = undefined,
    cargandoAnteriores = false,
    /** Si se puede reintentar una entrega: NO en una conversación cerrada,
        que el motor ya no le acepta envíos (X26). Sin esto, "Reintentar" en
        una cerrada pasaba por T21 y abría una conversación fantasma
        (auditor de frontera, 21/10/2026). */
    puedeReintentar = true,
    /** Qué agente atiende esta conversación (`rol_efectivo`). Lo necesita
        «✎ Corregir»: una habilidad sin rol no la ve nadie, así que sin esto
        el botón se muestra apagado en vez de guardar una corrección muerta.
        Vacío = no se sabe, y entonces no se puede corregir desde acá. */
    rolActivo = ''
  } = $props();

  /** Si debajo de la burbuja hay algo que decir: el estado de entrega, el
      aviso de que no llego, el control de marcar como ejemplo, o el de
      corregir. Se pregunta antes de dibujar el pie para no dejar un renglon
      vacio con margen --que es lo que separa un hilo prolijo de uno con
      huecos.

      TODA RESPUESTA DEL AGENTE TIENE PIE (02/11/2026). Hasta hoy pedia
      ademas `estado_entrega` o que hubiera casos cargados, y «✎ Corregir» se
      agrego DENTRO de este bloque sin sumarse a esta lista: el boton solo
      aparecia cuando algo MAS ya habia puesto un pie ahi. En una
      conversacion sin casos del manual --o en un canal que no reporta
      entrega-- no se veia nunca. Corregir aplica a cualquier respuesta del
      agente, asi que ahora la condicion lo dice. */
  const conPie = (/** @type {any} */ m) =>
    !!(m.sinEntregar || m.estado_entrega === 'fallido' || m.rol === 'assistant');

  /* RÁFAGAS (04/11/2026): el nombre del autor va una vez por grupo de
     mensajes seguidos suyos, no en cada burbuja. La regla vive en
     agrupar.js, con sus pruebas; acá solo se dibuja. */
  const hiloAgrupado = $derived(agruparMensajes(hilo));

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
      <!-- EL ANÁLISIS NO SE DIBUJA ACÁ, y es a propósito: ya está en la
           burbuja, porque el motor lo guarda dentro del mensaje del cliente.
           Dibujarlo también junto a la miniatura lo mostraría dos veces en la
           misma pantalla, y quien lee no tendría forma de saber que es el
           mismo texto. La columna `analisis_visual` sigue viajando en el
           adjunto —la bandeja la recibe— pero la vista única es la de arriba. -->
    {:else if a.tipo === 'audio' || a.tipo === 'voice'}
      <!-- svelte-ignore a11y_media_has_caption -->
      <audio class="adjunto-audio" controls src="/api/media/{a.id}"></audio>
      <!-- Lo que dice la nota de voz, debajo del reproductor. Se muestra SOLO
           cuando hay texto: un audio que todavía no se transcribió, uno que
           falló y uno sin voz se ven los tres igual — sin nada. El motivo
           técnico del fallo no baja hasta aquí a propósito: no le sirve a
           quien atiende, y menos al cliente. -->
      {#if a.transcripcion}
        <p class="adjunto-transcripcion">
          <span class="adjunto-transcripcion-rotulo">Transcripción:</span>
          {a.transcripcion}
        </p>
      {/if}
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
    {#each hiloAgrupado as item (item.clave)}
      {#if item.tipo === 'dia'}
        <!-- El separador de día es una FICHA CENTRADA, no un renglón con dos
             filetes. La referencia lo dibuja así, y el motivo se ve al
             apilarlos: los filetes a los lados se confundían con el riel del
             evento de sistema, que sí es una línea que cruza. Dos separadores
             distintos tienen que verse distintos. -->
        <!-- 04/11/2026: escrito normal y sin ficha con filete; es un rótulo
             de orientación, no un dato que compita con los mensajes. -->
        <div class="dia"><span class="dia-chip">{item.texto}</span></div>
      {:else if item.tipo === 'mas'}
        <div class="mas">
          <button type="button" class="mas-boton" onclick={() => onVerAnteriores?.()}
                  disabled={cargandoAnteriores} aria-busy={cargandoAnteriores}>
            {cargandoAnteriores ? 'Cargando…' : item.texto}
          </button>
        </div>
      {:else if item.tipo === 'cierre'}
        <!-- UN CHAT, VARIAS CONVERSACIONES (21/10/2026, contrato §4.5): la
             marca entre una conversación y la siguiente del mismo número.
             Dice SOLO lo registrado -- sin hora ni motivo si el cierre no los
             dejó (T18) -- y es un renglón con filete, no una ficha: tiene que
             verse distinta del separador de día. -->
        <div class="cierre" role="separator" aria-label={item.texto}>
          <span class="cierre-texto">{item.texto}</span>
          {#if item.enlace}
            <!-- Una conversación del mismo número que sigue ABIERTA: se
                 atiende en ella, y sin el enlace no había cómo llegar. -->
            <a class="cierre-enlace" href="/conversaciones/{item.enlace}">Abrirla</a>
          {/if}
        </div>
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
          class:msg-sigue={!item.inicioDeGrupo}
        >
          <!-- QUIÉN escribió esto, dicho con palabras y no sólo con un color
               (D30). `rol` 'assistant' cubre por igual a la IA, a una persona
               y a las filas históricas sin origen: las tres se veían como si
               las hubiera escrito Dexter.

               El nombre va en texto chico escrito normal, arriba del globo
               (04/11/2026). Era una pastilla en mayúscula rellena del color
               de cada uno, y «ADMIN» en blanco sobre azul gritaba más que el
               mensaje: el color ya lo lleva el globo, acá alcanzan la palabra
               y el ícono. Y solo en el primero de una ráfaga (agrupar.js): en
               los siguientes la hora va al pie. -->
          {#if item.inicioDeGrupo}
            <div class="msg-cabeza">
              {#if autor.clase === 'a-cliente'}
                <!-- El nombre es el del cliente de ESTA conversación. Un mensaje
                     de una anterior del chat lleva la etiqueta neutra: el número
                     pudo ser de otra persona (revisor de PII, 21/10/2026). -->
                <span class="msg-quien">
                  <User size={12} aria-hidden="true" />
                  {(!item.m.deOtraConversacion && nombreCliente) || autor.etiqueta}
                </span>
              {:else}
                <!-- El ícono es la tercera señal, además de la palabra y el color
                     (29/10/2026): un robot para la IA y una persona para el
                     equipo se distinguen de reojo, sin leer y sin depender de
                     distinguir violeta de azul. -->
                <span class="msg-quien">
                  {#if autor.clase === 'a-ia'}
                    <Bot size={12} aria-hidden="true" />
                  {:else if autor.clase === 'a-humano'}
                    <UserRound size={12} aria-hidden="true" />
                  {:else}
                    <span class="msg-punto" aria-hidden="true"></span>
                  {/if}
                  {autor.etiqueta}
                </span>
              {/if}
              <span class="msg-hora v2-num">{hora(item.m.creado_en)}</span>
            </div>
          {/if}

          <div class="burbuja" class:sin-entregar={item.m.sinEntregar}>
            <!-- Un mensaje sin texto Y sin adjunto que se pueda dibujar no
                 puede quedar como una burbuja vacía: llegó algo (una
                 ubicación, un contacto, un sticker) que esta pantalla todavía
                 no representa. Decirlo es mejor que un hueco, que se lee como
                 un error de la aplicación. -->
            {#if item.m.contenido}
              {@const foto = partirMensaje(item.m.contenido)}
              {#if foto}
                <!-- UNA FOTO NO SE LEE COMO UN MENSAJE DE TEXTO.
                     El motor guarda el análisis DENTRO del mensaje del cliente
                     —es lo que el modelo necesita leer— y eso son 600
                     caracteres por foto en una burbuja. Quien repasa un hilo
                     para entender qué pasó tiene que saltearlos a mano.
                     Acá se parte en dos niveles: lo que el cliente escribió y
                     una línea de resumen arriba, el análisis entero a un clic.
                     No se toca nada de lo guardado. -->
                {#if foto.pie}
                  <div class="burbuja-texto">{foto.pie}</div>
                {/if}
                <div class="analisis">
                  <div class="analisis-titulo">👁️ Análisis de imagen</div>
                  <!-- El resumen sale del MISMO texto de abajo, extraído, sin
                       otra llamada al modelo. Si no se pudo extraer nada, cita
                       el original en vez de inventar una frase. -->
                  <p class="analisis-resumen">{resumir(foto.analisis)}</p>
                  <details>
                    <summary class="analisis-ver">
                      <span class="analisis-abrir">Ver análisis completo</span>
                      <span class="analisis-cerrar">Ocultar análisis completo</span>
                    </summary>
                    <!-- El análisis COMPLETO, carácter por carácter como lo
                         escribió el modelo. Lo de arriba es un atajo; esto es
                         la fuente. -->
                    <p class="analisis-texto">{foto.analisis}</p>
                  </details>
                </div>
              {:else}
                <!-- Los saltos de línea que respeta `pre-wrap` son los DEL
                     MENSAJE, así que la regla va acá y no en la burbuja: en la
                     burbuja, el salto y la sangría del propio marcado contaban
                     como texto. -->
                <div class="burbuja-texto">{item.m.contenido}</div>
              {/if}
            {:else if !(item.m.adjuntos ?? []).length}
              <div class="no-representable">
                <TriangleAlert size={12} />
                Mensaje de un tipo que todavía no mostramos acá — el cliente sí lo envió.
              </div>
            {/if}
            {@render adjuntos(item.m)}

            <!-- LA PALOMITA VA DENTRO, ABAJO A LA DERECHA -- como en WhatsApp
                 y por el mismo motivo: pertenece a ESE mensaje, y colgada
                 debajo de la burbuja se leía como un renglón aparte que hay
                 que asociar. Adentro se ve sin buscarla.

                 NULL no dibuja nada: significa «no se sabe» (otro canal, o
                 anterior al registro), y un tilde inventado sobre un mensaje
                 del que no sabemos nada es peor que no decir nada. Lo fallado
                 y lo descartado tampoco llevan: los dos dicen que el mensaje
                 NO salió, y un tilde diría lo contrario.

                 EL COLOR NO ES LA ÚNICA SEÑAL: entregado y leído son las
                 MISMAS dos palomitas y sólo las separa el azul, y un 8% de la
                 gente no distingue esos tonos. Por eso la palabra sigue
                 estando, en `title` y en `aria-label`. -->
            {#if item.m.rol === 'assistant' && item.m.estado_entrega && !item.m.sinEntregar && !['descartado', 'fallido'].includes(item.m.estado_entrega)}
              {@const entrega = ENTREGA_TEXTO[item.m.estado_entrega] ?? item.m.estado_entrega}
              <span
                class="palomita palomita-{item.m.estado_entrega}"
                title={entrega}
                aria-label={entrega}
                role="img"
              >
                {#if item.m.estado_entrega === 'pendiente'}
                  <Clock size={13} />
                {:else if item.m.estado_entrega === 'enviado'}
                  <Check size={14} />
                {:else}
                  <CheckCheck size={14} />
                {/if}
              </span>
            {/if}
          </div>

          {#if conPie(item.m)}
            <div class="msg-pie">
              <!-- Sin cabecera (sigue una ráfaga), la hora baja al pie: cada
                   mensaje conserva cuándo se dijo. -->
              {#if !item.inicioDeGrupo}
                <span class="msg-hora v2-num">{hora(item.m.creado_en)}</span>
              {/if}
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
                <!-- Un mensaje de una conversación ANTERIOR del chat no se
                     reintenta desde acá: esa conversación está cerrada y el
                     motor no le acepta envíos (X26). -->
                {#if puedeReintentar && !item.m.deOtraConversacion}
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
                {/if}
              {:else if item.m.estado_entrega === 'descartado'}
                <!-- D24: la IA la calculó y una persona tomó el control antes
                     de que saliera. Va con PALABRA y no con palomita: un tilde
                     diría que algo se mandó, y no se mandó nada. El resto de
                     los estados son palomitas y viven DENTRO de la burbuja. -->
                <span class="entrega">{ENTREGA_TEXTO.descartado}</span>
              {/if}
              {#if item.m.rol === 'assistant'}
                <!-- ENTRENAR APARECE AL ACERCARSE (04/11/2026). «Buen ejemplo»
                     y «Corregir» iban debajo de cada respuesta, siempre: en un
                     hilo de veinte respuestas eran cuarenta controles que
                     nadie estaba usando. Se muestran con el mouse encima o con
                     el foco adentro, y siempre en pantallas táctiles, donde no
                     hay «encima». El fallo de entrega de arriba NO entra acá:
                     ese se ve siempre. -->
                <span class="pie-entrenar">
                  {#if casos.length > 0}
                    <MarcarEjemplo
                      conversacionId={item.m.conversation_id || conversacionId}
                      mensajeId={item.m.id}
                      casoInicial={item.m.caso_marcado}
                      {casos}
                    />
                  {/if}
                  <!-- El otro lado: esta respuesta estuvo mal y así se hace.
                       NO depende de `casos` --eso es la taxonomía del manual--
                       sino del rol, que es a quien se le enseña. -->
                  <CorregirAgente
                    rol={rolActivo}
                    textoDeLaRespuesta={item.m.contenido || item.m.texto || ''}
                    conversacionId={item.m.conversation_id || conversacionId}
                  />
                </span>
              {/if}
            </div>
          {:else if !item.inicioDeGrupo}
            <div class="msg-pie">
              <span class="msg-hora v2-num">{hora(item.m.creado_en)}</span>
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
    /* p-5 en la referencia; 24 a los costados desde el 04/11/2026: con el
       centro en blanco y los globos más claros, el hilo pegado a los bordes
       se leía apretado contra la columna de contexto. */
    padding: 20px 24px;
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

  /* Escrito normal, sin mono ni versalita (04/11/2026): «Hoy» o «Lunes 3 de
     noviembre» se leen como palabras, no como un código. Sigue centrado y
     sin filetes a los lados, por lo que dice el comentario del marcado. */
  .dia-chip {
    padding: 2px 8px;
    color: var(--bandeja-texto-3);
    font-family: var(--bandeja-titulo);
    font-size: 12px;
    font-weight: 600;
  }

  /* ── el chat: la marca entre conversaciones y "ver anteriores" ─────── */
  .cierre {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 14px 0;
    color: var(--bandeja-texto-3);
    font-size: 11px;
  }
  .cierre::before,
  .cierre::after {
    content: '';
    flex: 1;
    border-top: 1px dashed var(--bandeja-borde);
  }
  .cierre-texto {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 80%;
  }
  .cierre-enlace {
    color: inherit;
    font-weight: 600;
    text-decoration: underline;
  }
  .mas {
    display: flex;
    justify-content: center;
    margin: 6px 0 10px;
  }
  .mas-boton {
    padding: 3px 10px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    font-size: 11px;
    cursor: pointer;
  }
  .mas-boton:disabled {
    cursor: progress;
    opacity: 0.7;
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
  /* 68ch desde el 04/11/2026: el ancho se mide en caracteres del texto que
     se lee, no en rem; ~68 es el renglón cómodo con la fuente del mensaje. */
  .msg {
    display: flex;
    flex-direction: column;
    max-width: 68ch;
    min-width: 0;
  }

  /* El segundo y siguientes de una ráfaga van pegados al anterior: el hueco
     de 16px entre bloques es lo que separa a un autor del otro, y dentro de
     un grupo diría lo contrario. 16 - 12 = 4px. */
  .msg-sigue {
    margin-top: -12px;
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

  /* EL NOMBRE, NO UNA FICHA (04/11/2026). Barlow 13 escrito normal: es un
     nombre propio y se lee como tal. La pastilla rellena en mayúscula que
     había antes se llevaba la mirada antes que el mensaje. El color NO es la
     señal: va la palabra, y el ícono la refuerza -- un 8% de la gente no
     distingue violeta de azul. */
  .msg-quien {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    font-family: var(--bandeja-titulo);
    font-size: 13px;
    font-weight: 600;
    color: var(--bandeja-texto);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* El ícono en el color de quien habla: es la única marca de color de la
     cabecera, y repite la del globo de abajo. */
  .a-ia .msg-quien :global(svg) {
    color: var(--bandeja-ia);
  }
  .a-humano .msg-quien :global(svg) {
    color: var(--bandeja-humano);
  }

  /* La hora es un dato: mono y chica, en gris. */
  .msg-hora {
    flex: none;
    font-family: var(--bandeja-mono);
    font-size: 11px;
    color: var(--bandeja-texto-3);
  }

  .msg-punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  /* Sistema y "origen no registrado" quedan en gris a propósito: ninguno de
     los dos es alguien con quien se pueda hablar, y el segundo además es la
     admisión de que no sabemos. Un color propio le daría una identidad que
     justamente no tiene. */
  .a-sin-registro .msg-quien,
  .a-sistema .msg-quien {
    color: var(--bandeja-texto-2);
    font-weight: 500;
  }

  /* ── la burbuja ─────────────────────────────────────────────────────────
     SUPERFICIE Y FILETE, NUNCA RELLENO SÓLIDO. Los seis valores salen del
     `tailwind.config` de la referencia:

        cliente   #FFFFFF sobre #E2E8F0
        Dexter IA #F5F3FF sobre #DDD6FE
        operador  #EFF6FF sobre #BFDBFE

     Tipografía: la referencia pide 12px (`text-xs leading-relaxed`); acá va 14, ver abajo.
     padding 12 y radio 8 (04/11/2026: con 4 el globo se leía como una ficha
     de formulario, no como algo que alguien dijo). */
  .burbuja {
    padding: 12px;
    border-radius: 8px;
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto);
    font-family: var(--bandeja-sans);
    /* 12px era el `text-xs` de la referencia, y es lo que se viene a LEER en
       esta pantalla: todo lo demás es contexto. 14 sobre 1.5 (29/10/2026). */
    font-size: 14px;
    line-height: 1.5;
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

  /* EL CLIENTE EN GRIS SUAVE (04/11/2026). El centro pasó a blanco, y un
     globo blanco sobre blanco solo se distinguía por el filete: lo que entra
     necesita su propia superficie, neutra porque el cliente no es ni la IA ni
     el equipo. */
  .a-cliente .burbuja {
    background: var(--bandeja-superficie-suave);
    border-color: var(--bandeja-borde);
  }

  /* IA en violeta y persona en azul, con los fondos y filetes de la base
     (04/11/2026). Antes eran mezclas hechas acá al 9% y 45%; ahora salen de
     los mismos tokens que la cola y la línea de estado, para que el violeta
     de un globo sea el mismo violeta de «La atiende la IA». */
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
  /* Texto normal y no mono (04/11/2026): «No le llegó — WhatsApp lo rechazó»
     es una frase, no un dato. La hora de adentro conserva su mono por clase. */
  .msg-pie {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 4px;
    padding: 0 4px;
    font-family: var(--bandeja-sans);
    font-size: 11px;
    color: var(--bandeja-texto-3);
  }

  .pie-entrenar {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    opacity: 0;
    transition: opacity 0.12s;
  }

  .msg:hover .pie-entrenar,
  .msg:focus-within .pie-entrenar {
    opacity: 1;
  }

  /* En una pantalla táctil no hay «pasar el mouse»: escondido, no se
     encontraría nunca. */
  @media (hover: none) {
    .pie-entrenar {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .pie-entrenar {
      transition: none;
    }
  }

  /* ── las palomitas ─────────────────────────────────────────────────────
     Un tilde = salió. Dos = le llegó al teléfono. Dos azules = lo abrió.
     Es la convención que la mano ya conoce de WhatsApp, y en una lista de
     veinte mensajes se recorre sin leer: la palabra «Entregado» repetida
     veinte veces es ruido, un tilde no. */
  /* Abajo a la derecha, DENTRO de la burbuja. Flotada y no absoluta: con
     `float` el último renglón del texto le deja el hueco y la palomita queda
     al lado de la última palabra, como en WhatsApp. Absoluta se montaría
     encima del texto en un mensaje que llena el ancho. */
  .palomita {
    float: right;
    display: inline-flex;
    align-items: center;
    margin: 3px 0 -1px 8px;
    color: var(--bandeja-texto-3);
  }

  /* Enviado y entregado comparten el gris: la diferencia está en la FORMA
     --uno o dos tildes-- y no en el color, que es lo que hace que se
     distingan sin mirar dos veces. */
  .palomita-leido {
    color: var(--bandeja-humano);
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
    border-radius: 8px;
    /* El mismo fondo que el cuadro de texto en modo nota (04/11/2026): lo que
       se escribe como nota se ve, ya guardado, igual que mientras se escribía. */
    background: var(--bandeja-nota-fondo);
    border: 1px solid var(--bandeja-aviso-borde);
  }

  .nota-cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 4px;
  }

  /* Rótulo escrito normal (04/11/2026), como todos los de la Bandeja: el
     candado y el color de nota ya lo distinguen sin la versalita en mono. */
  .nota-rotulo {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--bandeja-titulo);
    font-size: 13px;
    font-weight: 600;
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

  /* La transcripción acompaña al reproductor: se lee como una cita de lo que
     el cliente dijo, no como un dato más de la ficha. Por eso la barra a la
     izquierda y el tamaño menor que el del mensaje. */
  .adjunto-transcripcion {
    margin: 4px 0 0;
    padding-left: 8px;
    border-left: 2px solid var(--v2-line, #e2e8f0);
    font-size: 0.8125rem;
    line-height: 1.45;
    color: var(--v2-slate, #475569);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .adjunto-transcripcion-rotulo {
    font-weight: 600;
  }

  /* El análisis de una foto NO se ve como la transcripción de un audio, y la
     diferencia es deliberada: una transcripción es lo que el cliente dijo;
     un análisis es lo que una máquina cree ver. Por eso tiene su propio
     marco dentro de la burbuja, y el detalle nace cerrado. */
  .analisis {
    margin: 6px 0 0;
    padding: 8px 10px;
    border: 1px solid var(--v2-line, #e2e8f0);
    border-radius: 8px;
    background: color-mix(in srgb, var(--v2-line, #e2e8f0) 22%, transparent);
    font-size: 0.8125rem;
    line-height: 1.45;
  }
  .analisis-titulo {
    font-weight: 600;
    color: var(--v2-slate, #475569);
  }
  /* El resumen es lo único que se ve sin abrir, así que carga todo el peso:
     va en el color del texto normal, no en el apagado de un metadato. */
  .analisis-resumen {
    margin: 3px 0 0;
    color: var(--v2-slate, #475569);
    overflow-wrap: anywhere;
  }
  .analisis-ver {
    margin-top: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--v2-slate, #64748b);
    cursor: pointer;
    list-style: none;
  }
  .analisis-ver::-webkit-details-marker { display: none; }
  .analisis-ver::before {
    content: '▸ ';
    display: inline-block;
  }
  details[open] .analisis-ver::before { content: '▾ '; }
  .analisis-ver:hover { color: var(--v2-slate, #475569); }
  /* Abrir y cerrar sin una línea de JS ni estado: lo hace <details>. El texto
     del control cambia con el mismo mecanismo. */
  .analisis-cerrar { display: none; }
  details[open] .analisis-abrir { display: none; }
  details[open] .analisis-cerrar { display: inline; }
  .analisis-texto {
    margin: 6px 0 0;
    padding-left: 8px;
    border-left: 2px solid var(--v2-line, #e2e8f0);
    color: var(--v2-slate, #475569);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
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
