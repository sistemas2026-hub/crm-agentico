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
   * EL DUEÑO QUE MUESTRA ES `c.asignada_a` -- la ASIGNACIÓN DURABLE DE DEXTER,
   * que sale de `asignada_a_nombre` en la proyección. NO es el dueño del
   * ticket del CRM: ése es otra cosa, vive en CasePanel, y usarlo acá sería
   * exactamente lo que D28 prohíbe. Si alguna vez esta fila necesita un
   * nombre y `asignada_a` viene vacío, la respuesta es dejarlo vacío.
   *
   * `es_legado` sólo pinta una clase -- abrir una fila legada no la adopta ni
   * toca `relevo_version` (G8). Este archivo no escribe nada, nunca.
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
   * `.activa` SIGNIFICABA DOS COSAS y el scope NO las separaba — las dos viven
   * en este archivo, o sea en el MISMO scope:
   *
   *   .fila.activa   la conversación abierta ahora mismo
   *   .activa        el punto de "se movió hace un rato"
   *
   * Con la misma especificidad (0,2,0) ganaba la última del archivo, que era la
   * del punto. Medido el 21/09/2026 sobre la fila abierta: `display: inline-flex`
   * (en vez de block), `font-size: 10.5px`, `color: moss` y un `::before` de 6px
   * inyectado adentro del `<a>`. Efecto visible: la fila abierta se pintaba
   * verde, encogía, dejaba de llenar la columna y la desbordaba 147px — con
   * barra de scroll horizontal en la cola.
   *
   * El punto pasó a llamarse `.latido`. No es cosmética: mientras compartan
   * nombre, cualquier regla que se agregue a uno se le aplica al otro.
   */
  import Pill from '$lib/v2/components/Pill.svelte';
  import { Phone, User } from '@lucide/svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { pendiente, resuelta } from '$lib/conversaciones/estado.js';
  import { plazoDeToma, textoDePlazo } from '$lib/conversaciones/sla.js';

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
    motivoLabel,
    /** El plazo de toma del tenant, en minutos. 0 = la empresa no definió
        objetivo y no se dibuja cuenta regresiva. */
    slaToma = 0
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

  /**
   * El distintivo de la fila: SIEMPRE la banda que mandó el motor.
   *
   * Los seis nombres salen de `nucleo/relevo/proyeccion.py` y el mapa es uno a
   * uno: esta pantalla no clasifica nada, sólo le pone palabras y color a lo
   * que ya vino decidido. Si mañana el motor agrega una banda, acá cae en
   * `undefined` y no se dibuja distintivo -- que es mejor que inventarle uno.
   *
   * El texto va en español porque la aplicación está en español; el diseño
   * congelado está en inglés y eso es una diferencia deliberada, igual que el
   * resto de la Bandeja.
   */
  const BANDAS = {
    cliente_espera: { texto: 'Cliente respondió', clase: 'b-cliente' },
    sin_asignar: { texto: 'Sin asignar', clase: 'b-sin-asignar' },
    revisar_evaluacion: { texto: 'Falta revisar', clase: 'b-revisar' },
    interno_pendiente: { texto: 'Pendiente interno', clase: 'b-interno' },
    en_curso: { texto: 'En atención', clase: 'b-en-curso' },
    legado: { texto: 'Legado · revisar', clase: 'b-legado' }
  };

  /** Fuera de la cola y la lleva la IA: el único distintivo que no es banda. */
  const LA_LLEVA_LA_IA = { texto: 'La atiende la IA', clase: 'b-ia' };

  const distintivo = (/** @type {any} */ c) =>
    typeof c.banda === 'number'
      ? BANDAS[c.banda_nombre]
      : c.necesita_accion_de === 'ia'
        ? LA_LLEVA_LA_IA
        : null;
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
  /* El plazo de toma de ESTA fila. Se recalcula con el mismo reloj de 20 s
     que usa el punto "Activa": uno solo para toda la lista, así el número no
     depende de cuándo se montó cada fila. */
  const plazo = $derived(plazoDeToma(c, slaToma, ahora || Date.now()));

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
  <div class="cuerpo">
    <!-- Primer renglón: POR QUÉ está en la cola, y desde cuándo espera. El
         diseño pone estas dos cosas arriba de todo y tiene razón: son las que
         deciden si esta fila es la próxima. -->
    <div class="tope">
      {#if distintivo(c)}
        {@const d = distintivo(c)}
        <span class="marca-banda {d.clase}"><span class="punto"></span>{d.texto}</span>
      {/if}
      <!-- La espera que se muestra es la de la NECESIDAD actual
           (esperando_desde, B3.5): si el cliente volvio a escribir,
           es desde ese mensaje y no desde la escalada. Es el mismo
           dato con el que el motor ordena, asi que la lista no dice
           un numero y ordena por otro. -->
      <!-- EL PLAZO VA ANTES QUE LA ESPERA. La espera dice cuánto lleva; el
           plazo dice si eso está bien o mal, que es lo que decide si esta
           fila es la próxima. Sólo aparece si la empresa definió objetivo y
           si la conversación es de las que el plazo mide (escalada y sin
           dueño) -- ver lib/conversaciones/sla.js. -->
      {#if plazo}
        <span
          class="plazo"
          class:plazo-vencido={plazo.vencido}
          class:plazo-cerca={plazo.porVencer}
          title={plazo.vencido
            ? `Venció hace ${textoDePlazo(plazo).replace('+', '')} (objetivo: ${plazo.objetivoMinutos} min para tomarla)`
            : `Quedan ${textoDePlazo(plazo)} del objetivo de ${plazo.objetivoMinutos} min para tomarla`}
        >
          {plazo.vencido ? 'Vencido' : 'Quedan'}
          <b class="v2-num">{textoDePlazo(plazo)}</b>
        </span>
      {/if}
      {#if c.esperando_desde}
        <span
          class="cuando v2-num espera-{tramoEspera(c)}"
          title="Esperando desde hace {shortAge(c.esperando_desde)}"
        >
          Espera: {shortAge(c.esperando_desde)}
        </span>
      {:else if pendiente(c) && c.escalada_en}
        <span
          class="cuando v2-num espera-{tramoEspera(c)}"
          title="Esperando desde hace {shortAge(c.escalada_en)}"
        >
          Espera: {shortAge(c.escalada_en)}
        </span>
      {/if}
    </div>

    <div class="alta">
      <span class="quien">
        <!-- Quien escribe por WhatsApp se identifica con un telefono y quien
             prueba desde el CRM con un uuid. El icono se queda -- mas chico y
             pegado al nombre en vez de una columna propia -- porque distinguir
             un cliente real de una prueba de un vistazo sigue haciendo falta. -->
        {#if !c.nombre_cliente && esTelefono(c.usuario_externo)}
          <span class="ident" aria-hidden="true"><Phone size={11} /></span>
        {:else if !c.nombre_cliente && (!c.usuario_externo || esUuid(c.usuario_externo))}
          <span class="ident" aria-hidden="true"><User size={11} /></span>
        {/if}
        {c.nombre_cliente || quien(c.usuario_externo)}
      </span>
      <span class="cuando v2-num">{shortAge(c.actualizado_en)}</span>
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
          <!-- SOLO SI LA BANDA NO LO DIJO YA. `distintivo(c)` dibuja arriba
               "En atención", "Sin asignar", "Cliente respondió"… y abajo
               aparecía además una píldora "En curso" diciendo lo mismo con
               otras palabras: dos rótulos de estado en una fila que ya tiene
               banda, espera, nombre, motivo y dueño. La referencia pone UN
               distintivo por fila. No se pierde nada -- cuando no hay banda
               (una resuelta, por ejemplo) la píldora sigue estando. -->
        {:else if c.escalada_a_humano && !resuelta(c) && !distintivo(c)}
          <Pill tone="clay" dot>En curso</Pill>
        {:else if resuelta(c) && !distintivo(c)}
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
      <span class="latido">Activa</span>
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

    <!-- El pie: quién la tiene, y por dónde entró.
         `asignada_a` es la ASIGNACIÓN DURABLE DE DEXTER (proyeccion.py, sale
         de asignada_a_nombre). NO es el dueño del ticket del CRM, que es otra
         cosa y vive en CasePanel -- D28, y sigue reservado para B4. La cola
         nunca mostró dueño hasta acá: el dato estaba proyectado y sin usar. -->
    <div class="pie">
      {#if c.asignada_a}
        <span class="duenio"><span class="punto"></span>{c.asignada_a}</span>
      {:else if c.es_legado}
        <!-- Lo dice con todas las letras en vez de dejar el hueco: una legada
             NO tiene dueño en Dexter porque nunca entró al relevo
             (relevo_version = 0). Verlo escrito es parte de G8 -- que quede
             claro que abrirla no le asigna a nadie.

             OJO: esta rama es el `else` de `c.asignada_a`, así que la
             condición real es `!c.asignada_a && c.es_legado`. Si alguien
             reordena las ramas, una legada QUE SÍ tiene dueño diría "sin
             dueño", que es una afirmación falsa. Mantener este bloque
             después del de `asignada_a`, o volver la condición explícita. -->
        <span class="duenio duenio-sin-dexter">Sin dueño en Dexter</span>
      {:else if c.banda === 2}
        <span class="duenio duenio-vacante"><span class="punto"></span>Sin asignar</span>
      {:else}
        <span></span>
      {/if}
      <span class="canal">{canalLabel(c.canal)}</span>
    </div>
  </div>
</a>

<style>

  /* Las filas se separan con una línea, no con aire y esquinas redondeadas:
     así entra más cola en la misma altura y la lista se lee como una lista.
     La separación la dibuja ConversationList entre hermanas. */
  .fila {
    display: block;
    /* 10 -> 8: densidad. La referencia mete la misma fila en 112px y ésta
       pedía 132. Se saca aire, no renglones. */
    padding: 8px 12px;
    color: inherit;
    text-decoration: none;
    border-left: 3px solid transparent;
    /* La línea que separa de la fila anterior. Va acá y no en la lista con un
       `:global(a + a)`: el `<a>` es el elemento raíz de este componente, así
       que `:first-child` se evalúa contra sus hermanas REALES del DOM y la
       primera no arrastra un borde suelto. Sin cruzar la frontera de scope. */
    border-top: 1px solid var(--bandeja-borde);
  }

  .fila:first-child {
    border-top-color: transparent;
  }

  .fila:hover {
    background: var(--bandeja-superficie-suave);
  }

  /* La abierta se marca con el filete azul y un fondo apenas teñido: es la
     única fila con la que se está trabajando ahora mismo. */
  .fila.activa {
    background: var(--bandeja-humano-fondo);
    border-left-color: var(--bandeja-humano);
  }

  /* Lo que pide una persona lleva el filete rojo. Es el mismo lenguaje: el
     borde izquierdo dice de quién es la fila. */
  .fila.pide {
    border-left-color: var(--bandeja-error);
  }

  .fila.pide:hover {
    background: var(--bandeja-error-fondo);
  }

  /* Un teléfono o un uuid no dan iniciales, así que va un icono chico pegado
     al nombre en vez de un círculo con una letra que no significa nada. */
  .ident {
    display: inline-flex;
    vertical-align: -1px;
    margin-right: 3px;
    color: var(--bandeja-texto-3);
  }

  /* ── el distintivo de banda ──────────────────────────────────────────── */
  /* Lo que el motor decidió, en palabras y con color. Nunca un puntaje. */
  .marca-banda {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 5px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .marca-banda .punto {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .b-cliente {
    background: var(--bandeja-error-fondo);
    color: var(--bandeja-error);
    border-color: var(--bandeja-error-borde);
  }
  .b-sin-asignar,
  .b-interno {
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
    border-color: var(--bandeja-aviso-borde);
  }
  .b-revisar,
  .b-legado {
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    border-color: var(--bandeja-borde-fuerte);
  }
  .b-en-curso {
    background: var(--bandeja-humano-fondo);
    color: var(--bandeja-humano);
    border-color: var(--bandeja-humano-borde);
  }
  /* El violeta de la IA. Va con su palabra al lado, nunca solo: el color no
     alcanza para decir quién está atendiendo. */
  .b-ia {
    background: var(--bandeja-ia-fondo);
    color: var(--bandeja-ia);
    border-color: var(--bandeja-ia-borde);
  }

  /* ── el plazo de toma ──────────────────────────────────────────────────
     Tres estados y tres pesos. En reposo es apenas un dato más; cerca del
     vencimiento se enciende; vencido es lo único de la fila que grita.
     Nunca sólo color: siempre lleva la palabra ("Quedan" / "Vencido"). */
  .plazo {
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    flex: none;
    padding: 1px 5px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
    white-space: nowrap;
  }

  .plazo b {
    font-size: 10.5px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .plazo-cerca {
    color: var(--bandeja-aviso);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }

  .plazo-vencido {
    color: var(--bandeja-error);
    background: var(--bandeja-error-fondo);
    border-color: var(--bandeja-error-borde);
  }

  .tope {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 2px;
    min-height: 14px;
  }

  /* ── el pie: quién la tiene ──────────────────────────────────────────── */
  .pie {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-top: 4px;
    padding-top: 3px;
    border-top: 1px solid var(--bandeja-borde);
  }

  .duenio {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: var(--bandeja-mono);
    font-size: 10.5px;
    font-weight: 500;
    color: var(--bandeja-humano);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .duenio .punto {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  /* Vacante: el hueco se ve, pero no compite con una fila que sí tiene dueño. */
  .duenio-vacante {
    color: var(--bandeja-aviso);
  }

  /* Legada: apagado. No es un hueco que alguien deba llenar desde acá. */
  .duenio-sin-dexter {
    color: var(--bandeja-texto-3);
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
  .latido {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 600;
    color: var(--v2-moss);
  }

  .latido::before {
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

  /* POR QUÉ ESTÁ ACÁ: texto, no píldora.
     Era una píldora gris redondeada (radio 999) con `var(--v2-hueso, #f1efe9)`
     y `var(--v2-tinta-suave, #5c5850)` -- dos variables que NO existen, así
     que se pintaba con los colores de respaldo, fuera del sistema congelado,
     igual que pasaba con las burbujas del hilo.
     Además competía: en la referencia la fila tiene UN distintivo arriba
     --la banda-- y todo lo demás es texto de distinto peso. Una segunda forma
     redondeada al lado del badge hace que el ojo no sepa cuál de las dos
     contesta "¿es esta la próxima?".
     Una sola línea: el motivo orienta, no se lee entero. */
  .por-que {
    display: block;
    margin: 1px 0 0;
    color: var(--bandeja-texto-2);
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  /* Legado: apagado y en cursiva, sin caja. El borde punteado lo marcaba como
     algo accionable, y una legada sin adoptar es justo lo contrario (G8). */
  .por-que-legado {
    font-style: italic;
    color: var(--bandeja-texto-3);
  }


  .avance {
    margin: 1px 0 0;
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
    margin-top: 4px;
  }

  .canal {
    display: block;
    margin-top: 4px;
    font-size: 10.5px;
    color: var(--v2-slate);
  }
</style>
