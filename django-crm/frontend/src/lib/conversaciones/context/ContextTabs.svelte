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

  /* 12px, peso medio, sin versalita: es navegación, no un rótulo de dato. Los
     mismos valores que la referencia (medidos en su HTML: 12px / 500 / #64748B
     y 12px / 600 / #2563EB la activa). */
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
    padding: 9px 4px;
    border: 0;
    /* El filete de la activa se dibuja acá, transparente, para que la pestaña
       no cambie de alto al activarse. */
    border-bottom: 2px solid transparent;
    background: none;
    font-family: var(--bandeja-sans);
    /* 12px, los de la referencia. Estuvo en 11 mientras la columna medía 304
       y cinco palabras en español no entraban ("Actividad" es más larga que
       "Activity"). Con la Bandeja a pantalla completa la columna volvió a
       sus 350px y el tamaño original entra. */
    font-size: 12px;
    font-weight: 500;
    color: var(--bandeja-texto-2);
    cursor: pointer;
    white-space: nowrap;
  }

  .ctx-tab:hover {
    color: var(--bandeja-texto);
    background: var(--bandeja-superficie-suave);
  }

  .ctx-tab-activa {
    color: var(--bandeja-humano);
    font-weight: 600;
    border-bottom-color: var(--bandeja-humano);
  }

  .ctx-tab-activa:hover {
    background: none;
  }

  /* ── EL DEDO ────────────────────────────────────────────────────────────
     Debajo de 1000px la Bandeja ya pasó a master-detail (una vista por vez,
     ver el layout), que es el punto donde se la usa con el dedo y no con un
     puntero. Con `padding: 9px` y texto de 12px la pestaña mide unos 34px de
     alto: entra dentro del rango en que un toque cae en la pestaña de al
     lado. La referencia móvil pide 44px como mínimo y es el mismo número que
     recomiendan las guías de las dos plataformas.

     Se fija con `min-height` y no con más padding para que el alto sea el que
     se declara, sin depender de cuánto mida la línea de texto. */
  @media (max-width: 1000px) {
    .ctx-tab {
      min-height: 44px;
      font-size: 12.5px;
    }
  }

  /* El número de lo que espera adentro. Mono, como todo lo que es dato. */
  .ctx-cuenta {
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    line-height: 1;
    padding: 2px 4px;
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
    border: 1px solid var(--bandeja-aviso-borde);
  }
</style>
