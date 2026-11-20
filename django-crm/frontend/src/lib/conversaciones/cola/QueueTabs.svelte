<script>
  /**
   * La cabeza de la cola: una frase que dice cuánto trabajo hay, y debajo las
   * pestañas que lo separan.
   *
   * NO DECIDE NADA. `irA()` se queda en el layout porque cambia tres cosas a
   * la vez -- la pestaña, el orden que le corresponde a esa pestaña y la
   * marca de "el orden lo eligió una persona" -- y ese acople es del dueño de
   * la lista, no de una barra de botones. La frase y los números llegan
   * calculados (`cola/pestanas.js`).
   *
   * POR QUÉ UNA FRASE Y NO CUATRO CUADROS  (04/11/2026)
   * ---------------------------------------------------
   * Eran cuatro cajas del mismo peso, y lo único que se mira de reojo al
   * llegar es UNA cosa: cuánto espera y desde cuándo. Cuatro números iguales
   * obligan a leer los cuatro para encontrarlo. La frase lo dice entero
   * («20 por atender · la más antigua espera 2 h») y las pestañas pasan a ser
   * lo que son: un selector, chico.
   *
   * Los cuadros además no sumaban (20 + 2 + 17 sobre 50): faltaba «Lleva la
   * IA». Ahora está, y cuando igual no cierra -- un chat con dos abiertas en
   * estados distintos cuenta en las dos -- se dice en una línea, en vez de
   * dejar que parezca un error de cuenta.
   *
   * El rojo es solo de la cifra, y solo si hay alguna crítica: el mismo
   * criterio que la «Espera máx.» de la barra de consola, para que las dos no
   * digan cosas distintas del mismo número.
   */
  let {
    pestanas = [],
    filtro = '',
    onIr,
    /** {cifra, texto, espera} de `titularDeCola()`. */
    titular = { cifra: null, texto: '', espera: null },
    /** Hay al menos una que espera en el tramo crítico. */
    critico = false,
    /** Las cuatro primeras suman el total. */
    cierra = true
  } = $props();
</script>

<section class="cabeza-cola" aria-label="Estado de la cola">
  <p class="titular">
    {#if titular.cifra !== null}
      <span class="b-cifra cifra" class:cifra-critica={critico}>{titular.cifra}</span>
      {titular.texto}{#if titular.espera}<span class="sep" aria-hidden="true"> · </span
        ><span class="titular-espera">{titular.espera}</span>{/if}
    {:else}
      {titular.texto}
    {/if}
  </p>

  <nav class="tabs" aria-label="Filtrar por estado">
    {#each pestanas as t (t.id)}
      <button
        type="button"
        class="tab"
        aria-current={filtro === t.id ? 'true' : undefined}
        title={t.titulo}
        onclick={() => onIr(t.id)}
      >
        {t.label}<span class="b-cifra tab-n">{t.n}</span>
      </button>
    {/each}
  </nav>

  {#if !cierra}
    <p class="b-rotulo no-cierra">Un chat con dos conversaciones abiertas cuenta en dos pestañas.</p>
  {/if}
</section>

<style>
  .cabeza-cola {
    flex: none;
    padding: 12px 12px 8px;
  }

  /* La frase es lo más grande de la columna después de los nombres: es lo
     que se lee al llegar al turno. */
  .titular {
    margin: 0 0 8px;
    font-family: var(--bandeja-titulo);
    font-size: 18px;
    font-weight: 600;
    line-height: 1.25;
    color: var(--bandeja-texto);
  }

  .cifra-critica {
    color: var(--bandeja-error);
  }

  /* La espera es la segunda mitad de la frase, no un título aparte: mismo
     tamaño, un gris más abajo, para que la cifra mande. */
  .titular-espera,
  .sep {
    color: var(--bandeja-texto-2);
    font-weight: 500;
  }

  /* MEDIDO el 07/09/2026: la barra pedía 396px en 329 disponibles y «Todas»
     se dibujaba POR ENCIMA de la columna del chat. Con cinco pestañas sigue
     pudiendo pasar en una columna angosta, así que la red queda: si no
     entra, se desplaza DENTRO de la barra y nunca se sale de su columna.
     'overflow-x' necesita 'min-width: 0' en el contenedor flex o no recorta. */
  .tabs {
    display: flex;
    gap: 2px;
    padding: 2px;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio);
    background: var(--bandeja-superficie-suave);
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  /* Un segmento: el rótulo escrito normal y la cifra DEBAJO, no al lado.
     MEDIDO el 04/11/2026 con las fuentes cargadas, en la columna de 360px:
     en una línea las cinco piden 421px contra 334 (y 386 aun en Barlow 13px
     con 4px de aire) -- «Todos» y media «Resueltas» quedaban fuera de la
     vista. Apiladas piden 323 y entran las cinco; cuesta 13px de alto, que
     es menos que esconder una pestaña detrás de un desplazamiento. Toma lo
     que su texto pide y el sobrante se reparte para llenar el ancho. */
  .tab {
    flex: 1 0 auto;
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    padding: 4px;
    line-height: 1.2;
    border: 1px solid transparent;
    border-radius: var(--bandeja-radio-sm);
    background: none;
    font-family: var(--bandeja-sans);
    font-size: 12px;
    color: var(--bandeja-texto-2);
    white-space: nowrap;
    cursor: pointer;
  }

  .tab:hover {
    color: var(--bandeja-texto);
  }

  /* Activo = blanco y borde, como un segmento elegido. Nunca rojo: "dónde
     estoy" no es una alarma ni una acción. Sin cambiar el peso: la negrita
     ensancha el rótulo y la tira entera saltaría al cambiar de pestaña. */
  .tab[aria-current='true'] {
    background: var(--bandeja-superficie);
    border-color: var(--bandeja-borde);
    color: var(--bandeja-texto);
  }

  .tab-n {
    font-size: 13px;
    color: var(--bandeja-texto);
  }

  .no-cierra {
    margin: 4px 0 0;
  }
</style>
