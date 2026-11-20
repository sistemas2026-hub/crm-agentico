<script>
  /**
   * Cerrar un caso a mano: en qué terminó, y opcionalmente una nota (B6, T17).
   *
   * POR QUÉ ESTO REEMPLAZA AL `confirm()` DE ANTES
   * Antes cerrar era un «¿seguro?» y listo. La conversación se cerraba y de
   * lo que le había pasado al cliente no quedaba nada: ni si era la ONT, ni
   * si era facturación, ni si lo había resuelto él solo. Con cincuenta casos
   * cerrados por semana eso es cincuenta veces que nadie aprende nada.
   *
   * NINGUNA OPCIÓN VIENE ELEGIDA, y es la regla de este panel. Ni la primera
   * de la lista, ni la última que usó esta persona. Un valor por defecto
   * convierte cerrar en dos clics y llena la columna con lo que eligió el
   * formulario en vez de lo que pasó — y esa columna existe justo para poder
   * contar lo que pasó.
   *
   * LA LISTA VIENE DEL MOTOR, no de un array acá: una empresa puede agregar
   * códigos propios desde la configuración, y una copia en la pantalla se
   * desincroniza el día que alguien lo hace. También vienen del motor el
   * grupo de cada código y si exige nota (10/11/2026).
   *
   * DOS PREGUNTAS, DOS GRUPOS (10/11/2026). Eran doce opciones en una grilla
   * de tres columnas que se leía de costado: «Red de distribución» quedaba al
   * lado de «Equipo del cliente» y el orden del motor --de la casa del
   * cliente hacia la red-- no se veía. Ahora cada grupo es una fila de
   * fichas que se lee de izquierda a derecha, en ese orden.
   */
  import { CircleCheck, Check, Wrench, MessagesSquare } from '@lucide/svelte';
  import {
    MAX_NOTA,
    motivoParaNoCerrar,
    categoriaVisible,
    agruparDesenlaces
  } from '$lib/conversaciones/desenlaces.js';

  let {
    catalogo = [],
    errorCatalogo = '',
    guardando = false,
    error = '',
    onCerrar = undefined,
    onCancelar = undefined
  } = $props();

  let codigo = $state('');
  let nota = $state('');

  const grupos = $derived(agruparDesenlaces(catalogo));
  const elegido = $derived(catalogo.find((/** @type {any} */ d) => d.codigo === codigo));
  const impedimento = $derived(motivoParaNoCerrar({ codigo, nota, catalogo }));
</script>

<form
  class="cierre"
  aria-labelledby="cierre-titulo"
  onsubmit={(e) => {
    e.preventDefault();
    if (!impedimento) onCerrar?.({ codigo, nota });
  }}
