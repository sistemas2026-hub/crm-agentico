<script>
  /**
   * Las cinco pestañas de la columna de contexto.
   *
   * POR QUÉ EXISTEN
   * ---------------
   * Hasta el 21/09/2026 la columna derecha apilaba los diez paneles uno debajo
   * del otro: Cliente, Caso, Asignados, Acciones, Sincronización, Equipo,
   * Actividad, Retención, Proceso de la IA y Documentación. Todo estaba, y
   * nada se encontraba: para llegar a la traza había que pasar por delante de
   * otras ocho secciones, y la altura de la columna dependía de cuánto
   * contexto tuviera la conversación.
   *
   * La referencia congelada (`SPEC/BANDEJA_STITCH_REFERENCIAS.md`) tiene una
   * pantalla canónica POR PESTAÑA --Customer, Network, Case, Activity, Tools--
   * y cada una nombra su `Pestaña:` en el manifiesto. O sea que las pestañas no
   * son una decoración del diseño: son la forma en que la referencia organiza
   * esta columna, y apilada nunca se iba a parecer.
   *
   * NO SE INVENTA NINGUNA. Los diez paneles ya existían y siguen montados; lo
   * único que cambia es en cuál de las cinco vive cada uno. El reparto está
   * escrito en `+page.svelte`, al lado de los paneles, que es donde se puede
   * verificar de un vistazo.
   *
   * EL CONTADOR NO ES ADORNO
   * ------------------------
   * Meter algo en una pestaña lo esconde. Para lo que pide una acción --una
   * propuesta esperando aprobación-- eso sería un retroceso: antes estaba a la
   * vista aunque fuera al costado. Por eso la pestaña que lo contiene lleva el
   * número, y así se ve sin abrirla. Es el mismo criterio que la cola usa en
   * sus propias pestañas.
   */
  let {
    /** [{ id, etiqueta, cuenta? }] — las arma la página, que es la que sabe
        qué hay adentro de cada una. */
    pestanas = [],
    activa = '',
    onIr
  } = $props();
</script>

<nav class="ctx-tabs" aria-label="Contexto de la conversación">
  {#each pestanas as p (p.id)}
    <button
      type="button"
      class="ctx-tab"
      class:ctx-tab-activa={p.id === activa}
      aria-current={p.id === activa ? 'true' : undefined}
      onclick={() => onIr?.(p.id)}
    >
      {p.etiqueta}
      {#if p.cuenta}<span class="ctx-cuenta">{p.cuenta}</span>{/if}
    </button>
  {/each}
</nav>

<style>
  /* Pegada arriba: la columna scrollea debajo de ella, así que al bajar por la
     traza las otras cuatro siguen a un clic. */
  .ctx-tabs {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    flex: none;
    background: var(--bandeja-superficie);
    border-bottom: 1px solid var(--bandeja-borde);
  }

  /* 04/11/2026: Barlow 14px 600, escrito normal, como los títulos de
     sección de los paneles. Eran 12px / 500 en la letra del texto (los
     valores medidos de la referencia) y las pestañas se leían como un rótulo
     más; ahora tienen el mismo peso que el título de lo que abren. Barlow es
     condensada: a 14px las cinco palabras miden menos que a 12px en Atkinson,
     así que entran en la columna sin recortarse. */
  /* `flex: 1 1 auto` y NO `1 1 0`: con anchos iguales las cinco miden 61px y
     "Actividad" pide 70 -- se recortaba (medido). Cada pestaña toma lo que su
     palabra necesita y el sobrante se reparte, así que ninguna se corta
     mientras las cinco entren en la columna. */
  .ctx-tab {
    flex: 1 1 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 8px 4px;
    border: 0;
    /* El subrayado de la activa se dibuja acá, transparente, para que la
       pestaña no cambie de alto al activarse. */
    border-bottom: 2px solid transparent;
    background: none;
    font-family: var(--bandeja-titulo);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0;
    text-transform: none;
    color: var(--bandeja-texto-2);
    cursor: pointer;
    white-space: nowrap;
  }

  .ctx-tab:hover {
    color: var(--bandeja-texto);
    background: var(--bandeja-superficie-suave);
  }

  /* 04/11/2026: en marino (`--bandeja-accion`), no en el azul eléctrico de
     `--bandeja-humano`. Ese azul significa «lo hizo una persona» en toda la
     Bandeja, y una pestaña activa no dice eso: dice dónde estás. */
  .ctx-tab-activa {
    color: var(--bandeja-accion);
    border-bottom-color: var(--bandeja-accion);
  }

  .ctx-tab:focus-visible {
    outline: 2px solid var(--bandeja-accion);
    outline-offset: -2px;
  }

  .ctx-tab-activa:hover {
    background: none;
  }

  /* ── EL DEDO ────────────────────────────────────────────────────────────
     Debajo de 1000px la Bandeja ya pasó a master-detail (una vista por vez,
     ver el layout), que es el punto donde se la usa con el dedo y no con un
     puntero. Con `padding: 8px` y texto de 14px la pestaña mide unos 36px de
     alto: entra dentro del rango en que un toque cae en la pestaña de al
     lado. La referencia móvil pide 44px como mínimo y es el mismo número que
     recomiendan las guías de las dos plataformas.

     Se fija con `min-height` y no con más padding para que el alto sea el que
     se declara, sin depender de cuánto mida la línea de texto. */
  @media (max-width: 1000px) {
    .ctx-tab {
      min-height: 44px;
    }
  }

  /* El número de lo que espera adentro. 04/11/2026: en Barlow tabular como
     el resto de las cifras de la Bandeja (`.b-cifra`); el mono a 9,5px quedaba
     más chico que la palabra de al lado y había que buscarlo. */
  .ctx-cuenta {
    font-family: var(--bandeja-titulo);
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    padding: 2px 4px;
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
    border: 1px solid var(--bandeja-aviso-borde);
  }
</style>
