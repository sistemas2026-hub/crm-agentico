<script>
  /**
   * Los cuatro estados de la cola, como bloques con su contador.
   *
   * NO DECIDE NADA. `irA()` se queda en el layout porque cambia tres cosas a
   * la vez -- la pestaña, el orden que le corresponde a esa pestaña y la
   * marca de "el orden lo eligió una persona" -- y ese acople es del dueño de
   * la lista, no de una barra de botones.
   *
   * POR QUÉ BLOQUES Y NO UNA FILA DE PESTAÑAS
   * -----------------------------------------
   * La referencia abre la columna con tres recuadros --NEEDS ATTN / IN
   * PROGRESS / RESOLVED-- y el número grande adentro. Acá era una fila de
   * cuatro pestañas con el número en chico al lado del texto: la misma
   * información, pero el número --que es lo que se mira de reojo para saber
   * cuánto trabajo hay-- pesaba menos que su propia etiqueta.
   *
   * La referencia además DUPLICA el control: tiene los tres recuadros Y
   * debajo las pestañas con los mismos cuatro filtros. Acá no se copia esa
   * parte: dos controles para lo mismo, uno encima del otro, es algo que
   * alguien tiene que mantener sincronizado para siempre. Los bloques SON el
   * selector.
   *
   * Nunca ember en el bloque activo: "dónde estoy" no es una acción. El
   * contador de "Por atender" sí lo lleva, porque ese número es trabajo sin
   * tomar.
   */
  let { pestanas = [], filtro = '', onIr } = $props();
</script>

<nav class="tabs" aria-label="Filtrar por estado">
  {#each pestanas as t (t.id)}
    <button
      type="button"
      class="tab"
      aria-current={filtro === t.id ? 'true' : undefined}
      onclick={() => onIr(t.id)}
    >
      <span class="tab-rotulo">{t.label}</span>
      <span class="tab-n v2-num" class:urge={t.urge && t.n > 0}>{t.n}</span>
    </button>
  {/each}
</nav>

<style>
  /* MEDIDO el 07/09/2026: el contenido pedia 396px en 329 disponibles, y
     "Todas" se dibujaba 66px POR ENCIMA de la columna del chat. Lo mismo a
     1440, 1280 y 1100 -- no era un problema de pantalla chica: la barra no
     era responsive en absoluto.

     Se arregla en tres pasos, en este orden:
       1. repartir el espacio (flex:1 con min-width:0 en cada bloque)
       2. menos padding lateral
       3. si aun asi no entra, desplazamiento horizontal DENTRO de la barra

     El tercero es la red: pase lo que pase con los numeros --169 puede ser
     16.900-- la barra scrollea y NUNCA se sale de su columna. 'overflow-x'
     necesita 'min-width: 0' en el contenedor flex o no recorta nada. */
  .tabs {
    display: flex;
    align-items: stretch;
    gap: 5px;
    padding: 8px 8px;
    border-bottom: 1px solid var(--bandeja-borde);
    flex: none;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  /* El bloque: recuadro, rótulo arriba y número abajo. El número es lo que se
     lee de reojo, así que es lo más grande de la caja. */
  .tab {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    /* `1 1 auto` y no `1 1 0`: con anchos iguales los cuatro miden 71px y
       "POR ATENDER" pide 60 más 14 de padding -- se recortaba a "POR ATEN…".
       Cada bloque toma lo que su rótulo necesita y el sobrante se reparte
       (202px de texto + padding + huecos = 273 de 304). */
    flex: 1 1 auto;
    min-width: 0;
    padding: 5px 7px 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    cursor: pointer;
    text-align: left;
  }

  .tab:hover {
    border-color: var(--bandeja-texto-3);
    background: var(--bandeja-superficie-suave);
  }

  /* Activo = el azul de "acá estás vos", en el borde y en el fondo. */
  .tab[aria-current='true'] {
    border-color: var(--bandeja-humano-borde);
    background: var(--bandeja-humano-fondo);
  }

  /* El rótulo es rótulo: mono en versalita, como en toda la Bandeja. A 8.5px
     porque "En atención" tiene que entrar en un cuarto de 304px. */
  .tab-rotulo {
    font-family: var(--bandeja-mono);
    font-size: 8.5px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .tab[aria-current='true'] .tab-rotulo {
    color: var(--bandeja-humano);
  }

  .tab-n {
    font-family: var(--bandeja-mono);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--bandeja-texto);
    font-variant-numeric: tabular-nums;
  }

  .tab[aria-current='true'] .tab-n {
    color: var(--bandeja-humano);
  }

  /* El unico numero con color propio, y NO es el azul del bloque activo:
     trabajo que espera a alguien es una ALARMA, no algo que se pulsa ni el
     lugar donde estás parado. */
  .tab-n.urge {
    color: var(--bandeja-error);
  }

  .tab[aria-current='true'] .tab-n.urge {
    color: var(--bandeja-error);
  }
</style>
