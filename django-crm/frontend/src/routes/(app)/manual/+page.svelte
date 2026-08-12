<script>
  /**
   * Revision de lo marcado como "buen ejemplo" en Conversaciones y el
   * Simulador de WhatsApp (ver MarcarEjemplo.svelte), agrupado por
   * caso/proceso (tenant_config.manual.casos). Es la materia prima para
   * redactar el procedimiento de cada caso -- redactarlo y publicarlo al
   * corpus que usa el bot es una entrega aparte, esta pantalla es solo
   * lectura.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeTime } from '$lib/v2/format.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  const etiqueta = (c) => c.replaceAll('_', ' ');

  // Copia local mutable: quitar una marca la saca de la pantalla al toque,
  // sin esperar a recargar la pagina entera (ver quitarMarca abajo).
  let ejemplos = $state(data.ejemplos ?? []);

  const porCaso = $derived(
    (data.casos || []).map((caso) => ({
      caso,
      ejemplos: ejemplos.filter((e) => e.caso === caso)
    }))
  );

  const totalMarcado = $derived(ejemplos.length);

  /** Deshace el marcado de un ejemplo ya incorporado al manual -- mismo
   * endpoint que "Quitar marca" en MarcarEjemplo.svelte, pero se puede
   * hacer de una desde acá, sin abrir la conversación de origen. */
  async function quitarMarca(e) {
    const resp = await fetch(
      `/api/conversaciones/${e.conversation_id}/mensajes/${e.mensaje_id}/marcar`,
      { method: 'DELETE' }
    );
    if (resp.ok) {
      ejemplos = ejemplos.filter((x) => x.id !== e.id);
    }
  }

  /** id de documento -> 'cargando' | array de fragmentos | undefined */
  let fragmentosPorDoc = $state({});

  async function cargarFragmentos(id) {
    if (fragmentosPorDoc[id]) return; // ya cargado o cargando
    fragmentosPorDoc = { ...fragmentosPorDoc, [id]: 'cargando' };
    try {
      const resp = await fetch(`/api/corpus/documentos/${id}/fragmentos`);
      const datos = await resp.json();
      fragmentosPorDoc = { ...fragmentosPorDoc, [id]: resp.ok ? datos.fragmentos : [] };
    } catch {
      fragmentosPorDoc = { ...fragmentosPorDoc, [id]: [] };
    }
  }

  /** Agrupa fragmentos consecutivos del mismo numeral (metadata.seccion) --
   * asi se ve como secciones del manual en vez de texto corrido. */
  function agrupar(fragmentos) {
    const grupos = [];
    let actual = null;
    for (const f of fragmentos) {
      const seccion = f.metadata?.seccion ?? null;
      if (!actual || actual.seccion !== seccion) {
        actual = { seccion, fragmentos: [] };
        grupos.push(actual);
      }
      actual.fragmentos.push(f);
    }
    return grupos;
  }
</script>

