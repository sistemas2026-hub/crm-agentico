<script>
  /**
   * El compositor: lo que se escribe, lo que se adjunta, lo que se graba y lo
   * que se manda.
   *
   * ES PRESENTACION. No tiene un solo fetch, ni un timer propio, ni toca el
   * microfono, ni decide quien controla la conversacion. Todo eso -- el
   * MediaRecorder, el cronometro, los object URL, el reloj de la ventana de
   * 24 h, los seis caminos de envio y bloqueadoPorIA -- se quedo en la pagina
   * a proposito.
   *
   * POR QUE, si darle ciclo de vida propio parece mas prolijo: hoy esos
   * recursos NO se liberan al desmontar (D29 -- el microfono puede quedar
   * abierto al cambiar de conversacion). Mover su dueno ahora cambiaria cuando
   * nacen y mueren, que es justo lo que la Fase 0 promete no cambiar. D29 se
   * arregla en su propia pista, despues de cerrar la Fase 0A.
   *
   * Por eso son muchas props. Es a proposito: mecanico y equivalente antes que
   * elegante y distinto.
   */
  import { Send, X, Paperclip, Smile, Mic, Image as ImageIcon, FileText, Bot } from '@lucide/svelte';

  let {
    // --- lo que se ve
    conversacion, error = '', escalada = false, enviando = false,
    // --- verdad ya resuelta por el motor y la pagina
    bloqueadoPorIA = false, bloqueadoPorVentana = false,
    interviniendo = false, errorIntervenir = '',
    // --- adjunto y grabacion (el recurso vive en la pagina)
    adjunto = null, grabando = false, grabPausada = false, segundos = 0, limites,
    // --- ventana de 24 h (el reloj vive en la pagina)
    ventanaAbierta = null, ventanaRestante = null, ventanaPorCerrarse = false,
    // --- plantillas
    plantillas = [], cargandoPlantillas = false, errorPlantillas = '',
    enviandoPlantilla = false, plantillaCompleta = false,
    vistaPreviaPlantilla = '', hayPlantillaDeServicio = false,
    // Un rotulo por campo, ya resuelto por plantillas.js: la etiqueta de un
    // parametro nombrado es su nombre, y la de uno posicional solo puede
    // decir donde va. Llega resuelto porque el reparto entre encabezado y
    // cuerpo tiene que ser el mismo que usa el envio.
    /** @type {{hueco: string, parte: string, titulo: string, donde: string, reemplaza: string}[]} */
    etiquetasPlantilla = [],
    plantillaBloqueada = '',
    // --- T6: el desenlace del ultimo intento de devolver a la IA, ya traducido
    //     por devolucion.js. null = el ultimo envio no pidio devolver. Llega
    //     resuelto a proposito: si este componente lo dedujera de la respuesta
    //     del motor, tendria que saber la diferencia entre 'rechazado' e
    //     'incierto', y esa regla vive en un solo lugar.
    /** @type {{estado: string, tono: string, texto: string}|null} */
    avisoDevolucion = null,
    // --- lo que el marcado escribe
    entrada = $bindable(''),
    modo = $bindable('responder'),
    campoTexto = $bindable(),
    adjuntarAbierto = $bindable(false),
    emojisAbiertos = $bindable(false),
    arrastrando = $bindable(false),
    eligiendoPlantilla = $bindable(false),
    plantillaElegida = $bindable(null),
    /** @type {string[]} */
    valoresPlantilla = $bindable([]),
    // --- helpers puros que la pagina tambien usa
    EMOJIS = [], reloj, comoDuracion,
    // --- todo lo que muta, en la pagina
    onEnviar, onGuardarNota, onSoltar, onPegar, onElegirArchivo,
    onQuitarAdjunto, onEnviarAdjunto,
    onGrabar, onPausar, onParar, onCancelarGrabacion,
    onPonerEmoji, onAbrirPlantillas, onElegirPlantilla, onEnviarPlantilla,
    onDevolver, devolviendoAIA = false, errorDevolver = '',
    onIntervenir
  } = $props();

  /* QUÉ DICE LA BANDA, y de qué color. Sale del estado real --quién controla,
     qué modo está elegido, si la ventana está abierta-- y no de un texto
     fijo: la referencia tiene una sola banda porque su pantalla tiene un solo
     estado, y acá hay cinco.

     El tono NO es la señal: adentro va la frase entera. El color sólo
     refuerza, por lo mismo que en el hilo -- un punto de color sin palabra no
     dice QUÉ pasa. */
  const tonoBanda = $derived(
    modo === 'nota' ? 'nota'
      : bloqueadoPorIA ? 'ia'
        : bloqueadoPorVentana ? 'aviso'
          : escalada ? 'humano'
            : 'ia'
  );

  /* EL MISMO ORDEN QUE EL TEXTO, y no es una formalidad: el 22/09/2026 el
     texto decía «ventana cerrada» mientras el sello decía «responde el
     asistente», porque una lista se reordenó y la otra no. Las tres --texto,
     sello y tono-- describen el MISMO estado; si se separan, la banda se
     contradice a sí misma en el mismo renglón.

     El orden es de traba más dura a más blanda: sin el control no se escribe;
     con el control pero sin ventana, tampoco; recién entonces importa si está
     escalada.

     La marca de la derecha: de qué canal es esta salida. En versalita y en
     mono porque es un sello de procedencia, no un dato que se lea. */
  const canalBanda = $derived(
    modo === 'nota' ? 'Interno'
      : modo === 'responder_y_devolver' ? 'Sale y devuelve'
        : bloqueadoPorIA ? 'Responde el asistente'
          : bloqueadoPorVentana ? 'WhatsApp · 24 h'
            : escalada ? 'Canal directo del operador'
              : 'Responde el asistente'
  );

  /* Y por dónde sale, con el estado que de verdad tiene. La ventana de 24 h
     es una regla de WhatsApp: decir «en línea» cuando está cerrada sería
     exactamente lo contrario de lo que pasa. */
  const estadoCanal = $derived(
    conversacion.canal === 'whatsapp'
      ? bloqueadoPorVentana
        ? 'WhatsApp · ventana cerrada'
        : ventanaAbierta
          ? 'WhatsApp · ventana abierta'
          : 'WhatsApp'
      : conversacion.canal
  );
