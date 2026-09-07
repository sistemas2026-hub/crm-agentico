<script>
  import { untrack } from 'svelte';
  import { invalidate, goto } from '$app/navigation';
  import { enhance } from '$app/forms';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import MarcarEjemplo from '$lib/components/manual/MarcarEjemplo.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import {
    TriangleAlert,
    ChevronDown,
    ArrowRight,
    ArrowLeft,
    CircleCheck,
    CircleX,
    Send,
    Phone,
    User,
    PanelRight,
    X,
    Paperclip,
    RotateCcw,
    ShieldCheck,
    Smile,
    Mic,
    Image as ImageIcon,
    FileText
  } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  // untrack: la conversacion/hilo/caso se mutan localmente despues (enviar(),
  // la asignacion) -- capturar el valor inicial es lo que se quiere, no
  // seguir a `data` en cada re-render (mismo patron que goals/[id]/edit).
  //
  // Este componente se REMONTA por completo al pasar de una conversacion a
  // otra -- ver el {#key abierta} en +layout.svelte -- asi que este
  // untrack corre de nuevo, fresco, en cada chat. Se probaron dos versiones
  // de un $effect que resincronizaba sin remontar (para evitar el parpadeo),
  // pero en pruebas reales (grabaciones de Jam, agosto 2026) el panel se
  // quedaba mostrando la conversacion anterior pese al effect -- se volvio a
  // este enfoque, mas simple y con la garantia estructural de Svelte de que
  // un componente remontado siempre arranca de cero.
  let conversacion = $state(untrack(() => data.conversacion));
  let mensajes = $state(untrack(() => data.mensajes ?? []));
  let caso = $state(untrack(() => data.caso));
  let owners = $state(untrack(() => data.owners ?? []));
  let herramientas = $state(untrack(() => data.herramientas ?? []));
  let diagnostico = $state(untrack(() => data.diagnostico ?? null));
  let casos = $state(untrack(() => data.casos ?? []));

  // Que significa cada bloqueo, en el idioma de quien atiende. Un codigo como
  // PRECONDICION_NO_CUMPLIDA no le dice nada a alguien de soporte -- y de
  // esto depende que haga lo correcto: si el sistema lo freno por falta de
  // identidad, la accion es pedir la cedula, no reportar que la API fallo.
  const MOTIVO_BLOQUEO = {
    IDENTIDAD_NO_VERIFICADA: 'pidió datos de cuenta sin haber confirmado quién es',
    IDENTIDAD_NO_RESUELTA: 'no se pudo establecer de qué cliente se trata',
    PRECONDICION_NO_CUMPLIDA: 'quiso ejecutar algo sin el paso previo que exige el procedimiento',
    FALTA_HABLAR_CON_EL_CLIENTE: 'la acción interrumpe el servicio y el cliente todavía no dijo qué le pasa',
    HERRAMIENTA_DESCONOCIDA: 'intentó usar algo que este rol no tiene permitido',
    LIMITE_DE_CONVERSACION: 'se alcanzó el tope de pasos de la conversación'
  };

  // --- qué pasó acá, en cuatro renglones ------------------------------------
  // Lo que se le prometió al cliente no está guardado en ningún campo: es el
  // mensaje que el asistente mandó al escalar. Se lo busca por CERCANÍA en el
  // tiempo a 'escalada_en' y no por su texto, porque ese texto lo redacta el
  // modelo y cambia cada vez que alguien mejora el prompt. Después de escalar
  // el asistente sigue acusando recibo, así que "el último" no sirve: el que
  // importa es el de ese momento.
  let prometido = $derived.by(() => {
    if (!conversacion?.escalada_en) return '';
    const t = new Date(conversacion.escalada_en).getTime();
    let mejor = null;
    let dist = Infinity;
    for (const m of mensajes) {
      if (m.rol !== 'assistant' || !m.contenido) continue;
      const d = Math.abs(new Date(m.creado_en).getTime() - t);
      if (d < dist) { dist = d; mejor = m; }
    }
    // Si el mensaje más cercano está a más de cinco minutos de la escalada,
    // no es el anuncio: es otra cosa que pasó cerca. Mejor no decir nada que
    // afirmar que le prometimos algo que no le dijimos.
    return dist <= 5 * 60 * 1000 ? (mejor?.contenido ?? '') : '';
  });

  // Qué hizo la IA, sacado de la traza. Los nombres de herramienta los declara
  // cada empresa en su config, así que acá NO puede haber una tabla que
  // traduzca 'consultar_mi_servicio' a "Consultó el servicio": el próximo ISP
  // que se conecte tiene otras herramientas y esa tabla dejaría de coincidir
  // en silencio. Se humaniza el nombre y se conjuga el verbo, que es lo que
  // se puede hacer sin saber de qué empresa se trata.
  //
  // Deduplicado: el asistente llama a la misma herramienta varias veces en un
  // caso largo, y catorce renglones repetidos no son un resumen.
  let hizoLaIA = $derived.by(() => {
    const vistas = new Map();
    for (const h of herramientas) {
      const previo = vistas.get(h.herramienta);
      // Un bloqueo o un error pesa más que un éxito: si la misma herramienta
      // corrió bien y además se bloqueó, lo que hay que contar es el bloqueo.
      const rango = h.es_bloqueo ? 2 : h.exito ? 0 : 1;
      if (!previo || rango > previo.rango) {
        vistas.set(h.herramienta, { rango, llamada: h });
      }
    }
    return [...vistas.values()]
      // Primero lo que salió mal: es lo que cambia lo que hay que hacer.
      .sort((a, b) => b.rango - a.rango)
      .map(({ rango, llamada }) => ({
        estado: rango === 2 ? 'bloqueo' : rango === 1 ? 'error' : 'ok',
        texto: llamada.herramienta.replaceAll('_', ' '),
        detalle: rango === 2 ? (MOTIVO_BLOQUEO[llamada.codigo_error] ?? 'el sistema la frenó')
               : rango === 1 ? 'falló el sistema externo'
               : ''
      }));
  });

  const motivoLabel = (/** @type {string} */ m) => (m ? m.replaceAll('_', ' ') : '');

  /** Lo primero que escribió el cliente. Es el respaldo de "Qué quiere"
      cuando el modelo no dejó un resumen: no es tan bueno, pero es de él y es
      cierto -- y sirve mucho más que un renglón ausente. */
  let primerPedido = $derived.by(() => {
    const m = mensajes.find((x) => x.rol === 'user' && (x.contenido ?? '').trim());
    return (m?.contenido ?? '').trim();
  });

  // Las CUATRO preguntas, siempre las cuatro. Antes se filtraban las vacías, y
  // el resultado era que en 49 de las 51 conversaciones escaladas el bloque
  // mostraba solo "Le prometimos" y "Qué hizo la IA" -- justo las dos que NO
  // dicen qué pide el cliente ni qué falta hacer. Medido contra produccion:
  // 'resumen' y 'escalada_siguiente_paso' los escribe el modelo al escalar y
  // eso existe desde el 06/09/2026; todo lo anterior los tiene en null.
  //
  // Un renglón que falta se lee como que la pantalla está incompleta. Uno que
  // dice qué falta y por qué se lee como información. Y el orden es el de
  // quien toma el caso: qué pide, qué se intentó, qué se le dijo, qué queda.
  let resumenEscalada = $derived([
    {
      rotulo: 'Qué quiere',
      orden: 0,
      texto: (conversacion?.resumen ?? '').trim() || primerPedido,
      // Se dice que es el mensaje del cliente y no un resumen: quien lee
      // tiene que saber si está viendo una síntesis o una cita.
      nota: (conversacion?.resumen ?? '').trim() ? '' : 'lo que escribió, sin resumir',
      vacio: 'Sin mensajes del cliente todavía.'
    },
    {
      rotulo: 'Le prometimos',
      orden: 2,
      texto: prometido,
      vacio: 'No se encontró el mensaje con el que se le avisó.'
    },
    {
      rotulo: 'Qué falta',
      orden: 3,
      texto: (conversacion?.escalada_siguiente_paso ?? '').trim(),
      // Honesto sobre POR QUÉ está vacío. "No consta" a secas haría pensar en
      // un fallo; esto dice que es una conversación anterior al campo.
      vacio: 'El asistente no dejó anotado el siguiente paso.'
    },
    {
      rotulo: 'No se pudo comprobar',
      orden: 4,
      texto: (conversacion?.escalada_no_comprobado ?? '').trim(),
      // Este SÍ se oculta si está vacío: los otros tres son preguntas que
      // siempre tienen respuesta, y este es una excepción -- decir "no hay
      // nada sin comprobar" en cada caso es ruido.
      ocultarSiVacio: true
    }
  ].filter((f) => f.texto || !f.ocultarSiVacio));

  // El bloque se dibuja siempre que la conversación haya escalado: es
  // entonces cuando alguien tiene que entender el caso rápido.
  let hayResumenDelCaso = $derived(
    !!conversacion?.escalada_a_humano || resumenEscalada.some((f) => f.texto) || hizoLaIA.length > 0
  );

  let entrada = $state('');
  let enviando = $state(false);
  let error = $state('');
  /** Solo se usa por debajo de 1240px, donde la columna de contexto no cabe
      al lado y pasa a abrirse como panel. */
  let contextoAbierto = $state(false);

  // --- atender: sacar el caso de "Sin atender" sin pasar por el chat -------
  // 'atendida' hoy se calcula sola en cuanto alguien responde de verdad
  // (ver nucleo/persistencia/db.py::ultima_actividad) -- esto es el camino
  // manual para cuando el caso se resolvio por telefono, en persona, o por
  // otro canal, y no corresponde mandarle un mensaje al cliente solo para
  // que el calculo lo cuente. Sin desmarcar a proposito: ver
  // marcar_atendida() en el motor.
  let atendida = $state(untrack(() => !!data.conversacion?.atendida));
  let marcandoAtendida = $state(false);
  let errorAtender = $state('');

  async function marcarAtendida() {
    if (marcandoAtendida || atendida) return;
    marcandoAtendida = true;
    errorAtender = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/atender`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caso_id: conversacion.caso_id ?? null })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorAtender = datos.error || 'No se pudo guardar.';
        return;
      }
      atendida = true;
      // El servidor toma el ticket a nombre de quien dio "Atender" (ver el
      // proxy) -- reflejarlo ya mismo en "Asignado a", sin esperar a que
      // alguien reabra el ticket para verlo.
      if (datos.asignado) asignadoA = datos.asignado.id;
      // Sin esto, la lista de la izquierda (+layout.svelte, otro load())
      // no se entera hasta el proximo sondeo -- hasta 8s despues. Con
      // invalidate() se refresca al instante, apenas se guarda.
      invalidate('app:conversaciones');
    } catch (/** @type {any} */ err) {
      errorAtender = err?.message || 'No se pudo guardar.';
    } finally {
      marcandoAtendida = false;
    }
  }

  // Los cuatro estados de un envío, en palabras. 'pendiente' dice "saliendo"
  // y no "pendiente": lo segundo suena a que quedó algo por hacer, y lo que
  // pasa es que el acuse todavía no volvió.
  /** La extensión de un adjunto, sacada del nombre o del mime. Sirve para
      decir "PDF" en vez de "application/pdf", que no le dice nada a nadie. */
  function extension(/** @type {any} */ a) {
    const delNombre = (a.descripcion || '').split('.').pop();
    if (delNombre && delNombre.length <= 5 && delNombre !== a.descripcion) {
      return delNombre.toUpperCase();
    }
    return ((a.mime || '').split('/')[1] || 'archivo').toUpperCase();
  }

  const ENTREGA_TEXTO = {
    pendiente: 'Enviando…',
    enviado: 'Enviado',
    entregado: 'Entregado',
    leido: 'Leído'
  };

  // --- responder al cliente vs. nota interna --------------------------------
  // Dos modos, no una casilla. El compositor entero cambia de aspecto -- no
  // sólo una pestaña chiquita-- porque el error que hay que hacer imposible es
  // escribir algo interno creyendo que es privado y que le llegue al cliente.
  // Y las rutas son distintas: la nota va a /nota, que NO toca el canal en
  // ningún punto. No es que se decida no enviar; es que no hay con qué.
  let modo = $state('responder');

  async function guardarNota() {
    const texto = entrada.trim();
    if (!texto || enviando) return;
    enviando = true;
    error = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/nota`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        error = datos.error || 'No se pudo guardar la nota.';
        return;
      }
      entrada = '';
      await sondearMensajesNuevos();
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo guardar la nota.';
    } finally {
      enviando = false;
    }
  }

  /** El paso resaltado tras pulsar un contador del diagnóstico. */
  let pasoMarcado = $state(/** @type {number | null} */ (null));

  /** Lleva al primer paso bloqueado o fallido y lo resalta un momento. El
      numero ya dice que paso algo; esto contesta cuál, sin que nadie tenga que
      buscarlo entre catorce lineas de traza. */
  function irAlPaso(/** @type {'bloqueo' | 'error'} */ tipo) {
    const i = herramientas.findIndex((h) =>
      tipo === 'bloqueo' ? h.es_bloqueo : !h.exito && !h.es_bloqueo
    );
    if (i < 0) return;
    pasoMarcado = i;
    queueMicrotask(() => {
      document
        .querySelector(`[data-paso="${i}"]`)
        ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
    // Se apaga solo: un resaltado permanente deja de señalar nada en cuanto
    // alguien mira otra cosa.
    setTimeout(() => (pasoMarcado = null), 2500);
  }

  /** id del mensaje que se está reintentando, o null. */
  let reintentando = $state(/** @type {string | null} */ (null));

  /** Vuelve a mandar lo que ya está escrito. No crea un mensaje nuevo en la
      pantalla: si sale, el hilo se resincroniza y el estado cambia solo. */
  async function reintentar(/** @type {any} */ m) {
    if (reintentando) return;
    reintentando = m.id;
    error = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/humano`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: m.contenido })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        error = datos.error || 'No se pudo reenviar.';
        return;
      }
      if (datos.aviso) error = `Tampoco salió esta vez: ${datos.aviso}`;
      await sondearMensajesNuevos();
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo reenviar.';
    } finally {
      reintentando = null;
    }
  }

  // ==========================================================================
  //  COMPOSITOR -- adjuntos, emoji y nota de voz
  // ==========================================================================
  //  Los límites (formatos y tamaños) NO están acá: los declara el canal
  //  (nucleo/canales/whatsapp.py) y llegan por /api/canales/limites-media. Una
  //  copia en el frontend se desincroniza el día que Meta cambia un tope, y el
  //  síntoma sería un archivo que se sube entero para que lo rechacen al final.
  /** @type {any} */
  let limites = $state(null);
  $effect(() => {
    fetch('/api/canales/limites-media')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (limites = d?.limites ?? null))
      .catch(() => {});
  });

  /** {archivo, tipo, url, error} — uno solo por vez. WhatsApp manda un
      archivo por mensaje, así que una cola de varios daría a entender que van
      juntos cuando en realidad saldrían como mensajes separados. */
  let adjunto = $state(/** @type {any} */ (null));
  let arrastrando = $state(false);

  /** De qué tipo es para WhatsApp. image y audio se reconocen por su mime;
      todo lo demás es 'document', que es el tipo abierto de la API. */
  function tipoDe(/** @type {File} */ f) {
    const m = f.type || '';
    if (m.startsWith('image/')) return 'image';
    if (m.startsWith('audio/')) return 'audio';
    return 'document';
  }

  /** Valida contra lo que dijo el canal y deja el adjunto listo, con su
      previsualización. Rechaza ACÁ lo que WhatsApp rechazaría igual: hacer
      esperar una subida para dar un error evitable es maltrato. */
  function tomarArchivo(/** @type {File} */ f) {
    if (!f) return;
    const tipo = tipoDe(f);
    const lim = limites?.[tipo];
    if (lim) {
      if (lim.mime?.length && !lim.mime.includes(f.type)) {
        error = `WhatsApp no acepta ${f.type || 'ese formato'} como ${lim.etiqueta.toLowerCase()}. Acepta: ${lim.mime.join(', ')}.`;
        return;
      }
      if (f.size > lim.max_bytes) {
        error = `El archivo pesa ${(f.size / 1048576).toFixed(1)} MB y el tope para ${lim.etiqueta.toLowerCase()} es ${Math.round(lim.max_bytes / 1048576)} MB.`;
        return;
      }
    }
    error = '';
    // El objectURL anterior se libera: sin esto cada archivo elegido deja su
    // blob en memoria hasta que se recarga la página.
    if (adjunto?.url) URL.revokeObjectURL(adjunto.url);
    adjunto = {
      archivo: f,
      tipo,
      nombre: f.name || 'archivo',
      bytes: f.size,
      url: tipo === 'image' || tipo === 'audio' ? URL.createObjectURL(f) : ''
    };
  }

  function quitarAdjunto() {
    if (adjunto?.url) URL.revokeObjectURL(adjunto.url);
    adjunto = null;
  }

  /** Arrastrar un archivo sobre la conversación. */
  function alSoltar(/** @type {DragEvent} */ e) {
    e.preventDefault();
    arrastrando = false;
    const f = e.dataTransfer?.files?.[0];
    if (f) tomarArchivo(f);
  }

  /** Pegar una captura. Se trata igual que un adjunto elegido a mano: se
      previsualiza y espera confirmación, nunca se manda sola. */
  function alPegar(/** @type {ClipboardEvent} */ e) {
    const item = [...(e.clipboardData?.items ?? [])].find((i) => i.kind === 'file');
    if (!item) return;
    const f = item.getAsFile();
    if (!f) return;
    e.preventDefault();
    // Una captura pegada no trae nombre; sin esto llega como "image.png" o
    // vacío y en el hilo del cliente no se distingue de ninguna otra.
    tomarArchivo(
      f.name && f.name !== 'image.png'
        ? f
        : new File([f], `captura-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '')}.png`, {
            type: f.type
          })
    );
  }

  // --- emoji ----------------------------------------------------------------
  // Una lista corta y fija, no un catálogo completo: esto es soporte de un
  // ISP, no una app de mensajería. Los que están son los que de verdad se usan
  // al contestarle a alguien que espera.
  const EMOJIS = [
    '🙂', '😀', '😅', '👍', '🙏', '👌', '💪', '🎉',
    '✅', '❌', '⚠️', '📶', '📡', '🔌', '🔧', '🏠',
    '📞', '📅', '⏰', '💬', '📄', '📷', '❤️', '👋'
  ];
  let emojisAbiertos = $state(false);
  let adjuntarAbierto = $state(false);

  /** Compartido por las dos opciones del menú: lo único que cambia entre
      "Imagen" y "Documento" es el filtro del diálogo del navegador. */
  function alElegirArchivo(/** @type {any} */ e) {
    const f = e.currentTarget.files?.[0];
    if (f) tomarArchivo(f);
    e.currentTarget.value = '';
    adjuntarAbierto = false;
  }
  /** @type {HTMLTextAreaElement | null} */
  let campoTexto = $state(null);

  /** Inserta en la POSICIÓN DEL CURSOR, no al final: quien escribió una frase
      y volvió al medio espera que el emoji caiga donde está mirando. */
  function ponerEmoji(/** @type {string} */ e) {
    const el = campoTexto;
    const i = el?.selectionStart ?? entrada.length;
    const j = el?.selectionEnd ?? i;
    entrada = entrada.slice(0, i) + e + entrada.slice(j);
    emojisAbiertos = false;
    // El foco vuelve al texto con el cursor DESPUÉS del emoji, para poder
    // seguir escribiendo sin tocar el mouse.
    queueMicrotask(() => {
      el?.focus();
      el?.setSelectionRange(i + e.length, i + e.length);
    });
  }

  // --- nota de voz ----------------------------------------------------------
  // Nunca se envía sola al terminar de grabar: se para, se escucha si se
  // quiere, y recién ahí se manda o se descarta. Una nota de voz que sale sin
  // que nadie la haya escuchado es la forma más rápida de mandarle al cliente
  // treinta segundos de ruido de oficina.
  let grabando = $state(false);
  let grabPausada = $state(false);
  let segundos = $state(0);
  /** @type {MediaRecorder | null} */
  let grabador = null;
  /** @type {any} */
  let cronometro = null;

  /** El formato que graba el navegador tiene que ser uno de los que WhatsApp
      acepta. Chrome y Firefox dan 'audio/webm' por defecto, que NO está en la
      lista de Meta -- ogg/opus sí, y es el mismo códec. */
  function formatoDeGrabacion() {
    const candidatos = ['audio/ogg;codecs=opus', 'audio/mp4', 'audio/mpeg'];
    return candidatos.find((m) => window.MediaRecorder?.isTypeSupported?.(m)) ?? '';
  }

  async function grabar() {
    const formato = formatoDeGrabacion();
    if (!formato) {
      error =
        'Este navegador no graba en un formato que WhatsApp acepte. Podés adjuntar un audio ya grabado.';
      return;
    }
    try {
      const flujo = await navigator.mediaDevices.getUserMedia({ audio: true });
      const trozos = /** @type {Blob[]} */ ([]);
      grabador = new MediaRecorder(flujo, { mimeType: formato });
      grabador.ondataavailable = (ev) => ev.data.size && trozos.push(ev.data);
      grabador.onstop = () => {
        // El micrófono se suelta SIEMPRE: sin esto el navegador deja el
        // indicador de grabación encendido hasta cerrar la pestaña.
        flujo.getTracks().forEach((t) => t.stop());
        clearInterval(cronometro);
        grabando = false;
        grabPausada = false;
        if (!trozos.length) return;
        const base = formato.split(';')[0];
        tomarArchivo(
          new File([new Blob(trozos, { type: base })], `nota-de-voz.${base.split('/')[1]}`, {
            type: base
          })
        );
      };
      grabador.start();
      grabando = true;
      segundos = 0;
      error = '';
      cronometro = setInterval(() => {
        if (!grabPausada) segundos += 1;
      }, 1000);
    } catch {
      error = 'No se pudo usar el micrófono. Revisá el permiso del navegador.';
    }
  }

  function pausarGrabacion() {
    if (!grabador) return;
    if (grabPausada) {
      grabador.resume();
      grabPausada = false;
    } else {
      grabador.pause();
      grabPausada = true;
    }
  }

  /** Parar deja la grabación como adjunto pendiente de confirmación. */
  const pararGrabacion = () => grabador?.stop();

  /** Cancelar la tira: el onstop no llega a armar el adjunto. */
  function cancelarGrabacion() {
    if (!grabador) return;
    grabador.onstop = null;
    grabador.stream?.getTracks().forEach((t) => t.stop());
    grabador.stop();
    clearInterval(cronometro);
    grabando = false;
    grabPausada = false;
  }

  const reloj = (/** @type {number} */ s) =>
    `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  /** Manda el adjunto. El texto del cuadro viaja como pie cuando el tipo lo
      acepta -- el AUDIO no lo acepta (Meta lo ignora en silencio), así que en
      ese caso el texto se manda aparte, como mensaje propio, en vez de
      perderse. */
  async function enviarAdjunto() {
    if (!adjunto || enviando) return;
    enviando = true;
    error = '';
    const aceptaPie = limites?.[adjunto.tipo]?.acepta_pie ?? false;
    const pie = aceptaPie ? entrada.trim() : '';
    try {
      const cuerpo = new FormData();
      cuerpo.set('archivo', adjunto.archivo, adjunto.nombre);
      cuerpo.set('tipo', adjunto.tipo);
      cuerpo.set('pie', pie);
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/media`, {
        method: 'POST',
        body: cuerpo
      });
      const datos = await resp.json();
      if (!resp.ok) {
        error = datos.error || 'No se pudo enviar el archivo.';
        return;
      }
      if (datos.aviso) error = `Se guardó, pero no le llegó al cliente: ${datos.aviso}`;
      const texto = entrada.trim();
      quitarAdjunto();
      if (pie) entrada = '';
      await sondearMensajesNuevos();
      // El texto que no cabía como pie sale como mensaje aparte, después del
      // audio. Se manda acá y no antes para que el orden en el hilo del
      // cliente sea el mismo que el de esta pantalla.
      if (texto && !aceptaPie) await enviar();
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo enviar el archivo.';
    } finally {
      enviando = false;
    }
  }

  // --- resolver: el caso termino -------------------------------------------
  // Distinto de "Atender", que dice "alguien esta en esto". Esto dice "esto ya
  // se resolvio": cierra la conversacion para que el proximo mensaje de esa
  // persona empiece un hilo limpio en vez de arrastrar el caso viejo. Pide
  // confirmacion porque no hay boton para deshacerlo.
  let resolviendo = $state(false);
  let errorResolver = $state('');

  async function resolver() {
    if (resolviendo || conversacion.estado === 'cerrada') return;
    if (!confirm('¿Dar este caso por resuelto? La conversación se cierra y el próximo mensaje del cliente abre una nueva.'))
      return;
    resolviendo = true;
    errorResolver = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/resolver`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorResolver = datos.error || 'No se pudo guardar.';
        return;
      }
      conversacion = { ...conversacion, estado: 'cerrada' };
      atendida = true;
      invalidate('app:conversaciones');
    } catch (/** @type {any} */ err) {
      errorResolver = err?.message || 'No se pudo guardar.';
    } finally {
      resolviendo = false;
    }
  }

  // --- SOLO PARA PRUEBAS: reiniciar la conversacion para el entrenamiento
  // por WhatsApp real -- borra todo (mensajes, rol derivado, si ya escalo)
  // para poder reescribirle al bot de cero sin abrir otro numero. Sacar
  // este bloque, el boton en el header y el endpoint DELETE
  // (api/conversaciones/[id]/+server.js, nucleo/canales/api.py) cuando
  // termine esa etapa.
  let reiniciando = $state(false);
  let errorReiniciar = $state('');

  async function reiniciarConversacion() {
    if (reiniciando) return;
    if (!confirm('¿Borrar esta conversación de prueba? No se puede deshacer.')) return;
    reiniciando = true;
    errorReiniciar = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}`, { method: 'DELETE' });
      if (!resp.ok) {
        const datos = await resp.json().catch(() => ({}));
        errorReiniciar = datos.error || 'No se pudo borrar.';
        return;
      }
      invalidate('app:conversaciones');
      goto('/conversaciones');
    } catch (/** @type {any} */ err) {
      errorReiniciar = err?.message || 'No se pudo borrar.';
    } finally {
      reiniciando = false;
    }
  }

  // --- sondeo: mensajes nuevos sin recargar (para cuando WhatsApp real este
  // integrado y el cliente escriba mientras esta pantalla esta abierta) ----
  // Todavia no hay WebSocket -- sondea cada pocos segundos mientras la
  // pestaña esta visible (una de fondo no gasta pedidos). Nunca REEMPLAZA
  // 'mensajes': solo agrega lo que no estaba, para no perder ni duplicar los
  // push() optimistas de enviar().
  async function sondearMensajesNuevos() {
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/mensajes`);
      if (!resp.ok) return;
      const datos = await resp.json();
      const ahora = Date.now();
      for (const m of datos.mensajes ?? []) {
        if (!m.id || mensajes.some((loc) => loc.id === m.id)) continue;
        // Evita duplicar un mensaje que ESTA pestaña ya empujo de forma
        // optimista (sin id todavia) y que el sondeo recien ahora trae con
        // su id real -- match por rol + contenido + reciente.
        const esEcoDeOptimista = mensajes.some(
          (loc) =>
            !loc.id &&
            loc.rol === m.rol &&
            loc.contenido === m.contenido &&
            ahora - new Date(loc.creado_en).getTime() < 15000
        );
        if (!esEcoDeOptimista) mensajes.push(m);
      }

      // La conversacion tambien cambia sin que esta pestaña lo sepa -- se
      // puede escalar (o alguien mas la atiende/asigna el ticket) DESPUES
      // de que esta pantalla ya cargo. 'conversacion' se reemplaza entera
      // (no hay push() locales sobre ella como si hay en 'mensajes', asi que
      // no hay nada que perder). 'atendida' sigue la misma logica -- salvo
      // que este a mitad de guardarse desde ESTA pestaña ahora mismo, para
      // no pisar el propio click con una respuesta vieja del sondeo.
      if (datos.conversacion) conversacion = datos.conversacion;
      if (!marcandoAtendida) atendida = !!datos.conversacion?.atendida;
    } catch {
      // un sondeo que falla no tiene que avisar nada -- se reintenta solo.
    }
  }

  $effect(() => {
    const intervalo = setInterval(() => {
      if (document.visibilityState === 'visible') sondearMensajesNuevos();
    }, 5000);
    // Igual que en +layout.svelte: sin esto, volver a esta pestaña despues
    // de estar en otra espera hasta el proximo tick (y los navegadores
    // frenan los timers de pestañas de fondo) para notar algo nuevo. Dos
    // señales (visibilitychange + focus de ventana), no una -- entre las
    // dos es dificil que ninguna dispare al volver.
    const alVolver = () => sondearMensajesNuevos();
    document.addEventListener('visibilitychange', alVolver);
    window.addEventListener('focus', alVolver);
    return () => {
      clearInterval(intervalo);
      document.removeEventListener('visibilitychange', alVolver);
      window.removeEventListener('focus', alVolver);
    };
  });

  // --- conservar: sacar la conversacion de la purga por retencion ----------
  // Distinto de marcar un ejemplo: eso dice "esta respuesta fue buena" y
  // alimenta el manual; esto dice "no la borres todavia" -- un reclamo, un
  // incidente. Justo lo que NO hay que copiar como ejemplo.
  let conservada = $state(untrack(() => !!data.conversacion?.conservar));
  let motivoConservar = $state(untrack(() => data.conversacion?.conservar_motivo ?? ''));
  let pidiendoMotivo = $state(false);
  let guardandoConservar = $state(false);
  let errorConservar = $state('');

  async function guardarConservar(/** @type {boolean} */ valor) {
    if (guardandoConservar) return;
    // El motivo es obligatorio al conservar: dentro de seis meses nadie va a
    // saber si la marca sigue teniendo sentido sin el.
    if (valor && !motivoConservar.trim()) {
      pidiendoMotivo = true;
      return;
    }
    guardandoConservar = true;
    errorConservar = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/conservar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conservar: valor, motivo: motivoConservar.trim() })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorConservar = datos.error || 'No se pudo guardar.';
        return;
      }
      conservada = valor;
      if (!valor) motivoConservar = '';
      pidiendoMotivo = false;
    } catch (/** @type {any} */ err) {
      errorConservar = err?.message || 'No se pudo guardar.';
    } finally {
      guardandoConservar = false;
    }
  }

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (c) => CANAL_LABEL[c] ?? c;
  const canalTone = (c) => (c === 'whatsapp' ? 'moss' : 'slate');
  const estadoTone = (e) => (e === 'abierta' ? 'clay' : 'slate');

  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');

  // Mismo criterio que la lista del layout: un telefono o un uuid no dan
  // iniciales, y diez digitos seguidos no se leen.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    const d = v.replace(/\D/g, '');
    if (esTelefono(v) && d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    return v;
  }

  let asignadoA = $state(caso?.assignee_id ?? '');
  let ownerActual = $derived(owners.find((o) => o.id === asignadoA) ?? null);
  let listaAbierta = $state(false);
  /** @type {HTMLFormElement} */
  let formularioAsignar = $state();

  /** El esquema admite user|assistant|tool|system; solo los dos primeros
   *  aparecen hoy (nucleo/persistencia/db.py solo registra esos), pero un
   *  rol inesperado cae en un estilo neutro en vez de romper el render. */
  const burbujaClase = (rol) =>
    rol === 'user'
      ? 'chat-usuario'
      : rol === 'assistant'
        ? 'chat-asistente'
        : // Una nota interna NO se parece a un mensaje: si se ve como una
          // burbuja mas, alguien la va a leer como algo que se le dijo al
          // cliente. Es la mitad visual de la garantia; la otra mitad es que
          // la ruta que la guarda no toca el canal.
          rol === 'nota'
          ? 'chat-nota'
          : 'chat-otro';

  // Una vez que hay ticket, la caja deja de simular al cliente para que
  // conteste el bot -- pasa a ser la respuesta de la persona que tomo el
  // caso, tal cual la escribe, sin pasar por el modelo. El cliente del otro
  // lado no deberia notar el cambio de quien le esta escribiendo.
  //
  // LA MISMA condicion que usa el motor para callar al bot
  // (nucleo/canales/api.py: `previo["escalada"] and previo["necesita_atencion_humana"]`).
  //
  // Antes se derivaba de 'caso_id', y eso produjo una contradiccion visible en
  // la misma pantalla: el banner decia "Escalada · IA no responde" y el
  // compositor, diez centimetros abajo, "Responde el asistente". Pasa cuando
  // el modelo escala pero el CRM no llego a crear el ticket -- hay 2
  // conversaciones asi en produccion.
  //
  // No es solo cosmetico: con el bot en pausa y el compositor creyendo que no
  // lo esta, lo que alguien escribe se manda COMO SI FUERA EL CLIENTE, y como
  // el bot esta callado no contesta nadie. El mensaje no sale y nada lo dice.
  //
  // Y la escalada 'agendada sola' (necesita_atencion_humana=false) queda del
  // lado correcto: ahi el bot SIGUE contestando, asi que el cuadro simula al
  // cliente, que es lo que corresponde.
  let iaEnPausa = $derived(
    !!conversacion.escalada_a_humano && !!conversacion.necesita_atencion_humana
  );
  let escalada = $derived(iaEnPausa);

  /** Clave de dia local, para agrupar el hilo. */
  function diaDe(/** @type {string} */ iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toDateString();
  }

  function etiquetaDia(/** @type {string} */ iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const hoy = new Date();
    const ayer = new Date();
    ayer.setDate(hoy.getDate() - 1);
    if (d.toDateString() === hoy.toDateString()) return 'Hoy';
    if (d.toDateString() === ayer.toDateString()) return 'Ayer';
    return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'long' }).format(d);
  }

  function hora(/** @type {string} */ iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' }).format(d);
  }

  /** El hilo con separadores de dia intercalados: un chat largo sin ellos
      obliga a pasar el mouse por cada burbuja para ubicarse en el tiempo. */
  // --- que el hilo se vea por donde importa ---------------------------------
  // NO habia auto-scroll en toda la pantalla. Medido el 07/09/2026 sobre una
  // conversacion real: al enviar, la burbuja se agrega en 150 ms --el push
  // optimista siempre funciono-- pero queda 616 px POR DEBAJO del borde
  // visible, con el hilo en scrollTop 0. El mensaje esta ahi y no se ve, que
  // desde el otro lado es indistinguible de que no se haya enviado.
  //
  // Un chat se abre por el final, no por el principio: lo ultimo que se dijo
  // es lo que hace falta para contestar.
  /** @type {HTMLElement | undefined} */
  let hiloEl = $state();

  const alFinal = (suave = false) => {
    if (!hiloEl) return;
    hiloEl.scrollTo({ top: hiloEl.scrollHeight, behavior: suave ? 'smooth' : 'auto' });
  };

  /** Si quien mira ya estaba abajo. Con un margen de 120 px porque nadie deja
      el scroll exactamente al final, y porque una burbuja a medio entrar
      cuenta como "estaba mirando el final". */
  const estabaAlFinal = () =>
    !hiloEl || hiloEl.scrollHeight - hiloEl.clientHeight - hiloEl.scrollTop < 120;

  // Al abrir la conversacion, y en cada cambio del hilo.
  //
  // La condicion NO es "siempre": si alguien subio a leer lo que paso hace
  // dos semanas y entra un mensaje nuevo, arrastrarlo al fondo le quita de
  // la vista justo lo que estaba leyendo. Solo se sigue al que ya estaba
  // mirando el final. Cuando uno MISMO envia se fuerza aparte (ver enviar()):
  // ahi la intencion es evidente.
  let ultimoVisto = $state(0);
  $effect(() => {
    const n = mensajes.length;
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

  let hilo = $derived.by(() => {
    const salida = [];
    let dia = null;
    for (const m of mensajes) {
      const d = diaDe(m.creado_en);
      if (d !== dia) {
        salida.push({ tipo: 'dia', clave: `d-${d}-${salida.length}`, texto: etiquetaDia(m.creado_en) });
        dia = d;
      }
      salida.push({ tipo: 'msg', clave: `m-${salida.length}`, m });
    }
    return salida;
  });

  // --- copiloto documental -------------------------------------------------
  // Lo que dice la documentacion interna sobre lo ultimo que pregunto el
  // cliente. Recupera, no genera: son fragmentos reales con su procedencia, y
  // el agente decide que hacer con ellos. Cuesta un embedding, no una llamada
  // al modelo.
  let sugerencias = $state([]);
  let buscandoDocs = $state(false);
  let errorDocs = $state('');
  let mejorSimilitud = $state(null);
  let docsAbierto = $state(false);
  let expandido = $state(null);
  let copiado = $state(null);
  // La ultima pregunta del cliente es la mejor consulta de arranque; si no
  // sirve, el agente la reescribe.
  let consultaDocs = $state(
    untrack(() => [...(data.mensajes ?? [])].reverse().find((m) => m.rol === 'user')?.contenido ?? '')
  );

  async function buscarDocs() {
    const texto = consultaDocs.trim();
    if (!texto || buscandoDocs) return;
    buscandoDocs = true;
    errorDocs = '';
    expandido = null;
    try {
      const resp = await fetch('/api/sugerencias', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto })
      });
      const datos = await resp.json();
      if (resp.ok) {
        sugerencias = datos.sugerencias ?? [];
        mejorSimilitud = datos.mejor_similitud ?? null;
      } else {
        errorDocs = datos.error || 'No se pudo consultar la documentacion.';
      }
    } catch (/** @type {any} */ err) {
      errorDocs = err?.message || 'No se pudo consultar la documentacion.';
    } finally {
      buscandoDocs = false;
    }
  }

  /** Busca la primera vez que se abre el panel, no al cargar la pagina: si
      nadie lo mira, no se gasta el embedding. */
  function alAbrirDocs(/** @type {Event} */ ev) {
    docsAbierto = /** @type {HTMLDetailsElement} */ (ev.currentTarget).open;
    if (docsAbierto && sugerencias.length === 0 && !buscandoDocs && !errorDocs) buscarDocs();
  }

  /** @param {SubmitEvent} ev */
  function alBuscarDocs(ev) {
    ev.preventDefault();
    buscarDocs();
  }

  /**
   * Copiar, nunca insertar en el compositor: la documentacion esta escrita en
   * lenguaje interno y mandarsela cruda a un cliente seria peor que no
   * tenerla. El agente lee y redacta.
   *
   * @param {string} texto
   * @param {number} i
   */
  async function copiarFragmento(texto, i) {
    try {
      await navigator.clipboard.writeText(texto);
      copiado = i;
      setTimeout(() => (copiado = null), 1600);
    } catch {
      // Portapapeles bloqueado (sin https o sin permiso). El texto esta a la
      // vista para seleccionarlo a mano; no hay nada que avisar.
    }
  }

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || enviando) return;

    entrada = '';
    enviando = true;
    error = '';

    if (escalada) {
      // Una sola burbuja: lo que el agente escribio ES la respuesta, no hay
      // nada que "contestar" del otro lado.
      const burbuja = {
        rol: 'assistant',
        contenido: texto,
        creado_en: new Date().toISOString(),
        /** @type {string|null} */ sinEntregar: null
      };
      mensajes.push(burbuja);
      // Forzado, no condicional: el efecto de arriba solo sigue al que ya
      // estaba mirando el final, y quien acaba de apretar Enviar quiere ver
      // lo que envio aunque hubiera subido a releer algo.
      ultimoVisto = mensajes.length;
      requestAnimationFrame(() => alFinal(true));
      try {
        const resp = await fetch(`/api/conversaciones/${conversacion.id}/humano`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mensaje: texto })
        });
        const datos = await resp.json();
        if (!resp.ok) {
          error = datos.error || 'No se pudo guardar la respuesta.';
        } else if (datos.aviso) {
          // Se guardo pero NO salio por el canal. El caso mas comun es la
          // ventana de 24 h de WhatsApp. Va marcado en la burbuja y no solo
          // como error suelto: dentro de un rato el aviso de arriba ya no
          // esta, y la burbuja sigue ahi pareciendo entregada.
          burbuja.sinEntregar = datos.aviso;
          error = datos.aviso;
        }
      } catch (/** @type {any} */ err) {
        error = err?.message || 'No se pudo guardar la respuesta.';
      } finally {
        enviando = false;
      }
      return;
    }

    mensajes.push({ rol: 'user', contenido: texto, creado_en: new Date().toISOString() });
    ultimoVisto = mensajes.length;
    requestAnimationFrame(() => alFinal(true));
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mensaje: texto,
          usuario_externo: conversacion.usuario_externo,
          rol_efectivo: conversacion.rol_efectivo,
          canal: conversacion.canal
        })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        error = datos.error || 'El asistente no pudo responder.';
        return;
      }
      mensajes.push({
        rol: 'assistant',
        contenido: datos.respuesta,
        creado_en: new Date().toISOString(),
        id: datos.mensaje_id,
        caso_marcado: null
      });
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo contactar al asistente.';
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

