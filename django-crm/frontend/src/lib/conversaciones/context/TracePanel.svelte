<script>
  /**
   * Qué hizo la IA, paso por paso, sacado de la traza real.
   *
   * No hay puntajes ni confianza del modelo acá: eso no existe en Dexter. Lo
   * que se muestra son las herramientas que efectivamente se llamaron, con su
   * resultado, y el diagnóstico que dejó el motor.
   */
  import { TriangleAlert, ArrowRight, CircleCheck, CircleX, ShieldCheck } from '@lucide/svelte';

  let {
    herramientas = [], diagnostico, contrasteUtil = false,
    pasoMarcado = null, motivoBloqueo = {}, onIrAlPaso
  } = $props();
</script>

  {#if herramientas.length > 0}
  <!-- Abierto de entrada SOLO si hubo un bloqueo o un error. Si todo corrio
     normal el panel es secundario y no tiene por que ocupar la columna;
     cuando algo se freno o se rompio, el hallazgo tiene que estar a la
     vista sin que nadie sospeche primero -- que es justo lo que no pasa
     con un panel plegado que casi nadie abre. -->
  <details class="proceso" open={!!(diagnostico?.bloqueadas || diagnostico?.errores)}>
  <summary class="proceso-resumen">
    Ver proceso
    <span class="v2-muted">
      ({herramientas.length} paso{herramientas.length === 1 ? '' : 's'}{#if herramientas.some((h) => h.es_escritura)}, con escritura{/if})
    </span>
    <!-- Lo unico que se asoma con el panel cerrado. El resto de la traza se
         mira cuando hay una sospecha; un bloqueo o un fallo hay que verlo
         ANTES, porque cambia lo que quien atiende tiene que hacer. -->
    {#if diagnostico?.errores}
      <span class="diag-aviso diag-error">
        {diagnostico.errores} error{diagnostico.errores === 1 ? '' : 'es'}
      </span>
    {/if}
    {#if diagnostico?.bloqueadas}
      <span class="diag-aviso diag-bloqueo">
        {diagnostico.bloqueadas} bloqueada{diagnostico.bloqueadas === 1 ? '' : 's'}
      </span>
    {/if}
  </summary>
  <!-- Diagnostico de la IA. Va ARRIBA de la lista y no al final: quien abre
       esto lo hace porque sospecha de una respuesta, y lo primero que
       necesita saber es si algo se rompio o si el sistema hizo su trabajo.
       Leer catorce pasos para deducirlo es justo lo que hay que evitar. -->
  {#if diagnostico}
    <ul class="diag">
      <li>
        <CircleCheck size={14} style="color:var(--v2-moss);flex:none" />
        <b>{diagnostico.normales}</b>
        {diagnostico.normales === 1 ? 'ejecución normal' : 'ejecuciones normales'}
        <span class="v2-muted">corrió y devolvió datos</span>
      </li>
      <!-- Con cero, un renglon informativo. Con uno o mas, un BOTON que
           lleva al paso: el numero contesta "paso algo", y lo siguiente que
           se quiere es ver QUE, sin buscarlo entre catorce lineas.
           Los dos en cero no se dibujan: ver 'contrasteUtil'. -->
      {#if contrasteUtil}
      <li class:diag-hay={diagnostico.bloqueadas > 0}>
        <ShieldCheck size={14} style="color:var(--v2-clay);flex:none" />
        {#if diagnostico.bloqueadas > 0}
          <button type="button" class="diag-ir" onclick={() => onIrAlPaso?.('bloqueo')}>
            <b>{diagnostico.bloqueadas}</b>
            {diagnostico.bloqueadas === 1 ? 'acción bloqueada' : 'acciones bloqueadas'}
          </button>
          <span class="v2-muted">el sistema la frenó — no es una falla</span>
        {:else}
          <b>0</b> acciones bloqueadas
          <span class="v2-muted">el sistema la frenó — no es una falla</span>
        {/if}
      </li>
      <li class:diag-hay={diagnostico.errores > 0}>
        <CircleX size={14} style="color:var(--v2-rust);flex:none" />
        {#if diagnostico.errores > 0}
          <button type="button" class="diag-ir" onclick={() => onIrAlPaso?.('error')}>
            <b>{diagnostico.errores}</b>
            {diagnostico.errores === 1 ? 'error' : 'errores'} en herramienta
          </button>
          <span class="v2-muted">falló un sistema externo</span>
        {:else}
          <b>0</b> errores en herramienta
          <span class="v2-muted">falló un sistema externo</span>
        {/if}
      </li>
      {/if}
    </ul>
  {/if}

  <ol class="proceso-lista">
    {#each herramientas as h, i}
      <li
        class="proceso-item"
        class:bloqueada={h.es_bloqueo}
        class:paso-marcado={pasoMarcado === i}
        data-paso={i}
      >
        {#if h.es_bloqueo}
          <ShieldCheck size={15} style="color:var(--v2-clay);flex:none" />
        {:else if h.exito}
          <CircleCheck size={15} style="color:var(--v2-moss);flex:none" />
        {:else}
          <CircleX size={15} style="color:var(--v2-rust);flex:none" />
        {/if}
        <span class="proceso-nombre">{h.herramienta}</span>
        {#if h.n_registros !== null}
          <span class="v2-muted">{h.n_registros} resultado{h.n_registros === 1 ? '' : 's'}</span>
        {/if}
        {#if h.es_bloqueo}
          <!-- El motivo en palabras, no el codigo: el codigo queda en el
               title para quien depure, pero lo que se lee dice que hacer. -->
          <span class="v2-muted" title={h.codigo_error}>
            {motivoBloqueo[h.codigo_error] ?? 'el sistema frenó esta acción'}
          </span>
        {:else if h.codigo_error}
          <span class="v2-muted" title={h.codigo_error}>{h.codigo_error.split(':')[0]}</span>
        {/if}
        <span class="v2-muted proceso-duracion">{h.duracion_ms} ms</span>
      </li>
    {/each}
  </ol>
  </details>
  {:else}
  <!-- Sin traza el panel entero desaparecia, y la columna quedaba con dos
       controles sueltos y un hueco: se lee como una pantalla rota, no como
       "no hay nada que mostrar". Es el caso normal de una conversacion que
       el asistente resolvio hablando, sin consultar ningun sistema. -->
  <p class="proceso-vacio">
    El asistente no consultó ningún sistema en esta conversación.
  </p>
  {/if}

<style>
  .proceso {
    padding: 14px 0 0;
  }

  /* El resaltado del paso al que se salto. Se apaga solo. */
  .paso-marcado {
    background: var(--v2-ember-soft);
    border-radius: 6px;
    padding-left: 6px;
    padding-right: 6px;
  }

  .proceso-resumen {
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
    user-select: none;
  }

  .proceso-resumen .v2-muted {
    font-weight: 400;
  }

  .proceso-lista {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  /* NADA de esta columna puede provocar scroll horizontal. Un nombre de
     herramienta largo mas un mensaje de error entero (ErrorHerramientaHttp:
     400 Client Error for url...) empujaban la fila fuera de su columna, y
     aparecia una barra horizontal abajo.

     'min-width: 0' en el item Y en el nombre: sin lo primero, un hijo flex
     se niega a encogerse por debajo de su contenido y el ellipsis del hijo
     nunca llega a aplicarse. Es la causa mas comun de esto y no se ve
     leyendo el CSS del hijo. */
  .proceso-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    padding: 4px 0;
    min-width: 0;
  }

  .proceso-nombre {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--v2-mono, monospace);
  }

  /* El tiempo conserva su columna a la derecha pase lo que pase: es lo que
     se compara de un vistazo entre pasos. */
  .proceso-duracion {
    margin-left: auto;
    flex: none;
  }

  /* El resto encoge antes que el nombre y el tiempo. El texto completo del
     error sigue en el 'title'. */
  .proceso-item > .v2-muted:not(.proceso-duracion) {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .proceso-lista {
    min-width: 0;
  }

  .proceso-vacio {
    margin: 0;
    font-size: 12px;
    color: var(--v2-slate);
  }


  /* Diagnostico: tres lineas, no tres tarjetas. Es una lectura de dos
     segundos dentro de un panel plegable, no un tablero. */
  .diag {
    list-style: none;
    margin: 10px 0 0;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    font-size: 12.5px;
    border: 1px solid var(--v2-line);
    border-radius: 6px;
  }

  .diag li {
    display: flex;
    align-items: center;
    gap: 7px;
  }

  .diag b {
    font-variant-numeric: tabular-nums;
    min-width: 1.2em;
    text-align: right;
  }

  /* Un renglon con algo pesa mas que uno en cero. Cero bloqueadas y cero
     errores es la noticia buena y no tiene por que competir. */
  .diag-hay {
    font-weight: 600;
  }

  .diag-ir {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 0;
    background: none;
    font: inherit;
    color: inherit;
    padding: 2px 4px;
    margin: -2px -4px;
    border-radius: 5px;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .diag-ir:hover {
    background: var(--v2-line-soft);
  }

  .diag-ir:focus-visible {
    outline: 2px solid var(--v2-ember);
    outline-offset: 1px;
  }


  /* Los dos avisos del titulo cerrado. Sin borde de color al costado: se
     distinguen por el texto y el tono del fondo, que es lo que se lee. */
  .diag-aviso {
    font-size: 11px;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: 999px;
    white-space: nowrap;
  }

  .diag-error {
    color: var(--v2-rust);
    background: color-mix(in srgb, var(--v2-rust) 12%, transparent);
  }

  .diag-bloqueo {
    color: var(--v2-clay);
    background: color-mix(in srgb, var(--v2-clay) 14%, transparent);
  }

  /* Un bloqueo no es un fallo: se distingue del resto de la lista, pero sin
     la carga visual de un error. */
  .proceso-item.bloqueada .proceso-nombre {
    color: var(--v2-clay);
  }
</style>
