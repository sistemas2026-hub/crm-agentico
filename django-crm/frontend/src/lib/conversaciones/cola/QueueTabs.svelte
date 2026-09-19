<script>
  /**
   * Las cuatro pestañas de estado de la cola, con su contador.
   *
   * NO DECIDE NADA. `irA()` se queda en el layout porque cambia tres cosas a
   * la vez -- la pestaña, el orden que le corresponde a esa pestaña y la
   * marca de "el orden lo eligió una persona" -- y ese acople es del dueño de
   * la lista, no de una barra de botones.
   *
   * Nunca ember en la pestaña activa: "dónde estoy" no es una acción. El
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
        {t.label}
        <span class="tab-n v2-num" class:urge={t.urge && t.n > 0}>{t.n}</span>
      </button>
    {/each}
  </nav>

<style>


  /* ── pestañas + buscador ────────────────────────────────────────────── */
  /* MEDIDO el 07/09/2026: el contenido pedia 396px en 329 disponibles, y
     "Todas" se dibujaba 66px POR ENCIMA de la columna del chat. Lo mismo a
     1440, 1280 y 1100 -- no era un problema de pantalla chica: la barra no
     era responsive en absoluto.
     
     Se arregla en tres pasos, en este orden:
       1. repartir el espacio (flex:1 con min-width:0 en cada pestaña)
       2. menos padding lateral y el numero pegado al texto
       3. si aun asi no entra, desplazamiento horizontal DENTRO de la barra
     
     El tercero es la red: pase lo que pase con los numeros --169 puede ser
     16.900-- la barra scrollea y NUNCA se sale de su columna. 'overflow-x'
     necesita 'min-width: 0' en el contenedor flex o no recorta nada. */
  .tabs {
    display: flex;
    align-items: stretch;
    gap: 1px;
    padding: 8px 6px 0;
    border-bottom: 1px solid var(--bandeja-borde);
    flex: none;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  .tab {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    /* Reparten el ancho en vez de tomar cada una lo que necesita. */
    flex: 1 1 auto;
    min-width: 0;
    padding: 7px 4px 8px;
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    font: inherit;
    font-size: 11.8px;
    font-weight: 550;
    color: var(--v2-slate);
    cursor: pointer;
    white-space: nowrap;
  }

  .tab:hover {
    color: var(--bandeja-texto);
  }

  /* Activa = peso y el azul de "acá estás vos". El filete inferior es la
     misma señal que usa el diseño congelado. */
  .tab[aria-current='true'] {
    color: var(--bandeja-humano);
    font-weight: 640;
    border-bottom-color: var(--bandeja-humano);
  }

  /* El numero es parte de la pestaña, no una pildora aparte flotando al lado:
     sin fondo propio, mismo color que su texto, y solo se separa por el peso.
     Asi las cuatro se leen como cuatro unidades y no como ocho elementos. */
  .tab-n {
    font-family: var(--bandeja-mono);
    font-size: 10.5px;
    font-weight: 650;
    color: inherit;
    opacity: 0.62;
    font-variant-numeric: tabular-nums;
  }

  /* La activa destaca su numero; las inactivas lo dejan neutro. */
  .tab[aria-current='true'] .tab-n {
    opacity: 1;
  }

  /* El unico numero con color propio, y NO es el azul de la pestaña activa:
     trabajo que espera a alguien es una ALARMA, no algo que se pulsa ni el
     lugar donde estás parado. */
  .tab-n.urge {
    color: var(--bandeja-error);
    opacity: 1;
  }
</style>