<!-- ── CENTRO: la conversación ────────────────────────────────────────────── -->
<section class="centro">
  <header class="centro-top">
    <a class="volver" href="/conversaciones" aria-label="Volver a la lista">
      <ArrowLeft size={16} />
    </a>

    {#if conversacion.nombre_cliente}
      <Avatar name={conversacion.nombre_cliente} size={32} />
    {:else if esTelefono(conversacion.usuario_externo)}
      <span class="ident" aria-hidden="true"><Phone size={15} /></span>
    {:else if !conversacion.usuario_externo || esUuid(conversacion.usuario_externo)}
      <span class="ident" aria-hidden="true"><User size={15} /></span>
    {:else}
      <Avatar name={conversacion.usuario_externo} size={32} />
    {/if}

    <div class="centro-quien">
      <h2>{conversacion.nombre_cliente || quien(conversacion.usuario_externo)}</h2>
      <div class="centro-meta">
        <Pill tone={canalTone(conversacion.canal)}>{canalLabel(conversacion.canal)}</Pill>
        <Pill tone={estadoTone(conversacion.estado)}>{conversacion.estado}</Pill>
      </div>
    </div>

    <!-- Solo aparece cuando la columna de contexto no cabe al lado. Ahí se
         abre como panel, no se pierde: el ticket y la documentación siguen a
         un clic. -->
    <button
      type="button"
      class="v2-btn v2-btn-sm contexto-toggle"
      onclick={() => (contextoAbierto = !contextoAbierto)}
      aria-expanded={contextoAbierto}
    >
      <PanelRight size={14} /> Contexto
    </button>

    <!-- SOLO PARA PRUEBAS -- ver reiniciarConversacion() mas arriba. -->
    <button
      type="button"
      class="v2-btn v2-btn-sm v2-btn-danger"
      onclick={reiniciarConversacion}
      disabled={reiniciando}
      aria-busy={reiniciando}
      title="Borra esta conversación para volver a probar desde cero (solo entrenamiento)"
    >
      <RotateCcw size={14} />
      {reiniciando ? 'Borrando…' : 'Reiniciar (prueba)'}
    </button>
  </header>

  {#if errorReiniciar}
    <p class="aviso">{errorReiniciar}</p>
  {/if}

  {#if conversacion.escalada_a_humano}
    <p class="aviso">
      <TriangleAlert size={14} />
      <!-- "IA pausada" seria falso y no es un matiz de redaccion: el asistente
           SIGUE leyendo y procesando cada mensaje mientras espera -- de eso
           depende que un "listo, gracias" del cliente cierre el caso solo.
           Lo que dejo de hacer es contestar. -->
      <strong>
        {#if iaEnPausa}
          Escalada · IA no responde
        {:else}
          <!-- Escalo, pero no hay a quien esperar (quedo agendada, o el CRM no
               tomo el caso): el asistente SIGUE contestando. Decir "IA no
               responde" aca seria falso. -->
          Escalada · el asistente sigue respondiendo
        {/if}
      </strong>
      {#if conversacion.motivo_escalamiento}
        <!-- El separador no es adorno: sin el, "IA no responde El cliente
             reporto una falla..." se lee como una sola frase rota. -->
        <span class="aviso-motivo">· {motivoLabel(conversacion.motivo_escalamiento)}</span>
      {/if}
      <!-- Estado real y aparte: el CRM es la fuente de verdad de cuando el
           asistente puede volver a contestar, y no es lo mismo que el estado
           de la conversacion. -->
      <!-- Estado, no enlace: para ir al ticket ya esta "Ver ticket completo"
           en la columna derecha, y dos caminos al mismo lugar en la misma
           pantalla es una eleccion que nadie pidio hacer. -->
      {#if caso?.id}
        <span class="aviso-caso">Caso abierto en CRM</span>
      {/if}
      {#if conversacion.necesita_atencion_humana}
        {#if !atendida}
          <button
            type="button"
            class="v2-btn v2-btn-sm v2-btn-strong aviso-atender"
            title="Marca que te estás haciendo cargo: pasa a la pestaña «En atención» y sale de «Por atender». No le envía nada al cliente."
            onclick={marcarAtendida}
            disabled={marcandoAtendida}
            aria-busy={marcandoAtendida}
          >
            <CircleCheck size={13} />
            {marcandoAtendida ? 'Marcando…' : 'Atender'}
          </button>
        {:else}
          <span class="aviso-atendida">
            <CircleCheck size={13} /> Atendida
          </span>
        {/if}
      {/if}
      <!-- Cerrar el caso. Va junto a "Atender" porque es la otra mitad del
           mismo momento -- se toma un caso y despues se termina-- pero en
           tono secundario: "Atender" es lo que se hace al entrar, esto es lo
           que se hace al salir, y una sola vez. -->
      {#if conversacion.estado !== 'cerrada'}
        <!-- La ayuda va en un popover propio y no en el 'title' del navegador:
             ese tarda casi un segundo en aparecer, no sale con el teclado, y
             es justo el contexto que hace que alguien se anime a cerrar un
             caso que resolvio por telefono. -->
        <span class="con-ayuda">
          <button
            type="button"
            class="v2-btn v2-btn-sm aviso-resolver"
            onclick={resolver}
            disabled={resolviendo}
            aria-busy={resolviendo}
            aria-describedby="ayuda-resolver"
          >
            {resolviendo ? 'Cerrando…' : 'Marcar como resuelta'}
          </button>
          <span class="ayuda" id="ayuda-resolver" role="tooltip">
            Usá esto si el caso se resolvió por teléfono, presencialmente o por
            otro canal. Cierra la conversación; el próximo mensaje del cliente
            abre una nueva.
          </span>
        </span>
      {:else}
        <span class="aviso-atendida"><CircleCheck size={13} /> Resuelta</span>
      {/if}
      {#if errorAtender}<span class="aviso-mal">{errorAtender}</span>{/if}
      {#if errorResolver}<span class="aviso-mal">{errorResolver}</span>{/if}
    </p>
  {/if}

  <!-- Tomar un caso escalado empieza siempre igual: leer el hilo entero para
       reconstruir que queria el cliente, que alcanzo a hacer el asistente,
       que se le prometio y que falta. Los tres primeros textos los ESCRIBE el
       modelo al evaluar la escalada y hasta ahora solo iban a la descripcion
       del ticket del CRM -- quien atendia desde acá no los veia nunca.

       Solo se dibuja lo que existe de verdad: en las conversaciones escaladas
       antes del 06/09/2026 estos campos estan vacios, y media tarjeta con
       renglones en blanco informa menos que ninguna. -->
  {#if hayResumenDelCaso}
    <dl class="brief">
      {#each resumenEscalada as fila (fila.rotulo)}
        <div
          class="brief-fila"
          class:brief-sin-dato={!fila.texto}
          class:brief-primero={fila.orden === 0}
          style="order:{fila.orden}"
        >
          <dt>{fila.rotulo}</dt>
          <dd>
            {#if fila.texto}
              {fila.texto}
              {#if fila.nota}<span class="brief-nota">— {fila.nota}</span>{/if}
            {:else}
              <span class="brief-nada">{fila.vacio}</span>
            {/if}
          </dd>
        </div>
      {/each}

      <!-- Qué hizo la IA. Va después de "qué quiere" porque el orden en que
           alguien entiende un caso es ese: primero qué pedían, después qué se
           intentó. Y antes de "qué falta", que es lo que hay que hacer. -->
      {#if hizoLaIA.length > 0}
        <div class="brief-fila" style="order:1">
          <dt>Qué hizo la IA</dt>
          <dd>
            <ul class="hizo">
              {#each hizoLaIA as h (h.texto)}
                <li class="hizo-{h.estado}">
                  {#if h.estado === 'ok'}
                    <CircleCheck size={13} style="color:var(--v2-moss);flex:none" />
                  {:else if h.estado === 'bloqueo'}
                    <ShieldCheck size={13} style="color:var(--v2-clay);flex:none" />
                  {:else}
                    <CircleX size={13} style="color:var(--v2-rust);flex:none" />
                  {/if}
                  <span>{h.texto}</span>
                  {#if h.detalle}<span class="v2-muted">— {h.detalle}</span>{/if}
                </li>
              {/each}
            </ul>
          </dd>
        </div>
      {/if}
    </dl>
  {/if}

  <div class="hilo" bind:this={hiloEl}>
    <div class="chat-mensajes">
      {#each hilo as item (item.clave)}
        {#if item.tipo === 'dia'}
          <div class="dia"><span>{item.texto}</span></div>
        {:else}
          <div
            class="chat-burbuja {burbujaClase(item.m.rol)}"
            class:sin-entregar={item.m.sinEntregar}
          >
            <!-- Un mensaje sin texto Y sin adjunto que se pueda dibujar no
                 puede quedar como una burbuja vacía: llegó algo (una
                 ubicación, un contacto, un sticker) que esta pantalla todavía
                 no representa. Decirlo es mejor que un hueco, que se lee como
                 un error de la aplicación. -->
            {#if item.m.contenido}
              <div>{item.m.contenido}</div>
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
                  onclick={() => reintentar(item.m)}
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
                conversacionId={conversacion.id}
                mensajeId={item.m.id}
                casoInicial={item.m.caso_marcado}
                {casos}
              />
            {/if}
          </div>
        {/if}
      {/each}
      {#if enviando && !escalada}
        <div class="chat-burbuja chat-asistente chat-escribiendo" aria-label="Escribiendo…">
          <span class="punto"></span><span class="punto"></span><span class="punto"></span>
        </div>
      {/if}
    </div>
  </div>

  {#if conversacion.estado === 'abierta'}
    <div class="pie">
      {#if error}<p class="v2-error" style="margin:0 0 6px">{error}</p>{/if}
      <!-- Los dos modos, arriba del cuadro. Van acá y no dentro del pie para
           que se lean ANTES de escribir, no después. -->
      <div class="modos" role="group" aria-label="Qué estás escribiendo">
        <button
          type="button"
          class="modo"
          aria-pressed={modo === 'responder'}
          onclick={() => (modo = 'responder')}>Responder al cliente</button
        >
        <button
          type="button"
          class="modo modo-nota"
          aria-pressed={modo === 'nota'}
          onclick={() => (modo = 'nota')}>Nota interna</button
        >
      </div>

      <form
        class="compositor"
        class:arrastrando
        class:es-nota={modo === 'nota'}
        onsubmit={alEnviar}
        ondragover={(e) => {
          e.preventDefault();
          arrastrando = true;
        }}
        ondragleave={() => (arrastrando = false)}
        ondrop={alSoltar}
      >
        {#if arrastrando}
          <div class="soltar-aca">Soltá el archivo acá</div>
        {/if}

        <!-- Grabando: el cronómetro y los tres controles que el pedido exige,
             y NINGUNO que mande. Parar deja la nota como adjunto pendiente de
             confirmación -- se puede escuchar antes de mandarla. -->
        {#if grabando}
          <div class="grabando">
            <span class="grabando-punto" aria-hidden="true"></span>
            <span class="v2-num grabando-reloj">{reloj(segundos)}</span>
            <button type="button" class="v2-btn v2-btn-sm" onclick={pausarGrabacion}>
              {grabPausada ? 'Seguir' : 'Pausar'}
            </button>
            <button type="button" class="v2-btn v2-btn-sm v2-btn-danger" onclick={cancelarGrabacion}>
              Cancelar
            </button>
            <button type="button" class="v2-btn v2-btn-sm v2-btn-strong" onclick={pararGrabacion}>
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
              onclick={quitarAdjunto}
              aria-label="Quitar el archivo"><X size={14} /></button
            >
          </div>
        {/if}

        <textarea
          class="compositor-texto"
          bind:this={campoTexto}
          bind:value={entrada}
          onpaste={alPegar}
          rows="2"
          placeholder={modo === 'nota'
            ? 'Nota para el equipo — el cliente no la ve…'
            : escalada
              ? 'Escribí tu respuesta…'
              : 'Continuar la conversación…'}
          disabled={enviando}
          onkeydown={(e) => {
            // Enter envia, Shift+Enter hace salto de linea: es lo que la mano
            // ya espera de un chat.
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (modo === 'nota') guardarNota();
              else enviar();
            }
          }}
        ></textarea>
        <div class="compositor-pie">
          <!-- Emoji, adjuntar y micrófono. Iconos de 34px y no de 20: esta
               pantalla se usa con prisa, y un objetivo diminuto se falla. -->
          <div class="herramientas" hidden={modo === 'nota'}>
            <div class="emoji-caja">
              <button
                type="button"
                class="v2-btn v2-btn-quiet accion-icono"
                aria-label="Emoji"
                title="Emoji"
                aria-expanded={emojisAbiertos}
                onclick={() => (emojisAbiertos = !emojisAbiertos)}><Smile size={17} /></button
              >
              {#if emojisAbiertos}
                <div class="emoji-panel" role="group" aria-label="Elegí un emoji">
                  {#each EMOJIS as e (e)}
                    <button type="button" onclick={() => ponerEmoji(e)}>{e}</button>
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
                    <input type="file" hidden accept="image/jpeg,image/png" onchange={alElegirArchivo} />
                  </label>
                  <label>
                    <FileText size={14} /> Documento
                    <input type="file" hidden onchange={alElegirArchivo} />
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
                onclick={grabar}><Mic size={17} /></button
              >
            {/if}
          </div>

          <span class="compositor-nota">
            {#if modo === 'nota'}
              <strong class="nota-interna-aviso">Solo la ve el equipo</strong>
              <span class="v2-muted">· no se le envía al cliente</span>
            {:else if escalada}
              <!-- Más visible que antes (§11): cuando está escalada, esto sale
                   DIRECTO al cliente. "Le llega tal cual" no decía quién
                   habla ni que el asistente no interviene. -->
              <strong class="nota-directo">Se envía directo al cliente</strong>
              <span class="v2-muted">· no pasa por el asistente</span>
            {:else}
              Responde el asistente
            {/if}
            · <kbd class="v2-kbd">Enter</kbd> envía
          </span>

          {#if modo === 'nota'}
            <button
              class="v2-btn v2-btn-strong"
              type="button"
              onclick={guardarNota}
              disabled={enviando || !entrada.trim()}
              aria-busy={enviando}
            >
              {enviando ? 'Guardando…' : 'Guardar nota'}
            </button>
          {:else if adjunto}
            <button
              class="v2-btn v2-btn-primary"
              type="button"
              onclick={enviarAdjunto}
              disabled={enviando}
              aria-busy={enviando}
            >
              <Send size={14} />{enviando ? 'Enviando…' : 'Enviar archivo'}
            </button>
          {:else}
            <button
              class="v2-btn v2-btn-primary"
              type="submit"
              disabled={enviando || !entrada.trim()}
              aria-busy={enviando}
            >
              <Send size={14} />{enviando ? 'Enviando…' : 'Enviar'}
            </button>
          {/if}
        </div>
      </form>
    </div>
  {/if}
</section>

<!-- ── DERECHA: el contexto de la conversación ────────────────────────────
     Todo lo que ayuda a contestar pero no es la conversación: el ticket, qué
     hizo el asistente y qué dice la documentación. Antes vivía apilado encima
     del hilo y lo empujaba fuera de la vista. -->
{#if contextoAbierto}
  <!-- Fondo para cerrar el panel al hacer clic afuera. Solo existe mientras el
       panel está desplegado sobre el hilo. -->
  <button
    type="button"
    class="info-fondo"
    aria-label="Cerrar contexto"
    onclick={() => (contextoAbierto = false)}
  ></button>
{/if}

<aside class="info" class:abierto={contextoAbierto} aria-label="Contexto de la conversación">
  <button
    type="button"
    class="v2-btn v2-btn-sm info-cerrar"
    onclick={() => (contextoAbierto = false)}
  >
    <X size={14} /> Cerrar
  </button>

  {#if caso}
  <div class="caso-panel">
    <div class="caso-campo">
      <span class="v2-sub">Etiqueta</span>
      {#if conversacion.etiqueta}
        <Pill tone={etiquetaTone(conversacion.etiqueta)}>{etiquetaLabel(conversacion.etiqueta)}</Pill>
      {:else}
        <span class="v2-muted">Sin clasificar</span>
      {/if}
    </div>

    <div class="caso-campo">
      <span class="v2-sub">Asignado a</span>
      <form
        method="POST"
        action="?/asignar"
        bind:this={formularioAsignar}
        use:enhance={() => ({ update }) => update({ reset: false })}
      >
        <input type="hidden" name="caso_id" value={caso.id} />
        <input type="hidden" name="assigned_to" value={asignadoA} />
        <div class="asignado-picker">
          <button
            type="button"
            class="v2-btn asignado-trigger"
            onclick={() => (listaAbierta = !listaAbierta)}
          >
            {#if ownerActual}
              <Avatar name={ownerActual.name} size={18} />
              <span>{ownerActual.name}</span>
            {:else}
              <span class="v2-muted">Sin asignar</span>
            {/if}
            <ChevronDown size={14} style="margin-left:auto;opacity:0.6" />
          </button>
          {#if listaAbierta}
            <!-- Fondo invisible: cerrar al hacer clic afuera, patron estandar
                 sin depender de ninguna libreria de popover. -->
            <button
              type="button"
              class="asignado-fondo"
              aria-label="Cerrar"
              onclick={() => (listaAbierta = false)}
            ></button>
            <ul class="asignado-content">
              <li>
                <button
                  type="button"
                  class="asignado-item"
                  onclick={() => {
                    asignadoA = '';
                    listaAbierta = false;
                    formularioAsignar.requestSubmit();
                  }}
                >
                  <span class="v2-muted">Sin asignar</span>
                </button>
              </li>
              {#each owners as o (o.id)}
                <li>
                  <button
                    type="button"
                    class="asignado-item"
                    onclick={() => {
                      asignadoA = o.id;
                      listaAbierta = false;
                      formularioAsignar.requestSubmit();
                    }}
                  >
                    <Avatar name={o.name} size={18} />
                    <span>{o.name}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </form>
    </div>

    <a class="v2-btn v2-btn-sm caso-link" href="/tickets/{caso.id}">
      Ver ticket completo <ArrowRight size={14} />
    </a>
  </div>
  {/if}

  <!-- Conservar. Va arriba de todo y fuera de cualquier plegable: es una
       decisión sobre si esta conversación va a seguir existiendo, y hay que
       poder verla sin abrir nada. -->
  <div class="conservar" class:activa={conservada}>
    <label class="conservar-linea">
      <input
        type="checkbox"
        checked={conservada}
        disabled={guardandoConservar}
        onchange={(e) => guardarConservar(/** @type {HTMLInputElement} */ (e.currentTarget).checked)}
      />
      <span>
        <b>Conservar</b>
        <span class="v2-muted">— no borrar al vencer la retención</span>
      </span>
    </label>

    {#if pidiendoMotivo && !conservada}
      <div class="conservar-motivo">
        <input
          class="v2-input"
          type="text"
          bind:value={motivoConservar}
          placeholder="¿Por qué? Ej: reclamo en curso"
          onkeydown={(e) => { if (e.key === 'Enter') guardarConservar(true); }}
        />
        <button
          class="v2-btn v2-btn-sm"
          type="button"
          disabled={guardandoConservar || !motivoConservar.trim()}
          onclick={() => guardarConservar(true)}
        >
          Guardar
        </button>
      </div>
    {:else if conservada && motivoConservar}
      <p class="conservar-nota">{motivoConservar}</p>
    {/if}

    {#if errorConservar}<p class="conservar-mal">{errorConservar}</p>{/if}
  </div>

  {#if herramientas.length > 0}
  <!-- Abierto de entrada SOLO si hubo un bloqueo o un error. Si todo corrio
       normal el panel es secundario y no tiene por que ocupar la columna;
       cuando algo se freno o se rompio, el hallazgo tiene que estar a la
       vista sin que nadie sospeche primero -- que es justo lo que no pasa
       con un panel plegado que casi nadie abre. -->
  <details class="proceso" open={!!(diagnostico?.bloqueadas || diagnostico?.errores)}>
    <summary class="proceso-resumen">
      Ver proceso
      <span class="v2-muted">
        ({herramientas.length} paso{herramientas.length === 1 ? '' : 's'}{#if herramientas.some((h) => h.es_escritura)}, con escritura{/if})
      </span>
      <!-- Lo unico que se asoma con el panel cerrado. El resto de la traza se
           mira cuando hay una sospecha; un bloqueo o un fallo hay que verlo
           ANTES, porque cambia lo que quien atiende tiene que hacer. -->
      {#if diagnostico?.errores}
        <span class="diag-aviso diag-error">
          {diagnostico.errores} error{diagnostico.errores === 1 ? '' : 'es'}
        </span>
      {/if}
      {#if diagnostico?.bloqueadas}
        <span class="diag-aviso diag-bloqueo">
          {diagnostico.bloqueadas} bloqueada{diagnostico.bloqueadas === 1 ? '' : 's'}
        </span>
      {/if}
    </summary>
    <!-- Diagnostico de la IA. Va ARRIBA de la lista y no al final: quien abre
         esto lo hace porque sospecha de una respuesta, y lo primero que
         necesita saber es si algo se rompio o si el sistema hizo su trabajo.
         Leer catorce pasos para deducirlo es justo lo que hay que evitar. -->
    {#if diagnostico}
      <ul class="diag">
        <li>
          <CircleCheck size={14} style="color:var(--v2-moss);flex:none" />
          <b>{diagnostico.normales}</b>
          {diagnostico.normales === 1 ? 'ejecución normal' : 'ejecuciones normales'}
          <span class="v2-muted">corrió y devolvió datos</span>
        </li>
        <!-- Con cero, un renglon informativo. Con uno o mas, un BOTON que
             lleva al paso: el numero contesta "paso algo", y lo siguiente que
             se quiere es ver QUE, sin buscarlo entre catorce lineas. -->
        <li class:diag-hay={diagnostico.bloqueadas > 0}>
          <ShieldCheck size={14} style="color:var(--v2-clay);flex:none" />
          {#if diagnostico.bloqueadas > 0}
            <button type="button" class="diag-ir" onclick={() => irAlPaso('bloqueo')}>
              <b>{diagnostico.bloqueadas}</b>
              {diagnostico.bloqueadas === 1 ? 'acción bloqueada' : 'acciones bloqueadas'}
            </button>
            <span class="v2-muted">el sistema la frenó — no es una falla</span>
          {:else}
            <b>0</b> acciones bloqueadas
            <span class="v2-muted">el sistema la frenó — no es una falla</span>
          {/if}
        </li>
        <li class:diag-hay={diagnostico.errores > 0}>
          <CircleX size={14} style="color:var(--v2-rust);flex:none" />
          {#if diagnostico.errores > 0}
            <button type="button" class="diag-ir" onclick={() => irAlPaso('error')}>
              <b>{diagnostico.errores}</b>
              {diagnostico.errores === 1 ? 'error' : 'errores'} en herramienta
            </button>
            <span class="v2-muted">falló un sistema externo</span>
          {:else}
            <b>0</b> errores en herramienta
            <span class="v2-muted">falló un sistema externo</span>
          {/if}
        </li>
      </ul>
    {/if}

    <ol class="proceso-lista">
      {#each herramientas as h, i}
        <li
          class="proceso-item"
          class:bloqueada={h.es_bloqueo}
          class:paso-marcado={pasoMarcado === i}
          data-paso={i}
        >
          {#if h.es_bloqueo}
            <ShieldCheck size={15} style="color:var(--v2-clay);flex:none" />
          {:else if h.exito}
            <CircleCheck size={15} style="color:var(--v2-moss);flex:none" />
          {:else}
            <CircleX size={15} style="color:var(--v2-rust);flex:none" />
          {/if}
          <span class="proceso-nombre">{h.herramienta}</span>
          {#if h.n_registros !== null}
            <span class="v2-muted">{h.n_registros} resultado{h.n_registros === 1 ? '' : 's'}</span>
          {/if}
          {#if h.es_bloqueo}
            <!-- El motivo en palabras, no el codigo: el codigo queda en el
                 title para quien depure, pero lo que se lee dice que hacer. -->
            <span class="v2-muted" title={h.codigo_error}>
              {MOTIVO_BLOQUEO[h.codigo_error] ?? 'el sistema frenó esta acción'}
            </span>
          {:else if h.codigo_error}
            <span class="v2-muted" title={h.codigo_error}>{h.codigo_error.split(':')[0]}</span>
          {/if}
          <span class="v2-muted proceso-duracion">{h.duracion_ms} ms</span>
        </li>
      {/each}
    </ol>
  </details>
  {:else}
    <!-- Sin traza el panel entero desaparecia, y la columna quedaba con dos
         controles sueltos y un hueco: se lee como una pantalla rota, no como
         "no hay nada que mostrar". Es el caso normal de una conversacion que
         el asistente resolvio hablando, sin consultar ningun sistema. -->
    <p class="proceso-vacio">
      El asistente no consultó ningún sistema en esta conversación.
    </p>
  {/if}

  <!-- Copiloto documental. Mismo patron plegable que "Ver proceso": es ayuda
       lateral, no el contenido de la pantalla. -->
  <details class="docs" ontoggle={alAbrirDocs}>
  <!-- Una linea, no un bloque. Sin contenido activo ocupaba ancho para decir
       que existe, y ese ancho lo necesita el centro: resumen, conversacion y
       compositor. Se abre cuando hace falta. -->
  <summary class="proceso-resumen">
    Buscar en las guías
    {#if sugerencias.length}
      <span class="v2-muted">({sugerencias.length})</span>
    {/if}
  </summary>

  <form class="docs-buscar" onsubmit={alBuscarDocs}>
    <input
      class="v2-input"
      type="text"
      bind:value={consultaDocs}
      placeholder="¿Qué necesitás buscar?"
      aria-label="Buscar en la documentación interna"
    />
    <button class="v2-btn v2-btn-sm" type="submit" disabled={buscandoDocs}>Buscar</button>
  </form>

  {#if buscandoDocs}
    <p class="v2-muted docs-nota">Buscando…</p>
  {:else if errorDocs}
    <p class="docs-nota docs-malo">{errorDocs}</p>
  {:else if sugerencias.length === 0}
    <p class="v2-muted docs-nota">
      La documentación no cubre esta consulta.
      {#if mejorSimilitud !== null}
        Lo más parecido quedó en <span class="v2-num">{mejorSimilitud}</span>, por debajo del umbral.
      {/if}
    </p>
  {:else}
    {#each sugerencias as s, i}
      <article class="doc" class:abierto={expandido === i}>
        <button
          type="button"
          class="doc-head"
          onclick={() => (expandido = expandido === i ? null : i)}
          aria-expanded={expandido === i}
        >
          <span class="doc-codigo v2-num">{s.codigo || '—'}{#if s.version} v{s.version}{/if}</span>
          <span class="doc-titulo">{s.titulo || 'Sin título'}</span>
        </button>
        <p class="doc-texto">{s.contenido}</p>
        <div class="doc-pie">
          <button
            class="v2-btn v2-btn-sm"
            type="button"
            onclick={() => copiarFragmento(s.contenido, i)}
          >
            {copiado === i ? 'Copiado' : 'Copiar'}
          </button>
        </div>
      </article>
    {/each}
  {/if}
  </details>
</aside>

<style>
  /* ── columna del centro: la conversación ────────────────────────────── */
  .centro {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .centro-top {
    flex: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--v2-line);
  }
  .centro-quien {
    min-width: 0;
  }
  .centro-top h2 {
    margin: 0;
    font-size: 14.5px;
    font-weight: 640;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .centro-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 3px;
  }
  .ident {
    flex: none;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }
  /* Volver sólo tiene sentido cuando la lista no está al lado. */
  .volver {
    display: none;
    color: var(--v2-slate);
  }
  .aviso {
    flex-wrap: wrap;
    row-gap: 6px;
    flex: none;
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    padding: 8px 16px;
    font-size: 12.5px;
    color: var(--v2-rust);
    background: color-mix(in srgb, var(--v2-rust) 6%, transparent);
    border-bottom: 1px solid var(--v2-line);
  }
  .aviso-atender {
    margin-left: auto;
    flex: none;
  }
  /* Sin margin-left:auto a proposito: el hermano de la izquierda ya empuja al
     grupo a la derecha, y un segundo 'auto' los separaria a los extremos. */
  .aviso-resolver {
    flex: none;
  }
  .aviso-atendida {
    margin-left: auto;
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--v2-moss, #15803d);
    font-weight: 600;
  }
  .aviso-mal {
    flex: none;
    color: var(--v2-rust);
  }
  /* SOLO PARA PRUEBAS -- ver reiniciarConversacion(). El estilo local que
     imitaba a medias una accion destructiva se fue: ahora usa .v2-btn-danger
     del sistema, que ademas del color trae el borde punteado -- se distingue
     de una accion operativa antes de leer la etiqueta, no solo por el tono. */
  /* El hilo es lo único que scrollea acá: el encabezado y el compositor
     quedan fijos, para no tener que bajar hasta el fondo para escribir. */
  .hilo {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 16px;
  }
  .pie {
    flex: none;
    padding: 0 16px 14px;
  }

  /* ── columna de la derecha: el contexto ─────────────────────────────── */
  .info {
    /* 310 -> 292. Lo critico de esta columna es el ticket, el diagnostico, la
       etiqueta y la resolucion; lo demas se abre bajo demanda. Los 18px van
       al centro, que es donde se lee y se escribe. */
    width: 292px;
    flex: none;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 16px 20px;
    border-left: 1px solid var(--v2-line);
  }
  /* Por encima de 1240px la columna está siempre a la vista: ni botón para
     abrirla, ni botón para cerrarla, ni fondo que interceptar. */
  .contexto-toggle,
  .info-cerrar,
  .info-fondo {
    display: none;
  }
  .info-fondo {
    position: fixed;
    inset: 0;
    z-index: 55;
    background: rgba(28, 25, 23, 0.18);
    border: 0;
    padding: 0;
    cursor: default;
  }
  @media (max-width: 1240px) {
    .info-fondo {
      display: block;
    }
  }

  /* En la columna angosta los campos del ticket se apilan; en fila no
     entraban ni el nombre del responsable. */
  .caso-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }
  .caso-campo {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
  }
  .caso-campo > .v2-sub {
    font-size: 11.5px;
    white-space: nowrap;
  }
  .caso-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    align-self: flex-start;
  }
  .proceso,
  .docs {
    padding: 14px 0 0;
  }

  /* ── conservar ──────────────────────────────────────────────────────── */
  /* Sin recuadro mientras está apagada: es una casilla más, no una alerta.
     Al encenderla toma superficie, porque a partir de ahí sí es un estado
     que hay que poder ver de un vistazo. */
  .conservar {
    padding: 0 0 14px;
    border-bottom: 1px solid var(--v2-line-soft);
  }
  .conservar.activa {
    background: var(--v2-line-soft);
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 14px;
    border-bottom: 0;
  }
  .conservar-linea {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12.5px;
    line-height: 1.4;
    cursor: pointer;
  }
  .conservar-linea input {
    margin-top: 2px;
    flex: none;
    accent-color: var(--v2-ink);
  }
  .conservar-motivo {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }
  .conservar-motivo input {
    flex: 1;
    min-width: 0;
    font-size: 12.5px;
  }
  .conservar-nota {
    margin: 6px 0 0 22px;
    font-size: 11.5px;
    color: var(--v2-slate);
    line-height: 1.4;
  }
  .conservar-mal {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--v2-rust);
  }

  /* ── copiloto documental ────────────────────────────────────────────── */
  .docs-buscar {
    display: flex;
    gap: 6px;
    margin: 10px 0 4px;
  }
  .docs-buscar input {
    flex: 1;
    min-width: 0;
    font-size: 13px;
  }
  .docs-nota {
    font-size: 12.5px;
    line-height: 1.5;
    margin: 8px 0 0;
  }
  .docs-malo {
    color: var(--v2-rust);
  }
  /* Sin tarjeta: son citas de un documento, no objetos que se manipulan. */
  .doc {
    border-top: 1px solid var(--v2-line-soft);
    padding: 9px 0;
  }
  .doc-head {
    display: flex;
    flex-direction: column;
    gap: 1px;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    padding: 0;
    font: inherit;
    color: inherit;
    cursor: pointer;
  }
  .doc-codigo {
    font-size: 10.5px;
    color: var(--v2-slate);
  }
  .doc-titulo {
    font-size: 12.5px;
    font-weight: 620;
    letter-spacing: -0.01em;
    line-height: 1.35;
  }
  .doc-head:hover .doc-titulo {
    text-decoration: underline;
  }
  .doc-texto {
    font-size: 12.2px;
    color: var(--v2-slate);
    line-height: 1.5;
    margin: 5px 0 0;
    white-space: pre-wrap;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  /* Abierto: el fragmento entero, con su propio scroll para que un documento
     largo no empuje el hilo fuera de la vista. */
  .doc.abierto .doc-texto {
    display: block;
    max-height: 320px;
    overflow-y: auto;
  }
  .doc-pie {
    display: flex;
    justify-content: flex-end;
    margin-top: 6px;
  }
  .proceso-resumen {
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
    user-select: none;
  }
  .proceso-resumen .v2-muted {
    font-weight: 400;
  }
  .proceso-lista {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .proceso-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    padding: 4px 0;
  }
  .proceso-nombre {
    font-family: var(--v2-mono, monospace);
  }
  .proceso-duracion {
    margin-left: auto;
  }
  .proceso-vacio {
    margin: 0;
    font-size: 12px;
    color: var(--v2-slate);
  }

  /* ── qué pasó acá ───────────────────────────────────────────────────────
     Rótulo a la izquierda, texto a la derecha: se leen los cuatro rótulos en
     vertical de un vistazo y se entra al que interesa. Con el texto debajo
     del rótulo habría que recorrer ocho renglones para lo mismo. */
  .brief {
    margin: 0 0 4px;
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: var(--v2-ember-soft);
    border-radius: 7px;
    font-size: 12.5px;
    line-height: 1.45;
  }
  .brief-fila {
    display: grid;
    grid-template-columns: 8.5rem 1fr;
    gap: 10px;
    align-items: baseline;
  }
  .brief dt {
    color: var(--v2-slate);
    font-size: 11px;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .brief dd {
    margin: 0;
    color: var(--v2-ink);
  }
  /* El bloque era una sola masa rosa donde promesa, acciones y estado se
     fundian. El fondo de alerta se queda arriba, en el aviso de escalada, que
     es lo unico que de verdad alerta; el resumen pasa a tarjeta neutra con los
     renglones separados por una linea, para que el ojo encuentre cada
     pregunta sin leerlas todas. */
  .brief {
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
  }
  /* El orden en que alguien entiende un caso: que pide, que se intento, que
     se le dijo, que queda. 'Que hizo la IA' sale de un bloque aparte --viene
     de la traza, no de los textos del modelo-- asi que cada renglon lleva su
     posicion como dato y no por el lugar que ocupa en el marcado. */
  .brief {
    display: flex;
    flex-direction: column;
  }

  /* Con 'order' el orden visual no es el del DOM, asi que un selector de
     hermano adyacente pondria la linea entre los renglones equivocados. Se
     usa gap y un borde en todos menos el primero VISUAL, marcado por dato. */
  .brief {
    gap: 7px;
  }
  .brief-fila:not(.brief-primero) {
    border-top: 1px solid var(--v2-line-soft);
    padding-top: 7px;
  }
  /* Un renglon sin dato no puede pesar lo mismo que uno con dato: se ve, para
     que las cuatro preguntas esten siempre, pero no compite. */
  .brief-nada {
    color: var(--v2-slate);
    font-style: italic;
  }
  .brief-nota {
    color: var(--v2-slate);
    font-size: 11px;
  }

  .hizo {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .hizo li {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  /* Lo que se freno o fallo se lee distinto de lo que corrio bien, y no solo
     por el color: tambien por el peso y por el icono. */
  .hizo-bloqueo span:first-of-type {
    color: var(--v2-clay);
    font-weight: 600;
  }
  .hizo-error span:first-of-type {
    color: var(--v2-rust);
    font-weight: 600;
  }

  /* El aviso de escalada: tres piezas con jerarquia distinta -- que paso
     (fuerte), por que (medio), y el estado del CRM (chip aparte). */
  /* El recorte con puntos suspensivos lo dejaba en "sin datos pa..." -- que no
     dice nada y es peor que partirse en dos renglones. Ahora la FILA envuelve:
     el motivo se lleva la linea entera si hace falta, y los botones bajan con
     el, en vez de que el motivo desaparezca para que quepan. */
  .aviso-motivo {
    color: var(--v2-slate);
  }
  /* ── nota interna ───────────────────────────────────────────────────── */
  .modos {
    display: flex;
    gap: 4px;
    margin-bottom: 6px;
  }
  .modo {
    border: 1px solid transparent;
    background: none;
    font: inherit;
    font-size: 11.5px;
    color: var(--v2-slate);
    padding: 5px 10px;
    min-height: 30px;
    border-radius: 7px;
    cursor: pointer;
  }
  .modo:hover {
    color: var(--v2-ink);
  }
  .modo[aria-pressed='true'] {
    color: var(--v2-ink);
    font-weight: 650;
    border-color: var(--v2-line);
    background: var(--v2-card);
  }
  .modo-nota[aria-pressed='true'] {
    color: var(--v2-clay);
    border-color: color-mix(in srgb, var(--v2-clay) 45%, transparent);
  }

  /* El compositor entero cambia, no una pestaña chiquita: lo que hay que
     hacer imposible es escribir algo interno creyendo que es privado. */
  .compositor.es-nota {
    background: color-mix(in srgb, var(--v2-clay) 9%, transparent);
    border: 1px dashed color-mix(in srgb, var(--v2-clay) 45%, transparent);
    border-radius: 9px;
    padding: 8px;
  }
  .compositor.es-nota .compositor-texto {
    background: transparent;
  }
  .nota-interna-aviso {
    color: var(--v2-clay);
  }

  /* En el hilo tampoco se parece a un mensaje. */
  .chat-nota {
    align-self: stretch;
    max-width: 100%;
    background: color-mix(in srgb, var(--v2-clay) 8%, transparent);
    border: 1px dashed color-mix(in srgb, var(--v2-clay) 40%, transparent);
    color: var(--v2-ink);
    font-size: 12.5px;
  }
  .chat-nota::before {
    content: 'Nota interna · no la ve el cliente';
    display: block;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--v2-clay);
    margin-bottom: 3px;
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

  /* ── compositor ─────────────────────────────────────────────────────── */
  .compositor {
    position: relative;
  }
  .compositor.arrastrando {
    outline: 2px dashed var(--v2-ember);
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
    background: color-mix(in srgb, var(--v2-ember) 10%, var(--v2-card));
    color: var(--v2-ember);
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
  /* 38px, no 34: parecian decoracion. Y con hover visible -- un control sin
     respuesta al mouse no se lee como control. */
  .accion-icono {
    min-width: 38px;
    min-height: 38px;
    padding: 0;
    justify-content: center;
    cursor: pointer;
    color: var(--v2-slate);
    border-radius: 8px;
  }
  .accion-icono:hover {
    background: var(--v2-line-soft);
    color: var(--v2-ink);
  }
  .accion-icono:focus-visible {
    outline: 2px solid var(--v2-ember);
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
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
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
    background: var(--v2-line-soft);
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
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
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
    background: var(--v2-line-soft);
  }

  .adjunto-previo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px;
    margin-bottom: 6px;
    border: 1px solid var(--v2-line);
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
    background: var(--v2-line-soft);
    color: var(--v2-slate);
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

  .grabando {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 9px;
    margin-bottom: 6px;
    border: 1px solid color-mix(in srgb, var(--v2-rust) 35%, transparent);
    border-radius: 8px;
    font-size: 12.5px;
  }
  .grabando-punto {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--v2-rust);
    animation: latir 1.1s ease-in-out infinite;
    flex: none;
  }
  @keyframes latir {
    50% {
      opacity: 0.25;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .grabando-punto {
      animation: none;
    }
  }
  .grabando-reloj {
    font-weight: 700;
    color: var(--v2-rust);
    margin-right: auto;
  }

  /* Que sale directo al cliente no puede leerse igual que "Enter envía". */
  .nota-directo {
    color: var(--v2-ember);
  }

  /* Ayuda que aparece al pasar el mouse O al enfocar con el teclado. */
  .con-ayuda {
    position: relative;
    display: inline-flex;
  }
  .ayuda {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    z-index: 20;
    width: 250px;
    padding: 8px 10px;
    font-size: 11.5px;
    font-weight: 400;
    line-height: 1.4;
    color: var(--v2-ink);
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    box-shadow: 0 6px 18px rgb(0 0 0 / 12%);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s;
  }
  .con-ayuda:hover .ayuda,
  .con-ayuda:focus-within .ayuda {
    opacity: 1;
  }
  @media (prefers-reduced-motion: reduce) {
    .ayuda {
      transition: none;
    }
  }

  .aviso-caso {
    font-size: 11px;
    font-weight: 650;
    padding: 1px 8px;
    border-radius: 999px;
    color: var(--v2-slate);
    border: 1px solid var(--v2-line);
    white-space: nowrap;
  }
  @media (max-width: 640px) {
    /* En pantalla chica el rótulo de 8.5rem deja al texto en una columna
       inservible: pasan a apilarse. */
    .brief-fila {
      grid-template-columns: 1fr;
      gap: 1px;
    }
  }

  /* Diagnostico: tres lineas, no tres tarjetas. Es una lectura de dos
     segundos dentro de un panel plegable, no un tablero. */
  .diag {
    list-style: none;
    margin: 10px 0 0;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    font-size: 12.5px;
    border: 1px solid var(--v2-line);
    border-radius: 6px;
  }
  .diag li {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .diag b {
    font-variant-numeric: tabular-nums;
    min-width: 1.2em;
    text-align: right;
  }
  /* Un renglon con algo pesa mas que uno en cero. Cero bloqueadas y cero
     errores es la noticia buena y no tiene por que competir. */
  .diag-hay {
    font-weight: 600;
  }
  .diag-ir {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 0;
    background: none;
    font: inherit;
    color: inherit;
    padding: 2px 4px;
    margin: -2px -4px;
    border-radius: 5px;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 2px;
  }
  .diag-ir:hover {
    background: var(--v2-line-soft);
  }
  .diag-ir:focus-visible {
    outline: 2px solid var(--v2-ember);
    outline-offset: 1px;
  }
  /* El resaltado del paso al que se salto. Se apaga solo. */
  .paso-marcado {
    background: var(--v2-ember-soft);
    border-radius: 6px;
    padding-left: 6px;
    padding-right: 6px;
  }

  /* Los dos avisos del titulo cerrado. Sin borde de color al costado: se
     distinguen por el texto y el tono del fondo, que es lo que se lee. */
  .diag-aviso {
    font-size: 11px;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: 999px;
    white-space: nowrap;
  }
  .diag-error {
    color: var(--v2-rust);
    background: color-mix(in srgb, var(--v2-rust) 12%, transparent);
  }
  .diag-bloqueo {
    color: var(--v2-clay);
    background: color-mix(in srgb, var(--v2-clay) 14%, transparent);
  }
  /* Un bloqueo no es un fallo: se distingue del resto de la lista, pero sin
     la carga visual de un error. */
  .proceso-item.bloqueada .proceso-nombre {
    color: var(--v2-clay);
  }
  .asignado-picker {
    position: relative;
  }
  .asignado-trigger {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }
  /* Fondo invisible a pantalla completa: clic afuera cierra la lista. Es el
     patron sin dependencias -- ver por que se saco bits-ui mas arriba. */
  .asignado-fondo {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: transparent;
    border: none;
    cursor: default;
    padding: 0;
  }
  .asignado-content {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--v2-surface, #fff);
    border: 1px solid var(--v2-border, #e5e5e5);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 6px;
    min-width: 200px;
    z-index: 50;
    list-style: none;
    margin: 0;
  }
  .asignado-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border-radius: 7px;
    font-size: 13.5px;
    cursor: pointer;
    background: none;
    border: none;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }
  .asignado-item:hover,
  .asignado-item:focus-visible {
    background: var(--v2-surface-2, #f1f1f1);
    outline: none;
  }

  .chat-mensajes {
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 720px;
  }
  .dia {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 6px 0;
    color: var(--v2-slate);
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .dia::before,
  .dia::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--v2-line);
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
  .chat-otro {
    align-self: center;
    background: transparent;
    border: 1px dashed var(--v2-border, #e5e5e5);
    font-style: italic;
    opacity: 0.75;
  }
  .chat-hora {
    margin-top: 4px;
    font-size: 11px;
    opacity: 0.65;
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
  .adjunto-otro {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
    font-size: 11.5px;
    color: inherit;
    opacity: 0.85;
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
  .compositor {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-line);
  }
  .compositor-texto {
    width: 100%;
    resize: vertical;
    min-height: 44px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    padding: 9px 11px;
    background: var(--v2-card);
    color: var(--v2-ink);
    font-family: inherit;
    font-size: calc(var(--v2-fs) - 0.5px);
    line-height: 1.4;
  }
  .compositor-texto:focus {
    outline: 2px solid var(--v2-ember);
    outline-offset: -1px;
    border-color: transparent;
  }
  .compositor-texto:disabled {
    background: var(--v2-line-soft);
    color: var(--v2-slate);
    cursor: not-allowed;
  }
  .compositor-pie {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .compositor-nota {
    font-size: 11.5px;
    color: var(--v2-slate);
  }

  /* Debajo de 1240px las tres columnas ahogan el hilo. El contexto deja de
     estar fijo al lado y pasa a abrirse con el botón del encabezado -- no
     desaparece: el ticket y la documentación siguen estando a un clic. */
  @media (max-width: 1240px) {
    .contexto-toggle {
      display: inline-flex;
      margin-left: auto;
      flex: none;
    }
    .info {
      display: none;
    }
    .info.abierto {
      display: block;
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: min(340px, 88vw);
      z-index: 60;
      background: var(--v2-paper);
      box-shadow: -8px 0 24px rgba(0, 0, 0, 0.12);
    }
    .info-cerrar {
      display: inline-flex;
      margin-bottom: 12px;
    }
  }
  /* Y debajo de 1000px la lista deja de estar al lado (ver el layout), así que
     hace falta una forma de volver. */
  @media (max-width: 1000px) {
    .volver {
      display: grid;
      place-items: center;
    }
  }

  /* El orden de sacrificio, angosto: lo ultimo que se pierde es poder
     escribir. La fila del compositor tiene tres cosas --herramientas, aviso,
     boton-- y a 420px no entran; el AVISO es lo que se va a un renglon
     propio, nunca el boton ni los iconos, que son con lo que se trabaja.
     Encogerlo todo para que entre en una linea los deja ilegibles a los tres. */
  @media (max-width: 560px) {
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
</style>
