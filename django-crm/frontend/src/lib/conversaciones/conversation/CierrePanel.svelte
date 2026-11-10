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
  <h3 class="titulo" id="cierre-titulo">¿En qué terminó?</h3>
  <p class="instruccion">Elegí qué le pasaba al cliente. Con esto se cuenta dónde fallamos más.</p>

  {#if errorCatalogo}
    <p class="aviso-mal">{errorCatalogo}</p>
  {/if}

  {#each grupos as g (g.clave)}
    <fieldset class="grupo">
      {#if g.titulo}<legend class="grupo-titulo">{g.titulo}</legend>{/if}
      <div class="opciones">
        {#each g.desenlaces as d (d.codigo)}
          {@const categoria = categoriaVisible(d)}
          <label class="opcion" class:elegida={codigo === d.codigo}>
            <input type="radio" name="desenlace" value={d.codigo} bind:group={codigo} />
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
        class="v2-btn v2-btn-sm v2-btn-ink"
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
  .cierre {
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
    padding: 14px 16px;
    margin-top: 10px;
    background: var(--bandeja-superficie-suave);
  }
  .titulo {
    margin: 0;
    font-size: 15px;
    font-weight: 650;
  }
  .instruccion {
    margin: 2px 0 14px;
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
    padding: 0;
    margin-bottom: 6px;
    font-size: 11.5px;
    font-weight: 600;
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
    padding: 5px 10px 5px 8px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    font-size: 12.5px;
    line-height: 1.3;
    cursor: pointer;
  }
  .opcion input {
    margin: 0;
    accent-color: var(--bandeja-humano);
  }
  .opcion:hover {
    border-color: var(--bandeja-texto-3);
  }
  /* Elegida: borde, fondo y texto a la vez. Con solo un fondo apenas más
     claro, la única señal era el punto de la radio. */
  .opcion.elegida {
    border-color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
    color: var(--bandeja-humano);
    font-weight: 600;
  }
  .opcion:has(input:focus-visible) {
    outline: 2px solid var(--bandeja-humano);
    outline-offset: 1px;
  }
  .categoria {
    font-size: 11.5px;
    font-weight: 400;
    color: var(--bandeja-texto-2);
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