>
  <!-- El encabezado lleva el verde y el ícono de «Resuelto»: es el mismo
       gesto, y así se ve de dónde salió el panel (10/11/2026). -->
  <div class="cabeza">
    <span class="cabeza-icono" aria-hidden="true"><CircleCheck size={16} /></span>
    <div>
      <h3 class="titulo" id="cierre-titulo">¿En qué terminó?</h3>
      <p class="instruccion">Elegí qué le pasaba al cliente. Con esto se cuenta dónde fallamos más.</p>
    </div>
  </div>

  <!-- Lo unico que hace scroll: el titulo y los botones quedan siempre a la
       vista (10/11/2026). -->
  <div class="cuerpo">
  {#if errorCatalogo}
    <p class="aviso-mal">{errorCatalogo}</p>
  {/if}

  {#each grupos as g (g.clave)}
    <fieldset class="grupo">
      {#if g.titulo}
        <legend class="grupo-titulo">
          {#if g.clave === 'falla'}<Wrench size={13} aria-hidden="true" />{:else}<MessagesSquare size={13} aria-hidden="true" />{/if}
          {g.titulo}
        </legend>
      {/if}
      <div class="opciones">
        {#each g.desenlaces as d (d.codigo)}
          {@const categoria = categoriaVisible(d)}
          <!-- La radio sigue ahí, para el teclado y el lector de pantalla;
               lo que se ve es la ficha, con un tilde cuando está elegida. -->
          <label class="opcion" class:elegida={codigo === d.codigo}>
            <input class="radio-oculta" type="radio" name="desenlace" value={d.codigo} bind:group={codigo} />
            {#if codigo === d.codigo}<Check size={13} aria-hidden="true" />{/if}
            <span>{d.nombre}</span>
            {#if categoria}<span class="categoria">· {categoria}</span>{/if}
          </label>
        {/each}
      </div>
    </fieldset>
  {/each}

  <label class="campo-nota">
    <!-- Con «Otro» la nota deja de ser opcional, y el rótulo lo dice en el
         momento en que pasa: enterarse por el botón apagado es tarde. -->
    <span class="campo-rotulo" class:obligatoria={elegido?.exige_nota}>
      {elegido?.exige_nota ? `Nota (obligatoria con «${elegido.nombre}»)` : 'Nota (opcional)'}
    </span>
    <textarea
      bind:value={nota}
      maxlength={MAX_NOTA}
      rows="2"
      required={!!elegido?.exige_nota}
      placeholder="Qué pasó, en una línea. Sin datos personales del cliente."
    ></textarea>
  </label>
  </div>

  <div class="pie">
    <!-- La consecuencia va junto al botón, que es donde se decide. Arriba,
         entre las instrucciones, se leía antes de saber qué elegir. -->
    <p class="consecuencia">Se cierra la conversación. El próximo mensaje del cliente abre una nueva.</p>
    <div class="acciones">
      <!-- Deshabilitado CON el motivo al lado: un botón apagado y mudo hace que
           alguien recargue la página tres veces antes de preguntar. -->
      {#if impedimento && !guardando}<span class="impedimento" id="cierre-impedimento">{impedimento}</span>{/if}
      <button type="button" class="v2-btn v2-btn-sm v2-btn-quiet" onclick={() => onCancelar?.()}>
        Cancelar
      </button>
      <button
        type="submit"
        class="v2-btn v2-btn-sm boton-cerrar"
        disabled={!!impedimento || guardando}
        aria-busy={guardando}
        aria-describedby={impedimento && !guardando ? 'cierre-impedimento' : undefined}
      >
        {guardando ? 'Cerrando…' : 'Cerrar el caso'}
      </button>
    </div>
  </div>

  {#if error}<p class="aviso-mal">{error}</p>{/if}
</form>

<style>
  /* El verde de «Resuelto» en el borde y el encabezado: el panel se lee como
     parte de ese gesto, y no como una caja gris más entre el hilo y la
     barra (10/11/2026). Mezclado con el borde de siempre para que no grite. */
  .cierre {
    --cierre-verde: var(--bandeja-ok);
    --cierre-verde-suave: color-mix(in srgb, var(--bandeja-ok) 8%, var(--bandeja-superficie));
    border: 1px solid color-mix(in srgb, var(--cierre-verde) 40%, var(--bandeja-borde));
    border-radius: 8px;
    margin-top: 10px;
    background: var(--bandeja-superficie);
    /* NO SE DEJA APLASTAR, Y SI NO CABE HACE SCROLL ADENTRO (10/11/2026).
       El panel vive en la columna central, que es flex en columna. Con
       'overflow: hidden' (puesto para que el encabezado respetara las
       esquinas) un hijo flex pierde su altura minima, y en una pantalla
       baja la columna lo achicaba y cortaba las opciones sin dejar hacer
       scroll. 'flex: none' lo saca del reparto y el tope deja lugar al
       hilo de la conversacion.

       Encabezado, cuerpo y pie en columna, y SOLO el cuerpo hace scroll: el
       titulo y "Cerrar el caso" quedan siempre a la vista. Se probo primero
       con 'position: sticky' dentro de un panel con scroll, y Chromium pintaba
       las fichas por encima del borde del panel (medido en el navegador). */
    flex: none;
    display: flex;
    flex-direction: column;
    max-height: 65vh;
    overflow: hidden;
  }
  .cuerpo {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 14px 16px 0;
  }
  /* Un error, si lo hay, va debajo del pie: necesita su propio aire. */
  .cierre > .aviso-mal:last-child {
    margin: 0 16px 12px;
  }
  .cabeza {
    flex: none;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 16px;
    background: var(--cierre-verde-suave);
    border-bottom: 1px solid color-mix(in srgb, var(--cierre-verde) 25%, var(--bandeja-borde));
  }
  .cabeza-icono {
    display: inline-flex;
    margin-top: 1px;
    color: var(--cierre-verde);
  }
  .titulo {
    margin: 0;
    font-family: var(--bandeja-titulo);
    font-size: 17px;
    font-weight: 650;
    line-height: 1.2;
  }
  .instruccion {
    margin: 2px 0 0;
    font-size: 12.5px;
    color: var(--bandeja-texto-2);
  }

  .grupo {
    border: 0;
    margin: 0 0 12px;
    padding: 0;
    min-width: 0;
  }
  .grupo-titulo {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0;
    margin-bottom: 8px;
    font-size: 12px;
    font-weight: 650;
    color: var(--bandeja-texto);
  }
  .grupo-titulo :global(svg) {
    color: var(--bandeja-texto-2);
  }

  /* Fichas que envuelven: el orden se lee de izquierda a derecha, que es el
     orden del motor. Una grilla de columnas lo recorría de costado. */
  .opciones {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .opcion {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    position: relative;
    padding: 6px 12px;
    border: 1px solid var(--bandeja-borde-fuerte);
    border-radius: 999px;
    background: var(--bandeja-superficie);
    font-size: 12.5px;
    line-height: 1.3;
    cursor: pointer;
    transition:
      border-color 0.12s ease,
      background-color 0.12s ease;
  }
  /* Fuera de la vista pero en el orden del teclado y para el lector de
     pantalla: se elige con las flechas como cualquier grupo de radios. */
  .radio-oculta {
    position: absolute;
    inset: 0;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }
  .opcion:hover {
    border-color: var(--bandeja-texto-2);
  }
  /* Elegida: relleno, borde y tilde a la vez. Con solo un fondo apenas más
     claro, la única señal era el punto de la radio. Marino, que es el color
     de una acción de una persona en esta pantalla, no el verde del cierre:
     elegir no es todavía cerrar. */
  .opcion.elegida {
    border-color: var(--bandeja-accion);
    background: var(--bandeja-accion);
    color: var(--bandeja-superficie);
    font-weight: 600;
    padding-left: 9px;
  }
  .opcion:has(.radio-oculta:focus-visible) {
    outline: 2px solid var(--bandeja-humano);
    outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    .opcion {
      transition: none;
    }
  }
  .categoria {
    font-size: 11.5px;
    font-weight: 400;
    color: var(--bandeja-texto-2);
  }
  .opcion.elegida .categoria {
    color: inherit;
    opacity: 0.8;
  }

  .campo-nota {
    display: block;
    margin-top: 4px;
  }
  .campo-rotulo {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--bandeja-texto-2);
  }
  .campo-rotulo.obligatoria {
    color: var(--bandeja-texto);
  }
  .campo-nota textarea {
    display: block;
    width: 100%;
    margin-top: 4px;
    font: inherit;
    font-size: 12.5px;
    padding: 6px 8px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    resize: vertical;
  }

  .pie {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px 16px;
    margin-top: 12px;
    flex-wrap: wrap;
  }
  /* Fijo abajo, de borde a borde, separado del cuerpo que hace scroll. */
  .cierre > .pie {
    flex: none;
    margin: 12px 0 0;
    padding: 10px 16px 12px;
    background: var(--bandeja-superficie);
    border-top: 1px solid var(--bandeja-borde);
  }
  .consecuencia {
    margin: 0;
    font-size: 12px;
    color: var(--bandeja-texto-2);
  }
  .acciones {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
    flex-wrap: wrap;
    justify-content: flex-end;
    /* `.v2-btn` hereda el tamaño de letra: sin esto salían a 16px, más
       grandes que los de la barra de arriba (medido en el navegador). */
    font-size: 12px;
  }
  /* Verde, como «Resuelto» y el encabezado: es la misma acción terminada.
     La tinta queda para «Tomar», que es otra; con las dos en tinta se leían
     como el mismo tipo de botón. */
  .boton-cerrar {
    border: 1px solid var(--cierre-verde);
    background: var(--cierre-verde);
    color: var(--bandeja-superficie);
    font-weight: 650;
  }
  .boton-cerrar:hover:not(:disabled) {
    border-color: var(--cierre-verde);
    background: var(--cierre-verde);
    color: var(--bandeja-superficie);
    filter: brightness(0.92);
  }
  .boton-cerrar:disabled {
    border-color: var(--bandeja-borde-fuerte);
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-3);
  }
  .impedimento {
    font-size: 12px;
    color: var(--bandeja-texto-2);
  }
  .aviso-mal {
    margin: 8px 0 0;
    font-size: 12px;
    color: var(--bandeja-error);
  }
</style>
