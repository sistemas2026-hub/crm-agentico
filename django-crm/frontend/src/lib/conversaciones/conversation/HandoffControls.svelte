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
  import { TriangleAlert, CircleCheck, UserCheck } from '@lucide/svelte';

  let {
    conversacion,
    caso,
    operadores = [],
    // Verdad ya resuelta por el motor y por la pagina.
    iaEnPausa, escalada, atendida, esMia, asignadaA, esAdmin, gobernada,
    // Tomar / Soltar: una sola accion.
    marcandoAtendida = false, errorAtender = '', onAtender,
    // Cerrar la conversacion.
    resolviendo = false, errorResolver = '', onResolver,
    // Reasignar (solo ADMIN). El formulario escribe en la pagina.
    reasignando = $bindable(false),
    destinoReasignar = $bindable(''),
    motivoReasignar = $bindable(''),
    guardandoReasignar = false, errorReasignar = '', onReasignar
  } = $props();

  const motivoLabel = (/** @type {string} */ m) => (m ? m.replaceAll('_', ' ') : '');
</script>

  <!-- El icono dice QUÉ tipo de situación es, y no era así: el triángulo de
       alerta salía en los cuatro estados, incluido "asignada a mí", que no es
       una alerta sino trabajo normal en curso. Una alarma que está siempre
       encendida deja de significar algo.

       Alerta sólo cuando falta alguien; cuando ya hay dueño, la señal es que
       está en manos de una persona. -->
  <p class="aviso" class:aviso-sin-dueno={escalada && !atendida && !esMia && !asignadaA}>
    {#if escalada && !atendida && !esMia && !asignadaA}
      <TriangleAlert size={14} />
    {:else}
      <UserCheck size={14} />
    {/if}
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
    <!-- Tomar el caso, y soltarlo. Son el mismo boton porque son el mismo
         gesto en dos sentidos, y porque tener dos ("Atender" / "Soltar")
         obligaria a mirar cual esta activo para saber quien lo tiene. -->
    {#if escalada && !atendida && conversacion.estado !== 'cerrada'}
      {#if esMia}
        <span class="duenio duenio-mio">
          <span class="duenio-punto"></span>Asignada a mí
        </span>
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
             reasignar, y eso es de un administrador. -->
        <span class="duenio" title="La tiene {asignadaA}">
          <span class="duenio-punto"></span>{asignadaA}
        </span>
      {:else}
        <button
          type="button"
          class="v2-btn v2-btn-ink aviso-atender"
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
    {:else if atendida && conversacion.estado !== 'cerrada'}
      <span class="aviso-atendida"><CircleCheck size={13} /> Atendida</span>
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
          class="v2-btn v2-btn-sm v2-btn-quiet aviso-resolver"
          onclick={() => onResolver?.()}
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
        {#if errorReasignar}<span class="aviso-mal">{errorReasignar}</span>{/if}
      </div>
    </form>
  {/if}

<style>
  /* Duplicación temporal por CSS scoped durante Fase 0A: la misma regla
     sigue en +page.svelte, que todavía la necesita. Consolidar en Fase 1
     sin cambiar apariencia. */

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
    color: var(--bandeja-error);
    background: color-mix(in srgb, var(--bandeja-error) 6%, transparent);
    border-bottom: 1px solid var(--bandeja-borde);
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
    color: var(--bandeja-ok);
    font-weight: 600;
  }
  /* Duplicación temporal por CSS scoped durante Fase 0A: la misma regla
     sigue en +page.svelte, que todavía la necesita. Consolidar en Fase 1
     sin cambiar apariencia. */

  /* Sin dueño: lo único de los cuatro estados que pide que alguien haga algo.
     Se marca con el filete, no tiñendo el texto -- el resto de la línea tiene
     que seguir leyéndose igual de bien. */
  /* QUIÉN LA TIENE. Los dos casos --mía y de otra persona-- comparten forma
     porque son el mismo concepto: sólo cambia a quién nombran. Antes se veían
     distintos y eso hacía pensar que eran estados de distinta naturaleza.

     Es el mismo distintivo que usa el pie de la fila en la cola: la misma
     pregunta, la misma respuesta visual. */
  .duenio {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: var(--bandeja-mono);
    font-size: 10.5px;
    font-weight: 600;
    color: var(--bandeja-texto-2);
    white-space: nowrap;
    /* Un nombre largo se recorta en vez de empujar los botones fuera de la
       franja. El `title` de la etiqueta sigue teniendo el nombre completo, así
       que no se pierde: sólo deja de competir por el ancho.
       `min-width: 0` es obligatorio -- sin él un hijo flex no achica por
       debajo de su contenido y el ellipsis no llega a aplicarse. */
    min-width: 0;
    max-width: 22ch;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Cuando es mía va en azul: es la única de las dos sobre la que este
     operador puede actuar. */
  .duenio-mio {
    color: var(--bandeja-humano);
  }

  .duenio-punto {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .aviso-sin-dueno {
    border-left: 3px solid var(--bandeja-aviso);
  }

  .aviso-mal {
    flex: none;
    color: var(--bandeja-error);
  }

  /* El conflicto de asignación: informativo, no destructivo. Se distingue del
     resto por el filete y no por el color del texto, para que se lea como una
     nota al margen y no como una alarma. */
  .aviso-conflicto {
    flex: none;
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-left: 3px solid var(--bandeja-humano);
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
  .aviso-resolver {
    border-color: var(--bandeja-borde);
  }

  .aviso-resolver:hover {
    border-color: var(--bandeja-texto-2);
    background: var(--bandeja-superficie-suave);
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
