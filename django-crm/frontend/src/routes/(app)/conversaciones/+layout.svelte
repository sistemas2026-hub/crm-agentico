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
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { MessagesSquare, TriangleAlert, Search, X, Phone, User } from '@lucide/svelte';
  import { pendiente, resuelta, enAtencion } from '$lib/conversaciones/estado.js';

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

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (/** @type {string} */ c) => CANAL_LABEL[c] ?? c;

  // Un color por etiqueta, no toda la taxonomia hardcodeada -- si el tenant
  // agrega una categoria nueva en conversaciones.etiquetas, cae en 'ink' en
  // vez de romper.
  // ETIQUETA_TONE / etiquetaTone se fueron con la pildora de etiqueta: la
  // fila mostraba hasta tres pildoras y el pedido era justo lo contrario --
  // cliente, tiempo esperando, motivo, y la excepcion. El tema de la
  // conversacion sigue estando en 'caso_manual', que es mas especifico.
  const etiquetaLabel = (/** @type {string} */ e) => (e ? e.replaceAll('_', ' ') : '');

  // pendiente / resuelta / enAtencion viven en $lib/conversaciones/estado.js:
  // el indice necesita el mismo criterio y una copia ya se desincronizo
  // una vez (la cabecera decia 41 y el panel vacio 44, el 07/09/2026).

  const AUTOR = { user: 'Cliente', assistant: 'Asistente', humano: 'Vos', tool: 'Herramienta' };

  // Quien escribe por WhatsApp se identifica con un telefono, y quien prueba
  // desde el CRM con un uuid. Ninguno de los dos tiene iniciales: initials()
  // devuelve '3' o 'B', un circulo con una letra que no significa nada. Un
  // icono dice mas y no finge ser un nombre.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);

  /** '3007778899' -> '300 777 8899'. Diez digitos seguidos no se leen. */
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    const d = v.replace(/\D/g, '');
    if (esTelefono(v) && d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    return v;
  }

  // 'por-atender' de entrada: es a lo que se viene. Antes abria en "Todas",
  // que es la vista en la que un caso urgente se ve exactamente igual que uno
  // de hace un mes ya resuelto.
  let filtro = $state('por-atender');
  let busqueda = $state('');
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
  // Con decenas esperando, "la mas nueva primero" ordena al reves de lo que
  // hace falta: quien escalo hace tres dias y no volvio a escribir se hunde
  // al fondo, y es justo el que lleva tres dias esperando.
  //
  // El orden es: primero las que esperan a alguien, y entre ellas la de
  // espera mas larga arriba. El resto queda como estaba, por ultima
  // actividad. No hay un puntaje ponderado a proposito -- un numero que
  // mezcla antiguedad, insistencia y motivo no se puede explicar, y quien
  // atiende tiene que poder entender por que una fila esta donde esta.
  const espera = (/** @type {any} */ c) =>
    new Date(c.escalada_en ?? c.actualizado_en).getTime();

  const HORA = 3600 * 1000;

  // Cada cuanto se recalcula "activa". El sondeo de la lista ya corre cada 8s
  // e invalida el load, asi que la posicion se reordena sola; esto es solo
  // para que el punto se APAGUE sin depender de que llegue algo nuevo.
  let ahora = $state(Date.now());
  $effect(() => {
    const i = setInterval(() => (ahora = Date.now()), 20000);
    return () => clearInterval(i);
  });

  /** Se movio en los ultimos minutos. Cinco y no uno: con uno el punto
      parpadea y se pierde; con quince deja de significar "ahora". */
  const MINUTOS_ACTIVA = 5;
  const estaActiva = (/** @type {any} */ c) =>
    !!c.ultimo_mensaje_en &&
    ahora - new Date(c.ultimo_mensaje_en).getTime() < MINUTOS_ACTIVA * 60 * 1000;

  /** Horas que lleva esperando. 0 si no espera a nadie. */
  const horasEsperando = (/** @type {any} */ c) =>
    pendiente(c) ? Math.max(0, (Date.now() - espera(c)) / HORA) : 0;

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

  // Los motivos donde hay una persona molesta del otro lado pesan mas que un
  // tramite. No es un puntaje afinado -- es un desempate, y por eso son dos
  // valores y no cinco: cualquier cosa mas fina seria inventada.
  const MOTIVO_URGENTE = new Set(['frustracion_detectada', 'tres_fallos_seguidos']);

  /** Cuanto pesa una conversacion en el orden "Recomendado". Mas alto, mas
      arriba. Se calcula con lo que ya existe: tiempo esperando, si el cliente
      volvio a escribir, y el motivo. */
  function peso(/** @type {any} */ c) {
    if (!pendiente(c)) return -1;
    // La espera es la base y manda: es lo que de verdad mide el maltrato al
    // cliente. Se cuenta en dias para que las otras dos señales puedan
    // moverla sin taparla del todo.
    let p = horasEsperando(c) / 24;
    // Volver a escribir mientras espera es alguien golpeando la puerta, y
    // tiene que ganarle a la antiguedad: quien escribio hace dos minutos esta
    // ahi AHORA, y quien lleva 26 dias ya se acostumbro a esperar.
    //
    // 30 dias equivalentes, no 3: con el peso anterior una insistencia de hoy
    // perdia contra cualquier caso de mas de tres dias, y hay 34 con mas de
    // una semana. En la practica no subia a nadie.
    //
    // Ojo con lo que esto NO arregla: hay CERO mensajes posteriores a una
    // escalada en toda la base, y no porque nadie insista -- las
    // conversaciones se cierran a las 24 h de inactividad, asi que quien
    // vuelve a los dos dias abre una conversacion NUEVA y su insistencia no
    // se cuenta como tal. Esta señal solo ve al que insiste dentro del dia.
    if (c.mensajes_tras_escalar > 0) p += 30 + Math.min(c.mensajes_tras_escalar, 10);
    if (MOTIVO_URGENTE.has(c.motivo_escalamiento)) p += 2;
    return p;
  }

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

  /** La hora del ULTIMO MENSAJE, de quien sea -- cliente, asistente o
      colaborador. No 'actualizado_en': esa la mueve cualquier cosa que toque
      la fila, incluido cerrarla, y una conversacion cerrada hoy con su ultimo
      mensaje de hace 26 dias quedaba arriba de una con charla de verdad ayer. */
  const actividad = (/** @type {any} */ c) =>
    new Date(c.ultimo_mensaje_en ?? c.actualizado_en).getTime();

  function ordenar(/** @type {any[]} */ lista) {
    const recientes = (/** @type {any} */ a, /** @type {any} */ b) =>
      new Date(b.actualizado_en).getTime() - new Date(a.actualizado_en).getTime();

    // Actividad: SIN bloque de prioridad delante. Es lo que hace que un
    // mensaje que acaba de entrar aparezca primero aunque el bot lo este
    // llevando solo -- que es justo para lo que sirve esta vista.
    if (orden === 'actividad') {
      return [...lista].sort((a, b) => actividad(b) - actividad(a));
    }
    if (orden === 'creacion') return [...lista].sort(recientes);

    return [...lista].sort((a, b) => {
      // En los dos ordenes que priorizan, lo que espera va primero: una
      // conversacion resuelta no compite por el lugar de arriba.
      const pa = pendiente(a) ? 0 : 1;
      const pb = pendiente(b) ? 0 : 1;
      if (pa !== pb) return pa - pb;
      if (pa === 1) return recientes(a, b);
      // 'Mayor espera' es a proposito el orden CRUDO, sin ponderar: existe
      // para poder comprobar el otro. Si "Recomendado" pone algo arriba que
      // no lleva la espera mas larga, se puede ver por que cambiando aca.
      if (orden === 'espera') return espera(a) - espera(b);
      return peso(b) - peso(a);
    });
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
    return ordenar(lista);
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

<div class="mesa">
  <aside class="columna" class:hay-abierta={abierta} aria-label="Conversaciones">
    {#if !data.error && conversaciones.length > 0}
      <!-- Pestanas de estado. Nunca ember en la activa: "donde estoy" no es una
           accion. El contador de "Sin atender" si lo lleva, porque ese numero
           es trabajo sin tomar. -->
      <nav class="tabs" aria-label="Filtrar por estado">
        {#each pestanas as t (t.id)}
          <button
            type="button"
            class="tab"
            aria-current={filtro === t.id ? 'true' : undefined}
            onclick={() => irA(t.id)}
          >
            {t.label}
            <span class="tab-n v2-num" class:urge={t.urge && t.n > 0}>{t.n}</span>
          </button>
        {/each}
      </nav>

      <label class="buscar">
        <Search size={14} />
        <input
          type="text"
          bind:value={busqueda}
          placeholder="Buscar cliente o mensaje…"
          aria-label="Buscar conversaciones"
        />
        {#if busqueda}
          <button
            type="button"
            class="limpiar"
            onclick={() => (busqueda = '')}
            aria-label="Limpiar"
          >
            <X size={13} />
          </button>
        {/if}
      </label>

      <!-- Por que escalo. Veinte casos del mismo tipo se resuelven mas rapido
           seguidos que mezclados con otros veinte de otra cosa: quien atiende
           ya tiene el contexto cargado. El dato estaba guardado desde
           siempre y no habia forma de filtrarlo.

           Se dibuja solo si hay mas de un motivo entre las que esperan: con
           uno solo, el filtro no separa nada y es una fila de ruido. -->
      <div class="controles">
        <label class="orden">
          <span class="orden-rotulo">Ordenar por</span>
          <select
            bind:value={orden}
            onchange={() => (ordenElegido = true)}
            aria-label="Ordenar la lista"
          >
            {#each ORDENES as o (o.id)}
              <option value={o.id}>{o.label}</option>
            {/each}
          </select>
        </label>

        <button
          type="button"
          class="motivo"
          aria-pressed={soloEscaladas}
          onclick={() => (soloEscaladas = !soloEscaladas)}
          title="Escalada no es un estado aparte: se cruza con la pestaña que estés viendo"
        >
          Solo escaladas
        </button>
      </div>

      {#if motivos.length > 1}
        <div class="motivos" role="group" aria-label="Filtrar por motivo de escalada">
          <button
            type="button"
            class="motivo"
            aria-pressed={motivo === ''}
            onclick={() => (motivo = '')}>Todos</button
          >
          {#each motivosVisibles as [m, n] (m)}
            <button
              type="button"
              class="motivo"
              aria-pressed={motivo === m}
              onclick={() => (motivo = motivo === m ? '' : m)}
            >
              {motivoLabel(m)}
              <span class="v2-num">{n}</span>
            </button>
          {/each}
          {#if motivos.length > motivosVisibles.length}
            <button
              type="button"
              class="motivo motivo-mas"
              onclick={() => (motivosDesplegados = true)}
            >
              +{motivos.length - motivosVisibles.length} más
            </button>
          {/if}
        </div>
      {/if}
    {/if}

    <div class="lista">
      {#if data.error}
        <div class="hueco">
          <EmptyState title="No se pudo cargar la bandeja" body={data.error}>
            {#snippet icon()}<TriangleAlert size={21} />{/snippet}
          </EmptyState>
        </div>
      {:else if conversaciones.length === 0}
        <div class="hueco">
          <EmptyState
            title="Todavía no hay conversaciones"
            body="Acá van a aparecer los chats de WhatsApp con tus clientes."
          >
            {#snippet icon()}<MessagesSquare size={21} />{/snippet}
          </EmptyState>
        </div>
      {:else if visibles.length === 0}
        <div class="hueco">
          <EmptyState
            title="Nada acá"
            body={busqueda
              ? `Ninguna coincide con «${busqueda}».`
              : 'No hay conversaciones en este estado.'}
          >
            {#snippet icon()}<Search size={20} />{/snippet}
          </EmptyState>
        </div>
      {:else}
        {#each visibles as c (c.id)}
          <a
            class="fila"
            class:pide={pendiente(c)}
            class:activa={c.id === abierta}
            href="/conversaciones/{c.id}"
            aria-current={c.id === abierta ? 'page' : undefined}
          >
            {#if c.nombre_cliente}
              <Avatar name={c.nombre_cliente} size={30} />
            {:else if esTelefono(c.usuario_externo)}
              <span class="ident" aria-hidden="true"><Phone size={14} /></span>
            {:else if !c.usuario_externo || esUuid(c.usuario_externo)}
              <span class="ident" aria-hidden="true"><User size={14} /></span>
            {:else}
              <Avatar name={c.usuario_externo} size={30} />
            {/if}

            <div class="cuerpo">
              <div class="alta">
                <span class="quien">{c.nombre_cliente || quien(c.usuario_externo)}</span>
                <!-- En las que esperan, el tiempo que se muestra es el de la
                     ESPERA, no el del ultimo movimiento: es el numero que
                     decide a cual entrar primero, y son distintos en cuanto
                     el cliente vuelve a escribir. -->
                {#if pendiente(c) && c.escalada_en}
                  <span
                    class="cuando v2-num espera-{tramoEspera(c)}"
                    title="Esperando desde hace {shortAge(c.escalada_en)}"
                  >
                    {shortAge(c.escalada_en)} esperando
                  </span>
                {:else}
                  <span class="cuando v2-num">{shortAge(c.actualizado_en)}</span>
                {/if}
              </div>

              <!-- De que se trata, en una linea. El ultimo mensaje casi nunca
                   lo dice ("ok", "gracias", "listo"): quien atiende tiene que
                   abrir la conversacion solo para enterarse. El resumen lo
                   redacta el modelo al escalar, sin una llamada extra. Solo
                   existe en las escaladas DESPUES del 06/09/2026; en el
                   resto se cae al ultimo mensaje, como antes. -->
              {#if c.resumen}
                <p class="avance resumen">{c.resumen}</p>
              {:else}
                <!-- El RESUMEN si lo hay, y solo si no, el ultimo mensaje.
                     "Asistente: Entiendo, eso necesita revision..." vuelve a
                     contar la ultima respuesta del bot, que casi nunca dice de
                     que trataba el caso. El resumen lo escribe el modelo al
                     escalar y dice justo eso.

                     Todavia no lo tienen todas: son 2 de 51 escaladas, porque
                     el campo existe desde el 06/09/2026. Por eso el respaldo
                     sigue siendo el ultimo mensaje y no un hueco. -->
                <!-- Que TRABAJO hay delante, no que dijo el bot.
                     Tres fuentes, en orden de cuanto dicen:

                       resumen      lo escribe el modelo al escalar y dice de
                                    que trata el caso. Es el bueno.
                       caso_manual  de que es la conversacion, asignado en
                                    cada turno. Existe tambien donde el bot
                                    resolvio solo.
                       ultimo msj   el respaldo. "Asistente: Entiendo, eso
                                    necesita revision..." vuelve a contar la
                                    ultima respuesta, que casi nunca dice de
                                    que iba el caso -- pero es mejor que un
                                    hueco.

                     Hoy 'resumen' lo tienen 2 de 51 escaladas (el campo es
                     del 06/09/2026), asi que el respaldo se usa mucho
                     todavia. Va a ir desapareciendo solo. -->
                {#if (c.resumen ?? '').trim()}
                  <p class="avance avance-resumen">{c.resumen}</p>
                {:else if c.caso_manual}
                  <p class="avance avance-resumen">{etiquetaLabel(c.caso_manual)}</p>
                {:else}
                  <p class="avance">
                    {#if c.ultimo_rol && c.ultimo_rol !== 'user'}
                      <span class="avance-quien">{AUTOR[c.ultimo_rol] ?? c.ultimo_rol}:</span>
                    {/if}
                    {c.ultimo_mensaje || 'Sin mensajes todavía'}
                  </p>
                {/if}
              {/if}

              <!-- Solo se dibuja si hay algo que decir. "El bot la está
                   llevando" es el caso normal: ponerle una píldora a cada fila
                   agrega una línea y un rectángulo por conversación para no
                   informar nada. -->
              {#if c.escalada_a_humano || c.caso_manual || resuelta(c)}
                <div class="baja">
                  {#if pendiente(c)}
                    <!-- El motivo va en TEXTO y no en pildora: es lo mas
                         parecido a un subtitulo del caso, y una pildora mas
                         en una fila que ya tiene tres compite con la unica
                         que pide una accion. La pildora "Sin atender" se fue:
                         dentro de la pestaña "Por atender" repetia el nombre
                         de la pestaña en cada fila. -->
                    {#if c.motivo_escalamiento}
                      <span class="motivo-fila">{motivoLabel(c.motivo_escalamiento)}</span>
                    {/if}
                  {:else if c.escalada_a_humano && !resuelta(c)}
                    <Pill tone="clay" dot>En curso</Pill>
                  {:else if resuelta(c)}
                    <Pill tone="moss">Resuelta</Pill>
                  {/if}

                  <!-- De qué es la conversación, no si escaló: lo asigna el
                       asistente en cada turno y existe también en las que
                       resolvió solo (ver supabase/202608180923_caso_conversacion.sql).
                       Solo cuando NO hay motivo -- si hay, ese dice mas y los
                       dos juntos son ruido. -->
                  <!-- Solo si 'caso_manual' NO se uso ya como la linea de
                       arriba: decir lo mismo dos veces en la misma fila es
                       justo el ruido que se estaba sacando. -->
                  {#if c.caso_manual && (c.resumen ?? '').trim() && !(pendiente(c) && c.motivo_escalamiento)}
                    <Pill tone="ink">{etiquetaLabel(c.caso_manual)}</Pill>
                  {/if}
                </div>
              {/if}

              <!-- Actividad viva. Un punto y una palabra, no una pildora mas:
                   se enciende con cualquier mensaje de los ultimos minutos
                   --cliente, asistente o colaborador-- y se apaga solo. La
                   conversacion CONSERVA su posicion segun la hora de esa
                   actividad; el punto solo dice "esto se movio recien". -->
              {#if estaActiva(c)}
                <span class="activa">Activa</span>
              {/if}

              <!-- La excepcion va sola, en su propio renglon y al final: el
                   cliente escribio de nuevo despues de que le dijeramos que
                   un companero lo iba a atender. Es lo mas parecido a alguien
                   golpeando la puerta. Metida entre las pildoras se perdia. -->
              {#if pendiente(c) && c.mensajes_tras_escalar > 0}
                <span class="insiste">
                  Volvió a escribir{c.mensajes_tras_escalar > 1
                    ? ` ×${c.mensajes_tras_escalar}`
                    : ''} · hace {shortAge(c.actualizado_en)}
                </span>
              {/if}

              <span class="canal">{canalLabel(c.canal)}</span>
            </div>
          </a>
        {/each}
      {/if}
    </div>
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

  /* ── pestañas + buscador ────────────────────────────────────────────── */
  /* MEDIDO el 07/09/2026: el contenido pedia 396px en 329 disponibles, y
     "Todas" se dibujaba 66px POR ENCIMA de la columna del chat. Lo mismo a
     1440, 1280 y 1100 -- no era un problema de pantalla chica: la barra no
     era responsive en absoluto.
     
     Se arregla en tres pasos, en este orden:
       1. repartir el espacio (flex:1 con min-width:0 en cada pestaña)
       2. menos padding lateral y el numero pegado al texto
       3. si aun asi no entra, desplazamiento horizontal DENTRO de la barra
     
     El tercero es la red: pase lo que pase con los numeros --169 puede ser
     16.900-- la barra scrollea y NUNCA se sale de su columna. 'overflow-x'
     necesita 'min-width: 0' en el contenedor flex o no recorta nada. */
  .tabs {
    display: flex;
    align-items: stretch;
    gap: 1px;
    padding: 8px 6px 0;
    border-bottom: 1px solid var(--v2-line);
    flex: none;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .tabs::-webkit-scrollbar {
    display: none;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    /* Reparten el ancho en vez de tomar cada una lo que necesita. */
    flex: 1 1 auto;
    min-width: 0;
    padding: 7px 4px 8px;
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    font: inherit;
    font-size: 11.8px;
    font-weight: 550;
    color: var(--v2-slate);
    cursor: pointer;
    white-space: nowrap;
  }
  .tab:hover {
    color: var(--v2-ink);
  }
  /* Activa = peso y tinta. Ember marca lo que hay que hacer, no dónde estás. */
  .tab[aria-current='true'] {
    color: var(--v2-ink);
    font-weight: 640;
    border-bottom-color: var(--v2-ink);
  }
  /* El numero es parte de la pestaña, no una pildora aparte flotando al lado:
     sin fondo propio, mismo color que su texto, y solo se separa por el peso.
     Asi las cuatro se leen como cuatro unidades y no como ocho elementos. */
  .tab-n {
    font-size: 10.5px;
    font-weight: 650;
    color: inherit;
    opacity: 0.62;
    font-variant-numeric: tabular-nums;
  }
  /* La activa destaca su numero; las inactivas lo dejan neutro. */
  .tab[aria-current='true'] .tab-n {
    opacity: 1;
  }
  /* El unico numero con color propio, y NO es el naranja de accion: trabajo
     que espera a alguien es una ALARMA, no algo que se pulsa. Ver la
     semantica de color en v2.css. */
  .tab-n.urge {
    color: var(--v2-rust);
    opacity: 1;
  }
  .buscar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
    margin: 9px 10px 3px;
    padding: 5px 9px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    background: var(--v2-card);
    color: var(--v2-slate);
  }
  .buscar:focus-within {
    border-color: var(--v2-slate);
  }
  .buscar input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--v2-ink);
    font: inherit;
    font-size: 12.5px;
    outline: none;
  }
  .limpiar {
    border: 0;
    background: none;
    color: var(--v2-slate);
    cursor: pointer;
    display: grid;
    place-items: center;
    padding: 0;
  }
  .limpiar:hover {
    color: var(--v2-ink);
  }

  /* ── filas ──────────────────────────────────────────────────────────── */
  .lista {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 4px 6px 10px;
  }
  .hueco {
    padding: 18px 10px;
  }
  .fila {
    display: flex;
    gap: 10px;
    padding: 9px 9px 10px;
    border-radius: 8px;
    color: inherit;
    text-decoration: none;
  }
  .fila:hover {
    background: var(--v2-hover);
  }
  /* La abierta se marca con la superficie, no con ember: "estoy acá" no es
     trabajo pendiente. */
  .fila.activa {
    background: var(--v2-line-soft);
  }
  /* Un tinte apenas perceptible, no un bloque. Lo que marca "sin atender" es
     el punto ember de abajo; el fondo solo tiene que hacer que la fila salte
     al pasar la vista, no gritar. */
  .fila.pide {
    background: color-mix(in srgb, var(--v2-ember) 5%, transparent);
  }
  .fila.pide:hover,
  .fila.pide.activa {
    background: color-mix(in srgb, var(--v2-ember) 9%, transparent);
  }
  /* Círculo para quien no tiene nombre: un teléfono o un uuid no dan iniciales. */
  .ident {
    flex: none;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }
  .fila.activa .ident {
    background: var(--v2-card);
  }
  .cuerpo {
    flex: 1;
    min-width: 0;
  }
  .alta {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .quien {
    font-weight: 620;
    font-size: 13px;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cuando {
    margin-left: auto;
    flex: none;
    font-size: 10.5px;
    color: var(--v2-slate);
  }
  /* El tiempo de espera no es un dato de contexto como "hace 3h": es el
     numero por el que esta fila esta donde esta.

     Tres tramos, y la diferencia entre ellos es de PESO, no solo de color:
     23 dias esperando no puede tener la misma presencia que el nombre del
     canal. Quien mira la lista de reojo tiene que ver el numero grande antes
     de leer nada. */
  .cuando.espera-fresco {
    color: var(--v2-slate);
    font-weight: 600;
  }
  .cuando.espera-viejo {
    color: var(--v2-clay);
    font-weight: 650;
  }
  .cuando.espera-critico {
    color: var(--v2-rust);
    font-weight: 750;
    font-size: 11.5px;
    letter-spacing: -0.01em;
  }

  /* El resumen del caso pesa mas que el eco del ultimo mensaje: es lo que
     responde "de que iba esto" sin abrir la conversacion. */
  .avance-resumen {
    color: var(--v2-ink);
  }

  /* El motivo, como subtitulo del caso. Texto y no pildora a proposito. */
  .motivo-fila {
    font-size: 11.2px;
    color: var(--v2-slate);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ── orden y filtro de escalada ──────────────────────────────────────── */
  .controles {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 12px 8px;
  }
  .orden {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--v2-slate);
  }
  .orden-rotulo {
    white-space: nowrap;
  }
  .orden select {
    font: inherit;
    font-size: 11.5px;
    color: var(--v2-ink);
    background: none;
    border: 1px solid var(--v2-line);
    border-radius: 6px;
    /* 28px de alto: por debajo de eso un select deja de ser comodo de
       apuntar, y esta pantalla se usa con prisa. */
    min-height: 28px;
    padding: 2px 6px;
    cursor: pointer;
  }
  .orden select:hover {
    border-color: var(--v2-slate);
  }
  .motivo-mas {
    border-style: dashed;
  }
  /* El unico numero de la cabecera que pide una reaccion. */
  .critico {
    color: var(--v2-rust);
    font-weight: 750;
  }

  /* El resumen se lee, a diferencia del ultimo mensaje, que solo orienta --
     por eso no lleva el gris apagado de .avance. Misma linea, mismo lugar. */
  .avance.resumen {
    color: var(--v2-ink);
  }

  /* El cliente volvio a escribir mientras espera. Va al lado de "Sin
     atender" y no la reemplaza: son dos hechos distintos. */
  /* Actividad viva: verde y discreto. No pide nada -- dice que algo se movio
     recien, que es informacion, no trabajo. Por eso no compite con el rojo de
     "volvio a escribir" ni con el tiempo de espera. */
  .activa {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 600;
    color: var(--v2-moss);
  }
  .activa::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--v2-moss);
    flex: none;
  }

  /* Renglon propio. Lleva punto rojo porque es la unica excepcion de la fila
     que pide mirar: no se apoya SOLO en el color -- tambien lo dice el
     texto-- pero el punto es lo que hace que se encuentre de reojo. */
  .insiste {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 650;
    color: var(--v2-rust);
    white-space: nowrap;
  }
  .insiste::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--v2-rust);
    flex: none;
  }

  /* ── filtro por motivo ───────────────────────────────────────────────── */
  .motivos {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    padding: 0 12px 8px;
  }
  .motivo {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: 1px solid var(--v2-line);
    background: none;
    border-radius: 999px;
    padding: 2px 9px;
    font: inherit;
    font-size: 11px;
    color: var(--v2-slate);
    cursor: pointer;
    white-space: nowrap;
  }
  .motivo:hover {
    color: var(--v2-ink);
    border-color: var(--v2-slate);
  }
  .motivo[aria-pressed='true'] {
    color: var(--v2-ink);
    border-color: var(--v2-ink);
    font-weight: 650;
  }
  /* Una sola línea: el preview orienta, no se lee. Dos líneas hacen que la
     altura de cada fila dependa de lo largo que fue el último mensaje. */
  .avance {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--v2-slate);
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .avance-quien {
    font-weight: 600;
    color: var(--v2-ink);
    opacity: 0.6;
  }
  .baja {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 6px;
  }
  .canal {
    display: block;
    margin-top: 4px;
    font-size: 10.5px;
    color: var(--v2-slate);
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
