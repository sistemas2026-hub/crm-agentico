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
  // El sistema visual de la Bandeja. Todo cuelga de `.bandeja`, que es la
  // clase de la mesa de abajo: cubre las tres columnas y la conversación
  // abierta, y no puede alcanzar ninguna otra ruta del CRM.
  import '$lib/conversaciones/estilos/bandeja.css';
  import { pendiente, resuelta, enAtencion } from '$lib/conversaciones/estado.js';
  import { ordenar, horasEsperando } from '$lib/conversaciones/cola/ordenamiento.js';
  import { saludDelCanal } from '$lib/conversaciones/canal.js';
  import { barra, alternar } from '$lib/conversaciones/barra-lateral.svelte.js';
  import { PanelLeftClose, PanelLeftOpen } from '@lucide/svelte';
  import QueueTabs from '$lib/conversaciones/cola/QueueTabs.svelte';
  import QueueSearch from '$lib/conversaciones/cola/QueueSearch.svelte';
  import QueueFilters from '$lib/conversaciones/cola/QueueFilters.svelte';
  import ConversationList from '$lib/conversaciones/cola/ConversationList.svelte';

  /** @type {{ data: any, children: import('svelte').Snippet }} */
  let { data, children } = $props();

  /* Los módulos de la barra de consola. Rutas REALES del CRM, las cuatro con
     las que se trabaja un turno de atención. No es la barra lateral entera:
     poner los veinte destinos acá arriba sería mudarla, no reemplazarla. */
  const MODULOS = [
    { href: '/conversaciones', label: 'Conversaciones' },
    { href: '/tickets', label: 'Tickets' },
    { href: '/asistente', label: 'Asistente' },
    { href: '/agentes', label: 'Agentes' }
  ];

  let conversaciones = $derived(data.conversaciones ?? []);
  /* El plazo de toma que definió la empresa, en minutos. Viene con la cola
     --es uno solo para todas-- y 0 significa que no hay objetivo definido:
     entonces no se dibuja ninguna cuenta regresiva. Ver
     TenantConfig.sla_toma_minutos y lib/conversaciones/sla.js. */
  let slaToma = $derived(Number(data.sla_toma_minutos) || 0);

  /* Si el canal de WhatsApp está funcionando, medido sobre los acuses que
     volvieron. El veredicto vive en `canal.js` con sus pruebas: acá sólo se
     dibuja. Ver ahí por qué se miden los acuses y no la tasa de error. */
  let canal = $derived(saludDelCanal(data.canal_whatsapp));
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

  /* El logo de la empresa se cargó pero el archivo no se pudo mostrar. No es
     lo mismo que no tener logo: acá SÍ hay una URL y falló. Se separa para
     que el respaldo de texto cubra los dos casos sin dibujar una imagen rota
     donde está la única salida de la consola. */
  let logoRoto = $state(false);
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

  /* INDICADORES DE LA BARRA DE CONSOLA.
     La referencia pone arriba el estado del sistema: SLA de entrada, espera
     máxima, poller, latencia. Acá se calculan los que salen de datos que ya
     están cargados -- no hay ninguna llamada nueva ni ningún número fabricado.

     `esperaMaxima`  el mayor `horasEsperando()` entre las que de verdad
                     esperan. Es el mismo cálculo con el que la cola ordena,
                     así que la barra y la lista no pueden decir cosas
                     distintas.
     `sondeadoEn`    cuándo se leyó la cola por última vez. El layout se
                     invalida cada 8s, así que este número dice si lo que se
                     está mirando es de hace un momento o de hace un rato --
                     que es lo que un operador necesita saber de una consola. */
  let esperaMaxima = $derived.by(() => {
    const esperando = conversaciones.filter(pendiente);
    if (esperando.length === 0) return null;
    return Math.max(...esperando.map((/** @type {any} */ c) => horasEsperando(c)));
  });

  const enHoras = (/** @type {number|null} */ h) => {
    if (h === null) return '—';
    if (h < 1) return `${Math.max(1, Math.round(h * 60))}m`;
    if (h < 48) return `${Math.round(h)}h`;
    return `${Math.round(h / 24)}d`;
  };

  /* EL REPARTO DEL TRABAJO, para la barra de estado de abajo.
     Quién está llevando cada conversación ahora mismo. `control` lo decide el
     motor (control_efectivo, B3.3b) y acá sólo se cuenta -- esta pantalla no
     vuelve a deducir quién la lleva. "Sin dueño" son las que están en manos
     de una persona pero que todavía no tomó nadie: es el número que dice si
     la cola se está quedando sin atender. */
  let llevaIA = $derived(
    conversaciones.filter((/** @type {any} */ c) => c.control === 'ia' && !resuelta(c)).length
  );
  let llevaHumano = $derived(
    conversaciones.filter((/** @type {any} */ c) => c.control === 'humano' && !resuelta(c)).length
  );
  let sinDueno = $derived(
    conversaciones.filter(
      (/** @type {any} */ c) => c.control === 'humano' && !resuelta(c) && !c.asignada_a_usuario_id
    ).length
  );

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

  /* Hace cuánto se leyó la cola, para la barra de consola y la de estado.
     Va DESPUÉS de `ahora` y no antes: `$derived` se evalúa perezoso, así que
     en ejecución funcionaba igual, pero leer una variable declarada más abajo
     es una zona muerta esperando a que alguien mueva una línea. svelte-check
     lo marcó como error y tenía razón. */
  let sondeoHaceSegundos = $derived(
    data.sondeadoEn
      ? Math.max(0, Math.round((ahora - new Date(data.sondeadoEn).getTime()) / 1000))
      : null
  );


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
  /* Rótulos cortos: el selector se dibuja al ancho de su opción MÁS LARGA, y
     "Más reciente creación" lo estiraba a 216px en una columna de 304 -- o sea
     que una sola palabra de más obligaba a los filtros a ocupar dos renglones.
     Los ids no cambian: `ORDEN_POR_PESTANA` y `ordenamiento.js` siguen
     apuntando a los mismos cuatro. */
  const ORDENES = [
    { id: 'actividad', label: 'Actividad' },
    { id: 'recomendado', label: 'Recomendado' },
    { id: 'espera', label: 'Mayor espera' },
    { id: 'creacion', label: 'Más recientes' }
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

<!-- LA BARRA DE CONSOLA.
     Era un `<PageHeader>` del CRM: título "Conversaciones" a 26px con su
     subtítulo debajo, 76px de alto. Medido contra la referencia, esos primeros
     píxeles son los que hacían que las dos pantallas se leyeran como dos
     productos distintos -- la referencia arranca con una barra fina de consola
     y enseguida las tres columnas; acá arrancaba con una portada de página
     administrativa.

     Lo que va adentro es TODO dato real y ya calculado acá: no hay ningún
     indicador inventado. La referencia muestra además "Telemetry", "Incidents"
     y el estado de Radius; Dexter no tiene ninguna de esas tres medidas, así
     que no se dibujan -- una barra de consola con indicadores falsos es peor
     que una sin ellos.

     El nombre de la organización NO se repite acá: ya está arriba a la
     izquierda, en la barra lateral, y sale de la config del tenant. -->
<header class="consola bandeja">
  <!-- RECOGER LA BARRA LATERAL. Recogida, la Bandeja ocupa la pantalla
       entera y las tres columnas llegan a 360/730/350 -- los números de la
       referencia. Desplegada, la navegación del CRM está donde la gente la
       conoce. Lo decide quien trabaja, y se recuerda entre visitas. -->
  <button
    type="button"
    class="consola-recoger"
    onclick={alternar}
    aria-pressed={barra.recogida}
    title={barra.recogida ? 'Mostrar el menú lateral' : 'Recoger el menú lateral'}
    aria-label={barra.recogida ? 'Mostrar el menú lateral' : 'Recoger el menú lateral'}
  >
    {#if barra.recogida}<PanelLeftOpen size={15} />{:else}<PanelLeftClose size={15} />{/if}
  </button>

  <!-- LA SALIDA. Con la barra lateral recogida, ésta es la única puerta de
       vuelta al resto del CRM: por eso la marca es un enlace y no un rótulo.
       Una consola a pantalla completa sin salida visible es una trampa.

       EL LOGO ES UN SLOT, NO UN DIBUJO FIJO. La empresa que cargó el suyo en
       Ajustes → Organización lo ve acá; la que no, ve la marca Dexter. Es la
       misma regla multi-tenant del resto del proyecto: un dato que varía por
       empresa no se escribe en el código.

       El respaldo cubre DOS casos, no uno: que no haya logo cargado (lo
       corriente) y que el archivo esté cargado pero no se pueda mostrar
       (borrado del almacenamiento, URL vencida). Lo segundo dibujaría el
       ícono de imagen rota justo donde está la única salida de la consola. -->
  <a class="consola-marca" href="/" title="Volver al inicio">
    {#if data.org?.logo_url && !logoRoto}
      <img
        class="consola-logo"
        src={data.org.logo_url}
        alt={data.org.name || 'Inicio'}
        onerror={() => (logoRoto = true)}
      />
    {:else}
      Dexter
    {/if}
  </a>

  <!-- Los módulos operativos. Son rutas que YA existen -- no hay ninguna
       inventada -- y son las cuatro con las que se trabaja un turno: la
       cola, los tickets del CRM, el asistente y su configuración.
       El resto del CRM (facturación, negociaciones, ajustes) sigue a un clic
       por la marca: no se duplica acá la barra lateral entera, que era el
       motivo por el que esta navegación no existía. -->
  <nav class="consola-nav" aria-label="Módulos">
    {#each MODULOS as m (m.href)}
      <a
        href={m.href}
        class="consola-modulo"
        aria-current={page.url.pathname.startsWith(m.href) ? 'page' : undefined}
      >{m.label}</a>
    {/each}
  </nav>

  <!-- El buscador vive acá, como en la referencia, y no dentro de la columna
       de la cola. Sigue escribiendo en el mismo `busqueda` del layout y el
       filtrado se deriva igual en `visibles`: no cambió qué busca ni cómo,
       cambió dónde está. Sólo tiene sentido si hay algo que buscar. -->
  {#if !data.error && conversaciones.length > 0}
    <QueueSearch bind:busqueda />
  {/if}

  <span class="consola-datos">
    {#if pendientes > 0}
      <!-- Solo las que de verdad esperan: ni cerradas ni las que traian
           puesta la marca por el default viejo. Decia 155 y eran 31. -->
      <span class="consola-dato">
        Por atender <b class="v2-num">{pendientes}</b>
      </span>
      <span class="consola-dato" class:consola-critico={criticas > 0}>
        Espera máx. <b class="v2-num">{enHoras(esperaMaxima)}</b>
      </span>
    {:else}
      <span class="consola-dato">Ninguna esperando</span>
    {/if}
    <span class="consola-dato consola-total">
      Total <b class="v2-num">{conversaciones.length}</b>
    </span>

    <!-- El estado del enlace con el motor. No es un "99.99% uptime"
         inventado: es cuándo se leyó esta cola. Si el sondeo se cae, el
         número crece a la vista en vez de quedarse todo igual y mentir. -->
    {#if sondeoHaceSegundos !== null}
      <span class="consola-dato consola-sondeo" class:consola-frio={sondeoHaceSegundos > 60}>
        <span class="consola-punto"></span>
        {#if sondeoHaceSegundos < 60}En vivo{:else}Hace {enHoras(sondeoHaceSegundos / 3600)}{/if}
      </span>
    {/if}

    <!-- El estado del canal. No es un "uptime" del proveedor: es cuántos de
         los mensajes que salieron tienen acuse de vuelta. -->
    <span
      class="consola-dato consola-canal"
      class:consola-canal-mal={canal.alerta}
      class:consola-canal-mudo={canal.estado === 'sin_trafico' || canal.estado === 'no_medido'}
      title={canal.detalle}
    >
      <span class="consola-punto"></span>{canal.etiqueta}
    </span>

    {#if data.yo?.nombre}
      <span class="consola-operador" title="Sesión de {data.yo.nombre}">{data.yo.nombre}</span>
    {/if}
  </span>
</header>

<div class="mesa bandeja">
  <aside class="columna" class:hay-abierta={abierta} aria-label="Conversaciones">
    {#if !data.error && conversaciones.length > 0}
      <!-- Pestanas de estado. Nunca ember en la activa: "donde estoy" no es una
           accion. El contador de "Sin atender" si lo lleva, porque ese numero
           es trabajo sin tomar. -->
      <QueueTabs {pestanas} {filtro} onIr={irA} />

      <QueueFilters
        bind:vista bind:orden bind:ordenElegido
        bind:soloEscaladas bind:motivo bind:motivosDesplegados
        {motivos} {motivosVisibles} {motivoLabel} {ORDENES}
      />
    {/if}

    <ConversationList
      {visibles} {conversaciones} error={data.error} {busqueda}
      {abierta} {ahora} {tramoEspera} {motivoLabel} {slaToma}
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

<!-- LA BARRA DE ESTADO.
     La referencia cierra con una franja de estado del sistema. Acá lleva lo
     mismo que la de arriba pero del lado del proceso, y todo sale de datos ya
     cargados: cuántas lleva cada quién, y de cuándo es lo que se está
     mirando. Nada de SLA, cluster ni latencia inventados -- si alguna de esas
     se mide algún día, éste es el lugar donde va. -->
<footer class="pie-consola bandeja">
  <span class="pie-dato">
    <span class="pie-marca pie-ia"></span>
    Las lleva la IA <b class="v2-num">{llevaIA}</b>
  </span>
  <span class="pie-dato">
    <span class="pie-marca pie-humano"></span>
    En manos de una persona <b class="v2-num">{llevaHumano}</b>
  </span>
  {#if sinDueno > 0}
    <span class="pie-dato pie-alerta">Sin dueño <b class="v2-num">{sinDueno}</b></span>
  {/if}
  <span class="pie-derecha">
    {#if data.error}
      <span class="pie-dato pie-alerta">Sin conexión con el motor</span>
    {:else if sondeoHaceSegundos !== null}
      <span class="pie-dato">Cola leída hace <b class="v2-num">{sondeoHaceSegundos}s</b></span>
    {/if}
  </span>
</footer>

<style>
  /* ── la barra de consola ────────────────────────────────────────────────
     Fina, de borde a borde y con una sola línea de contenido. 40px contra los
     76 del encabezado de página que reemplaza: 36px que se van enteros a las
     tres columnas. */
  .consola {
    flex: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 16px;
    height: 40px;
    background: var(--bandeja-superficie);
    border-bottom: 1px solid var(--bandeja-borde);
  }

  /* El botón de recoger. Icono solo: es un control de cromo, no una acción
     sobre una conversación, y en una barra de 40px un rótulo al lado le
     quitaría lugar a lo que sí se lee. Lleva `aria-label` y `title`. */
  .consola-recoger {
    display: grid;
    place-items: center;
    flex: none;
    width: 26px;
    height: 26px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: var(--bandeja-radio-sm);
    background: none;
    color: var(--bandeja-texto-2);
    cursor: pointer;
  }

  .consola-recoger:hover {
    color: var(--bandeja-texto);
    background: var(--bandeja-superficie-suave);
    border-color: var(--bandeja-borde);
  }

  /* La marca, y la salida. Con la barra lateral oculta es la única puerta de
     vuelta al resto del CRM, así que se ve como lo que es: un enlace. */
  .consola-marca {
    flex: none;
    display: flex;
    align-items: center;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: -0.01em;
    color: var(--bandeja-texto);
    text-decoration: none;
  }
  /* Alto fijo y ancho libre: un logo es de la proporción que la empresa
     haya subido, y recortarlo a una caja cuadrada deforma marcas anchas.
     El tope de ancho evita que un logo apaisado empuje la navegación. */
  .consola-logo {
    height: 22px;
    max-width: 132px;
    width: auto;
    object-fit: contain;
    display: block;
  }

  .consola-marca:hover {
    color: var(--bandeja-humano);
  }

  /* Los módulos. En angosto la tira se desplaza en horizontal en vez de
     envolver: una barra de consola que crece a dos renglones deja de ser una
     barra. Sin barra de desplazamiento a la vista, como las pestañas del
     CRM. */
  .consola-nav {
    display: flex;
    align-items: center;
    gap: 2px;
    /* `1 1 auto` y no `none`: con `none` la tira no podía encogerse y era la
       BARRA la que se desbordaba -- medido a 390px, se salía de la pantalla.
       Encogiendo, el desplazamiento ocurre adentro de la tira, que es donde
       tiene que ocurrir. */
    flex: 1 1 auto;
    min-width: 0;
    padding-left: 10px;
    border-left: 1px solid var(--bandeja-borde);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .consola-nav::-webkit-scrollbar {
    display: none;
  }

  /* El módulo, en mono y versalita: es un rótulo, igual que los de la cola,
     el hilo y la columna de contexto. El activo lleva el azul de "acá
     estás", el mismo que las pestañas de la cola y las del contexto. */
  .consola-modulo {
    padding: 4px 8px;
    border-radius: var(--bandeja-radio-sm);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
    text-decoration: none;
    white-space: nowrap;
  }

  .consola-modulo:hover {
    color: var(--bandeja-texto);
    background: var(--bandeja-superficie-suave);
  }

  .consola-modulo[aria-current='page'] {
    color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
  }

  /* Los indicadores van a la derecha, como en la referencia. Sin `margin-left:
     auto`: ahora el buscador crece en el medio y ya los empuja. */
  .consola-datos {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
  }

  .consola-dato {
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
    white-space: nowrap;
  }

  .consola-dato b {
    font-size: 12px;
    font-weight: 700;
    color: var(--bandeja-texto);
  }

  /* El único número de la barra que pide una reacción. */
  .consola-critico,
  .consola-critico b {
    color: var(--v2-rust);
  }

  .consola-total,
  .consola-total b {
    color: var(--bandeja-texto-3);
  }

  /* El latido del sondeo. Verde mientras la cola es reciente; apagado cuando
     pasó más de un minuto sin releerla, que con un intervalo de 8s significa
     que algo no está andando. */
  .consola-sondeo {
    color: var(--v2-moss);
  }

  .consola-punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
    align-self: center;
  }

  .consola-frio {
    color: var(--bandeja-aviso);
  }

  /* El canal. Verde cuando los acuses vuelven, ámbar cuando no vuelve
     ninguno, apagado cuando no hay con qué afirmar nada -- que NO es lo
     mismo que estar bien. */
  .consola-canal {
    color: var(--v2-moss);
  }

  .consola-canal-mal {
    color: var(--bandeja-aviso);
  }

  .consola-canal-mudo {
    color: var(--bandeja-texto-3);
  }

  /* Quién está operando. Sale del JWT ya verificado, igual que `esMia`. */
  .consola-operador {
    padding-left: 12px;
    border-left: 1px solid var(--bandeja-borde);
    font-size: 12px;
    font-weight: 600;
    color: var(--bandeja-texto);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 170px;
  }

  /* Angosto: la marca y el módulo alcanzan. Los contadores de la cola siguen
     estando en sus pestañas, que es donde se usan. */
  @media (max-width: 760px) {
    .consola-datos {
      display: none;
    }
    /* El buscador tampoco: en un teléfono la barra tiene que ser una línea
       con la marca y los módulos, y nada más. Buscar se hace desde la cola. */
    .consola :global(.buscar) {
      display: none;
    }
  }

  /* ── la barra de estado ─────────────────────────────────────────────────
     Mismo lenguaje que la de arriba --mono, versalita, filete-- y la mitad de
     alto: es cromo de fondo, no algo que se lea todo el tiempo. */
  .pie-consola {
    flex: none;
    display: flex;
    align-items: center;
    gap: 16px;
    height: 26px;
    padding: 0 16px;
    background: var(--bandeja-superficie);
    border-top: 1px solid var(--bandeja-borde);
  }

  .pie-dato {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--bandeja-texto-3);
    white-space: nowrap;
  }

  .pie-dato b {
    font-size: 10.5px;
    font-weight: 700;
    color: var(--bandeja-texto-2);
  }

  /* Los dos puntos de color son los mismos dos de toda la Bandeja: violeta la
     IA, azul la persona. Nunca van solos -- la palabra está al lado. */
  .pie-marca {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex: none;
  }

  .pie-ia {
    background: var(--bandeja-ia);
  }

  .pie-humano {
    background: var(--bandeja-humano);
  }

  .pie-alerta,
  .pie-alerta b {
    color: var(--bandeja-aviso);
  }

  .pie-derecha {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 16px;
    min-width: 0;
  }

  @media (max-width: 760px) {
    .pie-consola {
      display: none;
    }
  }

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
    /* 360px: el número EXACTO de la referencia, que ahora sí se puede usar
       porque la Bandeja ocupa la pantalla entera. Mientras convivía con la
       barra lateral del CRM había que trabajar en proporción (304 sobre los
       1218 que quedaban); sin ella, 360/730/350 sobre 1440 cierra igual que
       en el diseño. */
    width: 360px;
    flex: none;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--v2-line);
  }

  /* ── filas ──────────────────────────────────────────────────────────── */
  /* `.critico` se fue con el `<PageHeader>`: su único consumidor era el
     subtítulo de esa portada. El mismo número lo marca ahora
     `.consola-critico`, arriba. */
  /* `.marca` se fue el 22/09/2026, por el mismo motivo que `.critico` de
     arriba: no le quedaba ningún consumidor en el marcado. Marcaba «trabajo
     sin tomar» en ámbar, y ese sentido lo lleva hoy el chip de plazo de la
     fila de la cola (`.plazo` en ConversationRow). svelte-check lo venía
     reportando como selector sin usar. */

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
