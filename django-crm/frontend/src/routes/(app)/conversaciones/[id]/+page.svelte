<script>
  import { untrack, onDestroy } from 'svelte';
  import { invalidate, goto } from '$app/navigation';
  import { enhance } from '$app/forms';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import ConversationHeader from '$lib/conversaciones/conversation/ConversationHeader.svelte';
  import EscalationSummary from '$lib/conversaciones/conversation/EscalationSummary.svelte';
  import HandoffControls from '$lib/conversaciones/conversation/HandoffControls.svelte';
  import MessageComposer from '$lib/conversaciones/composer/MessageComposer.svelte';
  import CasePanel from '$lib/conversaciones/context/CasePanel.svelte';
  import ActivityPanel from '$lib/conversaciones/context/ActivityPanel.svelte';
  import CustomerPanel from '$lib/conversaciones/context/CustomerPanel.svelte';
  import RetentionToggle from '$lib/conversaciones/context/RetentionToggle.svelte';
  import TracePanel from '$lib/conversaciones/context/TracePanel.svelte';
  import DocumentationPanel from '$lib/conversaciones/context/DocumentationPanel.svelte';
  import MessageThread from '$lib/conversaciones/messages/MessageThread.svelte';
  import { diaDe, etiquetaDia } from '$lib/conversaciones/formato.js';
  import { estadoDeDevolucion } from '$lib/conversaciones/devolucion.js';
  import {
    sesionDeGrabacion,
    soltarRecursosDelCompositor
  } from '$lib/conversaciones/grabacion.js';
  import {
    TriangleAlert,
    ChevronDown,
    ArrowRight,
    CircleCheck,
    CircleX,
    Send,
    X,
    Paperclip,
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
  // El registro del relevo. Mismo patrón que el resto: untrack porque el
  // componente se remonta entero al cambiar de conversación ({#key abierta}).
  let relevo = $state(untrack(() => data.relevo ?? []));

  /**
   * Vuelve a leer el registro del relevo desde el motor.
   *
   * Se llama DESPUÉS de que una transición terminó bien, nunca antes: si se
   * refrescara al lanzarla, el panel mostraría un movimiento que todavía puede
   * no haber ocurrido. Nada de optimismo acá — es un registro de auditoría.
   *
   * Sin esto, la pantalla sabía que acababa de reasignar la conversación y el
   * panel seguía mostrando el estado anterior hasta que alguien recargara.
   *
   * No hay sondeo ni temporizador: se refresca por un hecho, no por el paso
   * del tiempo. Un movimiento hecho desde OTRA pantalla aparece la próxima vez
   * que esta se abra, que es cuando alguien va a leerlo.
   */
  async function refrescarRelevo() {
    try {
      await invalidate('app:relevo');
      relevo = data.relevo ?? [];
    } catch {
      // El panel queda como estaba. Un registro desactualizado es mejor que
      // uno inventado, y la conversación se sigue atendiendo igual.
    }
  }
  let diagnostico = $state(untrack(() => data.diagnostico ?? null));
  let casos = $state(untrack(() => data.casos ?? []));

  // Que significa cada bloqueo, en el idioma de quien atiende. Un codigo como
  // PRECONDICION_NO_CUMPLIDA no le dice nada a alguien de soporte -- y de
  // esto depende que haga lo correcto: si el sistema lo freno por falta de
  // identidad, la accion es pedir la cedula, no reportar que la API fallo.
  const MOTIVO_BLOQUEO = {
    IDENTIDAD_NO_VERIFICADA: 'pidió datos de cuenta sin haber confirmado quién es',
    IDENTIDAD_NO_RESUELTA: 'no se pudo establecer de qué cliente se trata',
    DATO_DEL_EQUIPO_NO_CARGADO: 'la cuenta no tiene cargado el dato del equipo que esa consulta necesita',
    PRECONDICION_NO_CUMPLIDA: 'quiso ejecutar algo sin el paso previo que exige el procedimiento',
    FALTA_HABLAR_CON_EL_CLIENTE: 'la acción interrumpe el servicio y el cliente todavía no dijo qué le pasa',
    HERRAMIENTA_DESCONOCIDA: 'intentó usar algo que este rol no tiene permitido',
    LIMITE_DE_CONVERSACION: 'se alcanzó el tope de pasos de la conversación',
    CAMBIO_DE_CONTROL: 'una persona tomó la conversación antes de que la acción empezara'
  };

  /** Si los renglones de bloqueos y errores valen su lugar aunque uno esté en
      cero. El cero NO es ruido cuando el otro no lo está: con cuatro acciones
      bloqueadas, leer "0 errores en herramienta" es lo que confirma que no se
      rompió nada afuera y que el sistema frenó a propósito — justo la
      distinción que este panel existe para hacer. Con los dos en cero no dicen
      nada: son dos renglones de ceros debajo de "5 ejecuciones normales", que
      sola ya cuenta la historia entera. */
  let contrasteUtil = $derived(
    (diagnostico?.bloqueadas ?? 0) > 0 || (diagnostico?.errores ?? 0) > 0
  );

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

  /** Si el caso quedó en una cola de alguien. Es el ticket del CRM ya cargado,
      o al menos su id en la conversación cuando la ficha todavía no llegó.
      Decide si que falte el próximo paso es una alarma o solo una nota. */
  let tieneCaso = $derived(!!caso || !!conversacion?.caso_id);

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
      // La advertencia se guarda para cuando de verdad no hay a quién
      // preguntarle. Medido el 08/09/2026: este campo estaba vacío en las 52
      // conversaciones escaladas —no solo en las anteriores al 06/09, como
      // decía este comentario— porque el evaluador lo tenía como opcional y
      // no lo completaba nunca (corregido en nucleo/seguimiento/
      // escalamiento.py). Con eso, el triángulo salía en el 100% de los
      // casos: una alarma que suena siempre deja de ser una alarma.
      //
      // Y sonaba aun teniendo el caso abierto en el CRM, con responsable
      // asignado, a la vista en esta misma pantalla. Eso no es "nadie sabe
      // qué sigue": es que el asistente no lo dejó escrito, y el caso está
      // en una cola. Lo que SÍ merece alarma es lo otro: ni paso anotado ni
      // caso abierto, que es un cliente esperando a nadie.
      alerta: !tieneCaso,
      vacio: tieneCaso
        ? 'El asistente no dejó anotado el próximo paso. El caso quedó abierto en el CRM.'
        : 'Sin próximo paso anotado y sin caso abierto en el CRM: no está en ninguna cola.'
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
  /** Si la columna derecha tiene algo que valga su ancho. Lo accionable es:
      el ticket del CRM, el diagnostico de la IA, la etiqueta y la resolucion.
      Sin nada de eso son dos controles sueltos ocupando 292px que el chat
      necesita -- y no se llena con tarjetas inventadas: se cierra. */
  let hayContexto = $derived(
    !!caso ||
      herramientas.length > 0 ||
      !!conversacion?.etiqueta ||
      !!conversacion?.caso_id ||
      conversacion?.conservar
  );

  let hayResumenDelCaso = $derived(
    !!conversacion?.escalada_a_humano || resumenEscalada.some((f) => f.texto) || hizoLaIA.length > 0
  );

  let entrada = $state('');
  let enviando = $state(false);
  let error = $state('');
  /** Desenlace del último intento de devolver a la IA (T6), o null si el
      último envío no lo pidió. Lo calcula devolucion.js: la pantalla no
      deduce el desenlace, lo traduce. */
  let avisoDevolucion = $state(/** @type {any} */ (null));
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

  /* Quien tiene la conversacion, leido SIEMPRE del encabezado que manda el
      motor -- nunca puesto a mano por un clic (B3.4, D4). Si dos personas la
      toman a la vez, la pantalla de la que perdio no puede creer que gano: el
      409 refresca y muestra a quien quedo.
      Gobernada: asignada_a_* por id de usuario. Legado: tomada_por, que es un
      nombre, hasta que G8 la adopte. */
  let gobernada = $derived((conversacion.relevo_version ?? 0) > 0);
  let asignadaA = $derived(
    (gobernada ? conversacion.asignada_a_nombre : conversacion.tomada_por) ?? ''
  );
  let esMia = $derived(
    gobernada
      ? !!conversacion.asignada_a_usuario_id &&
          String(conversacion.asignada_a_usuario_id) === String(data.yo?.id ?? '')
      : !!conversacion.tomada_por && conversacion.tomada_por === (data.yo?.nombre ?? '')
  );
  let esAdmin = $derived(data.rol === 'ADMIN');

  async function marcarAtendida() {
    if (marcandoAtendida) return;
    marcandoAtendida = true;
    errorAtender = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/atender`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          caso_id: conversacion.caso_id ?? null,
          // Soltar es el mismo camino: quien lo tomo por error, o termina su
          // turno, lo devuelve a la cola. Tomar un caso NO es resolverlo, y
          // por eso se puede deshacer -- 'Marcar como resuelta' no.
          soltar: esMia,
          // Una por clic: si la respuesta se pierde y se vuelve a pulsar, el
          // motor reconoce la misma operacion y no deja dos eventos.
          clave_operacion: crypto.randomUUID()
        })
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        errorAtender = conflictoDeAsignacion(datos);
        // Otra persona gano, o ya no era de quien la soltaba: se relee para
        // mostrar como quedo, en vez de dejar la pantalla con lo que se creia.
        await sondearMensajesNuevos();
        return;
      }
      await sondearMensajesNuevos();
      // El servidor toma el ticket a nombre de quien dio "Atender" (ver el
      // proxy) -- reflejarlo ya mismo en "Asignado a", sin esperar a que
      // alguien reabra el ticket para verlo.
      if (datos.asignado) asignadoA = datos.asignado.id;
      // Sin esto, la lista de la izquierda (+layout.svelte, otro load())
      // no se entera hasta el proximo sondeo -- hasta 8s despues. Con
      // invalidate() se refresca al instante, apenas se guarda.
      invalidate('app:conversaciones');
      await refrescarRelevo();
    } catch (/** @type {any} */ err) {
      errorAtender = err?.message || 'No se pudo guardar.';
    } finally {
      marcandoAtendida = false;
    }
  }

  /** Un 409 de asignacion, dicho como lo que paso. */
  function conflictoDeAsignacion(/** @type {any} */ datos) {
    const quien = datos?.asignada_a;
    switch (datos?.codigo) {
      case 'ya_asignada':
        return quien ? `La tomó ${quien} antes.` : 'Otra persona la tomó antes.';
      case 'no_es_suya':
        return quien ? `La tiene ${quien}: solo esa persona puede soltarla.` : 'Ya no la tenés asignada.';
      case 'control_ia':
        return 'La atiende la IA: para tomarla usá «Intervenir».';
      case 'no_abierta':
        return 'La conversación ya está cerrada.';
      // Solo puede venir de Reasignar (transiciones.py::reasignar): una
      // reasignación deja evento de auditoría y el legado no tiene eventos,
      // así que primero hay que adoptarla -- eso es G8 y todavía no existe.
      // Se dice lo que pasa y por qué, sin sugerir que mirarla la adopte.
      case 'legado_sin_relevo':
        return 'Es anterior al relevo: no se puede reasignar hasta adoptarla.';
      default:
        return datos?.error || 'No se pudo guardar.';
    }
  }

  // --- reasignar (solo ADMIN, B3.4 / T4) -------------------------------------
  let reasignando = $state(false);
  let destinoReasignar = $state('');
  let motivoReasignar = $state('');
  let guardandoReasignar = $state(false);
  let errorReasignar = $state('');

  async function reasignar() {
    if (guardandoReasignar) return;
    errorReasignar = '';
    if (!destinoReasignar) {
      errorReasignar = 'Elegí a quién.';
      return;
    }
    if (!motivoReasignar.trim()) {
      errorReasignar = 'El motivo es obligatorio.';
      return;
    }
    guardandoReasignar = true;
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/reasignar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          destino_usuario_id: destinoReasignar,
          motivo: motivoReasignar.trim(),
          clave_operacion: crypto.randomUUID()
        })
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        errorReasignar = conflictoDeAsignacion(datos);
      } else {
        reasignando = false;
        destinoReasignar = '';
        motivoReasignar = '';
        invalidate('app:conversaciones');
        await refrescarRelevo();
      }
      await sondearMensajesNuevos();
    } catch (/** @type {any} */ err) {
      errorReasignar = err?.message || 'No se pudo reasignar.';
    } finally {
      guardandoReasignar = false;
    }
  }

  // Los cuatro estados de un envío, en palabras. 'pendiente' dice "saliendo"
  // y no "pendiente": lo segundo suena a que quedó algo por hacer, y lo que
  // pasa es que el acuse todavía no volvió.


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
    // Sin su clave, "reintentar" solo podria mandar OTRO mensaje igual: es lo
    // que pasaba antes -- cada intento dejaba una copia en el hilo (D15). Los
    // mensajes guardados antes de que existiera la clave no se reintentan.
    if (!m.clave_idempotencia) {
      error = 'Este mensaje no se puede reintentar sin duplicarlo. Escribilo de nuevo.';
      return;
    }
    reintentando = m.id ?? m.clave_idempotencia;
    error = '';
    // El desenlace del intento anterior deja de valer en cuanto empieza otro:
    // mostrarlo mientras este está en vuelo diría algo de un envío que ya no es
    // el que el operador está mirando.
    avisoDevolucion = null;
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/humano`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // MISMA clave y MISMA intención. La clave evita el segundo mensaje al
        // cliente; la intención evita que un T6 se convierta en un envío normal
        // y la conversación se quede en manos de la persona sin que nadie lo
        // haya decidido.
        body: JSON.stringify({
          mensaje: m.contenido,
          clave_idempotencia: m.clave_idempotencia,
          devolver_al_asistente: m.devolver === true
        })
      });
      const datos = await resp.json();
      avisoDevolucion = estadoDeDevolucion({ pedida: m.devolver === true, ok: resp.ok, datos });
      if (!resp.ok) {
        error = datos.error || 'No se pudo reenviar.';
        return;
      }
      if (datos.aviso) error = `Tampoco salió esta vez: ${datos.aviso}`;
      if (datos.devuelto_al_asistente) {
        conversacion.control_efectivo = 'ia';
        conversacion.control = 'ia';
        conversacion.escalada_a_humano = false;
        conversacion.necesita_atencion_humana = false;
        modo = 'responder';
        invalidate('app:conversaciones');
      }
      // Igual que en el envío: reintentar un T6 deja evento haya vuelto o no
      // a la IA. Un reenvío que no pedía devolver no toca el relevo, y por eso
      // no se refresca nada.
      if (m.devolver === true) await refrescarRelevo();
      await sondearMensajesNuevos();
    } catch (/** @type {any} */ err) {
      error = err?.message || 'No se pudo reenviar.';
      avisoDevolucion = estadoDeDevolucion({ pedida: m.devolver === true, ok: false, datos: null });
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
    // Pegar, arrastrar y elegir pasan todos por aca: un adjunto le llega al
    // cliente igual que un texto, asi que con la IA atendiendo no se toma.
    if (!f || bloqueadoPorIA) return;
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
      // Una por adjunto compuesto: si el envio se corta y se vuelve a apretar
      // Enviar, el motor reconoce el mismo adjunto en vez de guardar otro.
      clave_idempotencia: crypto.randomUUID(),
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

  // El micrófono, el MediaRecorder y el cronómetro viven en `grabacion.js`
  // (D29). Esta página sigue siendo la dueña -- crea la sesión, refleja su
  // estado y la suelta al desmontar -- pero el recurso tiene un solo camino de
  // liberación y se puede probar sin montar un componente.
  const voz = sesionDeGrabacion({
    alArchivo: (f) => tomarArchivo(f),
    alFallar: (m) => (error = m),
    alCambiar: ({ grabando: g, pausada }) => {
      grabando = g;
      grabPausada = pausada;
    },
    alSegundo: (s) => (segundos = s)
  });

  function grabar() {
    if (bloqueadoPorIA) return;
    voz.iniciar();
  }

  const pausarGrabacion = () => voz.pausar();
  /** Parar deja la grabación como adjunto pendiente de confirmación. */
  const pararGrabacion = () => voz.parar();
  /** Cancelar la tira: el onstop no llega a armar el adjunto. */
  const cancelarGrabacion = () => voz.cancelar();

  // D29. La conversación se REMONTA entera al cambiar de chat (el {#key
  // abierta} de +layout.svelte), y hasta acá no había un solo onDestroy: el
  // micrófono podía quedar abierto, el cronómetro vivo y el object URL del
  // adjunto sin revocar. Irse de una conversación no es terminar de grabar, así
  // que esto suelta sin armar ningún adjunto.
  onDestroy(() => soltarRecursosDelCompositor({ sesion: voz, adjunto }));

  const reloj = (/** @type {number} */ s) =>
    `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  /** Manda el adjunto. El texto del cuadro viaja como pie cuando el tipo lo
      acepta -- el AUDIO no lo acepta (Meta lo ignora en silencio), así que en
      ese caso el texto se manda aparte, como mensaje propio, en vez de
      perderse. */
  async function enviarAdjunto() {
    if (!adjunto || enviando || bloqueadoPorIA) return;
    enviando = true;
    error = '';
    const aceptaPie = limites?.[adjunto.tipo]?.acepta_pie ?? false;
    const pie = aceptaPie ? entrada.trim() : '';
    try {
      const cuerpo = new FormData();
      cuerpo.set('archivo', adjunto.archivo, adjunto.nombre);
      cuerpo.set('tipo', adjunto.tipo);
      cuerpo.set('pie', pie);
      cuerpo.set('clave_idempotencia', adjunto.clave_idempotencia);
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clave_operacion: crypto.randomUUID() })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorResolver = datos.error || 'No se pudo guardar.';
        return;
      }
      conversacion = { ...conversacion, estado: 'cerrada' };
      atendida = true;
      invalidate('app:conversaciones');
      await refrescarRelevo();
    } catch (/** @type {any} */ err) {
      errorResolver = err?.message || 'No se pudo guardar.';
    } finally {
      resolviendo = false;
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
      for (const crudo of datos.mensajes ?? []) {
        // LA RUTA DEVUELVE OTRA FORMA. /api/conversaciones/<id>/mensajes se
        // escribio para la vista de TICKETS y responde {quien, texto}; esta
        // pantalla trabaja con {rol, contenido}. Reusar la ruta sin traducir
        // metia en el hilo mensajes sin texto y sin rol: se dibujaban como
        // burbujas vacias, con el aviso de "tipo que todavia no mostramos" --
        // y el texto SI estaba en la base.
        //
        // Se traduce aca y no se cambia la ruta: la vista de tickets espera
        // su forma, y romperla para arreglar esta seria cambiar dos cosas
        // para arreglar una.
        const m = {
          ...crudo,
          rol: crudo.rol
            ?? (crudo.quien === 'cliente' ? 'user'
              : crudo.quien === 'humano' ? 'humano' : 'assistant'),
          contenido: crudo.contenido ?? crudo.texto ?? ''
        };
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
      // MEZCLA, no reemplazo: la ruta de sondeo devuelve el encabezado que
      // arma el motor, y la pantalla arranca con el que le dio el servidor.
      // Son el mismo objeto, pero si alguno de los dos gana un campo antes
      // que el otro, reemplazar entero lo borraria a mitad de sesion.
      if (datos.conversacion) conversacion = { ...conversacion, ...datos.conversacion };
      if (!marcandoAtendida && datos.conversacion) {
        atendida = !!datos.conversacion.atendida;
      }
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


  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');


  let asignadoA = $state(caso?.assignee_id ?? '');
  let ownerActual = $derived(owners.find((o) => o.id === asignadoA) ?? null);
  let listaAbierta = $state(false);
  /** @type {HTMLFormElement} */
  let formularioAsignar = $state();


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
  // Quien controla la conversacion HOY lo calcula el motor (control_efectivo,
  // B3.3b): legado -> las banderas; gobernada -> la columna control, que
  // incluye una intervencion. Si el motor todavia no lo manda, se cae a la
  // regla de siempre.
  let escalada = $derived(
    conversacion.control_efectivo ? conversacion.control_efectivo === 'humano' : iaEnPausa
  );


  /** El hilo con separadores de dia intercalados: un chat largo sin ellos
      obliga a pasar el mouse por cada burbuja para ubicarse en el tiempo. */

  /** El hilo, para poder pedirle que baje al final cuando UNO envia.
      El autoscroll que sigue al cliente vive dentro del componente. */
  let hiloRef = $state();

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

  // ==========================================================================
  //  VENTANA DE 24 H DE WHATSAPP
  //
  //  Meta solo acepta texto libre dentro de las 24 h desde el último mensaje
  //  DEL CLIENTE. Hasta ahora eso se descubría cuando Enviar fallaba.
  //
  //  Esto INFORMA, no autoriza. Quien decide es Meta al recibir el envío, y
  //  el manejo del rechazo (burbuja `sinEntregar` con el motivo) sigue igual
  //  de vivo: si el reloj de acá está corrido, el que manda es el de allá.
  // ==========================================================================

  /** Lo que dijo el servidor, más el instante MONOTÓNICO en que llegó. */
  let ventanaBase = $state(
    /** @type {{abierta: boolean|null, restante_seg: number|null, recibidoEn: number}|null} */ (
      null
    )
  );

  // Se resincroniza en cada sondeo: 'conversacion' se reemplaza entera, así
  // que un mensaje nuevo del cliente reabre la ventana en pantalla sin
  // recargar, que es justo lo que hace falta cuando alguien está mirando.
  //
  // 'performance.now()' y no 'Date.now()': es un reloj MONOTÓNICO, que no
  // salta si el sistema ajusta la hora (un sync de NTP, un cambio de zona, un
  // portátil que vuelve de suspensión). Con Date.now() un ajuste de reloj
  // hacia atrás haría que el contador CREZCA, y uno hacia adelante cerraría
  // la ventana en pantalla antes de tiempo. Ninguno de los dos avisa.
  $effect(() => {
    const v = conversacion?.ventana_whatsapp;
    ventanaBase = v ? { ...v, recibidoEn: performance.now() } : null;
  });

  /** Sólo para que el contador avance entre sondeos. */
  let tic = $state(performance.now());
  $effect(() => {
    if (!ventanaBase) return;
    const id = setInterval(() => (tic = performance.now()), 15000);
    // Un navegador RALENTIZA los timers de una pestaña en segundo plano --
    // hasta un tic por minuto, o ninguno. Sin esto, volver después de veinte
    // minutos mostraba el contador congelado en donde había quedado. Al
    // volver se recalcula de una y además el sondeo (que ya escucha 'focus')
    // trae el dato autoritativo del servidor.
    const alVolver = () => (tic = performance.now());
    document.addEventListener('visibilitychange', alVolver);
    window.addEventListener('focus', alVolver);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', alVolver);
      window.removeEventListener('focus', alVolver);
    };
  });

  // Se descuenta el tiempo TRANSCURRIDO, no se recalcula desde la fecha
  // absoluta: un navegador con la hora corrida daría un contador equivocado
  // que se ve igual de convincente que uno correcto. El instante autoritativo
  // lo puso el servidor; acá sólo se le resta lo que pasó desde que llegó.
  let ventanaRestante = $derived(
    ventanaBase?.restante_seg == null
      ? null
      : Math.max(0, ventanaBase.restante_seg - Math.floor((tic - ventanaBase.recibidoEn) / 1000))
  );

  /** true abierta · false cerrada · null no aplica (otro canal, o el cliente
      nunca escribió). null NO es cerrada: no se bloquea por un dato que no
      existe. */
  let ventanaAbierta = $derived(
    ventanaBase?.abierta == null ? null : ventanaBase.abierta && (ventanaRestante ?? 0) > 0
  );

  let ventanaPorCerrarse = $derived(
    ventanaAbierta === true && (ventanaRestante ?? 0) <= 60 * 60
  );

  /** El cuadro de texto se bloquea SOLO para lo que va al cliente. La nota
      interna sigue disponible: no sale por el canal, asi que la ventana de
      Meta no la gobierna -- y anotar lo que pasa mientras no se puede
      contestar es justo lo que alguien necesita hacer en ese momento. */
  let bloqueadoPorVentana = $derived(ventanaAbierta === false && modo !== 'nota');

  /* Hilo REAL de WhatsApp que atiende la IA: acá no se puede "continuar la
      conversación". Ese camino le hablaba al asistente como si fuera el
      cliente -- /chat nunca envía a Meta--, así que dejaba guardado un mensaje
      que el cliente no escribió y le movía la ventana de 24 h. El motor ya lo
      rechaza (403); esto evita ofrecer un gesto que no puede funcionar.
      Tomar el control para responder como persona es "Intervenir", que llega
      en una fase posterior (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, T8).
      Cubre TODO lo que le llega al cliente: texto, imagen, documento, nota de
      voz y plantilla. Solo la nota interna sigue, porque no sale del equipo. */
  let bloqueadoPorIA = $derived(
    !escalada && conversacion.canal === 'whatsapp' && modo !== 'nota'
  );

  let interviniendo = $state(false);
  let errorIntervenir = $state('');

  /* Tomar el control de una conversacion que atiende la IA. Solo adquiere el
      control: no le manda nada al cliente. El compositor se habilita cuando el
      motor CONFIRMA (se relee la conversacion), nunca antes: si otra persona
      intervino primero, el 409 lo dice y no se habilita nada. */
  async function intervenir() {
    if (interviniendo) return;
    interviniendo = true;
    errorIntervenir = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/intervenir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clave_operacion: crypto.randomUUID() })
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        errorIntervenir = datos.error || 'No se pudo tomar el control.';
      } else {
        await refrescarRelevo();
      }
      await sondearMensajesNuevos();
    } catch (/** @type {any} */ err) {
      errorIntervenir = err?.message || 'No se pudo tomar el control.';
    } finally {
      interviniendo = false;
    }
  }

  function comoDuracion(/** @type {number} */ seg) {
    const h = Math.floor(seg / 3600);
    const m = Math.floor((seg % 3600) / 60);
    return h > 0 ? `${h} h ${m} min` : `${m} min`;
  }

  // --- plantillas -----------------------------------------------------------
  //  Se piden recién cuando alguien las necesita: es una llamada en vivo a
  //  Meta, y la mayoría de las conversaciones se atienden con la ventana
  //  abierta. Pedirlas en cada carga del hilo sería pagarlas siempre para
  //  usarlas casi nunca.

  let eligiendoPlantilla = $state(false);
  let plantillas = $state(/** @type {any[]} */ ([]));
  let cargandoPlantillas = $state(false);
  let errorPlantillas = $state('');
  let plantillaElegida = $state(/** @type {any} */ (null));
  let valoresPlantilla = $state(/** @type {string[]} */ ([]));
  let enviandoPlantilla = $state(false);

  async function abrirPlantillas() {
    if (bloqueadoPorIA) return;
    eligiendoPlantilla = true;
    plantillaElegida = null;
    if (plantillas.length || cargandoPlantillas) return;
    cargandoPlantillas = true;
    errorPlantillas = '';
    try {
      const resp = await fetch('/api/canales/plantillas');
      const datos = await resp.json();
      if (!resp.ok) {
        errorPlantillas = datos.error || 'No se pudieron leer las plantillas.';
        return;
      }
      plantillas = datos.plantillas ?? [];
      // Distinguir "no hay ninguna aprobada" de "hay, pero ninguna lista":
      // en el segundo caso alguien está esperando una aprobación de Meta y
      // eso se resuelve solo; en el primero hay que ir a crear una.
      if (!plantillas.length && (datos.total_en_meta ?? 0) > 0) {
        errorPlantillas =
          `Esta cuenta tiene ${datos.total_en_meta} plantilla(s) en Meta, pero ` +
          `ninguna aprobada todavía. Hasta que Meta apruebe una no hay forma ` +
          `de escribirle al cliente fuera de la ventana.`;
      }
    } catch (/** @type {any} */ err) {
      errorPlantillas = err?.message || 'No se pudieron leer las plantillas.';
    } finally {
      cargandoPlantillas = false;
    }
  }

  /** Si hay alguna plantilla que sirva para RETOMAR UN CASO.

      Meta clasifica cada plantilla, y la categoria no es una etiqueta
      cosmetica: una MARKETING existe para promocionar, se le puede haber
      dado de baja al cliente, y llega con la cara equivocada cuando lo que
      se quiere es seguir una falla de servicio. UTILITY es la que
      corresponde.

      Se mira la categoria y no el texto: el texto lo escribio alguien y
      puede decir cualquier cosa; la categoria la aprobo Meta.

      Hoy Rapilink tiene UNA sola aprobada, MARKETING, y su encabezado dice
      "Bienvenido a Isergy". Sin este aviso la pantalla ofreceria una salida
      que en la practica no lo es. */
  let hayPlantillaDeServicio = $derived(
    plantillas.some((p) => ['UTILITY', 'SERVICE'].includes((p.categoria ?? '').toUpperCase()))
  );

  function elegirPlantilla(/** @type {any} */ p) {
    plantillaElegida = p;
    valoresPlantilla = Array.from({ length: p.variables ?? 0 }, () => '');
  }

  /** El texto tal como lo va a leer el cliente. Se arma acá sólo para la
      vista previa: el que se envía y se guarda lo arma el motor, con la
      plantilla que vuelve a leer de Meta en ese momento. */
  let vistaPreviaPlantilla = $derived.by(() => {
    if (!plantillaElegida) return '';
    let cuerpo = plantillaElegida.cuerpo ?? '';
    valoresPlantilla.forEach((v, i) => {
      cuerpo = cuerpo.replaceAll(`{{${i + 1}}}`, v || `{{${i + 1}}}`);
    });
    const enc = (plantillaElegida.encabezado ?? '').trim();
    return enc ? `${enc}\n\n${cuerpo}` : cuerpo;
  });

  let plantillaCompleta = $derived(
    !!plantillaElegida && valoresPlantilla.every((v) => v.trim().length > 0)
  );

  async function enviarPlantilla() {
    if (!plantillaElegida || enviandoPlantilla || !plantillaCompleta || bloqueadoPorIA) return;
    enviandoPlantilla = true;
    errorPlantillas = '';
    try {
      const resp = await fetch(`/api/conversaciones/${conversacion.id}/plantilla`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plantilla: plantillaElegida.nombre,
          variables: valoresPlantilla,
          clave_idempotencia: crypto.randomUUID()
        })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        errorPlantillas = datos.error || 'No se pudo enviar la plantilla.';
        return;
      }
      eligiendoPlantilla = false;
      // Si el canal la rechazó, se dice acá y además queda en la burbuja: el
      // aviso de arriba desaparece y el mensaje se queda en el hilo.
      if (datos.aviso) error = `Se guardó pero no salió: ${datos.aviso}`;
      await sondearMensajesNuevos();
      requestAnimationFrame(() => hiloRef?.alFinal(true));
    } catch (/** @type {any} */ err) {
      errorPlantillas = err?.message || 'No se pudo enviar la plantilla.';
    } finally {
      enviandoPlantilla = false;
    }
  }

  async function enviar() {
    const texto = entrada.trim();
    // `enviando` es la guarda del doble envío: Enter repetido, doble clic y el
    // botón entran todos por acá y salen sin hacer nada mientras el anterior
    // siga en vuelo. Es lo que impide que la clave de idempotencia se
    // regenere: no hay segundo intento hasta que el primero termina.
    if (!texto || enviando) return;
    avisoDevolucion = null;

    // El caso frontera: empezó a escribir con la ventana abierta y pulsa
    // Enviar después del vencimiento. El borrador NO se pierde -- se corta
    // ANTES de vaciar 'entrada' -- y se le ofrece la salida que sí existe.
    //
    // Vale para las dos ramas de abajo, no sólo la escalada. Si no está
    // escalada, lo que se escribe acá entra como si lo hubiera dicho el
    // cliente y contesta el asistente -- y ESA respuesta también sale por
    // WhatsApp, así que también la rechaza Meta. Dejarla pasar sería además
    // peor que un envío fallido: escribiría un mensaje de cliente que el
    // cliente no mandó, y la ventana pasaría a verse abierta por un mensaje
    // nuestro. Justo lo que este cálculo existe para no hacer.
    //
    // (Corrección 16/09/2026: esa respuesta NO sale por WhatsApp -- /chat no
    // envía a ningún medio. El daño era igual: el mensaje falso del cliente
    // quedaba guardado. Hoy ese camino está cerrado para hilos reales; ver
    // bloqueadoPorIA.)
    if (bloqueadoPorIA) return;
    if (ventanaAbierta === false) {
      error =
        'La ventana de 24 h de WhatsApp se cerró mientras escribías. Tu texto ' +
        'sigue acá; para volver a contactar al cliente hay que usar una plantilla.';
      abrirPlantillas();
      return;
    }

    entrada = '';
    enviando = true;
    error = '';

    if (escalada) {
      // Una sola burbuja: lo que el agente escribio ES la respuesta, no hay
      // nada que "contestar" del otro lado.
      // La intención se congela ACÁ, con la burbuja. Si se leyera `modo` más
      // tarde, un clic en otra pestaña del compositor mientras el envío está
      // en vuelo cambiaría lo que el reintento le pide al motor.
      const devolviendo = modo === 'responder_y_devolver';
      const burbuja = {
        rol: 'assistant',
        contenido: texto,
        creado_en: new Date().toISOString(),
        // La clave viaja con la burbuja: "Reintentar" la reusa y el motor
        // reintenta la entrega de ESA fila en vez de guardar otra (D15).
        clave_idempotencia: crypto.randomUUID(),
        // Y la intención viaja con ella por el mismo motivo: reintentar un T6
        // como si fuera un envío normal dejaría la conversación en manos de la
        // persona sin que nadie lo hubiera decidido.
        devolver: devolviendo,
        /** @type {string|null} */ sinEntregar: null
      };
      mensajes.push(burbuja);
      // Forzado, no condicional: el efecto de arriba solo sigue al que ya
      // estaba mirando el final, y quien acaba de apretar Enviar quiere ver
      // lo que envio aunque hubiera subido a releer algo.
      hiloRef?.forzarAlFinal(mensajes.length);
      try {
        const resp = await fetch(`/api/conversaciones/${conversacion.id}/humano`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mensaje: texto,
            clave_idempotencia: burbuja.clave_idempotencia,
            devolver_al_asistente: devolviendo
          })
        });
        const datos = await resp.json();
        avisoDevolucion = estadoDeDevolucion({ pedida: devolviendo, ok: resp.ok, datos });
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
        if (datos.devuelto_al_asistente) {
          conversacion.control_efectivo = 'ia';
          conversacion.control = 'ia';
          conversacion.escalada_a_humano = false;
          conversacion.necesita_atencion_humana = false;
          modo = 'responder';
          invalidate('app:conversaciones');
        }
        // Fuera del `if`: una devolución que NO se aplicó también deja su
        // evento ('devolucion_fallida'), y ese es justo el movimiento que
        // alguien va a querer ver en el registro.
        if (devolviendo) await refrescarRelevo();
      } catch (/** @type {any} */ err) {
        error = err?.message || 'No se pudo guardar la respuesta.';
        // Un error de transporte NO es "no salió": la petición pudo haber
        // llegado. Se dice que no se sabe, y el control se queda donde está.
        avisoDevolucion = estadoDeDevolucion({ pedida: devolviendo, ok: false, datos: null });
      } finally {
        enviando = false;
      }
      return;
    }

    mensajes.push({ rol: 'user', contenido: texto, creado_en: new Date().toISOString() });
    hiloRef?.forzarAlFinal(mensajes.length);
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
  <ConversationHeader
    {conversacion}
    {escalada}
    {asignadaA}
    {contextoAbierto}
    onAlternarContexto={() => (contextoAbierto = !contextoAbierto)}
  />

  <HandoffControls
    {conversacion}
    {caso}
    operadores={data.operadores ?? []}
    {iaEnPausa} {escalada} {atendida} {esMia} {asignadaA} {esAdmin} {gobernada}
    {marcandoAtendida} {errorAtender} onAtender={marcarAtendida}
    {resolviendo} {errorResolver} onResolver={resolver}
    bind:reasignando bind:destinoReasignar bind:motivoReasignar
    {guardandoReasignar} {errorReasignar} onReasignar={reasignar}
  />

  <!-- Tomar un caso escalado empieza siempre igual: leer el hilo entero para
       reconstruir que queria el cliente, que alcanzo a hacer el asistente,
       que se le prometio y que falta. Los tres primeros textos los ESCRIBE el
       modelo al evaluar la escalada y hasta ahora solo iban a la descripcion
       del ticket del CRM -- quien atendia desde acá no los veia nunca.

       Solo se dibuja lo que existe de verdad. Ojo con la razon, que hasta el
       08/09/2026 estaba mal escrita aca: no es que "antes del 06/09 estos
       campos estan vacios". Medido contra produccion, estaban vacios en las
       52 conversaciones escaladas, sin excepcion -- el evaluador los tenia
       como opcionales y no los completaba nunca. Se corrigio del lado que
       los produce (nucleo/seguimiento/escalamiento.py); las 52 viejas se
       quedan vacias igual, y por eso el estado vacio tiene que seguir
       diciendo algo util en vez de un renglon en blanco. -->
  {#if hayResumenDelCaso}
    <EscalationSummary {resumenEscalada} {hizoLaIA} />
  {/if}

  <MessageThread
    bind:this={hiloRef}
    {hilo}
    cantidadMensajes={mensajes.length}
    conversacionId={conversacion.id}
    {casos}
    escribiendo={enviando && !escalada}
    {reintentando}
    onReintentar={reintentar}
  />

  {#if conversacion.estado === 'abierta'}
    <MessageComposer
      {conversacion} {error} {escalada} {enviando} {avisoDevolucion}
      {bloqueadoPorIA} {bloqueadoPorVentana}
      {interviniendo} {errorIntervenir}
      {adjunto} {grabando} {grabPausada} {segundos} {limites}
      {ventanaAbierta} {ventanaRestante} {ventanaPorCerrarse}
      {plantillas} {cargandoPlantillas} {errorPlantillas}
      {enviandoPlantilla} {plantillaCompleta}
      {vistaPreviaPlantilla} {hayPlantillaDeServicio}
      bind:entrada bind:modo bind:campoTexto
      bind:adjuntarAbierto bind:emojisAbiertos bind:arrastrando
      bind:eligiendoPlantilla bind:plantillaElegida bind:valoresPlantilla
      {EMOJIS} {reloj} {comoDuracion}
      onEnviar={alEnviar} onGuardarNota={guardarNota}
      onSoltar={alSoltar} onPegar={alPegar} onElegirArchivo={alElegirArchivo}
      onQuitarAdjunto={quitarAdjunto} onEnviarAdjunto={enviarAdjunto}
      onGrabar={grabar} onPausar={pausarGrabacion} onParar={pararGrabacion}
      onCancelarGrabacion={cancelarGrabacion}
      onPonerEmoji={ponerEmoji} onAbrirPlantillas={abrirPlantillas}
      onElegirPlantilla={elegirPlantilla} onEnviarPlantilla={enviarPlantilla}
      onIntervenir={intervenir}
    />
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

<aside
  class="info"
  class:abierto={contextoAbierto}
  class:vacia={!hayContexto && !contextoAbierto}
  aria-label="Contexto de la conversación"
>
  <button
    type="button"
    class="v2-btn v2-btn-sm info-cerrar"
    onclick={() => (contextoAbierto = false)}
  >
    <X size={14} /> Cerrar
  </button>

  <!-- Quién es el cliente va PRIMERO: antes de mirar el caso o cómo llegó la
       conversación, quien la abre necesita saber con quién está hablando. -->
  <CustomerPanel {conversacion} />

  <CasePanel
    {caso} {conversacion} {owners} {ownerActual}
    asignadaDexter={asignadaA}
    bind:asignadoA bind:listaAbierta bind:formularioAsignar
  />

  <!-- Después del caso y antes del proceso de la IA: primero qué es esta
       conversación, después cómo llegó acá, y recién entonces qué hizo el
       asistente dentro de ella. -->
  <ActivityPanel eventos={relevo} />

  <RetentionToggle
    {conservada} {guardandoConservar} {errorConservar}
    bind:motivoConservar bind:pidiendoMotivo
    onGuardar={guardarConservar}
  />

  <TracePanel
    {herramientas} {diagnostico} {contrasteUtil} {pasoMarcado}
    motivoBloqueo={MOTIVO_BLOQUEO}
    onIrAlPaso={irAlPaso}
  />

  <DocumentationPanel
    {sugerencias} {buscandoDocs} {errorDocs} {mejorSimilitud} {copiado}
    bind:consultaDocs bind:expandido
    onAbrir={alAbrirDocs} onBuscar={alBuscarDocs} onCopiar={copiarFragmento}
  />
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

  /* ── columna de la derecha: el contexto ─────────────────────────────── */
  /* Sin nada accionable la columna se encoge a una tira: el boton para
     abrirla sigue estando, pero el ancho se lo lleva el chat. */
  .info.vacia {
    width: 0;
    padding: 0;
    overflow: hidden;
    border-left: 0;
  }
  .info {
    /* Ningun contenido de esta columna puede desbordarla. Es la red por si
       algo nuevo se agrega sin acordarse de truncarlo. */
    overflow-x: hidden;
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
     cerrarla, ni fondo que interceptar. El del encabezado que la abre vive
     con el encabezado. */
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
  @keyframes latir {
    50% {
      opacity: 0.25;
    }
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

  /* Debajo de 1240px las tres columnas ahogan el hilo. El contexto deja de
     estar fijo al lado y pasa a abrirse con el botón del encabezado -- no
     desaparece: el ticket y la documentación siguen estando a un clic. */
  @media (max-width: 1240px) {
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
</style>
