<script>
  /**
   * Bandeja de conversaciones — la mesa de trabajo.
   *
   * TRES COLUMNAS, NO DOS PANTALLAS
   * Antes esto eran dos rutas separadas: una lista, y al hacer clic, una
   * pantalla aparte. Atender una bandeja no funciona asi: se entra, se
   * contesta, se pasa a la siguiente. Con dos pantallas cada salto cuesta un
   * "volver" y se pierde de vista que mas hay esperando.
   *
   * Por eso la lista vive en el layout y acompaña siempre:
   *   izquierda   quienes escribieron (esta columna)
   *   centro      la conversacion abierta            -> [id]/+page.svelte
   *   derecha     el ticket, el proceso, la documentacion   -> idem
   *
   * Las URLs no cambian: /conversaciones/<id> sigue siendo un enlace que se
   * puede compartir y abrir directo.
   *
   * COMO SE LEE  (la regla de v2.css: ember marca lo que te necesita o
   * aquello sobre lo que podes actuar, nunca cromo)
   *   Sin atender   escalada y NADIE del equipo escribio todavia. Es el unico
   *                 estado que pide algo, y el unico con ember.
   *   En curso      escalada y ya contestada por una persona. Sigue abierta
   *                 pero no espera a nadie -> clay, quieto.
   *   (sin marca)   el bot la esta resolviendo solo. Es el caso normal: una
   *                 pildora por fila para decir "todo bien" es ruido.
   *
   * Las pestanas, el buscador y el filtro trabajan sobre lo ya cargado: la
   * bandeja entra en una pagina y filtrar del lado del cliente es instantaneo,
   * sin un viaje de red por cada clic.
   */
  import { page } from '$app/state';
  import { invalidate } from '$app/navigation';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  // El sistema visual de la Bandeja. Todo cuelga de `.bandeja`, que es la
  // clase de la mesa de abajo: cubre las tres columnas y la conversación
  // abierta, y no puede alcanzar ninguna otra ruta del CRM.
  import '$lib/conversaciones/estilos/bandeja.css';
  import { pendiente, resuelta, enAtencion } from '$lib/conversaciones/estado.js';
  import { ordenar, horasEsperando } from '$lib/conversaciones/cola/ordenamiento.js';
  import QueueTabs from '$lib/conversaciones/cola/QueueTabs.svelte';
  import QueueSearch from '$lib/conversaciones/cola/QueueSearch.svelte';
  import QueueFilters from '$lib/conversaciones/cola/QueueFilters.svelte';
  import ConversationList from '$lib/conversaciones/cola/ConversationList.svelte';

  /** @type {{ data: any, children: import('svelte').Snippet }} */
  let { data, children } = $props();

  let conversaciones = $derived(data.conversaciones ?? []);
  let abierta = $derived(page.params.id ?? null);

  // Sondeo: mientras esta pestaña esta abierta, revisa cada pocos segundos
  // si hay algo nuevo (un chat que nadie tenia, un mensaje que cambio el
  // "ultimo_mensaje" de una fila) -- para cuando WhatsApp real este
  // integrado y un cliente escriba sin que nadie tenga que recargar. Solo
  // si la pestaña esta visible: una de fondo no gasta pedidos al motor.
  // Todavia no hay WebSocket, esto es sondeo simple.
  //
  // El intervalo NO alcanza solo: si la pestaña estuvo de fondo (otra
  // pestaña, otra app), el intervalo de 8s puede haber estado corriendo
  // igual pero cada disparo se descartaba por el chequeo de arriba -- al
  // volver, el proximo disparo real puede tardar hasta 8s mas (y los
  // navegadores frenan los timers de pestañas de fondo, asi que puede ser
  // bastante mas). El listener de 'visibilitychange' sondea AL INSTANTE
  // apenas la pestaña vuelve a estar visible, en vez de esperar al proximo
  // tick -- confirmado en vivo (agosto 2026): sin esto, dos pestañas
  // (conversaciones + simulador) no mostraban el mensaje nuevo en minutos.
  $effect(() => {
    const intervalo = setInterval(() => {
      if (document.visibilityState === 'visible') invalidate('app:conversaciones');
    }, 8000);
    // Dos señales, no una: 'visibilitychange' no siempre alcanza (algunos
    // navegadores/arreglos de ventana no la disparan de forma confiable
    // segun como se cambia de pestaña o ventana). 'focus' de la ventana es
    // una segunda red -- entre las dos, es dificil que ninguna dispare al
    // volver.
    const alVolver = () => invalidate('app:conversaciones');
    document.addEventListener('visibilitychange', alVolver);
    window.addEventListener('focus', alVolver);
    return () => {
      clearInterval(intervalo);
      document.removeEventListener('visibilitychange', alVolver);
      window.removeEventListener('focus', alVolver);
    };
  });


  // pendiente / resuelta / enAtencion viven en $lib/conversaciones/estado.js:
  // el indice necesita el mismo criterio y una copia ya se desincronizo
  // una vez (la cabecera decia 41 y el panel vacio 44, el 07/09/2026).


  // 'por-atender' de entrada: es a lo que se viene. Antes abria en "Todas",
  // que es la vista en la que un caso urgente se ve exactamente igual que uno
  // de hace un mes ya resuelto.
  let filtro = $state('por-atender');
  let busqueda = $state('');
  /* Que canales se ven. Por defecto SOLO los reales: el simulador, el
     asistente interno y las baterias escriben en las mismas tablas, y mezclar
     una prueba de hace dos horas con un cliente esperando hace que la cola
     deje de servir para trabajar. El motor marca cada fila con
     'canal_operativo' (canal.REALES); aca no hay una lista de canales. */
  let vista = $state('operativo');
  /** '' = todos. Filtra por el motivo por el que el asistente escalo. */
  let motivo = $state('');
  /** Escalada no es un estado paralelo a los otros: una conversacion escalada
      esta ADEMAS por atender, o en atencion, o resuelta. Por eso es un filtro
      que se cruza con la pestaña, y no una quinta pestaña. */
  let soloEscaladas = $state(false);
  /** Ver ORDENES y ORDEN_POR_PESTANA. Arranca con el de 'Por atender', que es
      la pestaña con la que abre la bandeja. */
  let orden = $state('recomendado');

  let pendientes = $derived(conversaciones.filter(pendiente).length);
  // El numero que de verdad duele. Va en la cabecera al lado del total
  // porque "44 por atender" no dice nada si 20 llevan mas de una semana.
  let criticas = $derived(
    conversaciones.filter((/** @type {any} */ c) => tramoEspera(c) === 'critico').length
  );

  // --- por donde empezar ----------------------------------------------------
  // El orden vive en $lib/conversaciones/cola/ordenamiento.js -- las MISMAS
  // funciones que se importan acá, no una copia. De ahí depende D18 (que una
  // escalada nueva sin dueño no quede enterrada detrás de las viejas) y es lo
  // único de esta pantalla que puede romperse sin que se note mirándola: una
  // lista mal ordenada se ve perfecta. El harness no compila .svelte, así que
  // sin extraerlas no había forma de ponerles una guarda.

  // Cada cuanto se recalcula "activa". El sondeo de la lista ya corre cada 8s
  // e invalida el load, asi que la posicion se reordena sola; esto es solo
  // para que el punto se APAGUE sin depender de que llegue algo nuevo.
  let ahora = $state(Date.now());
  $effect(() => {
    const i = setInterval(() => (ahora = Date.now()), 20000);
    return () => clearInterval(i);
  });


  // Tres tramos, no un gradiente: el ojo no distingue 61h de 58h, y si
  // distingue "hoy" de "hace mas de una semana". Los cortes son a un dia y a
  // una semana porque es como habla la gente de esto, no por un umbral
  // calculado.
  const tramoEspera = (/** @type {any} */ c) => {
    const h = horasEsperando(c);
    if (h >= 168) return 'critico';
    if (h >= 24) return 'viejo';
    return 'fresco';
  };

  // Se dibuja en QueueFilters pero se declara acá, al lado de
  // ORDEN_POR_PESTANA: ese mapa apunta a estos mismos ids, y separarlos
  // dejaría la correspondencia repartida en dos archivos sin nada que la
  // mantenga junta.
  const ORDENES = [
    { id: 'actividad', label: 'Actividad reciente' },
    { id: 'recomendado', label: 'Recomendado' },
    { id: 'espera', label: 'Mayor espera' },
    { id: 'creacion', label: 'Más reciente creación' }
  ];

  // Cada pestaña arranca con el orden que le corresponde POR LO QUE ES.
  //
  //   Por atender   decide a quien atender primero -> prioridad
  //   En atencion   es trabajo en curso            -> lo ultimo que se movio
  //   Resueltas     es un archivo                  -> lo ultimo cerrado
  //   Todas         es "que esta pasando ahora"    -> actividad
  //
  // Todas ordenaba por prioridad, y eso la hacia inutil para vigilar: un
  // mensaje que acababa de entrar quedaba en la posicion 40 de 169, detras de
  // las 39 que esperan a alguien. Medido el 07/09/2026 con un mensaje real.
  const ORDEN_POR_PESTANA = {
    'por-atender': 'recomendado',
    'en-atencion': 'actividad',
    resueltas: 'creacion',
    todas: 'actividad'
  };

  /** Cuando se cambia de pestaña, el orden vuelve al que le toca -- salvo que
      la persona haya elegido uno a mano, que manda hasta que se cambie de
      pestaña otra vez. */
  let ordenElegido = $state(false);
  function irA(/** @type {string} */ id) {
    filtro = id;
    ordenElegido = false;
    orden = ORDEN_POR_PESTANA[id] ?? 'actividad';
  }

  // Los motivos que de verdad hay en la bandeja, no una lista fija: los
  // declara cada empresa en su config, y una lista hardcodeada aca dejaria
  // de coincidir en cuanto alguien agregue uno.
  // Se cuentan sobre la PESTAÑA actual, no sobre todo: estando en "Resueltas",
  // unos chips que cuentan las que estan por atender ofrecen filtros que no
  // devuelven nada.
  let motivos = $derived.by(() => {
    const enPestana = conversaciones.filter((/** @type {any} */ c) =>
      filtro === 'por-atender' ? pendiente(c)
      : filtro === 'en-atencion' ? enAtencion(c)
      : filtro === 'resueltas' ? resuelta(c)
      : true
    );
    const cuenta = new Map();
    for (const c of enPestana) {
      if (!c.motivo_escalamiento) continue;
      cuenta.set(c.motivo_escalamiento, (cuenta.get(c.motivo_escalamiento) ?? 0) + 1);
    }
    return [...cuenta.entries()].sort((a, b) => b[1] - a[1]);
  });

  // Con muchos motivos la fila de chips se come la lista, que es lo que
  // importa. Se muestran los mas frecuentes y el resto se despliega -- salvo
  // que el elegido este escondido, en cuyo caso se abre sola: un filtro
  // activo que no se ve es la forma mas rapida de creer que la bandeja esta
  // vacia.
  const MOTIVOS_A_LA_VISTA = 4;
  let motivosDesplegados = $state(false);
  let motivosVisibles = $derived(
    motivosDesplegados || motivos.length <= MOTIVOS_A_LA_VISTA + 1
      ? motivos
      : motivos.slice(0, MOTIVOS_A_LA_VISTA)
  );
  $effect(() => {
    if (motivo && !motivosVisibles.some(([m]) => m === motivo)) motivosDesplegados = true;
  });

  const motivoLabel = (/** @type {string} */ m) => (m ? m.replaceAll('_', ' ') : '');

  // Cuatro estados que se excluyen entre si, en el orden en que transcurre un
  // caso. La pestaña "Asistente" (las que el bot lleva solo) desaparecio: no
  // era un estado de atencion sino su ausencia, y ocupaba el lugar de
  // "Resueltas", que si es trabajo terminado y alguien quiere revisar.
  let pestanas = $derived([
    { id: 'por-atender', label: 'Por atender', n: pendientes, urge: true },
    { id: 'en-atencion', label: 'En atención', n: conversaciones.filter(enAtencion).length },
    { id: 'resueltas', label: 'Resueltas', n: conversaciones.filter(resuelta).length },
    { id: 'todas', label: 'Todas', n: conversaciones.length }
  ]);

  let visibles = $derived.by(() => {
    let lista = conversaciones;
    if (vista !== 'todos') {
      const operativo = vista === 'operativo';
      // 'canal_operativo' puede faltar si el motor todavia no la manda: en ese
      // caso no se esconde nada (mejor de mas que ocultar un cliente real).
      lista = lista.filter((/** @type {any} */ c) =>
        c.canal_operativo === undefined ? true : c.canal_operativo === operativo);
    }
    if (filtro === 'por-atender') lista = lista.filter(pendiente);
    else if (filtro === 'en-atencion') lista = lista.filter(enAtencion);
    else if (filtro === 'resueltas') lista = lista.filter(resuelta);

    if (soloEscaladas) lista = lista.filter((/** @type {any} */ c) => c.escalada_a_humano);
    if (motivo) lista = lista.filter((/** @type {any} */ c) => c.motivo_escalamiento === motivo);

    const q = busqueda.trim().toLowerCase();
    if (q) {
      lista = lista.filter((/** @type {any} */ c) =>
        [c.usuario_externo, c.nombre_cliente, c.ultimo_mensaje, c.resumen,
         c.etiqueta, c.caso_manual, c.motivo_escalamiento]
          .filter(Boolean)
          .some((campo) => String(campo).toLowerCase().includes(q))
      );
    }
    return ordenar(lista, orden);
  });
