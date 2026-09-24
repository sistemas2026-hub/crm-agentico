<script>
  /**
   * La franja de cifras del dia. Recibe los totales ya calculados por el
   * motor: aqui no se suma ni se promedia nada (PRD 12.5, el codigo calcula
   * y en este caso el codigo es SQL).
   */
  /** @type {{ totales: any, ms: (v: any) => string }} */
  let { totales, ms } = $props();

  const cifras = $derived([
    ['Activas (24 h)', totales.conversaciones_activas, ''],
    ['Agentes con trabajo', totales.agentes_activos, ''],
    ['Conversaciones hoy', totales.atendidas_hoy, ''],
    ['Herramientas hoy', totales.herramientas_hoy, ''],
    ['Herramienta promedio', ms(totales.duracion_media_ms), ''],
    ['Esperan a una persona', totales.esperando_humano, 'ambar']
  ]);
</script>

<div class="cifras">
  {#each cifras as [rotulo, valor, tono]}
    <div class="cifra {tono}">
      <div class="v">{valor ?? '—'}</div>
      <div class="k">{rotulo}</div>
    </div>
  {/each}
</div>

<style>
  /* auto-fit y no un numero fijo de columnas: el ancho disponible cambia con
     el menu lateral, y con columnas fijas la ultima cifra se caia a una
     segunda fila fuera del marco. */
  .cifras { display: grid; grid-template-columns: repeat(auto-fit, minmax(146px, 1fr)); border-bottom: 1px solid #e2e8f0; }
  .cifra { padding: 12px 16px; border-right: 1px solid #e2e8f0; }
  .cifra:last-child { border-right: 0; }
  .v { font-family: ui-monospace, monospace; font-size: 22px; font-weight: 700; line-height: 1; color: #0f172a; }
  .k { font-size: 10px; letter-spacing: .1em; color: #475569; text-transform: uppercase; margin-top: 6px; }
  .cifra.ambar .v { color: #a15c07; }
</style>
