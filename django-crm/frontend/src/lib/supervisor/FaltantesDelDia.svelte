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
    loQueHayQueResolver,
    pastillaDeBodega,
    pastillasDeCuentas
  } from './material-del-dia.js';

  /**
   * `apps`: lo de `resumenDeLoSinBajar`, que antes era un párrafo rojo suelto
   * debajo de esta franja. Entra al mismo bloque porque es la misma clase de
   * cosa: algo que alguien tiene que resolver hoy.
   * @type {{ cuentas: any, faltantes: any[], equipos?: { equipo: string, cuadrillas: number, todas?: boolean }[], apps?: string }}
   */
  let { cuentas, faltantes, equipos = [], apps = '' } = $props();

  const grupos = $derived(faltantesPorBodega(faltantes));
  const resolver = $derived(loQueHayQueResolver(equipos, apps));
</script>

<div class="fd">
  <!-- LAS CUENTAS SON CUENTAS (07/11/2026, tercera vuelta): en gris. El rojo
       se gasta abajo, en lo que hay que resolver. -->
  <div class="fd-cuentas">
    {#each pastillasDeCuentas(cuentas) as p (p.texto)}
      <span class="fd-pastilla fd-{p.tono}">{p.texto}</span>
    {/each}
  </div>

  <!-- PARA QUE EL DÍA SALGA COMPLETO (07/11/2026, tercera vuelta). El usuario,
       eligiendo sobre la maqueta: lo accionable junto y en orden, en vez de
       seis pastillas rojas y un párrafo suelto repartidos por la franja. -->
  {#if resolver.length}
    <div class="fd-resolver">
      <span class="fd-rotulo">Para que el día salga completo</span>
      <ul>
        {#each resolver as linea (linea)}<li>{linea}</li>{/each}
      </ul>
    </div>
  {/if}

  <!-- CADA BODEGA EN UNA PASTILLA, TODAS EN UNA FILA (07/11/2026). Eran dos
       barras de ancho completo apiladas; ver `pastillaDeBodega`. Lo que se
       abre se lleva la fila entera: una tabla de cuatro columnas en una
       columna de 200 px no se lee. -->
  {#if grupos.length}
    <div class="fd-bodegas">
      {#each grupos as g (g.bodega)}
        <details class="fd-bodega">
          <summary>
            <span class="fd-pastilla fd-b">{pastillaDeBodega(g)}<span class="fd-punta" aria-hidden="true">▾</span></span>
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
    gap: 6px;
    font-size: 13px;
    line-height: 18px;
    color: var(--snoc-on-surface-variant);
  }
  .fd-cuentas {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .fd-pastilla {
    display: inline-block;
    padding: 1px 9px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  /*  Las tres en gris desde el 07/11/2026: son cuentas del día, no alarmas. */
  .fd-ok { background: var(--snoc-surface-container-high); color: var(--snoc-on-surface); }
  .fd-falta { background: var(--snoc-surface-container-high); color: var(--snoc-on-surface); }
  .fd-sin { background: var(--snoc-surface-container); color: var(--snoc-on-surface-variant); }

  /*  EL ÚNICO ROJO DE LA FRANJA (07/11/2026): lo que hay que resolver hoy. */
  .fd-resolver {
    display: grid;
    gap: 2px;
    padding: 6px 10px;
    border-radius: var(--snoc-r-xl);
    border-left: 3px solid var(--snoc-error);
    background: var(--snoc-error-container);
    color: var(--snoc-on-error-container);
  }
  .fd-rotulo {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .fd-resolver ul { margin: 0; padding-left: 16px; }
  .fd-resolver li { font-size: 13px; line-height: 18px; }

  /*  LAS BODEGAS EN UNA FILA (07/11/2026): la que se abre se lleva el ancho
      entero para que la tabla quepa. */
  .fd-bodegas {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
  }
  /*  La bodega no es una alarma del día: es dónde ir a buscar. Gris con el
      número en rojo, para que se distinga sin sumar otro bloque rojo. */
  .fd-b { background: var(--snoc-surface-container-high); color: var(--snoc-error); }
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
