<script>
  /**
   * Qué hizo la IA, paso por paso, sacado de la traza real.
   *
   * No hay puntajes ni confianza del modelo acá: eso no existe en Dexter. Lo
   * que se muestra son las herramientas que efectivamente se llamaron, con su
   * resultado, y el diagnóstico que dejó el motor.
   */
  import { CircleCheck, CircleX, ShieldCheck, ChevronDown } from '@lucide/svelte';

  let {
    herramientas = [], diagnostico, contrasteUtil = false,
    pasoMarcado = null, motivoBloqueo = {}, onIrAlPaso
  } = $props();

  /* LA DURACION EN SEGUNDOS, como la referencia («ok 0.4s»). En milisegundos
     --como estaba-- un numero de cuatro cifras al lado de otro de dos no se
     compara de un vistazo, y lo que se busca en esta lista es justamente cual
     paso tardo. Por debajo de 100 ms se dice «<0.1s» en vez de «0.0s», que
     parece un dato que no se midio. */
  const duracion = (/** @type {number|null} */ ms) => {
    if (ms === null || ms === undefined) return '—';
    if (ms < 100) return '<0.1s';
    return `${(ms / 1000).toFixed(1)}s`;
  };
</script>

<!-- ══════════════════════════════════════════════════════════════════════════
     «AI PROCESS», con los datos de la traza real

     Referencia: la pestaña Tools de las pantallas de contexto. La forma es la
     suya -- tarjeta con cabecera, tira de contadores y pasos numerados con su
     duración a la derecha.

     LO QUE NO SE COPIA es el párrafo de prosa que la referencia pone arriba
     («Automated loop detected physical layer disruption at Belgrano node...»).
     Ese texto es un resumen narrado del diagnóstico, y Dexter no lo produce:
     la traza tiene qué herramienta corrió, con qué resultado y en cuánto
     tiempo, no una redacción. Escribirlo acá sería inventarlo; los tres
     contadores dicen lo mismo con lo que sí se midió.
     ══════════════════════════════════════════════════════════════════════════ -->

