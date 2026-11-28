<script>
  /**
   * Un caso dorado listo para copiar o descargar (12/11/2026).
   *
   * Producción no puede escribir el repositorio: el caso se muestra y lo lleva
   * una persona al final de `evaluacion/<empresa>.casos.yaml`, o lo trae
   * `cli/importar_casos_dorados.py` junto con todos los marcados. Los avisos
   * del motor van arriba y no abajo: dicen lo que la máquina no pudo
   * garantizar (un nombre propio que la redacción por patrón no tapa, una
   * traza con errores) y se leen antes de copiar, no después.
   *
   * @type {{ estado: any, nombreArchivo?: string }}
   */
  let { estado, nombreArchivo = 'caso-dorado.yaml' } = $props();
  let copiado = $state(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(estado.yaml);
      copiado = true;
      setTimeout(() => (copiado = false), 2000);
    } catch {
      copiado = false;
    }
  }

  function descargar() {
    const url = URL.createObjectURL(new Blob([estado.yaml], { type: 'text/yaml' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = nombreArchivo;
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="caso-dorado">
  {#if estado?.cargando}
    <p class="v2-sub">Armando el caso desde la traza…</p>
  {:else if estado?.error}
    <p class="error">{estado.error}</p>
  {:else if estado?.yaml}
    {#if (estado.avisos ?? []).length > 0}
      <ul class="avisos">
        {#each estado.avisos as a, i (i)}<li>{a}</li>{/each}
      </ul>
    {/if}
    <pre>{estado.yaml}</pre>
    <div class="acciones">
      <button type="button" class="v2-btn v2-btn-sm" onclick={copiar}>
        {copiado ? 'Copiado' : 'Copiar'}
      </button>
      <button type="button" class="v2-btn v2-btn-sm" onclick={descargar}>Descargar</button>
      <span class="v2-sub">
        Va al final de <code>evaluacion/&lt;empresa&gt;.casos.yaml</code>, debajo de <code>casos:</code>.
      </span>
    </div>
  {/if}
</div>

<style>
  .caso-dorado {
    margin-top: 10px;
    font-size: 12px;
  }
  pre {
    margin: 6px 0 0;
    padding: 10px 12px;
    background: var(--v2-paper);
    border-radius: 6px;
    font-family: ui-monospace, monospace;
    font-size: 11.5px;
    line-height: 1.5;
    white-space: pre-wrap;
    max-height: 340px;
    overflow: auto;
  }
  .acciones {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
  }
  .avisos {
    margin: 0;
    padding: 8px 12px 8px 26px;
    border-radius: 6px;
    background: color-mix(in oklab, var(--v2-clay, #b4642e) 8%, transparent);
    color: var(--v2-slate);
    line-height: 1.5;
  }
  .error {
    color: var(--v2-rust);
  }
</style>
