<script>
  /**
   * Las cuentas y los faltantes del material del día, en Programación
   * (29/10/2026). El usuario, con la captura: «¿qué podemos hacer con esto
   * para que se vea más estético?» — una frase larga de cuentas y trece líneas
   * rojas iguales, una por material. Ahora: las cuentas en pastillas, una
   * línea por bodega y el detalle plegado en una tabla.
   */
  import {
    cantidad,
    faltantesPorBodega,
    pastillaDeBodega,
    pastillaDeEquipo,
    pastillasDeCuentas
  } from './material-del-dia.js';

  /** @type {{ cuentas: any, faltantes: any[], equipos?: { equipo: string, cuadrillas: number }[] }} */
  let { cuentas, faltantes, equipos = [] } = $props();

  const grupos = $derived(faltantesPorBodega(faltantes));
</script>

<div class="fd">
  <div class="fd-cuentas">
    {#each pastillasDeCuentas(cuentas) as p (p.texto)}
      <span class="fd-pastilla fd-{p.tono}">{p.texto}</span>
    {/each}
    <!-- QUÉ EQUIPO FALTA Y A CUÁNTAS (07/11/2026): lo que cada tarjeta repetía
         («sale sin ONU CATV y ONU WIFI», igual en las cuatro) y estas cuentas
         no decían. Acá una vez; en la tarjeta, cuál le toca a cada una. -->
    {#each equipos as e (e.equipo)}
      <span class="fd-pastilla fd-falta">{pastillaDeEquipo(e)}</span>
    {/each}
  </div>

  <!-- CADA BODEGA EN UNA PASTILLA, TODAS EN UNA FILA (07/11/2026). Eran dos
       barras de ancho completo apiladas; ver `pastillaDeBodega`. Lo que se
       abre se lleva la fila entera: una tabla de cuatro columnas en una
       columna de 200 px no se lee. -->
  {#if grupos.length}
    <div class="fd-bodegas">
      {#each grupos as g (g.bodega)}
        <details class="fd-bodega">
          <summary>
            <span class="fd-pastilla fd-falta">{pastillaDeBodega(g)}<span class="fd-punta" aria-hidden="true">▾</span></span>
          </summary>
          {#if g.sinNada}
            <p class="fd-pista">
              No hay libre nada de lo que piden los kits. Si en la bodega sí hay, falta cargar su
              stock en Inventario.
            </p>
          {/if}
          <table class="fd-tabla">
            <thead>
              <tr><th>Material</th><th>Se piden</th><th>Hay libres</th><th>Faltan</th></tr>
            </thead>
            <tbody>
              {#each g.materiales as m (m.material)}
                <tr>
                  <td>{m.material}</td>
                  <td>{cantidad(m.pedido, m.unidad)}</td>
                  <td>{m.disponible}</td>
                  <td class="fd-faltan">{m.falta}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </details>
      {/each}
    </div>
  {/if}
</div>

<style>
  .fd {
    display: grid;
    gap: 8px;
    font-size: 13px;
    line-height: 18px;
    color: var(--snoc-on-surface-variant);
  }
  .fd-cuentas {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .fd-pastilla {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  .fd-ok { background: var(--snoc-surface-container-high); color: var(--snoc-on-surface); }
  .fd-falta { background: var(--snoc-error-container); color: var(--snoc-on-error-container); }
  .fd-sin { background: var(--snoc-surface-container); color: var(--snoc-on-surface-variant); }

  /*  LAS BODEGAS EN UNA FILA (07/11/2026): la que se abre se lleva el ancho
      entero para que la tabla quepa. */
  .fd-bodegas {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
  }
  .fd-bodega { min-width: 0; }
  .fd-bodega[open] {
    flex: 1 0 100%;
    padding: 8px 10px;
    border-radius: var(--snoc-r-xl);
    border-left: 3px solid var(--snoc-error);
    background: var(--snoc-surface-container-low);
  }
  .fd-bodega summary { cursor: pointer; list-style: none; }
  .fd-bodega summary::-webkit-details-marker { display: none; }
  .fd-punta { margin-left: 6px; font-size: 10px; }
  .fd-bodega[open] .fd-punta { transform: rotate(180deg); display: inline-block; }
  .fd-pista { margin: 6px 0 0; color: var(--snoc-secondary); }

  .fd-tabla {
    width: 100%;
    margin-top: 6px;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }
  .fd-tabla th {
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    color: var(--snoc-secondary);
    padding: 2px 6px 4px 0;
    border-bottom: 1px solid var(--snoc-outline-variant);
  }
  .fd-tabla td {
    padding: 3px 6px 3px 0;
    border-bottom: 1px solid var(--snoc-surface-container);
    overflow-wrap: anywhere;
  }
  .fd-tabla th:not(:first-child),
  .fd-tabla td:not(:first-child) { text-align: right; white-space: nowrap; }
  .fd-faltan { color: var(--snoc-error); font-weight: 600; }
</style>
