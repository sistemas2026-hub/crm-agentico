<script>
  /**
   * Las cuentas y los faltantes del material del día, en Programación
   * (29/10/2026). El usuario, con la captura: «¿qué podemos hacer con esto
   * para que se vea más estético?» — una frase larga de cuentas y trece líneas
   * rojas iguales, una por material. Ahora: las cuentas en pastillas, una
   * línea por bodega y el detalle plegado en una tabla.
   */
  import { cantidad, cuantosFaltan, faltantesPorBodega, pastillasDeCuentas } from './material-del-dia.js';

  /** @type {{ cuentas: any, faltantes: any[] }} */
  let { cuentas, faltantes } = $props();

  const grupos = $derived(faltantesPorBodega(faltantes));
</script>

<div class="fd">
  <div class="fd-cuentas">
    {#each pastillasDeCuentas(cuentas) as p (p.texto)}
      <span class="fd-pastilla fd-{p.tono}">{p.texto}</span>
    {/each}
  </div>

  {#each grupos as g (g.bodega)}
    <details class="fd-bodega">
      <summary>
        <span class="fd-nombre">{g.bodega}</span>
        <span class="fd-cuenta">{cuantosFaltan(g.materiales.length)}</span>
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
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  .fd-ok { background: var(--snoc-surface-container-high); color: var(--snoc-on-surface); }
  .fd-falta { background: var(--snoc-error-container); color: var(--snoc-on-error-container); }
  .fd-sin { background: var(--snoc-surface-container); color: var(--snoc-on-surface-variant); }

  .fd-bodega {
    padding: 8px 10px;
    border-radius: var(--snoc-r-xl);
    border-left: 3px solid var(--snoc-error);
    background: var(--snoc-surface-container-low);
  }
  .fd-bodega summary {
    cursor: pointer;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: baseline;
  }
  .fd-nombre { font-weight: 700; color: var(--snoc-on-surface); }
  .fd-cuenta { color: var(--snoc-error); font-weight: 600; }
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
