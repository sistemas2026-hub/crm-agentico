<script>
  /**
   * EL ANCHO DE BANDA DE CADA PLAN (27/11/2026): las filas de la tabla de
   * Programación → El contrato de instalación. Cada plan con su perfil de
   * bajada y de subida de SmartOLT.
   *
   * Cada opción dice su velocidad y cuál es la sugerida, y la fila avisa si lo
   * elegido queda por debajo de lo que paga el cliente: al cargarla en
   * producción ELITE (350 de subida) quedó dos veces con un perfil más chico
   * (`PLAN_300MB`, `PLAN_100MB` en vez de `PLAN_1000MB`) porque los nombres se
   * confunden a simple vista.
   */
  import { etiquetaDePerfil, quedaPorDebajo } from './perfiles-de-velocidad.js';

  /** @type {{ perfiles: { filas: import('./perfiles-de-velocidad.js').Fila[],
   *   perfiles: { bajada: import('./perfiles-de-velocidad.js').Perfil[],
   *               subida: import('./perfiles-de-velocidad.js').Perfil[] } } }} */
  let { perfiles } = $props();

  //  Lo que se cambió en pantalla, para que el aviso siga a la lista. Las
  //  listas no se atan a esto: muestran lo guardado y el formulario manda lo
  //  que se ve.
  /** @type {Record<string, string>} */
  let cambios = $state({});

  /** @param {string} nombre @param {import('./perfiles-de-velocidad.js').Perfil[]} lista */
  const noEsta = (nombre, lista) => !!nombre && !lista.some((p) => p.nombre === nombre);
</script>

{#each perfiles.filas as fila, i}
  {@const bajada = cambios[`${i}-bajada`] ?? fila.bajada}
  {@const subida = cambios[`${i}-subida`] ?? fila.subida}
  {@const bajaCorta = quedaPorDebajo(bajada, perfiles.perfiles.bajada, fila.kbps.bajada)}
  {@const subeCorta = quedaPorDebajo(subida, perfiles.perfiles.subida, fila.kbps.subida)}
  <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap; align-items:center;">
    <input type="hidden" name={`perfil_plan_${i}`} value={fila.plan} />
    <span class="snoc-body-sm" style="flex:1; min-width:12rem;">
      {fila.plan}
      {#if fila.velocidad}<span class="snoc-secundario"> · {fila.velocidad}</span>{/if}
      {#if !fila.seVende}<span class="snoc-secundario"> · ya no se vende</span>{/if}
    </span>
    <select class="snoc-select" name={`perfil_bajada_${i}`} value={fila.bajada}
            aria-label={`Perfil de bajada del ${fila.plan}`}
            onchange={(e) => (cambios[`${i}-bajada`] = e.currentTarget.value)}>
      <option value="">Bajada: sin perfil</option>
      {#if noEsta(fila.bajada, perfiles.perfiles.bajada)}
        <option value={fila.bajada}>{fila.bajada} (ya no está en SmartOLT)</option>
      {/if}
      {#each perfiles.perfiles.bajada as p}
        <option value={p.nombre}>{etiquetaDePerfil(p, fila.sugeridos.bajada)}</option>
      {/each}
    </select>
    <select class="snoc-select" name={`perfil_subida_${i}`} value={fila.subida}
            aria-label={`Perfil de subida del ${fila.plan}`}
            onchange={(e) => (cambios[`${i}-subida`] = e.currentTarget.value)}>
      <option value="">Subida: sin perfil</option>
      {#if noEsta(fila.subida, perfiles.perfiles.subida)}
        <option value={fila.subida}>{fila.subida} (ya no está en SmartOLT)</option>
      {/if}
      {#each perfiles.perfiles.subida as p}
        <option value={p.nombre}>{etiquetaDePerfil(p, fila.sugeridos.subida)}</option>
      {/each}
    </select>
    {#if fila.sugerido}<span class="snoc-body-sm snoc-secundario">sugerido</span>{/if}
  </div>
  {#if bajaCorta || subeCorta}
    <span class="snoc-body-sm snoc-error-txt">
      {fila.plan}: {bajaCorta && subeCorta ? 'la bajada y la subida quedan' : bajaCorta ? 'la bajada queda' : 'la subida queda'}
      por debajo de lo que paga el cliente ({fila.velocidad}).
    </span>
  {/if}
{:else}
  <span class="snoc-body-sm snoc-secundario">No hay planes de venta cargados.</span>
{/each}
