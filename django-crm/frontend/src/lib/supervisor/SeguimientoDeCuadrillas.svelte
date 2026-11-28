<!--
  EL SEGUIMIENTO DE LAS CUADRILLAS, arriba de Programación (30/10/2026). El
  usuario: «unos cuadros indicando la cuadrilla, qué tiene en progreso y qué
  tiempo lleva, y un log contraíble de los seguimientos que le ha hecho el
  Supervisor al técnico».

  Un cuadro por cuadrilla: en qué está ahora y hace cuánto, cuántas lleva de
  cuántas, y lo que pide atención (una novedad, o una orden sin reporte). Con
  el asunto y la dirección de la orden en curso o, si no hay, de LA QUE SIGUE
  (30/10/2026, el usuario: «donde dice todavía no sale debería ir el asunto del
  ticket y la dirección»). Al pie, el log del día plegado: lo que hizo el
  Supervisor y lo que reportó el técnico, en orden de hora. Todo lo calcula el
  servidor (`campo/tiempos_del_dia.py`); acá no se resta nada.

  Desde el 07/11/2026 cada cuadro se puede RECORRER: una flecha con el nombre
  de la orden que sigue, y así hasta la última del día. El cuadro vive en
  `CuadroDeCuadrilla.svelte` —cada uno con su propio recorrido— y acá queda la
  grilla. La clave del `{#each}` es la jornada, que no cambia entre recargas:
  por eso recorrer no se deshace cuando Programación se refresca.
-->
<script>
  import CuadroDeCuadrilla from './CuadroDeCuadrilla.svelte';

  /** @type {{ cuadrillas: any[] }} */
  let { cuadrillas = [] } = $props();
</script>

{#if cuadrillas.length}
  <section class="sc" aria-label="Seguimiento de las cuadrillas">
    {#each cuadrillas as c (c.jornada)}
      <CuadroDeCuadrilla cuadrilla={c} />
    {/each}
  </section>
{/if}

<style>
  .sc {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
    gap: 10px;
  }
</style>
