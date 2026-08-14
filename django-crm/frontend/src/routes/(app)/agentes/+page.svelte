<script>
  /**
   * Muestra los agentes ya configurados en tenants/*.yaml (del lado de
   * crm-agentico) y, para cada uno, un diagrama con lineas hacia cada
   * herramienta que puede usar. Un ADMIN puede crear/editar/borrar agentes
   * desde aca (via AgenteFormDialog, que habla con /api/agentes); crear una
   * herramienta nueva sigue siendo trabajo de codigo.
   *
   * El diagrama es SVG a mano (mismo estilo que Sparkline.svelte: viewBox +
   * coordenadas calculadas), sin libreria de graficos -- no hay ninguna en
   * este frontend y el tamano del grafo (un agente + hasta ~7 herramientas)
   * no lo amerita.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import AgenteFormDialog from '$lib/components/agentes/AgenteFormDialog.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { toast } from 'svelte-sonner';
  import { invalidateAll } from '$app/navigation';

  /** @type {{ data: any }} */
  let { data } = $props();

  const esAdmin = $derived(data.role === 'ADMIN');

  let dialogoAbierto = $state(false);
  // Anotado, no inferido: sin esto $state lo ensancha a 'string' y no encaja
  // en el prop del dialogo, que solo acepta estos dos.
  let modoDialogo = $state(/** @type {'crear' | 'editar'} */ ('crear'));
  let agenteEnEdicion = $state(/** @type {any} */ (null));

  function abrirCrear() {
    modoDialogo = 'crear';
    agenteEnEdicion = null;
    dialogoAbierto = true;
  }

  function abrirEditar(/** @type {any} */ agente) {
    modoDialogo = 'editar';
    agenteEnEdicion = agente;
    dialogoAbierto = true;
  }

  /** @type {Record<string, boolean>} */
  let borradoArmado = $state({});

  async function borrar(/** @type {string} */ nombre) {
    if (!borradoArmado[nombre]) {
      borradoArmado = { ...borradoArmado, [nombre]: true };
      return;
    }
    borradoArmado = { ...borradoArmado, [nombre]: false };
    const res = await fetch(`/api/agentes/${encodeURIComponent(nombre)}`, { method: 'DELETE' });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      toast.error(e?.error || 'No se pudo borrar el agente');
      return;
    }
    toast.success('Agente borrado.');
    await invalidateAll();
  }

  const ANCHO = 300;
  const ALTO = 220;
  const CX = ANCHO / 2;
  const CY = ALTO / 2;
  const RADIO = 82;

  /** Primer parrafo de la descripcion -- algunas (cliente_final) son largas
   * porque duplican el prompt completo; acá solo hace falta el resumen. */
  function resumen(texto) {
    return (texto || '').trim().split('\n')[0];
  }

  function nodosDe(herramientas) {
    const n = herramientas.length;
    return herramientas.map((h, i) => {
      const angulo = (i / Math.max(n, 1)) * 2 * Math.PI - Math.PI / 2;
      return { ...h, x: CX + RADIO * Math.cos(angulo), y: CY + RADIO * Math.sin(angulo) };
    });
  }

  const COLOR_TIPO = { http: '#2563eb', agregado: '#7c3aed', batch: '#b45309' };
</script>

