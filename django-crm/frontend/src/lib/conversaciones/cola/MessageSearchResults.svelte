<script>
  /**
   * «En mensajes»: lo que el motor encontró en el CONTENIDO de los mensajes
   * (11/11/2026), debajo de la cola filtrada.
   *
   * Va aparte de la lista de arriba y no mezclado en ella a propósito: arriba
   * están las conversaciones de la cola que coinciden por nombre, número o
   * último mensaje --instantáneo, sobre lo ya cargado--; acá, cada MENSAJE
   * que contiene lo buscado, de cualquier conversación de la empresa, aunque
   * no esté en la cola de hoy. Son dos preguntas, y mezclarlas haría que una
   * fila de la cola apareciera dos veces o que una de hace un mes pareciera
   * estar por atender.
   *
   * El fragmento es texto de un cliente: se resalta PARTIÉNDOLO
   * (partirPorCoincidencia) y dibujando cada trozo como texto. Nunca
   * `{@html}`.
   *
   * Los tres estados no se tapan entre sí ni tapan la cola: un error del
   * motor dice que la búsqueda en mensajes falló, y la lista de arriba sigue
   * filtrando igual.
   */
  import { partirPorCoincidencia } from '$lib/conversaciones/busqueda-mensajes.js';
  import { etiquetaDia, hora, telefonoLegible } from '$lib/conversaciones/formato.js';

  /** @type {{ busqueda: import('$lib/conversaciones/busqueda-mensajes.js').EstadoBusqueda, resultados?: any[], abierta?: string | null }} */
  let { busqueda, resultados = [], abierta = null } = $props();

  const quien = (/** @type {any} */ r) =>
    r.nombre_cliente || telefonoLegible(r.usuario_externo) || r.usuario_externo || 'Sin identificar';
  const cuando = (/** @type {string} */ iso) => {
    const d = etiquetaDia(iso);
    return d === 'Hoy' ? hora(iso) : d;
  };
  const alTope = $derived(
    busqueda.estado === 'listo' && busqueda.tope != null && busqueda.resultados.length >= busqueda.tope
  );
</script>

{#if busqueda.estado !== 'inactivo'}
  <section class="en-mensajes" aria-label="Resultados en el contenido de los mensajes">
    <h3 class="titulo">
      En mensajes
      {#if busqueda.estado === 'listo' && resultados.length}
        <span class="cuenta b-cifra">{resultados.length}{alTope ? '+' : ''}</span>
      {/if}
    </h3>

    {#if busqueda.estado === 'buscando'}
      <p class="estado" role="status">Buscando «{busqueda.q}» en los mensajes…</p>
    {:else if busqueda.estado === 'error'}
      <p class="estado estado-error" role="status">
        No se pudo buscar en los mensajes: {busqueda.error}
      </p>
    {:else if !resultados.length}
      <p class="estado" role="status">Ningún mensaje contiene «{busqueda.q}».</p>
    {:else}
      <ul class="lista">
        {#each resultados as r (r.mensaje_id)}
          <li>
            <a
              class="resultado"
              class:abierta={abierta === String(r.conversation_id)}
              href="/conversaciones/{r.conversation_id}"
            >
              <span class="renglon">
                <span class="quien">{quien(r)}</span>
                {#if r.es_nota}<span class="marca-nota">Nota interna</span>{/if}
                {#if r.estado === 'cerrada'}<span class="marca">Cerrada</span>{/if}
                <span class="cuando">{cuando(r.creado_en)}</span>
              </span>
              <span class="fragmento"
                >{#each partirPorCoincidencia(r.fragmento, busqueda.q) as p, i (i)}{#if p.coincide}<mark
                      >{p.texto}</mark
                    >{:else}{p.texto}{/if}{/each}</span
              >
            </a>
          </li>
        {/each}
      </ul>
      {#if alTope}
        <p class="estado">Se muestran los {busqueda.tope} más recientes. Escribí algo más para acotar.</p>
      {/if}
    {/if}
  </section>
{/if}

<style>
  .en-mensajes {
    border-top: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
  }

  .titulo {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    padding: 10px 12px 6px;
    font-family: var(--bandeja-titulo);
    font-size: var(--bandeja-rotulo-tam);
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }

  .cuenta {
    color: var(--bandeja-texto);
  }

  .estado {
    margin: 0;
    padding: 4px 12px 12px;
    font-size: 12px;
    color: var(--bandeja-texto-2);
  }

  .estado-error {
    color: var(--bandeja-error);
  }

  .lista {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .resultado {
    display: block;
    padding: 8px 12px;
    color: inherit;
    text-decoration: none;
    border-top: 1px solid var(--bandeja-borde);
  }

  li:first-child .resultado {
    border-top-color: transparent;
  }

  .resultado:hover {
    background: var(--bandeja-superficie-suave);
  }

  .resultado.abierta {
    background: var(--bandeja-humano-fondo);
    outline: 1px solid var(--bandeja-humano-borde);
    outline-offset: -1px;
  }

  .resultado:focus-visible {
    outline: 2px solid var(--bandeja-accion);
    outline-offset: -2px;
  }

  .renglon {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
  }

  .quien {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--bandeja-titulo);
    font-size: 13.5px;
    font-weight: 600;
    color: var(--bandeja-texto);
  }

  .marca,
  .marca-nota {
    flex: none;
    padding: 0 5px;
    border-radius: var(--bandeja-radio-sm);
    font-size: 10.5px;
    border: 1px solid var(--bandeja-neutro-borde);
    color: var(--bandeja-neutro-texto);
    background: var(--bandeja-neutro-fondo);
  }

  .marca-nota {
    border-color: transparent;
    color: var(--bandeja-nota);
    background: var(--bandeja-nota-fondo);
  }

  .cuando {
    flex: none;
    margin-left: auto;
    font-size: 11px;
    color: var(--bandeja-texto-3);
  }

  .fragmento {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-top: 2px;
    font-size: 12.5px;
    line-height: 1.4;
    color: var(--bandeja-texto-2);
  }

  .fragmento mark {
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-texto);
    font-weight: 600;
    border-radius: 2px;
  }
</style>
