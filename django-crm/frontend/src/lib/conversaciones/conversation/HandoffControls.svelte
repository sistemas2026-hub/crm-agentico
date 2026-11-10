<script>
  /**
   * El banner de una conversación escalada: en qué estado está el relevo, y
   * los gestos que se hacen desde ahí.
   *
   * NO DECIDE NADA. Quién controla la conversación lo resuelve el motor
   * (`control_efectivo`, B3.3b), el dueño durable sale de la asignación de
   * Dexter (B3.4, y nunca del dueño del ticket del CRM — D28), y la banda de
   * la cola la calcula el backend (B3.5). Todo eso llega acá ya decidido, como
   * props. Si alguna vez hace falta recalcular una de esas cosas acá, la
   * frontera está mal trazada.
   *
   * `onAtender` es UNA sola acción para Tomar y para Soltar, igual que antes:
   * son el mismo gesto en dos sentidos, y tener dos botones obligaría a mirar
   * cuál está activo para saber quién la tiene.
   *
   * "Marcar como resuelta" cierra la conversación, que no es relevo. Está acá
   * porque está físicamente en este bloque; su lugar se reconsidera en la fase
   * visual, no ahora.
   */
  import { TriangleAlert, CircleCheck, UserCheck, Bot } from '@lucide/svelte';
  import { rotuloDe } from '$lib/conversaciones/rotulos.js';
  import { estadoDeLaConversacion, cierreDe } from '$lib/conversaciones/estado-unico.js';

  let {
    conversacion,
    caso,
    operadores = [],
    // Verdad ya resuelta por el motor y por la pagina.
    iaEnPausa, escalada, atendida, esMia, asignadaA, esAdmin, gobernada,
    /** LA LÍNEA DE ESTADO (04/11/2026), ya elegida por la página con
        estado-unico.js. Si no viene --una prueba que dibuja el componente
        suelto, o un montaje que no la pasa-- se calcula acá con las MISMAS
        props, sin los eventos del relevo: sale igual salvo quién cerró y
        cuándo, que solo la página conoce. */
    estadoUnico = undefined,
    // Tomar / Soltar: una sola accion.
    marcandoAtendida = false, errorAtender = '', onAtender,
    // Cerrar la conversacion. `cerrando`: el panel de cierre esta abierto.
    resolviendo = false, errorResolver = '', onResolver, cerrando = false,
    // Reasignar (solo ADMIN). El formulario escribe en la pagina.
    reasignando = $bindable(false),
    destinoReasignar = $bindable(''),
    motivoReasignar = $bindable(''),
    guardandoReasignar = false, errorReasignar = '', onReasignar,
    // Cómo se lee cada motivo en esta empresa (lib/conversaciones/rotulos.js).
    rotulos = {},
    // ESCALAR A UN ÁREA (T22): las áreas de la empresa {clave: etiqueta} y la
    // acción, que vive en la página.
    areas = {},
    escalandoArea = false, errorEscalarArea = '', onEscalarArea = undefined
  } = $props();

  /* Lo puede hacer cualquier operador con la conversación SUYA o SIN dueño;
     la de otra persona se pasa con Reasignar, que es de administrador. */
  const puedeEscalar = $derived(
    escalada && gobernada && conversacion.estado !== 'cerrada' && (esMia || !asignadaA) &&
      Object.keys(areas).length > 0
  );
  let escalando = $state(false);
  let areaElegida = $state('');
  let motivoArea = $state('');
  let notaArea = $state('');
  async function enviarEscalada() {
    const ok = await onEscalarArea?.({ area: areaElegida, motivo: motivoArea, nota: notaArea });
    if (ok) {
      escalando = false;
      areaElegida = '';
      motivoArea = '';
      notaArea = '';
    }
  }

  const motivoLabel = (/** @type {string} */ m) => rotuloDe(m, rotulos);

  /* UNA SOLA LÍNEA DE ESTADO (04/11/2026). El chip tenía sus propias tres
     ramas de texto --«Respondida por el equipo · IA no responde», «Escalada ·
     IA no responde», «Escalada · el asistente sigue respondiendo»-- y la
     cabecera tenía otra caja que decía lo suyo. Ahora el texto, el detalle y
     el tono salen de estado-unico.js, que explica por qué existe.

     El tono sigue la regla de antes: rojo SOLO cuando nadie se hizo cargo
     (29/10/2026: «ESCALADA» en rojo junto a «Atendida» en verde eran dos
     veredictos opuestos en la misma línea). */
  const estado = $derived(
    estadoUnico ??
      estadoDeLaConversacion({
        estado: conversacion.estado, iaEnPausa, escalada, atendida, esMia, asignadaA,
        cierre: cierreDe(null, conversacion)
      })
  );
  /* Cerrada, la línea es lo único: quién la tomó, el motivo, el caso del CRM
     y «Resuelta» en verde eran historia, y contaban una conversación viva. */
  const cerrada = $derived(conversacion.estado === 'cerrada');