<PageHeader title="Agentes">
  {#snippet sub()}
    Quién es cada agente y qué herramientas puede usar.
  {/snippet}
  {#snippet actions()}
    {#if esAdmin}
      <a class="v2-btn v2-btn-sm" href="/agentes/asignaciones">Quién usa cada agente</a>
      <Button type="button" onclick={abrirCrear}>Nuevo agente</Button>
    {/if}
  {/snippet}
</PageHeader>

{#if esAdmin}
  <AgenteFormDialog
    bind:open={dialogoAbierto}
    modo={modoDialogo}
    agente={agenteEnEdicion}
    catalogo={data.catalogo || []}
  />
{/if}

{#if data.error}
  <p class="aviso-error">⚠️ {data.error}</p>
{:else if !data.agentes || data.agentes.length === 0}
  <p class="chat-vacio">No hay agentes configurados.</p>
{:else}
  <!--
    El shell de la app recorta con overflow:hidden (ver (app)/+layout.svelte),
    asi que cada pantalla tiene que pedir su propio scroll. Sin este envoltorio
    la grilla se corta en el borde de la ventana en vez de dejar bajar --
    mismo patron que /settings y sus subpaginas.
  -->
  <div class="v2-scroll">
  <div class="v2-pad grilla-envoltorio">
  <div class="grilla">
    {#each data.agentes as agente}
      {#if agente.automatico}
        <!--
          El supervisor no es un Rol real (no tiene herramientas ni
          puede_consultar): sin diagrama de herramientas y sin acciones de
          editar/borrar, que no aplican -- no hay '/api/agentes/supervisor'
          contra el que llamarlas. Ver nucleo/canales/api.py:_agente_supervisor_json.
        -->
        <div class="tarjeta tarjeta-automatica">
          <div class="encabezado-tarjeta">
            <h3>{agente.nombre}</h3>
            <span class="pill-orientacion pill-automatico">Automático · segundo plano</span>
          </div>

          <p class="descripcion">{agente.descripcion}</p>

          <p class="modelo-automatico">
            Modelo: <strong>{agente.modelo || 'hereda el del rol que cierra cada conversación'}</strong>
          </p>
        </div>
      {:else}
        {@const nodos = nodosDe(agente.herramientas)}
        <div class="tarjeta">
          <div class="encabezado-tarjeta">
            <h3>{agente.nombre}</h3>
            {#if agente.area || agente.cargo}
              <p class="organizacion">
                {agente.cargo || '—'}{#if agente.area} · {agente.area}{/if}
              </p>
            {/if}
            <span class="pill-orientacion" class:cliente={agente.orientado_a === 'cliente_final'}>
              {agente.orientado_a === 'cliente_final' ? 'Habla con el cliente' : 'Uso interno'}
            </span>
          </div>

          <p class="descripcion">{resumen(agente.descripcion)}</p>

          <svg viewBox="0 0 {ANCHO} {ALTO}" class="diagrama" role="img" aria-label="Herramientas de {agente.nombre}">
            {#each nodos as nodo}
              <line x1={CX} y1={CY} x2={nodo.x} y2={nodo.y} stroke="#d1d5db" stroke-width="1.5" />
            {/each}

            <circle cx={CX} cy={CY} r="30" fill="#111827" />
            <text x={CX} y={CY} text-anchor="middle" dominant-baseline="middle" fill="white" font-size="10" font-weight="600">
              {agente.nombre}
            </text>

            {#each nodos as nodo}
              <g>
                <title>{nodo.descripcion || nodo.nombre}</title>
                <circle cx={nodo.x} cy={nodo.y} r="26" fill={COLOR_TIPO[nodo.tipo] || '#6b7280'} fill-opacity="0.15"
                       stroke={COLOR_TIPO[nodo.tipo] || '#6b7280'} stroke-width="1.5" />
                <text x={nodo.x} y={nodo.y} text-anchor="middle" dominant-baseline="middle"
                     font-size="7" fill="#374151">
                  {nodo.nombre.length > 16 ? nodo.nombre.slice(0, 14) + '…' : nodo.nombre}
                </text>
              </g>
            {/each}
          </svg>

          <div class="leyenda">
            <span><i class="punto" style="background:{COLOR_TIPO.http}"></i>http</span>
            <span><i class="punto" style="background:{COLOR_TIPO.agregado}"></i>agregado</span>
            <span><i class="punto" style="background:{COLOR_TIPO.batch}"></i>batch</span>
          </div>

          {#if agente.prompt_piezas?.length}
            <details class="recibe">
              <summary>Qué recibe este agente</summary>

              <p class="recibe-nota v2-sub">
                Las instrucciones que le llegan en cada turno, en orden. No se editan acá: cada
                bloque dice de dónde sale.
              </p>

              {#each agente.prompt_piezas as pieza (pieza.titulo)}
                <div class="pieza">
                  <div class="pieza-cabeza">
                    <span class="pieza-titulo">{pieza.titulo}</span>
                    <span class="pieza-origen" class:fijo={!pieza.editable}>{pieza.origen}</span>
                  </div>
                  <pre class="pieza-texto">{pieza.texto}</pre>
                </div>
              {/each}

              <!--
                El prompt no es todo lo que recibe: tambien van las descripciones de
                las herramientas de arriba (que cargan bastante comportamiento) y el
                contexto del corpus, que cambia con cada pregunta. Sin este aviso,
                alguien podria depurar mirando solo esta lista y concluir que el
                agente "no tiene" una instruccion que en realidad le llega por otro
                lado.
              -->
              <p class="recibe-nota v2-sub">
                Además de esto recibe la descripción de cada herramienta de arriba, y —cuando la
                pregunta coincide con el corpus— los fragmentos del manual, que cambian en cada
                turno.
              </p>
            </details>
          {/if}

          {#if esAdmin}
            <div class="acciones-tarjeta">
              <button class="v2-btn v2-btn-sm" type="button" onclick={() => abrirEditar(agente)}>
                Editar
              </button>
              {#if borradoArmado[agente.nombre]}
                <span class="confirmar-borrado">
                  <span class="v2-sub" style="font-size:11.5px">Esto no se puede deshacer.</span>
                  <button class="v2-btn v2-btn-sm" type="button" onclick={() => borrar(agente.nombre)}>
                    Confirmar
                  </button>
                  <button
                    class="v2-btn v2-btn-sm"
                    type="button"
                    onclick={() => (borradoArmado = { ...borradoArmado, [agente.nombre]: false })}
                  >
                    Cancelar
                  </button>
                </span>
              {:else}
                <button class="v2-btn v2-btn-sm" type="button" onclick={() => borrar(agente.nombre)}>
                  Eliminar
                </button>
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    {/each}
  </div>
  </div>
  </div>
{/if}

<style>
  .grilla-envoltorio {
    padding-top: 12px;
    padding-bottom: 32px;
  }
  .aviso-error {
    color: #991b1b;
    font-size: 14px;
  }
  .chat-vacio {
    color: var(--v2-muted, #888);
    font-size: 14px;
  }
  .grilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }
  .tarjeta {
    border: 1px solid var(--v2-border, #e5e5e5);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .encabezado-tarjeta h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    text-transform: capitalize;
  }
  .organizacion {
    margin: 2px 0 4px;
    font-size: 12px;
    color: var(--v2-muted, #888);
  }
  .pill-orientacion {
    display: inline-block;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 999px;
    background: #f1f1f1;
    color: #4b5563;
    width: fit-content;
  }
  .pill-orientacion.cliente {
    background: #dcfce7;
    color: #15803d;
  }
  .pill-orientacion.pill-automatico {
    background: #ede9fe;
    color: #6d28d9;
  }
  .tarjeta-automatica {
    border-style: dashed;
    background: var(--v2-bg-subtle, #fafafa);
  }
  .modelo-automatico {
    font-size: 11px;
    color: var(--v2-muted, #888);
    margin: 0;
  }
  .descripcion {
    font-size: 12px;
    color: #4b5563;
    margin: 0;
  }
  .diagrama {
    width: 100%;
    height: auto;
  }
  .leyenda {
    display: flex;
    gap: 12px;
    font-size: 10px;
    color: var(--v2-muted, #888);
  }
  .punto {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 4px;
  }
  .acciones-tarjeta {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-top: 4px;
    border-top: 1px solid var(--v2-border, #e5e5e5);
    margin-top: 4px;
  }
  .confirmar-borrado {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .recibe {
    border-top: 1px solid var(--v2-border, #e5e5e5);
    padding-top: 8px;
  }
  .recibe summary {
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    user-select: none;
  }
  .recibe-nota {
    font-size: 11.5px;
    margin: 8px 0;
  }
  .pieza {
    margin-bottom: 10px;
  }
  .pieza-cabeza {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
  }
  .pieza-titulo {
    font-size: 11.5px;
    font-weight: 600;
  }
  .pieza-origen {
    font-size: 10.5px;
    color: var(--v2-muted, #888);
  }
  /* Lo generado o fijo se distingue de lo editable: si no, alguien busca
     donde cambiar un bloque que nadie escribio. */
  .pieza-origen.fijo {
    font-style: italic;
  }
  .pieza-texto {
    margin: 3px 0 0;
    font-size: 11.5px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: inherit;
    color: #4b5563;
    background: var(--v2-bg-subtle, #fafafa);
    border-radius: 6px;
    padding: 7px 9px;
    max-height: 190px;
    overflow-y: auto;
  }
</style>