<PageHeader title="Manual">
  {#snippet sub()}
    Respuestas del agente marcadas como buen ejemplo, agrupadas por caso — base para redactar el
    procedimiento de cada una. Se marca desde Conversaciones o el Simulador de WhatsApp.
  {/snippet}
</PageHeader>

{#if data.error}
  <p class="aviso-error v2-pad">⚠️ {data.error}</p>
{:else if !data.casos || data.casos.length === 0}
  <p class="v2-sub v2-pad">
    Todavía no hay casos configurados (tenant_config.manual.casos). Se definen en la configuración
    del tenant.
  </p>
{:else}
  <div class="v2-scroll">
    <div class="v2-pad manual-envoltorio">
      {#if data.documentos && data.documentos.length > 0}
        <div class="v2-label" style="margin-bottom:10px">Documentos publicados</div>
        <div class="docs-lista">
          {#each data.documentos as doc (doc.id)}
            <details
              class="v2-card doc-detalle"
              ontoggle={(e) => e.currentTarget.open && cargarFragmentos(doc.id)}
            >
              <summary class="doc-resumen">
                <span class="doc-titulo">{doc.titulo}</span>
                <span class="v2-muted">{doc.codigo} · v{doc.version} · {doc.n_fragmentos} fragmento{doc.n_fragmentos === 1 ? '' : 's'}</span>
                <Pill tone={doc.estado === 'vigente' ? 'moss' : 'slate'}>{doc.estado}</Pill>
              </summary>
              <div class="doc-cuerpo">
                {#if fragmentosPorDoc[doc.id] === 'cargando'}
                  <p class="v2-sub">Cargando…</p>
                {:else if fragmentosPorDoc[doc.id]?.length === 0}
                  <p class="v2-sub">Sin fragmentos vigentes.</p>
                {:else if fragmentosPorDoc[doc.id]}
                  {#each agrupar(fragmentosPorDoc[doc.id]) as grupo}
                    {#if grupo.seccion}<div class="doc-seccion">Sección {grupo.seccion}</div>{/if}
                    {#each grupo.fragmentos as f}
                      <p class="doc-fragmento">{f.contenido}</p>
                    {/each}
                  {/each}
                {/if}
              </div>
            </details>
          {/each}
        </div>
      {/if}

      <div class="v2-label" style="margin:24px 0 10px">Ejemplos marcados por caso</div>
      {#if totalMarcado === 0}
        <p class="v2-sub" style="margin-bottom:16px">
          Todavía no se marcó ninguna respuesta como buen ejemplo.
        </p>
      {/if}
      {#each porCaso as grupo (grupo.caso)}
        <section class="caso-seccion">
          <h3 class="caso-titulo">
            {etiqueta(grupo.caso)}
            <span class="v2-muted">({grupo.ejemplos.length})</span>
          </h3>
          {#if grupo.ejemplos.length === 0}
            <p class="v2-sub caso-vacio">Sin ejemplos todavía.</p>
          {:else}
            <div class="ejemplos-lista">
              {#each grupo.ejemplos as e (e.id)}
                <div class="v2-card ejemplo-card">
                  <div class="ejemplo-pregunta"><b>Cliente:</b> {e.pregunta || '—'}</div>
                  <div class="ejemplo-respuesta"><b>Agente:</b> {e.respuesta}</div>
                  <div class="ejemplo-meta v2-sub">
                    {#if e.marcado_por}Marcado por {e.marcado_por} ·{/if}
                    {relativeTime(e.creado_en)} ·
                    <a href="/conversaciones/{e.conversation_id}">Ver conversación completa</a> ·
                    <button type="button" class="quitar-marca-link" onclick={() => quitarMarca(e)}>
                      Quitar marca
                    </button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </section>
      {/each}
    </div>
  </div>
{/if}

<style>
  .aviso-error {
    color: #991b1b;
    font-size: 14px;
  }
  .manual-envoltorio {
    padding-top: 12px;
    padding-bottom: 32px;
  }
  .caso-seccion {
    margin-bottom: 28px;
  }
  .caso-titulo {
    margin: 0 0 10px;
    font-size: 15px;
    font-weight: 600;
    text-transform: capitalize;
    display: flex;
    align-items: baseline;
    gap: 6px;
  }
  .caso-vacio {
    font-size: 12.5px;
  }
  .ejemplos-lista {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .ejemplo-card {
    padding: 14px 16px;
    max-width: 720px;
  }
  .ejemplo-pregunta,
  .ejemplo-respuesta {
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
  }
  .ejemplo-respuesta {
    margin-top: 6px;
  }
  .ejemplo-meta {
    margin-top: 10px;
    font-size: 11.5px;
  }
  .quitar-marca-link {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    font-size: 11.5px;
    color: var(--v2-rust, #b91c1c);
    cursor: pointer;
    text-decoration: underline;
  }

  .docs-lista {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 720px;
    margin-bottom: 8px;
  }
  .doc-detalle {
    padding: 12px 16px;
  }
  .doc-resumen {
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    user-select: none;
    list-style: none;
  }
  .doc-resumen::-webkit-details-marker {
    display: none;
  }
  .doc-titulo {
    font-weight: 600;
  }
  .doc-cuerpo {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-border, #e5e5e5);
  }
  .doc-seccion {
    font-size: 12px;
    font-weight: 600;
    color: var(--v2-muted, #888);
    margin: 14px 0 6px;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }
  .doc-seccion:first-child {
    margin-top: 0;
  }
  .doc-fragmento {
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    margin: 0 0 8px;
  }
</style>