</script>

  <!-- El icono dice QUÉ tipo de situación es, y no era así: el triángulo de
       alerta salía en los cuatro estados, incluido "asignada a mí", que no es
       una alerta sino trabajo normal en curso. Una alarma que está siempre
       encendida deja de significar algo.

       Alerta sólo cuando falta alguien; cuando ya hay dueño, la señal es que
       está en manos de una persona. -->
  <p class="aviso">
    <!-- El icono va DENTRO del chip: fuera de él heredaba el rojo de la franja
         entera, y ese rojo se fue. -->
    <!-- "IA pausada" seria falso y no es un matiz de redaccion: el asistente
         SIGUE leyendo y procesando cada mensaje mientras espera -- de eso
         depende que un "listo, gracias" del cliente cierre el caso solo.
         Lo que dejo de hacer es contestar. Por eso estado-unico.js dice «la
         IA no responde» y nunca «pausada». -->
    <span class="aviso-estado aviso-estado-{estado.tono}" role="status">
      {#if estado.tono === 'alerta' || estado.tono === 'aviso'}
        <TriangleAlert size={13} aria-hidden="true" />
      {:else if estado.tono === 'humano'}
        <UserCheck size={13} aria-hidden="true" />
      {:else if estado.tono === 'ia'}
        <Bot size={13} aria-hidden="true" />
      {:else}
        <CircleCheck size={13} aria-hidden="true" />
      {/if}
      <span>
        <strong>{estado.texto}</strong>{#if estado.detalle}<span class="aviso-detalle">{` · ${estado.detalle}`}</span>{/if}
      </span>
    </span>
    {#if !cerrada}
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
    <!-- EN ESPERA (29/10/2026): qué se espera, para quien la abra después.
         Se quita respondiendo sin marcar «Queda en espera». -->
    {#if conversacion.pendiente_interno_desde && conversacion.estado !== 'cerrada'}
      <span class="aviso-espera" title="Se quita al responder sin marcar «Queda en espera»">
        En espera: {conversacion.pendiente_interno_nota || 'sin detalle'}{#if conversacion.pendiente_interno_hasta}
          · hasta {new Date(conversacion.pendiente_interno_hasta).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}{/if}
      </span>
    {/if}
    <!-- ESCALADA A UN ÁREA (T22): a cuál, y la nota de lo que se validó para
         quien la recibe. -->
    {#if conversacion.area_destino && conversacion.estado !== 'cerrada'}
      <span class="aviso-area" title={conversacion.area_destino_nota || ''}>
        Escalada a {areas[conversacion.area_destino] || conversacion.area_destino}
      </span>
    {/if}
    <!-- LOS GESTOS, EN UN SOLO GRUPO (10/11/2026). Sueltos en la fila, el
         ultimo que no entraba bajaba solo a la linea de abajo: «Resuelto»
         quedaba huerfano debajo del estado. Juntos, si no entran bajan los
         cuatro, alineados a la derecha. -->
    <span class="aviso-acciones">
    <!-- Tomar el caso, y soltarlo. Son el mismo boton porque son el mismo
         gesto en dos sentidos, y porque tener dos ("Atender" / "Soltar")
         obligaria a mirar cual esta activo para saber quien lo tiene. -->
    <!-- Quién la tiene ya lo dice la línea de estado («Asignada a mí», «La
         atiende Ana»): la ficha de dueño que iba acá lo repetía al lado
         (04/11/2026). Quedan los gestos. -->
    {#if escalada && !atendida && conversacion.estado !== 'cerrada'}
      {#if esMia}
        <button
          type="button"
          class="v2-btn v2-btn-sm aviso-atender"
          title="Devuelve el caso a «Por atender» para que lo tome otra persona. Sigue en manos del equipo, no vuelve a la IA."
          onclick={() => onAtender?.()}
          disabled={marcandoAtendida}
          aria-busy={marcandoAtendida}
        >
          {marcandoAtendida ? 'Soltando…' : 'Soltar'}
        </button>
      {:else if asignadaA}
        <!-- De otra persona: no se ofrece soltar ni tomar. Pasarla es
             reasignar, y eso es de un administrador. El hueco empuja lo que
             sigue a la derecha, salvo que venga «Reasignar», que ya empuja:
             dos `auto` separarían el grupo en los dos extremos. -->
        {#if !(esAdmin && gobernada && operadores.length)}
          <span class="aviso-empuje" aria-hidden="true"></span>
        {/if}
      {:else}
        <!-- Mientras se cierra, la accion de ese momento es el cierre:
             «Tomar» en tinta competia con «Cerrar el caso» del panel. -->
        <button
          type="button"
          class="v2-btn aviso-atender {cerrando ? 'v2-btn-sm v2-btn-quiet' : 'v2-btn-ink'}"
          title="Te hacés cargo: pasa a «En atención» y sale de «Por atender». No le envía nada al cliente, y se puede soltar."
          onclick={() => onAtender?.()}
          disabled={marcandoAtendida}
          aria-busy={marcandoAtendida}
        >
          <CircleCheck size={13} />
          {marcandoAtendida ? 'Tomando…' : 'Tomar'}
        </button>
      {/if}
      {#if esAdmin && gobernada && operadores.length}
        <button
          type="button"
          class="v2-btn v2-btn-sm v2-btn-quiet aviso-atender"
          onclick={() => { reasignando = !reasignando; errorReasignar = ''; }}
          aria-expanded={reasignando}
        >
          Reasignar
        </button>
      {/if}
    {:else if atendida && !iaEnPausa && conversacion.estado !== 'cerrada'}
      <!-- Con la IA en pausa el chip ya dice «Respondida por el equipo»:
           repetirlo en verde era la segunda voz de la misma línea. -->
      <span class="aviso-atendida"><CircleCheck size={13} /> Atendida</span>
    {:else if conversacion.estado !== 'cerrada'}
      <!-- Lo que empujaba «Marcar como resuelta» a la derecha era el verde de
           al lado; sin él, este hueco hace lo mismo. -->
      <span class="aviso-empuje" aria-hidden="true"></span>
    {/if}
    <!-- ESCALAR A UN ÁREA va FUERA del bloque de Tomar/Soltar a propósito:
         el caso típico es el de alguien que ya respondió, validó y no pudo
         resolver -- o sea una conversación «atendida», que ese bloque no
         dibuja. -->
    {#if puedeEscalar}
      <button
        type="button"
        class="v2-btn v2-btn-sm v2-btn-quiet"
        title="Pasarla a otra área con lo que validaste: queda sin dueño y marcada para esa área"
        onclick={() => (escalando = !escalando)}
        aria-expanded={escalando}
      >
        Escalar a un área
      </button>
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
        <!-- Abre y cierra el panel, y mientras esta abierto se ve apretado:
             es el gesto que se esta haciendo. -->
        <button
          type="button"
          class="v2-btn v2-btn-sm aviso-resolver"
          class:aviso-resolver-activo={cerrando}
          onclick={() => onResolver?.()}
          disabled={resolviendo}
          aria-busy={resolviendo}
          aria-expanded={cerrando}
          aria-describedby="ayuda-resolver"
        >
          <!-- «Resuelto» a secas (29/10/2026): «Marcar como resuelta» era el
               rótulo más largo de la barra y el más apagado, para la acción
               que cierra el caso. La ayuda de al lado sigue explicando qué
               hace. -->
          <CircleCheck size={13} aria-hidden="true" />
          {resolviendo ? 'Cerrando…' : 'Resuelto'}
        </button>
        <span class="ayuda" id="ayuda-resolver" role="tooltip">
          Usá esto si el caso se resolvió por teléfono, presencialmente o por
          otro canal. Abajo elegís en qué terminó y se cierra la conversación;
          el próximo mensaje del cliente abre una nueva.
        </span>
      </span>
    {/if}
    </span>
    {/if}
    <!-- Cerrada: sin la marca verde «Resuelta» que iba acá (04/11/2026). La
         línea de estado ya dice «Cerrada · la resolvió…», y el verde se
         reserva para lo confirmado. -->

    <!-- Un 409 de asignación NO es un error de quien apretó: es la realidad
         -- otra persona la tomó primero, o la IA la controla. El mensaje ya
         dice QUIÉN quedó (conflictoDeAsignacion en la página), así que se
         presenta como información y no como falla: filete azul, sin rojo y
         sin modal, igual que el diseño congelado.

         Un rojo acá le diría al operador que hizo algo mal cuando lo único
         que pasó es que llegó segundo. -->
    {#if errorAtender}<span class="aviso-conflicto">{errorAtender}</span>{/if}
    {#if errorResolver}<span class="aviso-mal">{errorResolver}</span>{/if}
  </p>
  {#if escalando && puedeEscalar}
    <form class="reasignar" onsubmit={(e) => { e.preventDefault(); enviarEscalada(); }}>
      <label>
        <span>A qué área</span>
        <select class="v2-input" bind:value={areaElegida} required>
          <option value="">Elegí un área…</option>
          {#each Object.entries(areas) as [clave, etiqueta] (clave)}
            <option value={clave}>{etiqueta}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Por qué no la resolviste</span>
        <input class="v2-input" bind:value={motivoArea} maxlength="200" required
          placeholder="Ej: la ONT no levanta después de reiniciar" />
      </label>
      <label>
        <span>Qué validaste y qué falta</span>
        <textarea class="v2-input" bind:value={notaArea} maxlength="1000" rows="3" required
          placeholder="Lo que quien la reciba necesita para no empezar de cero"></textarea>
        <span class="ayuda-campo">Queda como nota interna en la conversación</span>
      </label>
      <div class="reasignar-acciones">
        <button type="submit" class="v2-btn v2-btn-sm v2-btn-ink"
          disabled={escalandoArea || !areaElegida || !motivoArea.trim() || !notaArea.trim()}>
          {escalandoArea ? 'Escalando…' : 'Escalar'}
        </button>
        <button type="button" class="v2-btn v2-btn-sm v2-btn-quiet" onclick={() => (escalando = false)}>
          Cancelar
        </button>
        {#if errorEscalarArea}<span class="aviso-conflicto">{errorEscalarArea}</span>{/if}
      </div>
    </form>
  {/if}
  {#if reasignando && esAdmin && gobernada}
    <form class="reasignar" onsubmit={(e) => { e.preventDefault(); onReasignar?.(); }}>
      <label>
        <span>Pasar a</span>
        <select bind:value={destinoReasignar} required>
          <option value="" disabled>Elegí a quién…</option>
          {#each operadores as o (o.usuario_id)}
            <option value={o.usuario_id}>{o.nombre}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Motivo (obligatorio)</span>
        <!-- Que quede en la auditoría no es un detalle legal: cambia cómo se
             escribe. «pasa a Ana» y «Ana tiene el historial del caso con la
             cooperativa» cuestan lo mismo, y dentro de tres semanas sólo uno
             de los dos sirve. El evento `reasignada` lo guarda con actor,
             anterior, nuevo y versión (C16). -->
        <span class="ayuda-campo">Queda registrado en la auditoría del caso</span>
        <textarea bind:value={motivoReasignar} rows="2" maxlength="500" required></textarea>
      </label>
      <div class="reasignar-acciones">
        <button type="submit" class="v2-btn v2-btn-sm v2-btn-ink" disabled={guardandoReasignar}
                aria-busy={guardandoReasignar}>
          {guardandoReasignar ? 'Reasignando…' : 'Confirmar reasignación'}
        </button>
        <button type="button" class="v2-btn v2-btn-sm v2-btn-quiet" onclick={() => (reasignando = false)}>
          Cancelar
        </button>
        <!-- El mismo tratamiento que el 409 de Tomar/Soltar: `reasignar()`
             usa conflictoDeAsignacion(), así que acá llega el mismo tipo de
             mensaje -- «la tomó Ana antes», «es anterior al relevo». Verlo en
             rojo acá y en azul allá haría parecer que son cosas distintas. -->
        {#if errorReasignar}<span class="aviso-conflicto">{errorReasignar}</span>{/if}
      </div>
    </form>
  {/if}

<style>
  /* Nació duplicada en 0A.3: el CSS de Svelte es por componente, así que al
     mudar este banner hubo que copiar la regla porque `+page.svelte` también
     la usaba. Esa copia del padre se fue en 1.4B.1, cuando el retiro del reset
     de prueba eliminó su único consumidor -- así que la duplicación quedó
     cerrada y ésta es ahora la única. */

  /* LA ALARMA ES EL CHIP, NO LA FRANJA.
     Era un lavado rosa de borde a borde con TODO el texto en rojo --el estado,
     el motivo, el caso del CRM-- y 56px de alto. En la referencia (medida en
     el HTML de Stitch) la franja no tiene fondo, mide 38px, y lo único que
     lleva color es una etiqueta mono de 10px: #B91C1C sobre #FEF2F2, radio 4,
     padding 2px 8px. El resto de la línea se lee en tinta normal.

     No es sólo estética: cuando todo el renglón grita, el motivo --que es el
     dato que hace falta para decidir-- grita igual que el estado, y la franja
     compite con el hilo por la atención de una pantalla entera. */
  .aviso {
    flex-wrap: wrap;
    row-gap: 6px;
    flex: none;
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
    /* 8/20: alineada con la cabecera de arriba (04/11/2026). */
    padding: 8px 20px;
    font-size: 12px;
    color: var(--bandeja-texto);
    background: var(--bandeja-superficie);
    border-bottom: 1px solid var(--bandeja-borde);
  }

  /* LA LÍNEA DE ESTADO (04/11/2026). Era una etiqueta mono en versalita de
     9,5px: se leía como un código, y la caja «Control humano» de la cabecera
     tenía que completar lo que no decía. Ahora es la única que lo dice, así
     que se escribe normal: el estado en negrita, el detalle al lado en peso
     normal. Envuelve antes que recortar: «Cerrada · la resolvió…» con su
     detalle es una frase larga, y cortada no informa.

     El tono significa algo: gris = nada pendiente, rojo = nadie se hizo
     cargo, azul = en manos de una persona, violeta = la lleva la IA. */
  .aviso-estado {
    display: inline-flex;
    align-items: flex-start;
    gap: 6px;
    min-width: 0;
    padding: 4px 8px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-family: var(--bandeja-sans);
    font-size: 12px;
    line-height: 1.4;
  }

  .aviso-estado :global(svg) {
    flex: none;
    margin-top: 2px;
  }

  .aviso-estado strong {
    font-weight: 600;
  }

  .aviso-detalle {
    font-weight: 400;
  }

  .aviso-estado-neutro {
    border-color: var(--bandeja-neutro-borde);
    background: var(--bandeja-neutro-fondo);
    color: var(--bandeja-neutro-texto);
  }

  .aviso-estado-alerta {
    border-color: var(--bandeja-error-borde);
    background: var(--bandeja-error-fondo);
    color: var(--bandeja-error);
  }

  /* Escaló pero el asistente sigue contestando: en riesgo, no urgente. */
  .aviso-estado-aviso {
    border-color: var(--bandeja-aviso-borde);
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
  }

  .aviso-estado-humano {
    border-color: var(--bandeja-humano-borde);
    background: var(--bandeja-humano-fondo);
    color: var(--bandeja-humano);
  }

  .aviso-estado-ia {
    border-color: var(--bandeja-ia-borde);
    background: var(--bandeja-ia-fondo);
    color: var(--bandeja-ia);
  }

  .aviso-atender {
    margin-left: auto;
    flex: none;
  }

  /* El grupo es el que se empuja a la derecha; adentro, los 'auto' de cada
     boton ya no tienen espacio que repartir. */
  .aviso-acciones {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    margin-left: auto;
  }

  /* Sin margin-left:auto a proposito: el hermano de la izquierda ya empuja al
     grupo a la derecha, y un segundo 'auto' los separaria a los extremos. */
  .aviso-empuje {
    margin-left: auto;
  }

  .aviso-resolver {
    flex: none;
  }

  .aviso-atendida {
    margin-left: auto;
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--bandeja-ok);
    font-weight: 600;
  }
  /* Nació duplicada en 0A.3: el CSS de Svelte es por componente, así que al
     mudar este banner hubo que copiar la regla porque `+page.svelte` también
     la usaba. Esa copia del padre se fue en 1.4B.1, cuando el retiro del reset
     de prueba eliminó su único consumidor -- así que la duplicación quedó
     cerrada y ésta es ahora la única. */

  /* La ficha de dueño (`.duenio`) y el filete ámbar de «sin dueño»
     (`.aviso-sin-dueno`, un borde lateral de 3px) se fueron el 04/11/2026:
     quién la tiene lo dice la línea de estado, y «sin dueño» lo dice su rojo.
     Un acento de color al costado que repite lo que ya está escrito es ruido. */

  .aviso-mal {
    flex: none;
    color: var(--bandeja-error);
  }

  /* El conflicto de asignación: informativo, no destructivo. Se distingue del
     resto por el filete y no por el color del texto, para que se lea como una
     nota al margen y no como una alarma. */
  .ayuda-campo {
    font-size: 10.5px;
    color: var(--bandeja-texto-3);
    font-weight: 400;
  }

  .aviso-conflicto {
    flex: none;
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    /* Filete de 1px en todo el contorno (04/11/2026): el borde lateral de
       3px era un acento decorativo, no una señal. */
    border: 1px solid var(--bandeja-humano-borde);
    background: var(--bandeja-humano-fondo);
    border-radius: var(--bandeja-radio-sm);
    color: var(--bandeja-texto);
    font-size: 12px;
  }



  /* El aviso de escalada: tres piezas con jerarquia distinta -- que paso
     (fuerte), por que (medio), y el estado del CRM (chip aparte). */
  /* El recorte con puntos suspensivos lo dejaba en "sin datos pa..." -- que no
     dice nada y es peor que partirse en dos renglones. Ahora la FILA envuelve:
     el motivo se lleva la linea entera si hace falta, y los botones bajan con
     el, en vez de que el motivo desaparezca para que quepan. */
  .aviso-motivo {
    color: var(--bandeja-texto-2);
  }

  .aviso-area {
    padding: 1px 7px;
    border: 1px solid var(--bandeja-humano-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-humano-fondo);
    color: var(--bandeja-humano);
    font-size: 11.5px;
    font-weight: 600;
  }

  .aviso-espera {
    padding: 1px 7px;
    border: 1px solid var(--bandeja-aviso-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
    font-size: 11.5px;
    font-weight: 600;
    max-width: 22rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
    color: var(--bandeja-texto);
    background: var(--bandeja-superficie);
    border: 1px solid var(--bandeja-borde);
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


  /* El secundario de verdad: se lee, pero no compite con "Atender". */
  /* Verde y con relleno suave: se ve sin gritar, y no se confunde con
     «Tomar» (tinta), que es lo que se hace al ENTRAR; esto es al salir. */
  .aviso-resolver {
    border-color: var(--bandeja-ok);
    background: color-mix(in srgb, var(--bandeja-ok) 10%, #fff);
    color: var(--bandeja-ok);
    font-weight: 600;
  }

  .aviso-resolver:hover:not(:disabled),
  .aviso-resolver-activo {
    background: var(--bandeja-ok);
    color: #fff;
  }


  .reasignar {
    display: grid;
    gap: 8px;
    max-width: 100%;
    margin: 6px 0 10px;
    padding: 10px 12px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
  }


  .reasignar label {
    display: grid;
    gap: 4px;
    font-size: 12px;
  }


  .reasignar select,
  .reasignar textarea {
    width: 100%;
    font: inherit;
  }


  .reasignar-acciones {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }




  .aviso-caso {
    font-size: 11px;
    font-weight: 650;
    padding: 1px 8px;
    border-radius: 999px;
    color: var(--bandeja-texto-2);
    border: 1px solid var(--bandeja-borde);
    white-space: nowrap;
  }
</style>
