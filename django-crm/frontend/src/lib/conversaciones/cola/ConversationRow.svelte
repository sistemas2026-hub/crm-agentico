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
   *
   * TRES RENGLONES Y NO OCHO  (04/11/2026)
   * La fila tenía hasta ocho renglones -- banda, nombre, por qué, resumen,
   * motivo, latido, «volvió a escribir» y pie -- y medía ~140px: entraban
   * cuatro en la columna. Para elegir a quién atender hay que ver la cola, no
   * cuatro tarjetas. Ahora:
   *
   *   1  quién · cuánto           lo que decide si es la próxima
   *   2  de qué se trata · estado lo que se lee para decidir
   *   3  las marcas               solo si hay alguna (plazo, área, ventana,
   *                               insiste, activa, dueño, canal)
   *
   * Nada de lo que se sacó era un dato sin otro lugar: la banda es el estado
   * del renglón 2; `motivo_cola` («Cliente respondió — espera a Ana») es su
   * `title`, porque la banda ya dice lo primero y el dueño del renglón 3 lo
   * segundo; y el motivo de escalada y el caso abren el renglón 2.
   */
  import { Phone, User } from '@lucide/svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { telefonoLegible } from '$lib/conversaciones/formato.js';
  import { pendiente, resuelta } from '$lib/conversaciones/estado.js';
  import { plazoDeToma, textoDePlazo } from '$lib/conversaciones/sla.js';
  import { ventanaUrge, comoRestante } from '$lib/conversaciones/ventana.js';
  import { noLeidos } from '$lib/conversaciones/lectura.js';
  import { etiquetasDeFila, recortar } from '$lib/conversaciones/etiquetas.js';
  import EtiquetaChip from '$lib/conversaciones/etiquetas/EtiquetaChip.svelte';

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
    /** Segundos que le quedan a la ventana de 24 h de esta fila, o null. Lo
        calcula el layout con la hora en que leyó la cola (ventana.js). */
    ventanaDe = () => null,
    /** Las áreas de la empresa {clave: etiqueta}, para decir a cuál se
        escaló (T22). */
    areas = {},
    /** El plazo de toma del tenant, en minutos. 0 = la empresa no definió
        objetivo y no se dibuja cuenta regresiva. */
    slaToma = 0,
    /** El catálogo de etiquetas del equipo [{clave, nombre, color}], uno solo
        para la empresa: viaja con la cola, como los rótulos (11/11/2026). */
    etiquetas = []
  } = $props();

  /* EL CANAL SE NOMBRA SOLO CUANDO NO ES WHATSAPP (04/11/2026). La vista que
     abre la Bandeja es «Operativo», y hoy el único canal operativo es
     WhatsApp: «WhatsApp» al pie de cada fila era la misma palabra cuarenta
     veces sin informar nada. Lo que sí hay que ver es la excepción -- una
     fila del simulador mezclada en «Todos» --, y esa sigue apareciendo. */
  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (/** @type {string} */ c) => CANAL_LABEL[c] ?? c;
  // Los casos se rotulan igual que los motivos: con la palabra de la empresa
  // (lib/conversaciones/rotulos.js), que viene en el mismo `motivoLabel`.
  const etiquetaLabel = (/** @type {string} */ e) => motivoLabel(e);

  const AUTOR = { user: 'Cliente', assistant: 'Asistente', humano: 'Vos', tool: 'Herramienta' };

  /**
   * El distintivo de la fila: SIEMPRE la banda que mandó el motor.
   *
   * Los siete nombres salen de `nucleo/relevo/proyeccion.py` y el mapa es uno a
   * uno: esta pantalla no clasifica nada, sólo le pone palabras y color a lo
   * que ya vino decidido. Si mañana el motor agrega una banda, acá cae en
   * `undefined` y no se dibuja distintivo -- que es mejor que inventarle uno.
   */
  const BANDAS = {
    cliente_espera: { texto: 'Cliente respondió', clase: 'b-cliente' },
    // C22: la espera que se fijó ya pasó. Misma banda, mismo tono.
    espera_vencida: { texto: 'La espera venció', clase: 'b-cliente' },
    sin_asignar: { texto: 'Sin asignar', clase: 'b-sin-asignar' },
    revisar_evaluacion: { texto: 'Falta revisar', clase: 'b-revisar' },
    // No dice "el cliente abandono": no se sabe por que no volvio. Dice lo que
    // si se sabe: nadie registro una accion de resolucion.
    sin_gestion: { texto: 'Sin resolución registrada', clase: 'b-sin-gestion' },
    interno_pendiente: { texto: 'En espera', clase: 'b-interno' },
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

  /* El estado del renglón 2: la banda si la hay; si no, lo que antes era una
     píldora. «Resuelta» va en gris y SIN punto: es un archivo, no algo que
     pida nada, y el verde queda para lo confirmado en vivo. */
  const estadoDe = (/** @type {any} */ c) => {
    const d = distintivo(c);
    if (d) return d;
    if (c.escalada_a_humano && !resuelta(c)) return { texto: 'En curso', clase: 'b-en-curso' };
    if (resuelta(c)) return { texto: 'Resuelta', clase: 'b-resuelta' };
    return null;
  };

  // Quien escribe por WhatsApp se identifica con un telefono, y quien prueba
  // desde el CRM con un uuid. Ninguno de los dos tiene iniciales: initials()
  // devuelve '3' o 'B', un circulo con una letra que no significa nada. Un
  // icono dice mas y no finge ser un nombre.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);

  /** '573023608750' -> '+57 302 360 8750' (formato.js); '3007778899' ->
      '300 777 8899'. Diez dígitos sin indicativo los deja como estaban:
      `telefonoLegible` les pondría un «+» que no es de nadie. */
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    if (!esTelefono(v)) return v;
    const d = v.replace(/\D/g, '');
    if (d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    return telefonoLegible(v);
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

  /* La fila es un CHAT (21/10/2026): se marca abierta si la URL apunta a
     CUALQUIERA de sus conversaciones -- un enlace viejo a una anterior del
     mismo número abre este mismo chat. */
  const esDeEsteChat = $derived((c.ids || [c.id]).includes(abierta));

  const tramo = $derived(tramoEspera(c));
  const pide = $derived(pendiente(c) && tramo !== 'legado');

  /* UN SOLO TIEMPO EN EL RENGLÓN 1 (04/11/2026). Había dos: «Espera: 3h»
     arriba y la última actividad al lado del nombre. Si la fila espera, el
     número es la espera de la NECESIDAD actual (esperando_desde, B3.5): el
     mismo dato con el que el motor ordena, así la lista no dice un número y
     ordena por otro. Si no espera, es la última actividad. El `title` dice
     cuál de los dos es. */
  const esperaIso = $derived(c.esperando_desde || (pendiente(c) && c.escalada_en) || null);
  /* Rojo solo si el plazo de toma venció -- o, si la empresa no definió
     plazo, si lleva una semana (el tramo «crítico»): es el mismo criterio
     que pone en rojo la «Espera máx.» de la barra de consola. */
  const tarde = $derived(!!esperaIso && (!!plazo?.vencido || tramo === 'critico'));

  /* El punto antes del nombre: solo en las que esperan a una persona, y su
     color dice cuánto. Rojo vencido, ámbar por vencer o viejo, azul «espera a
     una persona» sin apuro todavía. Nunca solo: el tiempo está al lado. */
  const urgencia = $derived(
    !pide
      ? null
      : plazo?.vencido || tramo === 'critico'
        ? 'urg-error'
        : plazo?.porVencer || tramo === 'viejo'
          ? 'urg-aviso'
          : 'urg-humano'
  );

  const estado = $derived(estadoDe(c));

  /* De qué se trata, en UN renglón: el tema corto primero (el motivo de la
     escalada si espera, o el caso) y después el resumen que redacta el
     modelo al escalar. Si no hay ninguno de los dos, el último mensaje, que
     casi nunca dice de qué iba («ok», «gracias») pero es mejor que un hueco. */
  const tema = $derived(
    pendiente(c) && c.motivo_escalamiento
      ? motivoLabel(c.motivo_escalamiento)
      : c.caso_manual
        ? etiquetaLabel(c.caso_manual)
        : ''
  );
  const resumen = $derived((c.resumen ?? '').trim());

  const insiste = $derived(pendiente(c) && c.mensajes_tras_escalar > 0);
  const urgeVentana = $derived(ventanaUrge(c, ventanaDe(c)));
  /* «Sin dueño en Dexter» solo en las abiertas: en una resuelta no le sirve a
     nadie -- no hay nada que tomar. */
  const sinDuenioDexter = $derived(!c.asignada_a && c.es_legado && !resuelta(c));
  const canalAparte = $derived(!!c.canal && c.canal !== 'whatsapp');

  /* NO LEÍDOS (11/11/2026), como WhatsApp Business: el número de mensajes del
     cliente que nadie del equipo abrió, y el nombre en negrita. Lo cuenta el
     motor (db.ultima_actividad) y, en un chat, suma sus abiertas. */
  const sinLeer = $derived(noLeidos(c));

  /* Las etiquetas del equipo: dos a la vista y «+N». Más empujarían el resto
     de las marcas fuera de la columna; todas se ven en la conversación. */
  const deLaFila = $derived(etiquetasDeFila(c.etiquetas_del_equipo, etiquetas));
  const chips = $derived(recortar(deLaFila));

  const hayMarcas = $derived(
    !!plazo || !!c.area_destino || urgeVentana || insiste || estaActiva(c) ||
      !!c.asignada_a || sinDuenioDexter || canalAparte || chips.visibles.length > 0
  );
</script>

<a
  class="fila"
  class:pide
  class:activa={esDeEsteChat}
  href="/conversaciones/{c.id}"
  aria-current={esDeEsteChat ? 'page' : undefined}
>
  <div class="cuerpo">
    <div class="renglon">
      {#if urgencia}
        <span class="urgencia {urgencia}" aria-hidden="true"></span>
      {/if}
      <span class="quien" class:sin-leer={sinLeer > 0}>
        <!-- Quien escribe por WhatsApp se identifica con un telefono y quien
             prueba desde el CRM con un uuid. El icono se queda porque
             distinguir un cliente real de una prueba de un vistazo sigue
             haciendo falta. -->
        {#if !c.nombre_cliente && esTelefono(c.usuario_externo)}
          <span class="ident" aria-hidden="true"><Phone size={12} /></span>
        {:else if !c.nombre_cliente && (!c.usuario_externo || esUuid(c.usuario_externo))}
          <span class="ident" aria-hidden="true"><User size={12} /></span>
        {/if}
        {c.nombre_cliente || quien(c.usuario_externo)}
      </span>
      <span
        class="b-cifra hace"
        class:hace-tarde={tarde}
        title={esperaIso
          ? `Esperando desde hace ${shortAge(esperaIso)}`
          : `Última actividad hace ${shortAge(c.actualizado_en)}`}
      >{shortAge(esperaIso || c.actualizado_en)}</span>
      {#if sinLeer > 0}
        <!-- El número va oculto al lector de pantalla y la frase entera no:
             «3» solo no dice de qué es. -->
        <span class="no-leidos" title="{sinLeer} {sinLeer === 1 ? 'mensaje' : 'mensajes'} del cliente sin leer">
          <span aria-hidden="true">{sinLeer > 99 ? '99+' : sinLeer}</span>
          <span class="oculto">{sinLeer} sin leer</span>
        </span>
      {/if}
    </div>

    <div class="renglon renglon-2">
      <span class="de-que" class:sin-leer={sinLeer > 0}>
        {#if tema}<span class="tema">{tema}</span>{#if resumen}<span aria-hidden="true">{' · '}</span>{resumen}{/if}
        {:else if resumen}{resumen}
        {:else}
          {#if c.ultimo_rol && c.ultimo_rol !== 'user'}
            <span class="de-que-autor">{AUTOR[c.ultimo_rol] ?? c.ultimo_rol}:</span>
          {/if}
          {c.ultimo_mensaje || 'Sin mensajes todavía'}
        {/if}
      </span>
      {#if estado}
        <!-- POR QUÉ está donde está va en el `title`: lo redacta el motor
             (proyeccion.motivo_cola) y dice lo mismo que la banda más el
             dueño, que ya están a la vista. -->
        <span
          class="estado-fila {estado.clase}"
          class:estado-legado={c.es_legado}
          title={c.motivo_cola && typeof c.banda === 'number' ? c.motivo_cola : estado.texto}
        >{estado.texto}</span>
      {/if}
    </div>

    <!-- Solo se dibuja si hay algo que decir. "El bot la está llevando" es el
         caso normal: un renglón por fila para no informar nada es lo que hacía
         que entraran cuatro. -->
    {#if hayMarcas}
      <div class="renglon marcas">
        <!-- EL PLAZO VA PRIMERO. La espera dice cuánto lleva; el plazo dice si
             eso está bien o mal. Sólo aparece si la empresa definió objetivo y
             si la conversación es de las que el plazo mide (escalada y sin
             dueño) -- ver lib/conversaciones/sla.js. -->
        {#if plazo}
          <span
            class="chip"
            class:chip-error={plazo.vencido}
            class:chip-aviso={plazo.porVencer}
            title={plazo.vencido
              ? `Venció hace ${textoDePlazo(plazo).replace('+', '')} (objetivo: ${plazo.objetivoMinutos} min para tomarla)`
              : `Quedan ${textoDePlazo(plazo)} del objetivo de ${plazo.objetivoMinutos} min para tomarla`}
          >
            {plazo.vencido ? 'Vencido' : 'Quedan'} <b class="b-cifra">{textoDePlazo(plazo)}</b>
          </span>
        {/if}
        {#if c.area_destino}
          <span class="chip chip-humano" title="Escalada a un área: la puede tomar alguien de ahí">
            → {areas[c.area_destino] || c.area_destino}
          </span>
        {/if}
        <!-- LA VENTANA DE 24 H, solo cuando queda poco y le toca a una persona
             (29/10/2026). Pasada, ya no se le puede escribir texto libre: hay
             que usar una plantilla, y eso tiene que verse antes de abrirla. -->
        {#if urgeVentana}
          <span
            class="chip chip-aviso"
            title="La ventana de WhatsApp cierra en {comoRestante(ventanaDe(c) ?? 0)}: después solo se le puede escribir con una plantilla"
          >
            Ventana <b class="b-cifra">{comoRestante(ventanaDe(c) ?? 0)}</b>
          </span>
        {/if}
        <!-- El cliente escribió de nuevo después de que le dijéramos que un
             compañero lo iba a atender: lo más parecido a alguien golpeando
             la puerta. Sin el «hace …»: ese tiempo ya es el del renglón 1,
             que cuenta desde su último mensaje. -->
        {#if insiste}
          <span class="insiste" title="Escribió de nuevo hace {shortAge(c.actualizado_en)}">
            Volvió a escribir{c.mensajes_tras_escalar > 1 ? ` ×${c.mensajes_tras_escalar}` : ''}
          </span>
        {/if}
        <!-- Actividad viva. Un punto y una palabra: se enciende con cualquier
             mensaje de los ultimos minutos y se apaga solo. -->
        {#if estaActiva(c)}
          <span class="latido">Activa</span>
        {/if}
        <!-- Las etiquetas que le puso el equipo al chat (11/11/2026). -->
        {#each chips.visibles as e (e.clave)}
          <EtiquetaChip nombre={e.nombre} color={e.color} tamano="fila" />
        {/each}
        {#if chips.resto > 0}
          <span class="etq-resto" title={deLaFila.slice(chips.visibles.length).map((e) => e.nombre).join(', ')}
            >+{chips.resto}</span
          >
        {/if}
        <!-- `asignada_a` es la ASIGNACIÓN DURABLE DE DEXTER (proyeccion.py).
             NO es el dueño del ticket del CRM -- D28.

             La rama «Sin asignar» que vivía acá (banda 2) se fue: banda 2 ES
             `sin_asignar`, así que el estado del renglón 2 ya lo dice con la
             misma palabra. Eran dos «Sin asignar» en la misma fila. -->
        {#if c.asignada_a}
          <span class="duenio"><span class="punto"></span>{c.asignada_a}</span>
        {:else if sinDuenioDexter}
          <!-- Una legada NO tiene dueño en Dexter porque nunca entró al relevo
               (relevo_version = 0). Verlo escrito es parte de G8 -- que quede
               claro que abrirla no le asigna a nadie. La condición es
               explícita (`sinDuenioDexter` exige `!c.asignada_a`): una legada
               que SÍ tiene dueño no puede decir "sin dueño". -->
          <span class="duenio duenio-sin-dexter">Sin dueño en Dexter</span>
        {/if}
        {#if canalAparte}
          <span class="canal">{canalLabel(c.canal)}</span>
        {/if}
      </div>
    {/if}
  </div>
</a>

<style>
  /* Las filas se separan con una línea, no con aire y esquinas redondeadas:
     así entra más cola en la misma altura y la lista se lee como una lista.
     Sin raya de color a la izquierda (04/11/2026): lo que esa raya decía --
     «esta pide algo» -- lo dice ahora el punto antes del nombre, con un color
     por urgencia en vez de un rojo igual para todas. */
  .fila {
    display: block;
    padding: 8px 12px;
    color: inherit;
    text-decoration: none;
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

  /* La abierta: fondo teñido y un borde de 1px alrededor -- con `outline` y
     desplazamiento negativo para que no empuje el contenido ni cambie el alto
     de la fila al seleccionarla. */
  .fila.activa {
    background: var(--bandeja-humano-fondo);
    outline: 1px solid var(--bandeja-humano-borde);
    outline-offset: -1px;
  }

  .fila:focus-visible {
    outline: 2px solid var(--bandeja-accion);
    outline-offset: -2px;
  }

  .cuerpo {
    min-width: 0;
  }

  /* Cada renglón es una línea y nunca dos: lo que no entra se corta con
     puntos suspensivos. Es lo que mantiene el alto de la fila fijo. */
  .renglon {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
  }

  .renglon-2 {
    margin-top: 2px;
  }

  /* ── renglón 1: quién y cuánto ───────────────────────────────────────── */
  .urgencia {
    flex: none;
    align-self: center;
    width: 8px;
    height: 8px;
    margin-right: -4px;
    border-radius: 50%;
  }
  .urg-error {
    background: var(--bandeja-error);
  }
  .urg-aviso {
    background: var(--bandeja-aviso);
  }
  .urg-humano {
    background: var(--bandeja-humano);
  }

  .quien {
    flex: 1 1 auto;
    min-width: 0;
    font-family: var(--bandeja-titulo);
    font-size: 15px;
    font-weight: 600;
    line-height: 20px;
    color: var(--bandeja-texto);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Un teléfono o un uuid no dan iniciales, así que va un icono chico pegado
     al nombre en vez de un círculo con una letra que no significa nada. */
  .ident {
    display: inline-flex;
    vertical-align: -1px;
    margin-right: 4px;
    color: var(--bandeja-texto-3);
  }

  .hace {
    flex: none;
    font-size: 12px;
    color: var(--bandeja-texto-2);
  }

  .hace-tarde {
    color: var(--bandeja-error);
  }

  /* SIN LEER (11/11/2026): como WhatsApp, el nombre y el texto un tono más
     fuertes y un contador al final del renglón. El contador es marino -- el
     color de la acción de una persona --, no el verde: en esta Bandeja el
     verde dice «en vivo / confirmado». */
  .quien.sin-leer {
    font-weight: 700;
  }

  .de-que.sin-leer {
    color: var(--bandeja-texto);
  }

  .no-leidos {
    flex: none;
    align-self: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    background: var(--bandeja-accion);
    color: #fff;
    font-family: var(--bandeja-titulo);
    font-size: 11.5px;
    font-weight: 700;
    line-height: 18px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }

  .oculto {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .etq-resto {
    flex: none;
    color: var(--bandeja-texto-2);
    font-size: 11px;
  }

  /* ── renglón 2: de qué se trata, y el estado ─────────────────────────── */
  .de-que {
    flex: 1 1 auto;
    min-width: 0;
    font-size: 13px;
    line-height: 18px;
    color: var(--bandeja-texto-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* El tema es lo que se lee de reojo; el resumen lo completa. */
  .tema {
    color: var(--bandeja-texto);
  }

  .de-que-autor {
    font-weight: 700;
  }

  /* El estado: texto chico con un punto de su color. No cede ancho: medido el
     04/11/2026, con `flex-shrink` el resumen largo lo aplastaba a «Sin asig…»
     y «La atiende l…», que es justo la palabra que se busca de reojo. Lo que
     se corta es el resumen; el tope de 50% es la red para el estado más
     largo («Sin resolución registrada», ~150px de 336). */
  .estado-fila {
    flex: none;
    max-width: 50%;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .estado-fila::before {
    content: '';
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
  }

  .b-cliente {
    color: var(--bandeja-error);
  }
  .b-sin-asignar,
  .b-interno,
  .b-sin-gestion {
    color: var(--bandeja-aviso);
  }
  .b-revisar,
  .b-legado {
    color: var(--bandeja-texto-2);
  }
  .b-en-curso {
    color: var(--bandeja-humano);
  }
  /* El violeta de la IA. Va con su palabra al lado, nunca solo: el color no
     alcanza para decir quién está atendiendo. */
  .b-ia {
    color: var(--bandeja-ia);
  }
  /* Resuelta: gris neutro y sin punto. No es una alerta ni una buena noticia
     que celebrar en cada fila: es un archivo. */
  .b-resuelta {
    color: var(--bandeja-neutro-texto);
  }
  .b-resuelta::before {
    display: none;
  }

  /* Legado: apagado y en cursiva. Una legada sin adoptar no es algo
     accionable desde acá (G8). */
  .estado-legado {
    font-style: italic;
  }

  /* ── renglón 3: las marcas ───────────────────────────────────────────── */
  .marcas {
    align-items: center;
    gap: 8px;
    margin-top: 4px;
    overflow: hidden;
    font-size: 12px;
    line-height: 16px;
  }

  /* Plazo, área y ventana: un dato con su palabra, en un recuadro de 1px.
     En reposo es apenas un dato más; cerca del vencimiento se enciende;
     vencido es lo único de la fila que grita. Nunca sólo color. */
  .chip {
    flex: none;
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    padding: 0 4px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto-2);
    white-space: nowrap;
  }

  .chip b {
    font-weight: 600;
  }

  .chip-humano {
    color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
  }

  .chip-aviso {
    color: var(--bandeja-aviso);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }

  .chip-error {
    color: var(--bandeja-error);
    background: var(--bandeja-error-fondo);
    border-color: var(--bandeja-error-borde);
  }

  /* Punto y palabra, sin recuadro: «volvió a escribir» pide mirar y «activa»
     solo informa, pero los dos son hechos de la conversación, no datos de
     plazo. */
  .insiste,
  .latido {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }

  .insiste::before,
  .latido::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .insiste {
    color: var(--bandeja-error);
    font-weight: 700;
  }

  /* Actividad viva: el verde de «en vivo», el único uso que tiene acá. */
  .latido {
    color: var(--bandeja-ok);
  }

  .duenio {
    flex: 0 1 auto;
    min-width: 0;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--bandeja-humano);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .duenio .punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  /* Legada: apagado. No es un hueco que alguien deba llenar desde acá. */
  .duenio-sin-dexter {
    color: var(--bandeja-texto-3);
  }

  .canal {
    flex: none;
    margin-left: auto;
    color: var(--bandeja-texto-3);
    white-space: nowrap;
  }
</style>
