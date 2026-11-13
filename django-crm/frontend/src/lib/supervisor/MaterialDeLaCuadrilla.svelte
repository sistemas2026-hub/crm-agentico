<!--
  EL MATERIAL DE UNA CUADRILLA en su tarjeta de Programación (29/10/2026).
  Pedido del usuario, mirando la tarjeta: «arriba se ve muy feo… el acta está
  de más… y los avisos, que se contraigan como el material».

  A la vista: el kit, de qué bodega y para quién, y si ya se cargó. El porqué de
  cada elección del Supervisor y la lista de materiales, adentro del desplegable.

  LOS AVISOS, EN UNA PASTILLA (07/11/2026). Eran una línea roja en negrita que
  decía «Falta material · sale sin ONU CATV y ONU WIFI», igual en las cuatro
  tarjetas de la captura del usuario. «Falta material» ya lo dicen las
  pastillas de arriba, así que la línea gastaba su espacio repitiendo lo común
  en vez de decir lo propio. Ahora: una pastilla corta con lo que ESTA
  cuadrilla no puede hacer, en la misma fila que la lista del kit —dos
  renglones pasan a ser uno— y el texto entero adentro.

  Esto reemplaza la regla del 29/10 de mostrar un aviso solo entero: con una
  tarjeta por cuadrilla, una frase larga repetida cuatro veces es el mismo muro
  tenga uno o tres avisos adentro.
-->
<script>
  import {
    estadoDeCarga,
    lineaDeMaterial,
    pastillaDeAvisos,
    porQue,
    resumenDeLineas
  } from './material-del-dia.js';

  /**
   * `comunes`: los equipos que le faltan a TODAS las cuadrillas del día. No se
   * repiten acá —ya se dicen una vez arriba— porque una pastilla idéntica en
   * las cuatro tarjetas no distingue a ninguna. Ver `pastillaDeAvisos`.
   * @type {{ m: any, comunes?: string[] }}
   */
  let { m, comunes = [] } = $props();

  let cargado = $derived(estadoDeCarga(m));
  let chip = $derived(pastillaDeAvisos(m.avisos, comunes));
</script>

<!--
  DOS RENGLONES, NO CUATRO (07/11/2026, tercera vuelta). El usuario, eligiendo
  sobre la maqueta: «hacelo así pero más pequeño». La cabecera «Material ·
  Propuesta» era un renglón entero para decir de qué sección se trata, con el
  kit en negrita justo debajo diciéndolo mejor. El estado de carga se mudó a la
  fila de los desplegables, donde ocupa el hueco que ya había. Con cinco
  cuadrillas, son diez renglones menos.
-->
<section class="mc" aria-label="Material">
  {#if m.kit}
    <p class="mc-kit">
      <strong>{m.kit}</strong>{#if m.kit_apoyo}<span> + </span><strong>{m.kit_apoyo}</strong>{/if}{#if m.lineas.length}<span class="mc-desde">{' · '}{m.bodega} → {m.lider}</span>{/if}
    </p>
  {/if}

  <div class="mc-pie">
    <span class="mc-estado" class:mc-cargado={cargado}>{cargado || 'Propuesta'}</span>
    {#if m.avisos.length}
      <details class="mc-avisos">
        <summary><span class="mc-chip" class:mc-chip-comun={!chip.propio}>{chip.texto}</span></summary>
        {#each m.avisos as a (a)}<p>{a}</p>{/each}
      </details>
    {/if}

    {#if m.lineas.length}
      <details class="mc-lineas">
        <summary>{resumenDeLineas(m.lineas)}</summary>
        <p class="mc-porque">Kit: {porQue(m.kit_por)}</p>
        <p class="mc-porque">Bodega: {porQue(m.bodega_por)}</p>
        {#each m.lineas as l (l.material)}<p>{lineaDeMaterial(l)}</p>{/each}
      </details>
    {/if}
  </div>
</section>

<style>
  .mc {
    display: grid;
    gap: 2px;
    padding: 6px 9px;
    border-radius: var(--snoc-r-xl);
    background: var(--snoc-surface-container-low);
    font-size: 13px;
    line-height: 18px;
    color: var(--snoc-on-surface-variant);
  }
  .mc-estado {
    font-size: 12px;
    color: var(--snoc-secondary);
  }
  .mc-cargado {
    color: var(--snoc-primary);
    font-weight: 600;
  }
  .mc-kit { margin: 0; overflow-wrap: anywhere; }
  .mc-kit strong { font-weight: 600; color: var(--snoc-on-surface); }
  .mc-desde { color: var(--snoc-secondary); }

  /*  LOS DOS DESPLEGABLES EN UNA FILA (07/11/2026): la pastilla de lo que
      falta y la lista del kit, uno al lado del otro mientras haya ancho. Lo
      que se abre se lleva la fila entera para que el texto no quede en una
      columna de 80 px. */
  .mc-pie {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 3px 8px;
  }
  .mc-pie details[open] { flex: 1 0 100%; }

  .mc-avisos summary { list-style: none; }
  .mc-avisos summary::-webkit-details-marker { display: none; }
  .mc-chip {
    display: inline-block;
    padding: 0 8px;
    border-radius: 999px;
    background: var(--snoc-error-container);
    color: var(--snoc-on-error-container);
    font-size: 12px;
    line-height: 18px;
    font-weight: 600;
  }
  /*  Nada propio que decir: el rótulo gris del desplegable, no una alarma.
      Ver `pastillaDeAvisos` (07/11/2026, segunda vuelta). */
  .mc-chip-comun {
    background: var(--snoc-surface-container);
    color: var(--snoc-on-surface-variant);
    font-weight: 400;
  }
  .mc-avisos p { margin: 2px 0 0 2px; color: var(--snoc-error); }

  summary { cursor: pointer; }
  .mc-lineas summary { color: var(--snoc-on-surface-variant); }
  .mc-lineas p { margin: 2px 0 0 14px; }
  .mc-porque { color: var(--snoc-secondary); }
</style>
