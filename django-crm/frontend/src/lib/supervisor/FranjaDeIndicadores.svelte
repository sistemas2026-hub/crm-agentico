<!--
  LA FRANJA DE INDICADORES (31/10/2026). Lo que el supervisor tiene que saber
  antes de leer nada: cuántas cuadrillas hay, cuántas van en ruta, cuánto se
  publicó, cuánto espera, y qué necesita atención.

  Los números los calcula el servidor (`campo/dia_publicado.py::cuentas`); acá
  solo se muestran. El material viene de su propia lectura, así que puede
  faltar sin que la franja deje de servir.

  Lo que necesita acción va en rojo; lo demás, neutro. Que todo grite es lo
  mismo que no avisar nada.
-->
<script>
  /** @type {{ cuentas: any, kitsIncompletos?: number | null }} */
  let { cuentas, kitsIncompletos = null } = $props();

  let fichas = $derived([
    { clave: 'cuadrillas', valor: cuentas?.cuadrillas ?? 0, nombre: 'Cuadrillas', tono: 'neutro' },
    { clave: 'en_camino', valor: cuentas?.en_camino ?? 0, nombre: 'En camino', tono: 'ok' },
    { clave: 'publicadas', valor: cuentas?.publicadas ?? 0, nombre: 'OT publicadas', tono: 'neutro' },
    { clave: 'esperan', valor: cuentas?.esperan ?? 0, nombre: 'Esperan cuadrilla', tono: 'neutro' },
    //  El material puede no haberse podido leer: entonces no se inventa un 0.
    { clave: 'kits', valor: kitsIncompletos, nombre: 'Kits incompletos', tono: 'malo' },
    { clave: 'novedad', valor: cuentas?.con_novedad ?? 0, nombre: 'Con novedad', tono: 'avisa' }
  ].filter((f) => f.valor !== null && f.valor !== undefined));
</script>

<ul class="fi" aria-label="Indicadores del día">
  {#each fichas as f (f.clave)}
    <li class="fi-f fi-{f.valor ? f.tono : 'neutro'}">
      <strong>{f.valor}</strong>
      <span>{f.nombre}</span>
    </li>
  {/each}
</ul>

<style>
  .fi {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr));
    gap: var(--snoc-sm);
  }
  .fi-f {
    display: grid;
    gap: 2px;
    padding: 10px 14px;
    min-width: 0;
    border: 1px solid var(--snoc-outline-variant);
    border-left-width: 4px;
    border-radius: var(--snoc-r-xl);
    background: var(--snoc-surface-container-lowest);
  }
  .fi-f strong {
    font-size: 24px;
    line-height: 1.1;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .fi-f span { font-size: 12px; color: var(--snoc-on-surface-variant); }
  .fi-neutro { border-left-color: var(--snoc-outline-variant); }
  .fi-ok { border-left-color: var(--snoc-primary); }
  .fi-ok strong { color: var(--snoc-primary); }
  .fi-avisa { border-left-color: #8a5300; }
  .fi-avisa strong { color: #8a5300; }
  .fi-malo { border-left-color: var(--snoc-error); }
  .fi-malo strong { color: var(--snoc-error); }
</style>