</script>

  <div class="pie">
    {#if error}<p class="v2-error" style="margin:0 0 6px">{error}</p>{/if}
    <!-- Los dos modos, arriba del cuadro. Van acá y no dentro del pie para
         que se lean ANTES de escribir, no después. -->

    <!-- EL DESENLACE DE LA DEVOLUCIÓN, cuando la hubo. No se mezcla con
         `error` a propósito: "no salió" y "no sabemos si salió" son dos cosas
         distintas, y la segunda no es un error -- es lo único honesto que se
         puede decir. El texto lo arma devolucion.js. -->
    {#if avisoDevolucion}
      <p
        class="devolucion devolucion-{avisoDevolucion.tono}"
        role="status"
        aria-live="polite"
      >
        {avisoDevolucion.texto}
      </p>
    {/if}

    <!-- LA VENTANA DE 24 H, ANTES DE ESCRIBIR Y NO DESPUÉS DE FALLAR.
         Sólo aparece en WhatsApp: los otros canales no tienen esta regla y
         heredarla dejaría a alguien sin poder escribir donde nadie se lo
         impide. -->
    <!-- SÓLO CUANDO AVISA ALGO. Medido el 22/09/2026 sobre la columna real:
         esta banda son 48px de 702, y aparecía SIEMPRE -- también para decir
         «ventana abierta», que es el estado normal y no necesita un renglón.

         Los otros dos estados ya tienen dónde vivir, y ahí se leen mejor:

           abierta  -> el sello del canal, a la derecha de la barra, dice
                       «WhatsApp · ventana abierta». Es el mismo dato en un
                       lugar que ya existía.
           cerrada  -> la banda de estado, que es la que contesta «¿le puedo
                       escribir?». Tenerlo en dos bandas apiladas repetía la
                       misma respuesta y se comía 92px juntas.

         Queda sólo el aviso de que ESTÁ POR CERRARSE, que es el único de los
         tres que pide una decisión: escribir ahora o quedarse sin poder. -->
    {#if ventanaPorCerrarse && ventanaAbierta !== false}
      <div class="ventana ventana-avisa" role="status">
        <!-- El rótulo del canal dice de qué sistema viene el límite. No
             aparecía con la ventana abierta y sigue sin aparecer: un
             distintivo permanente en el estado normal es ruido que compite
             con el que sí importa. -->
        <span class="ventana-marca">WhatsApp · 24 h</span>
        <strong>La ventana cierra en {comoDuracion(ventanaRestante ?? 0)}</strong>
        <span class="v2-muted">· después sólo se le puede escribir por plantilla</span>
      </div>
    {/if}

    <!-- Panel y no ventana modal: el hilo tiene que seguir visible mientras
         se elige qué mandar. Media pantalla tapada por un diálogo obliga a
         recordar de memoria de qué se estaba hablando. -->
    {#if eligiendoPlantilla}
      <div class="plantillas">
        <div class="plantillas-top">
          <strong>Plantilla aprobada por Meta</strong>
          <!-- Cuántas hay. El motor ya filtra a APPROVED antes de mandarlas
               (api.py::canales_plantillas), así que todas las de esta lista lo
               están y no hace falta un distintivo por fila diciéndolo. -->
          {#if plantillas.length}
            <span class="plantillas-cuenta v2-num">{plantillas.length} disponibles</span>
          {/if}
          <button
            type="button"
            class="v2-btn v2-btn-sm v2-btn-quiet"
            onclick={() => (eligiendoPlantilla = false)}
            aria-label="Cerrar el selector de plantillas"><X size={14} /></button
          >
        </div>

        {#if cargandoPlantillas}
          <p class="v2-muted" style="margin:0">Buscando las plantillas de la cuenta…</p>
        {:else if errorPlantillas}
          <p class="v2-error" style="margin:0">{errorPlantillas}</p>
        {/if}

        {#if !cargandoPlantillas && !plantillaElegida}
          {#if plantillas.length && !hayPlantillaDeServicio}
            <p class="plantilla-inadecuada">
              <strong>No hay una plantilla adecuada para retomar un caso.</strong>
              Las aprobadas de esta cuenta son de categoría MARKETING: existen para
              promocionar, no para seguir una falla de servicio, y no le llegan a quien
              se dio de baja de mensajes comerciales. Hace falta una plantilla UTILITY
              propia — aprobarla en Meta lleva días. Se pueden mandar igual, pero
              sabiendo eso.
            </p>
          {/if}
          {#if plantillas.length}
            <ul class="plantillas-lista">
              {#each plantillas as p (p.nombre)}
                <li>
                  <button type="button" class="plantilla-item" onclick={() => onElegirPlantilla?.(p)}>
                    <span class="plantilla-nombre">{p.nombre}</span>
                    <span class="v2-muted plantilla-cuerpo">{p.cuerpo}</span>
                    <span class="v2-sub"
                      >{p.categoria} · {p.idioma}{p.variables
                        ? ` · ${p.variables} dato(s) a completar`
                        : ''}</span
                    >
                  </button>
                </li>
              {/each}
            </ul>
          {:else if !errorPlantillas}
            <p class="v2-muted" style="margin:0">
              Esta cuenta no tiene ninguna plantilla aprobada en Meta, así que no hay forma de
              escribirle al cliente fuera de la ventana. Crear y hacer aprobar una lleva días:
              conviene no esperar a necesitarla.
            </p>
          {/if}
        {/if}

        {#if plantillaElegida}
          {#if plantillaBloqueada}
            <p class="v2-error" style="margin:0">{plantillaBloqueada}</p>
          {/if}
          {#each etiquetasPlantilla as etiqueta, i (etiqueta.parte + etiqueta.hueco)}
            <label class="plantilla-var">
              <span class="v2-sub"
                >{etiqueta.titulo}{etiqueta.donde ? ` · ${etiqueta.donde}` : ''} — reemplaza {etiqueta.reemplaza}</span
              >
              <input class="v2-input" bind:value={valoresPlantilla[i]} />
            </label>
          {/each}

          <!-- Vista previa: lo que va a leer el cliente, antes de mandarlo.
               El texto de una plantilla lo aprueba Meta y no se puede
               corregir después de enviada. -->
          <div class="plantilla-previa">
            <span class="v2-sub">Así le va a llegar</span>
            <p>{vistaPreviaPlantilla}</p>
          </div>

          <div class="plantilla-acciones">
            <button
              type="button"
              class="v2-btn v2-btn-sm"
              onclick={() => (plantillaElegida = null)}>Volver a la lista</button
            >
            <button
              type="button"
              class="v2-btn v2-btn-primary"
              onclick={() => onEnviarPlantilla?.()}
              disabled={enviandoPlantilla || !plantillaCompleta}
              aria-busy={enviandoPlantilla}
            >
              <Send size={14} />{enviandoPlantilla ? 'Enviando…' : 'Enviar plantilla'}
            </button>
          </div>
          {#if !plantillaCompleta}
            <span class="v2-sub"
              >Faltan datos por completar. Meta rechaza el envío si no van todos.</span
            >
          {/if}
        {/if}
      </div>
    {/if}

    <form
      class="compositor"
      class:arrastrando
      class:es-nota={modo === 'nota'}
      onsubmit={(e) => onEnviar?.(e)}
      ondragover={(e) => {
        e.preventDefault();
        arrastrando = true;
      }}
      ondragleave={() => (arrastrando = false)}
      ondrop={(e) => onSoltar?.(e)}
    >
      {#if arrastrando}
        <div class="soltar-aca">Soltá el archivo acá</div>
      {/if}

      <!-- ── 1. LA BANDA DE ESTADO ─────────────────────────────────────────
           Lo primero del compositor en la referencia: un punto, qué va a
           pasar con lo que se escriba, y a la derecha por dónde sale.

           Estaba abajo, entre los iconos y el botón de enviar, y ahí llegaba
           tarde: se lee DESPUÉS de haber escrito. Arriba contesta la pregunta
           que uno se hace antes de tipear -- «¿esto le llega al cliente o se
           queda en el equipo?». -->
      <div class="banda banda-{tonoBanda}">
        <span class="banda-punto" aria-hidden="true"></span>
        <span class="banda-texto">
          {#if modo === 'nota'}
            <strong class="nota-interna-aviso">Solo la ve el equipo</strong>
            <span class="v2-muted">· no se le envía al cliente</span>
          {:else if modo === 'responder_y_devolver'}
            <!-- Lo que va a pasar, dicho antes de apretar: el mensaje sale Y la
                 conversación deja de ser tuya. Y la condición, que no es
                 obvia: si el mensaje no sale, la conversación se queda. -->
            <strong class="nota-directo">Se envía y la conversación vuelve a la IA</strong>
            <span class="v2-muted">· solo si el mensaje sale</span>
          {:else if bloqueadoPorIA}
            La atiende la IA · para escribirle al cliente hace falta tomar el control
            <button
              type="button"
              class="v2-btn v2-btn-sm v2-btn-strong"
              onclick={() => onIntervenir?.()}
              disabled={interviniendo}
              aria-busy={interviniendo}
            >
              {interviniendo ? 'Tomando el control…' : 'Intervenir'}
            </button>
            {#if errorIntervenir}<span class="aviso-mal">{errorIntervenir}</span>{/if}
            <!-- Si ADEMAS la ventana está cerrada, se dice acá y no en una
                 banda aparte. Pero va DESPUES y en segundo plano: lo primero
                 es tomar el control, y la plantilla es el problema del paso
                 siguiente. Poner la ventana antes dejaba esta rama --y con
                 ella el botón «Intervenir»-- sin dibujar. -->
            {#if bloqueadoPorVentana}
              <span class="v2-muted">· y la ventana de WhatsApp está cerrada</span>
            {/if}
          {:else if bloqueadoPorVentana}
            <!-- LO QUE ANTES DECIA LA BANDA DE LA VENTANA. Vive acá porque es
                 la respuesta a la misma pregunta que contesta esta banda --
                 «¿le puedo escribir?»-- y tenerlo en dos renglones apilados
                 repetía el mismo «no» dos veces, en 92px. -->
            <strong class="nota-aviso">Ventana de WhatsApp cerrada</strong>
            <span class="v2-muted"
              >· el cliente no escribe hace más de 24 h; hay que usar una
              plantilla aprobada</span
            >
          {:else if escalada}
            <!-- Más visible que antes (§11): cuando está escalada, esto sale
                 DIRECTO al cliente. "Le llega tal cual" no decía quién
                 habla ni que el asistente no interviene. -->
            <strong class="nota-directo">Se envía directo al cliente</strong>
            <span class="v2-muted">· no pasa por el asistente</span>
          {:else}
            Responde el asistente
          {/if}
        </span>
        <span class="banda-canal">{canalBanda}</span>
      </div>

      <!-- ── 2. LA BARRA ───────────────────────────────────────────────────
           Adjuntos y modos ARRIBA del cuadro, como la referencia. Los modos
           eran tres pestañas sobre el compositor y ocupaban un renglón
           entero; acá entran en la misma barra que los iconos.

           Siguen siendo tres estados y no dos: «al cliente», «nota interna» y
           --sólo con la conversación en manos de una persona-- «devolver a la
           IA». La referencia sólo tiene dos porque su pantalla no tiene la
           devolución; el contrato manda sobre el diseño. -->
      <div class="barra">
        <div class="herramientas" hidden={modo === 'nota' || bloqueadoPorIA}>
          <div class="emoji-caja">
            <button
              type="button"
              class="v2-btn v2-btn-quiet accion-icono"
              aria-label="Emoji"
              title="Emoji"
              aria-expanded={emojisAbiertos}
              onclick={() => (emojisAbiertos = !emojisAbiertos)}><Smile size={18} /></button
            >
            {#if emojisAbiertos}
              <div class="emoji-panel" role="group" aria-label="Elegí un emoji">
                {#each EMOJIS as e (e)}
                  <button type="button" onclick={() => onPonerEmoji?.(e)}>{e}</button>
                {/each}
              </div>
            {/if}
          </div>

          <!-- Menú de dos opciones. El tipo se sigue deduciendo del archivo
               (tipoDe) -- esto no cambia qué se manda: cambia el DIÁLOGO que
               abre el navegador. "Imagen" filtra a jpeg/png, que es justo lo
               que WhatsApp acepta, y evita que alguien elija un HEIC del
               celular para que se lo rechacen después. -->
          <div class="emoji-caja">
            <button
              type="button"
              class="v2-btn v2-btn-quiet accion-icono"
              aria-label="Adjuntar"
              title="Adjuntar"
              aria-expanded={adjuntarAbierto}
              onclick={() => (adjuntarAbierto = !adjuntarAbierto)}><Paperclip size={17} /></button
            >
            {#if adjuntarAbierto}
              <div class="menu-adjuntar" role="group" aria-label="Qué querés adjuntar">
                <label>
                  <ImageIcon size={14} /> Imagen
                  <input type="file" hidden accept="image/jpeg,image/png" onchange={(e) => onElegirArchivo?.(e)} />
                </label>
                <label>
                  <FileText size={14} /> Documento
                  <input type="file" hidden onchange={(e) => onElegirArchivo?.(e)} />
                </label>
              </div>
            {/if}
          </div>

          {#if !grabando}
            <button
              type="button"
              class="v2-btn v2-btn-quiet accion-icono"
              aria-label="Grabar una nota de voz"
              title="Grabar audio"
              onclick={() => onGrabar?.()}><Mic size={18} /></button
            >
          {/if}
        </div>
        <span class="barra-sep" aria-hidden="true"></span>
        <div class="modos" role="group" aria-label="Qué estás escribiendo">
          <button
            type="button"
            class="modo"
            aria-pressed={modo === 'responder'}
            onclick={() => (modo = 'responder')}>Al cliente</button
          >
          <button
            type="button"
            class="modo modo-nota"
            aria-pressed={modo === 'nota'}
            onclick={() => (modo = 'nota')}>Nota interna</button
          >
          <!-- Sólo con la conversación en manos de una persona: devolverla supone
               tenerla. Con la IA atendiendo, el motor responde 409 y el botón no
               tendría a qué. -->
          <!-- DEVOLVER A LA IA ES UNA ACCION, NO UN MODO (22/09/2026).
               Estaba como tercer modo: elegirlo no devolvia nada, habia que
               ademas escribir y enviar. En produccion se apreto esperando que
               devolviera; el cliente escribio dos veces mas y la IA no
               contesto, porque el control seguia en 'humano'. Medido en la
               base: quedo un evento 'intervencion' y ningun 'devuelta_a_ia'.

               Ahora hace lo que su nombre dice, y con algo escrito hace las
               dos cosas -- lo manda Y devuelve. La garantia de siempre se
               conserva: con mensaje, la conversacion vuelve SOLO si el
               mensaje sale. Sin mensaje, vuelve y punto. -->
          {#if escalada}
            <button
              type="button"
              class="barra-boton barra-devolver"
              onclick={() => onDevolver?.()}
              disabled={enviando || devolviendoAIA}
              aria-busy={devolviendoAIA}
              title={entrada.trim()
                ? 'Envía lo que escribiste y devuelve la conversación al asistente'
                : 'Devuelve la conversación al asistente sin enviar nada'}
            >
              <Bot size={13} />
              {devolviendoAIA ? 'Devolviendo…' : 'Devolver a la IA'}
            </button>
          {/if}
        </div>
        <!-- PLANTILLAS SIEMPRE A LA VISTA, no sólo con la ventana cerrada.
             Una plantilla aprobada sirve igual con la ventana abierta, y
             tenerla escondida detrás de un estado hacía que nadie supiera que
             existía hasta que ya no se podía escribir. -->
        <button
          type="button"
          class="barra-boton"
          onclick={() => onAbrirPlantillas?.()}
          disabled={cargandoPlantillas}
        >
          <FileText size={13} /> Plantillas
        </button>

        {#if errorDevolver}
          <span class="barra-mal">{errorDevolver}</span>
        {/if}

        <!-- Por dónde sale y si el canal está disponible. La ventana de 24 h
             es de WhatsApp, así que el estado se dice con ese dato real y no
             con un «Online» fijo. -->
        <span class="barra-canal">{estadoCanal}</span>
      </div>


      <!-- Grabando: el cronómetro y los tres controles que el pedido exige,
           y NINGUNO que mande. Parar deja la nota como adjunto pendiente de
           confirmación -- se puede escuchar antes de mandarla. -->
      {#if grabando}
        <div class="grabando">
          <span class="grabando-punto" aria-hidden="true"></span>
          <span class="v2-num grabando-reloj">{reloj(segundos)}</span>
          <button type="button" class="v2-btn v2-btn-sm" onclick={() => onPausar?.()}>
            {grabPausada ? 'Seguir' : 'Pausar'}
          </button>
          <button type="button" class="v2-btn v2-btn-sm v2-btn-danger reiniciar-discreto" onclick={() => onCancelarGrabacion?.()}>
            Cancelar
          </button>
          <button type="button" class="v2-btn v2-btn-sm v2-btn-strong" onclick={() => onParar?.()}>
            Listo
          </button>
        </div>
      {/if}

      <!-- El adjunto elegido, ANTES de mandarlo. Nada sale sin pasar por
           acá: ni un archivo arrastrado, ni una captura pegada, ni una nota
           de voz recién grabada. -->
      {#if adjunto}
        <div class="adjunto-previo">
          {#if adjunto.tipo === 'image'}
            <img src={adjunto.url} alt="Lo que vas a enviar" />
          {:else if adjunto.tipo === 'audio'}
            <!-- svelte-ignore a11y_media_has_caption -->
            <audio controls src={adjunto.url}></audio>
          {:else}
            <span class="adjunto-icono"><Paperclip size={18} /></span>
          {/if}
          <span class="adjunto-datos">
            <b>{adjunto.nombre}</b>
            <span class="v2-muted v2-num">
              {(adjunto.bytes / 1048576).toFixed(2)} MB
              {#if !(limites?.[adjunto.tipo]?.acepta_pie ?? true)}
                · el texto va como mensaje aparte
              {/if}
            </span>
          </span>
          <button
            type="button"
            class="v2-btn v2-btn-sm v2-btn-quiet"
            onclick={() => onQuitarAdjunto?.()}
            aria-label="Quitar el archivo"><X size={14} /></button
          >
        </div>
      {/if}

      <!-- UNA FILA CUANDO NO SE PUEDE ESCRIBIR. Son 64px de caja donde
           nadie puede tipear, en una pantalla donde el hilo se queda con el
           18%. El texto de adentro explica por qué está bloqueado, así que la
           caja sigue diciendo algo -- pero en la mitad de alto. -->
      <textarea
        class="compositor-texto"
        class:texto-inerte={bloqueadoPorVentana || bloqueadoPorIA}
        bind:this={campoTexto}
        bind:value={entrada}
        onpaste={(e) => onPegar?.(e)}
        rows={bloqueadoPorVentana || bloqueadoPorIA ? 1 : 2}
        placeholder={bloqueadoPorIA
          ? 'La IA está atendiendo — dejá una nota interna para el equipo'
          : bloqueadoPorVentana
          ? 'La ventana de WhatsApp está cerrada — usá una plantilla'
          : modo === 'nota'
            ? 'Nota para el equipo — el cliente no la ve…'
            : escalada
              ? 'Escribí tu respuesta…'
              : 'Continuar la conversación…'}
        disabled={enviando || bloqueadoPorVentana || bloqueadoPorIA}
        onkeydown={(e) => {
          // Enter envia, Shift+Enter hace salto de linea: es lo que la mano
          // ya espera de un chat.
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (modo === 'nota') onGuardarNota?.();
            else onEnviar?.();
          }
        }}
      ></textarea>
      <!-- ── 4. EL PIE ─────────────────────────────────────────────────────
           La pista del teclado a la izquierda y el envío a la derecha, como
           la referencia. La pista no se dibuja cuando Enter no manda nada:
           con la ventana cerrada o con la IA atendiendo, dejarla puesta
           sería invitar al gesto que no funciona. -->
      <div class="compositor-pie">
        <span class="pista">
          {#if !bloqueadoPorVentana && !bloqueadoPorIA}
            <kbd class="v2-kbd">Enter</kbd> envía · <kbd class="v2-kbd">Shift</kbd>+<kbd
              class="v2-kbd">Enter</kbd
            > salto de línea
          {/if}
        </span>

        {#if modo === 'nota'}
          <button
            class="v2-btn v2-btn-strong"
            type="button"
            onclick={() => onGuardarNota?.()}
            disabled={enviando || !entrada.trim()}
            aria-busy={enviando}
          >
            {enviando ? 'Guardando…' : 'Guardar nota'}
          </button>
        {:else if adjunto}
          <button
            class="v2-btn v2-btn-primary"
            type="button"
            onclick={() => onEnviarAdjunto?.()}
            disabled={enviando || bloqueadoPorVentana || bloqueadoPorIA}
            aria-busy={enviando}
          >
            <Send size={14} />{enviando ? 'Enviando…' : 'Enviar archivo'}
          </button>
        {:else if bloqueadoPorVentana && !bloqueadoPorIA}
          <button
            class="v2-btn v2-btn-primary"
            type="button"
            onclick={() => onAbrirPlantillas?.()}
          >
            Elegir plantilla
          </button>
        {:else}
          <button
            class="v2-btn v2-btn-primary"
            type="submit"
            disabled={enviando || bloqueadoPorIA || !entrada.trim()}
            aria-busy={enviando}
          >
            <Send size={14} />{#if modo === 'responder_y_devolver'}
              {enviando ? 'Enviando y devolviendo…' : 'Enviar y devolver'}
            {:else}{enviando ? 'Enviando…' : 'Enviar'}{/if}
          </button>
        {/if}
      </div>
    </form>
  </div>

<style>

  .aviso-mal {
    flex: none;
    color: var(--bandeja-error);
  }

  /* EL AIRE DEL COMPOSITOR, apretado el 22/09/2026. Medido sobre la
     columna real: el compositor se llevaba 322px de 702 y 79 de esos eran
     margen y padding entre cinco bandas de 40-48px. Bajarlos no saca ni una
     palabra de la pantalla -- saca el espacio vacío entre ellas, que es de
     donde tiene que salir el alto que le falta al hilo. */
  .pie {
    flex: none;
    padding: 0 16px 10px;
  }

  /* ── nota interna ───────────────────────────────────────────────────── */
  /* --- ventana de 24 h ---------------------------------------------------
     Un renglon, no una tarjeta: informa antes de escribir y no compite con
     el hilo. Solo se pone fuerte cuando cambia lo que se puede hacer. */
  .ventana {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    font-size: 11.5px;
    color: var(--bandeja-texto-2);
    padding: 5px 8px;
    margin-bottom: 5px;
    border-radius: 8px;
    background: var(--bandeja-canvas);
  }

  /* Advertencia, no error: el filete ámbar es la misma señal que usa el
     handoff sin dueño. Se puede seguir escribiendo con normalidad -- lo que
     cambia es que conviene hacerlo ahora. */
  .ventana-avisa {
    color: var(--bandeja-texto);
    background: var(--bandeja-aviso-fondo);
    border-left: 3px solid var(--bandeja-aviso);
  }

  /* Cerrada SÍ es un límite en vigor, y lleva el filete del mismo color que
     su distintivo. No es rojo: no se rompió nada, hay otra forma de escribir. */
  .ventana-cerrada {
    border-left: 3px solid var(--bandeja-borde-fuerte);
  }

  .ventana-cerrada {
    color: var(--bandeja-texto);
    background: var(--bandeja-aviso-fondo);
  }

  /* Empuja el botón al extremo: el aviso se lee de izquierda a derecha y la
     acción queda al final, no metida entre el texto. */
  /* `.ventana-cerrada button` se fue con el boton duplicado (22/09/2026).
     Su unico consumidor era ese segundo «Elegir plantilla»; svelte-check lo
     reportaba como selector sin usar. */

  /* El rótulo del canal, con la misma forma que los distintivos de la cola:
     mono, versalita y un filete. Dice DE QUÉ sistema viene el límite -- no es
     una decisión de Dexter, es la ventana de 24 h de WhatsApp. */
  .plantillas-cuenta {
    font-family: var(--bandeja-mono);
    font-size: 10.5px;
    color: var(--bandeja-texto-2);
  }

  .ventana-marca {
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    padding: 1px 5px;
    border: 1px solid var(--bandeja-borde-fuerte);
    border-radius: var(--bandeja-radio-sm);
    color: var(--bandeja-texto-2);
    background: var(--bandeja-superficie);
    white-space: nowrap;
  }


  /* Un cuadro deshabilitado que se ve igual que uno normal invita a
     escribir y no avisa hasta que alguien ya escribio. */
  /* Bloqueado no hace falta el piso: no se va a escribir dentro. */
  .texto-inerte {
    background: var(--bandeja-canvas);
    cursor: not-allowed;
    /* Sin piso: bloqueado no se va a escribir adentro, y los 44px de
       `.compositor-texto` dejaban el cuadro igual de alto que con dos filas
       -- o sea que `rows=1` no ahorraba nada. */
    min-height: 0;
  }


  /* --- selector de plantillas -------------------------------------------- */
  .plantillas {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
    margin-bottom: 8px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
    background: var(--bandeja-superficie);
  }

  .plantillas-top {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .plantillas-top strong {
    font-size: 12px;
  }

  .plantillas-top button {
    margin-left: auto;
  }

  .plantilla-inadecuada {
    margin: 0;
    padding: 8px;
    border-radius: 8px;
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-texto);
    font-size: 11.5px;
    line-height: 1.45;
  }

  .plantillas-lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .plantilla-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    text-align: left;
    font: inherit;
    padding: 8px;
    border: 1px solid var(--bandeja-superficie-suave);
    border-radius: 8px;
    background: var(--bandeja-canvas);
    cursor: pointer;
  }

  .plantilla-item:hover {
    border-color: var(--bandeja-borde);
  }

  .plantilla-nombre {
    font-weight: 600;
    font-size: 12px;
    color: var(--bandeja-texto);
  }

  /* El cuerpo puede ser largo: se recorta en una linea para que la lista se
     pueda barrer de un vistazo. El texto completo se ve en la vista previa,
     que es donde importa. */
  .plantilla-cuerpo {
    font-size: 11.5px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .plantilla-var {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .plantilla-previa {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 8px;
    border-radius: 8px;
    background: var(--bandeja-canvas);
  }

  .plantilla-previa p {
    margin: 0;
    font-size: 12.5px;
    color: var(--bandeja-texto);
    white-space: pre-wrap;
  }

  .plantilla-acciones {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }


  /* Con wrap desde que son tres: "Responder y devolver a IA" es mucho más
     largo que los dos de antes, y sin esto los tres se comprimen hasta que el
     texto se corta en pantallas angostas. */
  /* LOS MODOS, DENTRO DE LA BARRA. Eran tres pestañas en un renglón propio
     sobre el compositor: 30px de alto para tres palabras, en una pantalla
     donde el hilo pelea por cada píxel. Acá comparten renglón con los
     iconos, como en la referencia. */
  .modos {
    display: flex;
    align-items: center;
    gap: 3px;
    min-width: 0;
  }

  /* SE VEN SIEMPRE, no solo el elegido. Con el filete transparente parecian
     texto suelto: no habia forma de saber que «Nota interna» era algo que se
     podia apretar hasta que estaba apretado. Un control que solo se ve cuando
     ya lo usaste no sirve para descubrirlo. */
  .modo {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
    font: inherit;
    font-size: 11px;
    color: var(--bandeja-texto-2);
    padding: 3px 7px;
    border-radius: 3px;
    white-space: nowrap;
    cursor: pointer;
  }

  .modo:hover {
    color: var(--bandeja-texto);
  }

  .modo[aria-pressed='true'] {
    color: var(--bandeja-texto);
    font-weight: 650;
    border-color: var(--bandeja-borde-fuerte);
    background: var(--bandeja-superficie-suave);
  }


  .modo:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .devolucion {
    margin: 0 0 6px;
    padding: 7px 10px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-size: 12.5px;
    line-height: 1.45;
  }
  .devolucion-ok {
    color: var(--bandeja-ia);
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
  }
  /* Ámbar, no rojo: "no pudimos confirmar" no es un fallo, y pintarlo de rojo
     empujaría a reintentar un mensaje que pudo haber salido. */
  .devolucion-aviso {
    color: var(--bandeja-aviso);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }
  .devolucion-mal {
    color: var(--bandeja-error);
    background: var(--bandeja-error-fondo);
    border-color: var(--bandeja-error-borde);
  }

  .modo-nota[aria-pressed='true'] {
    color: var(--bandeja-nota);
    border-color: color-mix(in srgb, var(--bandeja-nota) 45%, transparent);
  }


  /* El compositor entero cambia, no una pestaña chiquita: lo que hay que
     hacer imposible es escribir algo interno creyendo que es privado. */
  .compositor.es-nota {
    background: color-mix(in srgb, var(--bandeja-nota) 9%, transparent);
    border: 1px dashed color-mix(in srgb, var(--bandeja-nota) 45%, transparent);
    border-radius: 9px;
    padding: 8px;
  }

  .compositor.es-nota .compositor-texto {
    background: transparent;
  }

  .nota-interna-aviso {
    color: var(--bandeja-nota);
  }



  /* ── compositor ─────────────────────────────────────────────────────── */
  .compositor {
    position: relative;
  }

  .compositor.arrastrando {
    outline: 2px dashed var(--bandeja-humano);
    outline-offset: 3px;
    border-radius: 8px;
  }

  /* La zona de destino tiene que decirse, no insinuarse: quien arrastra un
     archivo no sabe si va a caer en el chat o en la pestaña del navegador. */
  .soltar-aca {
    position: absolute;
    inset: 0;
    z-index: 2;
    display: grid;
    place-items: center;
    border-radius: 8px;
    background: color-mix(in srgb, var(--bandeja-humano) 10%, var(--bandeja-superficie));
    color: var(--bandeja-humano);
    font-weight: 650;
    font-size: 13px;
    pointer-events: none;
  }


  .herramientas {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  /* 34px de lado: un icono de 17px con padding llegaba a 26, que es de los
     objetivos que se fallan cuando se atiende con prisa. */
  /* 40px de AREA con el dibujo en 17: lo que se apunta es el area, no el
     trazo. A 34 se leian como decoracion y a 38 seguian chicos -- medido en
     la pantalla, no en el codigo. */
  .accion-icono {
    min-width: 40px;
    min-height: 40px;
    padding: 0;
    justify-content: center;
    cursor: pointer;
    color: var(--bandeja-texto-2);
    border-radius: 8px;
  }

  .accion-icono:hover {
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto);
  }

  .accion-icono:focus-visible {
    outline: 2px solid var(--bandeja-humano);
    outline-offset: 2px;
  }


  .emoji-caja {
    position: relative;
  }

  .emoji-panel {
    position: absolute;
    bottom: calc(100% + 6px);
    left: 0;
    z-index: 5;
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 2px;
    padding: 6px;
    background: var(--bandeja-superficie);
    border: 1px solid var(--bandeja-borde);
    border-radius: 9px;
    box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  }

  .emoji-panel button {
    border: 0;
    background: none;
    font-size: 18px;
    line-height: 1;
    padding: 5px;
    border-radius: 6px;
    cursor: pointer;
  }

  .emoji-panel button:hover {
    background: var(--bandeja-superficie-suave);
  }

  .menu-adjuntar {
    position: absolute;
    bottom: calc(100% + 6px);
    left: 0;
    z-index: 5;
    display: flex;
    flex-direction: column;
    min-width: 160px;
    padding: 4px;
    background: var(--bandeja-superficie);
    border: 1px solid var(--bandeja-borde);
    border-radius: 9px;
    box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  }

  .menu-adjuntar label {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    font-size: 12.5px;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
  }

  .menu-adjuntar label:hover {
    background: var(--bandeja-superficie-suave);
  }


  .adjunto-previo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px;
    margin-bottom: 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
  }

  .adjunto-previo img {
    width: 56px;
    height: 56px;
    object-fit: cover;
    border-radius: 6px;
    flex: none;
  }

  .adjunto-previo audio {
    height: 34px;
    max-width: 240px;
  }

  .adjunto-icono {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 6px;
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    flex: none;
  }

  .adjunto-datos {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    font-size: 12px;
  }

  .adjunto-datos b {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }


  /* El Cancelar de la grabacion. La clase se llama asi por herencia: nacio
     compartida con "Reiniciar (prueba)", que vivio en ConversationHeader
     hasta 1.4B y ya no existe -- este boton quedo como su unico consumidor.
     El nombre no se cambia ahora: renombrar es limpieza, y esta fase pinta.

     Baja de opacidad hasta que se la busca con el mouse: cancelar una
     grabacion existe, se encuentra, y no compite con Enviar. */
  .reiniciar-discreto {
    opacity: 0.62;
    font-size: 10.8px;
  }

  .reiniciar-discreto:hover,
  .reiniciar-discreto:focus-visible {
    opacity: 1;
  }

  .grabando {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 9px;
    margin-bottom: 6px;
    border: 1px solid color-mix(in srgb, var(--bandeja-error) 35%, transparent);
    border-radius: 8px;
    font-size: 12.5px;
  }

  .grabando-punto {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--bandeja-error);
    animation: latir 1.1s ease-in-out infinite;
    flex: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .grabando-punto {
      animation: none;
    }
  }

  .grabando-reloj {
    font-weight: 700;
    color: var(--bandeja-error);
    margin-right: auto;
  }


  /* Que sale directo al cliente no puede leerse igual que "Enter envía". */
  .nota-directo {
    color: var(--bandeja-humano);
  }


  .compositor {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--bandeja-borde);
    /* El compositor se mide a SÍ MISMO, no a la ventana. Con la columna de
       contexto abierta mide 564px en una pantalla de 1440, así que una regla
       colgada de `@media` no se enteraba de que estaba angosto. Ver el
       `@container` de abajo. */
    container-type: inline-size;
  }

  .compositor-texto {
    width: 100%;
    resize: vertical;
    /* El piso vale para el cuadro EN USO. Bloqueado, `rows=1` no alcanzaba:
       los 44px lo dejaban igual de alto que con dos filas, y la mitad del
       ahorro se perdia en el piso. */
    min-height: 44px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
    padding: 9px 11px;
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto);
    font-family: inherit;
    font-size: calc(var(--v2-fs) - 0.5px);
    line-height: 1.4;
  }

  /* EL FOCO SE NOTA SIN GRITAR. Eran 2px de azul rodeando todo el cuadro, y
     como el cuadro ocupa el ancho del compositor quedaba un marco azul
     permanente mientras se escribe -- que es TODO el tiempo que dura la
     tarea. Un filete del color de la accion y un halo suave dicen lo mismo:
     el cursor esta acá. */
  .compositor-texto:focus {
    outline: none;
    border-color: var(--bandeja-humano);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--bandeja-humano) 14%, transparent);
  }

  .compositor-texto:disabled {
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    cursor: not-allowed;
  }

  /* Igual que los modos: "Enviar y devolver" y su "Enviando y devolviendo…"
     son mas anchos que "Enviar", y el pie tambien lleva la pista del canal a
     la izquierda. Que baje en vez de apretarse. */
  .compositor-pie {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  /* La pista del teclado. Vacía cuando Enter no manda nada, y entonces no
     ocupa nada: es un `span` sin contenido, y el `justify-content` del pie
     deja el botón solo a la derecha. */
  .pista {
    min-width: 0;
    font-size: 10.5px;
    color: var(--bandeja-texto-3);
  }


  /* El orden de sacrificio, angosto: lo ultimo que se pierde es poder
     escribir. La fila del compositor tiene tres cosas --herramientas, aviso,
     boton-- y angosta no entran; el AVISO es lo que se va a un renglon
     propio, nunca el boton ni los iconos, que son con lo que se trabaja.
     Encogerlo todo para que entre en una linea los deja ilegibles a los tres.

     MIDE EL COMPOSITOR, NO LA VENTANA. Era `@media (max-width: 560px)`, y por
     eso no se aplicaba en el caso que más importa: con la columna de contexto
     abierta el compositor mide 564px aunque la ventana tenga 1440. Ahí el aviso
     NO se iba a su renglón, envolvía el BOTÓN, y `justify-content:
     space-between` lo dejaba solo en la segunda línea contra el borde
     IZQUIERDO -- la acción principal de la pantalla cambiaba de esquina según
     el ancho. Medido el 21/09/2026: "Enviar" en x=568 a 1440px y a 1024px.

     600 y no 560: los 564px medidos caían justo del lado de afuera. */
  @container (max-width: 600px) {
    .compositor-pie {
      flex-wrap: wrap;
      row-gap: 6px;
    }
    .compositor-nota {
      order: 3;
      flex-basis: 100%;
    }
    /* El panel de emoji se sale por la izquierda si se ancla al boton en una
       pantalla angosta: pasa a ocupar el ancho del compositor. */
    .emoji-panel {
      left: 0;
      right: 0;
      grid-template-columns: repeat(auto-fill, minmax(38px, 1fr));
    }
    .grabando {
      flex-wrap: wrap;
    }
    .grabando-reloj {
      margin-right: 0;
    }
    /* Una previsualizacion de 56px al lado de un nombre largo deja el nombre
       en dos caracteres. */
    .adjunto-previo {
      flex-wrap: wrap;
    }
    .adjunto-datos {
      flex-basis: 100%;
    }
  }

  /* ── LA BANDA DE ESTADO ──────────────────────────────────────────────────
     Un renglón sobre la barra: punto, qué pasa con lo que se escriba, y de
     qué canal sale. Los cuatro tonos salen de los mismos tokens que usan el
     hilo y la cola -- que la nota interna sea ámbar acá y ámbar allá no es
     una coincidencia, es la misma pregunta contestada igual. */
  .banda {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 9px;
    margin-bottom: 5px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-size: 11.5px;
    line-height: 1.35;
  }

  .banda-punto {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
  }

  .banda-texto {
    flex: 1 1 auto;
    min-width: 0;
    color: var(--bandeja-texto-2);
  }

  /* El sello de la derecha: de dónde sale esto. Mono y versalita, como el
     resto de lo que rotula en la Bandeja. */
  .banda-canal {
    flex: none;
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    opacity: 0.75;
  }

  .banda-humano {
    color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
  }
  .banda-ia {
    color: var(--bandeja-ia);
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
  }
  .banda-nota {
    color: var(--bandeja-nota);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }
  .banda-aviso {
    color: var(--bandeja-aviso);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }

  /* ── LA BARRA ────────────────────────────────────────────────────────────
     Iconos, modos y plantillas en un renglón, con filete abajo como la
     referencia. Envuelve antes que recortar: en angosto los modos bajan
     solos, y ninguno de los controles desaparece. */
  .barra {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    padding-bottom: 5px;
    margin-bottom: 5px;
    border-bottom: 1px solid var(--bandeja-borde);
  }

  .barra-sep {
    flex: none;
    width: 1px;
    height: 14px;
    margin: 0 3px;
    background: var(--bandeja-borde);
  }

  .barra-boton {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 7px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie);
    font: inherit;
    font-size: 11px;
    color: var(--bandeja-texto-2);
    white-space: nowrap;
    cursor: pointer;
  }
  .barra-boton:hover:not(:disabled) {
    color: var(--bandeja-texto);
    border-color: var(--bandeja-borde-fuerte);
  }
  .barra-boton:disabled {
    opacity: 0.55;
    cursor: default;
  }

  /* Por dónde sale, al borde derecho. `margin-left:auto` y no un espaciador:
     cuando la barra envuelve, esto se va con su renglón en vez de quedar
     colgado en el medio. */
  /* DEVOLVER SE PINTA CON EL VIOLETA DE LA IA, el mismo de la cola, del
     encabezado y de las burbujas: es la misma pregunta --quien la lleva-- y
     conviene que se responda con el mismo color en todas las pantallas.
     Y resalta siempre, porque es una accion disponible, no un estado. */
  .barra-devolver {
    color: var(--bandeja-ia);
    border-color: var(--bandeja-ia-borde);
    background: var(--bandeja-ia-fondo);
    font-weight: 600;
  }
  .barra-devolver:hover:not(:disabled) {
    color: var(--bandeja-ia);
    border-color: var(--bandeja-ia);
  }

  .barra-mal {
    font-size: 10.5px;
    color: var(--bandeja-error);
  }

  .barra-canal {
    margin-left: auto;
    flex: none;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    color: var(--bandeja-texto-3);
    white-space: nowrap;
  }

  /* La barra vive DENTRO del cuadro del compositor, así que los iconos ya no
     necesitan los 34px que tenían cuando estaban sueltos en el pie. */
  .barra .herramientas {
    display: flex;
    align-items: center;
    gap: 2px;
    margin: 0;
  }

</style>