{#if herramientas.length > 0}
  <!-- Abierto de entrada SOLO si hubo un bloqueo o un error. Si todo corrió
       normal el panel es secundario y no tiene por qué ocupar la columna;
       cuando algo se frenó o se rompió, el hallazgo tiene que estar a la
       vista sin que nadie sospeche primero -- que es justo lo que no pasa con
       un panel plegado que casi nadie abre. -->
  <details
    class="panel-tarjeta proceso"
    open={!!(diagnostico?.bloqueadas || diagnostico?.errores)}
  >
    <summary class="panel-tarjeta-cabeza proceso-cabeza">
      <span class="panel-titulo">Proceso de la IA</span>
      <span class="proceso-cabeza-fin">
        <!-- Lo único que se asoma con el panel cerrado. El resto de la traza
             se mira cuando hay una sospecha; un bloqueo o un fallo hay que
             verlo ANTES, porque cambia lo que quien atiende tiene que hacer. -->
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
        <ChevronDown size={14} class="proceso-flecha" />
      </span>
    </summary>

    <!-- ── LA TIRA DE CONTADORES ──────────────────────────────────────────
         Tres números en una línea, en mono y dentro de un recuadro, como la
         referencia. Antes eran tres renglones con icono y una frase cada uno:
         nueve palabras para decir «5 · 1 · 0», en una columna de 350px.

         La frase no se pierde del todo -- vive en el `title` de cada
         contador--, porque «bloqueada» no significa lo mismo que «error» y esa
         distinción es la razón de que sean dos contadores y no uno. -->
    {#if diagnostico}
      <div class="tira">
        <span class="tira-par" title="Herramientas que corrieron y devolvieron datos">
          <span class="tira-rotulo">pasos</span>
          <b>{diagnostico.normales + (diagnostico.bloqueadas ?? 0) + (diagnostico.errores ?? 0)}</b>
        </span>
        <span class="tira-sep" aria-hidden="true">·</span>
        <!-- Con cero, sólo el número. Con uno o más, un BOTÓN que lleva al
             paso: el número contesta «pasó algo», y lo siguiente que se
             quiere es ver QUÉ, sin buscarlo entre catorce líneas. -->
        <span
          class="tira-par"
          class:tira-hay={diagnostico.bloqueadas > 0}
          title="El sistema la frenó — no es una falla"
        >
          <span class="tira-rotulo">bloqueadas</span>
          {#if diagnostico.bloqueadas > 0}
            <button type="button" class="tira-ir" onclick={() => onIrAlPaso?.('bloqueo')}>
              {diagnostico.bloqueadas}
            </button>
          {:else}
            <b>0</b>
          {/if}
        </span>
        <span class="tira-sep" aria-hidden="true">·</span>
        <span
          class="tira-par"
          class:tira-mal={diagnostico.errores > 0}
          title="Falló un sistema externo"
        >
          <span class="tira-rotulo">errores</span>
          {#if diagnostico.errores > 0}
            <button type="button" class="tira-ir" onclick={() => onIrAlPaso?.('error')}>
              {diagnostico.errores}
            </button>
          {:else}
            <b>0</b>
          {/if}
        </span>
      </div>
    {/if}

    <!-- ── LOS PASOS ──────────────────────────────────────────────────────
         Numerados, con el estado a la izquierda y la duración a la derecha.
         El número importa: la referencia dice «Jump to step 4» y sin un
         número visible ese salto no se puede seguir con el ojo. -->
    <ol class="proceso-lista">
      {#each herramientas as h, i}
        <li
          class="proceso-item"
          class:bloqueada={h.es_bloqueo}
          class:fallada={!h.es_bloqueo && !h.exito}
          class:paso-marcado={pasoMarcado === i}
          data-paso={i}
        >
          <span class="proceso-n v2-num">{i + 1}</span>
          {#if h.es_bloqueo}
            <ShieldCheck size={14} style="color:var(--bandeja-aviso);flex:none" />
          {:else if h.exito}
            <CircleCheck size={14} style="color:var(--bandeja-ok);flex:none" />
          {:else}
            <CircleX size={14} style="color:var(--bandeja-error);flex:none" />
          {/if}
          <span class="proceso-nombre">{h.herramienta}</span>
          <span class="proceso-duracion v2-num">{duracion(h.duracion_ms)}</span>

          {#if h.es_bloqueo}
            <!-- El motivo en palabras, no el código: el código queda en el
                 title para quien depure, pero lo que se lee dice qué hacer. -->
            <span class="proceso-sub" title={h.codigo_error}>
              {motivoBloqueo[h.codigo_error] ?? 'el sistema frenó esta acción'}
            </span>
          {:else if h.codigo_error}
            <span class="proceso-sub" title={h.codigo_error}>
              {h.codigo_error.split(':')[0]}
            </span>
          {:else if h.n_registros !== null}
            <span class="proceso-sub">
              {h.n_registros} resultado{h.n_registros === 1 ? '' : 's'}
            </span>
          {/if}
        </li>
      {/each}
    </ol>
  </details>
{:else}
  <!-- Sin traza el panel entero desaparecía, y la columna quedaba con dos
       controles sueltos y un hueco: se lee como una pantalla rota, no como
       «no hay nada que mostrar». Es el caso normal de una conversación que el
       asistente resolvió hablando, sin consultar ningún sistema. -->
  <div class="panel-tarjeta">
    <div class="panel-tarjeta-cabeza">
      <span class="panel-titulo">Proceso de la IA</span>
      <span class="panel-marca">sin pasos</span>
    </div>
    <p class="proceso-vacio">
      El asistente no consultó ningún sistema en esta conversación.
    </p>
  </div>
{/if}

<style>
  /* La tarjeta y su cabecera salen de `bandeja.css`: son las mismas que usan
     Equipo y Caso. Acá sólo lo propio del proceso. */
  .proceso {
    margin-bottom: 10px;
  }

  .proceso-cabeza {
    cursor: pointer;
    list-style: none;
    user-select: none;
  }
  .proceso-cabeza::-webkit-details-marker {
    display: none;
  }

  .proceso-cabeza-fin {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: none;
    color: var(--bandeja-texto-3);
  }

  /* La flecha gira al abrir. Es el único indicio de que la tarjeta se
     despliega, así que no puede faltar cuando está cerrada. */
  .proceso :global(.proceso-flecha) {
    transition: transform 0.15s ease;
  }
  .proceso[open] :global(.proceso-flecha) {
    transform: rotate(180deg);
  }

  /* ── la tira de contadores ─────────────────────────────────────────────
     Un recuadro con los tres números en mono, como la referencia. El rótulo
     va en minúscula y apagado: lo que se lee es la cifra. */
  .tira {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
    padding: 5px 8px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
    font-family: var(--bandeja-mono);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }

  .tira-par {
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    color: var(--bandeja-texto);
  }

  .tira-rotulo {
    color: var(--bandeja-texto-2);
  }

  .tira-sep {
    color: var(--bandeja-borde-fuerte);
  }

  /* Un contador en cero no se pinta: el color tiene que significar «pasó
     algo», y si «0 errores» sale en rojo deja de decir nada. */
  .tira-hay {
    color: var(--bandeja-aviso);
  }
  .tira-mal {
    color: var(--bandeja-error);
  }

  /* El número es el control: se salta al paso desde la cifra, que es lo que
     se está mirando. Un botón aparte al lado repetiría el dato. */
  .tira-ir {
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    font-weight: 700;
    color: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .tira-ir:hover {
    text-decoration-thickness: 2px;
  }
  .tira-ir:focus-visible {
    outline: 2px solid var(--bandeja-humano);
    outline-offset: 2px;
    border-radius: 2px;
  }

  /* ── los pasos ─────────────────────────────────────────────────────────
     Rejilla de tres columnas --número, icono, nombre-- más la duración a la
     derecha. El subtexto ocupa una segunda fila alineada con el nombre, no
     con el número: se lee como una aclaración del paso, no como otro paso. */
  .proceso-lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .proceso-item {
    display: grid;
    grid-template-columns: 14px 14px 1fr auto;
    align-items: center;
    gap: 2px 7px;
    padding: 4px 5px;
    border-radius: 3px;
    border-left: 2px solid transparent;
    font-size: 12px;
  }

  .proceso-n {
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-3);
    text-align: right;
  }

  .proceso-nombre {
    min-width: 0;
    color: var(--bandeja-texto);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .proceso-duracion {
    font-family: var(--bandeja-mono);
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-3);
    white-space: nowrap;
  }

  /* Segunda fila, bajo el nombre: empieza en la tercera columna. */
  .proceso-sub {
    grid-column: 3 / -1;
    font-size: 10.5px;
    line-height: 1.35;
    color: var(--bandeja-texto-2);
  }

  /* UN PASO FRENADO NO ES UN PASO FALLADO, y por eso son dos tratamientos.
     El bloqueo es el sistema haciendo su trabajo --ámbar, que en esta paleta
     es «pide atención»-- y el error es algo roto del otro lado. Pintarlos
     igual haría que quien mira concluya que el asistente se rompió cuando en
     realidad se contuvo. */
  .proceso-item.bloqueada {
    background: var(--bandeja-aviso-fondo);
    border-left-color: var(--bandeja-aviso-borde);
  }
  .proceso-item.bloqueada .proceso-nombre {
    font-weight: 600;
    color: var(--bandeja-aviso);
  }
  .proceso-item.bloqueada .proceso-sub {
    color: var(--bandeja-aviso);
  }

  .proceso-item.fallada {
    background: var(--bandeja-error-fondo);
    border-left-color: var(--bandeja-error-borde);
  }
  .proceso-item.fallada .proceso-nombre {
    font-weight: 600;
    color: var(--bandeja-error);
  }

  /* Al saltar desde un contador, el paso se marca un momento: sin eso el
     salto deja el ojo en el lugar correcto sin decir cuál de los renglones
     era. */
  .paso-marcado {
    outline: 2px solid var(--bandeja-humano);
    outline-offset: 1px;
  }

  .proceso-vacio {
    margin: 0;
    font-size: 12px;
    line-height: 1.45;
    color: var(--bandeja-texto-2);
  }

  /* Lo que se asoma con la tarjeta cerrada. */
  .diag-aviso {
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    white-space: nowrap;
  }
  .diag-error {
    background: var(--bandeja-error-fondo);
    border-color: var(--bandeja-error-borde);
    color: var(--bandeja-error);
  }
  .diag-bloqueo {
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
    color: var(--bandeja-aviso);
  }
</style>
