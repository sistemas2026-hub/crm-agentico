<script>
  /**
   * Una fila de la cola: quién escribió, cuánto hace que espera, por qué está
   * donde está y de qué se trata.
   *
   * NO DECIDE SU POSICIÓN. La banda, `esperando_desde` y el texto de
   * `motivo_cola` los calcula el motor (B3.5); el orden lo resuelve
   * `ordenamiento.js`; y qué filas se ven, `visibles` en el layout. Acá sólo
   * se dibuja lo que ya vino decidido. Si alguna vez aparece la tentación de
   * calcular prioridad o banda en este archivo, la frontera está mal trazada.
   *
   * No muestra dueño, a propósito (D28): el owner del ticket del CRM no es la
   * asignación durable de Dexter, y la cola no usa ninguno de los dos para
   * nada. `es_legado` sólo pinta una clase -- abrir una fila legada no la
   * adopta ni toca `relevo_version` (G8).
   *
   * `c` llega entero y no desarmado en quince props: la fila consume quince
   * campos, y convertirlos en quince props sería inventar una API en una fase
   * que promete equivalencia. `ahora` viene del reloj de 20 s del layout, que
   * sigue siendo uno solo para toda la lista.
   *
   * La navegación es un `href` y nada más. Sin `goto`, sin `onclick`, sin
   * `fetch`: eso es lo que hace que abrir una conversación en pestaña nueva
   * funcione, y que la fila no tenga estado propio.
   *
   * OJO CON `.activa`, QUE SIGNIFICA DOS COSAS a un metro de distancia:
   *
   *   .fila.activa   la conversación abierta ahora mismo
   *   .activa        el punto de "se movió hace un rato"
   *
   * Las cinco reglas de las dos viven acá y el scope las mantiene separadas
   * del resto, pero la colisión de nombres es real. No se renombra en Fase 0.
   */
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { Phone, User } from '@lucide/svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { pendiente, resuelta } from '$lib/conversaciones/estado.js';

  let {
    // La conversación, entera y tal como la manda el motor.
    c,
    // El id de la conversación abierta, para marcarse seleccionada.
    abierta = null,
    // El reloj del layout. Sin él, el punto "Activa" se congela.
    ahora = 0,
    // Helpers que se quedan en el layout porque los usa alguien más:
    // tramoEspera lo consume el contador de críticas del encabezado, y
    // motivoLabel también lo usa QueueFilters.
    tramoEspera,
    motivoLabel
  } = $props();

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

  /** Se movio en los ultimos minutos. Cinco y no uno: con uno el punto
      parpadea y se pierde; con quince deja de significar "ahora". */
  const MINUTOS_ACTIVA = 5;
  const estaActiva = (/** @type {any} */ c) =>
    !!c.ultimo_mensaje_en &&
    ahora - new Date(c.ultimo_mensaje_en).getTime() < MINUTOS_ACTIVA * 60 * 1000;
</script>

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
      <!-- La espera que se muestra es la de la NECESIDAD actual
           (esperando_desde, B3.5): si el cliente volvio a escribir,
           es desde ese mensaje y no desde la escalada. Es el mismo
           dato con el que el motor ordena, asi que la lista no dice
           un numero y ordena por otro. -->
      {#if c.esperando_desde}
        <span
          class="cuando v2-num espera-{tramoEspera(c)}"
          title="Esperando desde hace {shortAge(c.esperando_desde)}"
        >
          {shortAge(c.esperando_desde)} esperando
        </span>
      {:else if pendiente(c) && c.escalada_en}
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

    <!-- POR QUE esta fila esta donde esta, en palabras. No un
         numero de prioridad: quien atiende tiene que poder leer
         "Cliente respondio - espera a Ana" y decidir. Lo redacta el
         motor (proyeccion.motivo_cola), no esta pantalla. -->
    {#if c.motivo_cola && typeof c.banda === 'number'}
      <span class="por-que" class:por-que-legado={c.es_legado}>{c.motivo_cola}</span>
    {/if}

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

<style>

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

  /* Una sola línea: el preview orienta, no se lee. Dos líneas hacen que la
     altura de cada fila dependa de lo largo que fue el último mensaje. */
  .por-que {
    display: inline-flex;
    align-self: flex-start;
    margin: 1px 0 2px;
    padding: 1px 6px;
    border-radius: 999px;
    background: var(--v2-hueso, #f1efe9);
    color: var(--v2-tinta-suave, #5c5850);
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }


  .por-que-legado {
    background: transparent;
    border: 1px dashed var(--v2-line, #ddd);
  }


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
</style>