</script>

<PageHeader title="Conversaciones">
  {#snippet sub()}
    {#if pendientes > 0}
      <!-- Solo las que de verdad esperan: ni cerradas ni las que traian
           puesta la marca por el default viejo. Decia 155 y eran 31. -->
      <span class="v2-num">{pendientes}</span>
      por atender{#if criticas > 0},
        <span class="v2-num critico">{criticas}</span> hace más de una semana{/if} ·
      <span class="v2-num">{conversaciones.length}</span> en total
    {:else}
      <span class="v2-num">{conversaciones.length}</span>
      {conversaciones.length === 1 ? 'conversación' : 'conversaciones'}, ninguna esperando
    {/if}
  {/snippet}
</PageHeader>

<div class="mesa bandeja">
  <aside class="columna" class:hay-abierta={abierta} aria-label="Conversaciones">
    {#if !data.error && conversaciones.length > 0}
      <!-- Pestanas de estado. Nunca ember en la activa: "donde estoy" no es una
           accion. El contador de "Sin atender" si lo lleva, porque ese numero
           es trabajo sin tomar. -->
      <QueueTabs {pestanas} {filtro} onIr={irA} />

      <QueueSearch bind:busqueda />

      <QueueFilters
        bind:vista bind:orden bind:ordenElegido
        bind:soloEscaladas bind:motivo bind:motivosDesplegados
        {motivos} {motivosVisibles} {motivoLabel} {ORDENES}
      />
    {/if}

    <ConversationList
      {visibles} {conversaciones} error={data.error} {busqueda}
      {abierta} {ahora} {tramoEspera} {motivoLabel}
    />
  </aside>

  <!-- 'abierta' (el id de la URL) como key: [id]/+page.svelte inicializa su
       estado local con $state(untrack(...)) a proposito (para que enviar()
       no se pise con una relectura reactiva mientras se escribe), y ese
       mismo untrack hace que SvelteKit, al reusar este componente entre una
       conversacion y otra, se quede mostrando la anterior -- confirmado con
       grabaciones reales (Jam, agosto 2026): sin esto el panel no actualiza
       NUNCA, solo cambia la URL. Se probo resincronizar con un $effect en
       vez de esto (evitaba el parpadeo de remontar), pero en las mismas
       pruebas grabadas el effect no alcanzaba a aplicar el cambio a tiempo.
       La key fuerza a Svelte a destruir y recrear el componente -- unico
       mecanismo que garantiza la reinicializacion, al costo de un
       parpadeo breve. Solo envuelve el hijo, no <aside> de arriba: la
       lista de conversaciones NO se remonta al cambiar de chat. -->
  {#key abierta}
    {@render children()}
  {/key}
</div>

<style>
  /* La mesa ocupa lo que queda bajo el encabezado y no scrollea: cada columna
     maneja su propio desborde, para que leer un hilo largo no arrastre la
     lista fuera de la vista. */
  .mesa {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: stretch;
    border-top: 1px solid var(--v2-line);
  }
  .columna {
    width: 330px;
    flex: none;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--v2-line);
  }

  /* ── filas ──────────────────────────────────────────────────────────── */
  /* El unico numero de la cabecera que pide una reaccion. */
  .critico {
    color: var(--v2-rust);
    font-weight: 750;
  }
  /* No es un Pill: Pill.svelte excluye ember a propósito porque ember no es
     "un estado en el que un registro está". Acá no describe un estado, marca
     trabajo sin tomar -- el mismo sentido que la tira .v2-next. */
  .marca {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11.2px;
    font-weight: 650;
    color: var(--v2-ember);
    white-space: nowrap;
  }
  .marca::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--v2-ember);
    flex: none;
  }

  /* En pantallas angostas no caben tres columnas al lado. La lista pasa a ser
     la pantalla, y abrir una conversación la reemplaza -- el comportamiento
     de dos pantallas de antes, que es el correcto en un teléfono. */
  @media (max-width: 1000px) {
    .columna {
      width: 100%;
      border-right: 0;
    }
    .columna.hay-abierta {
      display: none;
    }
  }
</style>
