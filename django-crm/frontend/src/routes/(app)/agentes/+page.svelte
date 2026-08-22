<script>
  /**
   * Los agentes configurados y, para cada uno, que puede hacer y que puede
   * ver. Un ADMIN puede crear/editar/borrar desde aca (via AgenteFormDialog,
   * que habla con /api/agentes); crear una herramienta nueva sigue siendo
   * trabajo de codigo.
   *
   * La tarjeta esta armada para responder una pregunta concreta: "¿que le
   * estoy dejando hacer a este agente?". Por eso las herramientas van
   * agrupadas por lo que HACEN (ver porLoQueHace) con los campos que ve de
   * cada una, y no como el diagrama radial que hubo antes -- ese ocupaba mas
   * y decia menos: truncaba los nombres hasta volverlos ambiguos y no
   * distinguia una consulta de algo que cambia el mundo real.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import AgenteFormDialog from '$lib/components/agentes/AgenteFormDialog.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { toast } from 'svelte-sonner';
  import { invalidateAll } from '$app/navigation';
  import { AlertTriangle, Bot, BotMessageSquare, ScanEye } from '@lucide/svelte';

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

  // El shell de la app recorta con overflow:hidden (ver (app)/+layout.svelte),
  // asi que la grilla de tarjetas pide su propio scroll con .v2-scroll/.v2-pad
  // -- mismo patron que /settings y sus subpaginas. Documentado aca y no como
  // comentario HTML dentro del {:else}: un comentario ahi, como primer nodo de
  // la rama, choco con los marcadores de hidratacion de Svelte 5 y producia
  // 'hydration_mismatch' en cada carga -- Svelte tiraba el DOM del servidor y
  // volvia a armar todo desde cero en el cliente, lo que se sentia como que el
  // scroll "se resetea solo" a mitad de uso.

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

  /** Primer PARRAFO de la descripcion. Antes cortaba en el primer salto de
   * linea, y como el YAML usa bloques literales eso partia la frase al medio
   * ("...revisa" y nada mas). El parrafo entero se lee completo; si es largo
   * lo recorta el CSS, que al menos corta donde termina un renglon. */
  function resumen(texto) {
    return (texto || '').trim().split(/\n\s*\n/)[0].replace(/\s*\n\s*/g, ' ');
  }

  /**
   * Las herramientas por lo que HACEN, no por su tipo tecnico.
   *
   * 'http'/'agregado'/'batch' es detalle de implementacion: a quien revisa
   * que puede hacer un agente no le dice nada. Lo que le importa es si el
   * agente mira, cuenta, o CAMBIA algo del mundo real.
   *
   * El orden no es alfabetico ni el del YAML: 'Actua' va ultimo y aparte
   * porque es el unico grupo con consecuencias. En soporte es una sola
   * herramienta de ocho -- agendar_visita_tecnica crea una visita con costo
   * y logistica-- y hasta ahora se veia igual que una consulta.
   */
  function porLoQueHace(herramientas) {
    const grupos = [
      { clave: 'consulta', titulo: 'Consulta', items: [] },
      { clave: 'cuenta', titulo: 'Cuenta', items: [] },
      { clave: 'actua', titulo: 'Actúa', items: [] }
    ];
    for (const h of herramientas ?? []) {
      // Escribir manda sobre el tipo: una herramienta que cambia algo va a
      // 'Actua' aunque ademas sea un agregado.
      if (h.solo_lectura === false) grupos[2].items.push(h);
      else if (h.tipo === 'agregado') grupos[1].items.push(h);
      else grupos[0].items.push(h);
    }
    return grupos.filter((g) => g.items.length > 0);
  }

  /**
   * El motivo con mas conversaciones escaladas, o un guion si no escalo
   * ninguna en el periodo -- nunca "undefined" en pantalla.
   * @param {Record<string, number> | undefined} porMotivo
   */
  function motivoPrincipal(porMotivo) {
    const entradas = Object.entries(porMotivo ?? {});
    if (entradas.length === 0) return '—';
    return entradas.sort((a, b) => b[1] - a[1])[0][0];
  }
</script>

<PageHeader title="Agentes">
  {#snippet sub()}
    Quién es cada agente y qué herramientas puede usar.
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-sm" href="/agentes/flujo">Flujo de derivación</a>
    {#if esAdmin}
      <a class="v2-btn v2-btn-sm" href="/team">Quién usa cada agente</a>
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

{#if data.escalamiento}
  <!--
    No es un dato del catalogo de agentes, es la metrica de cuanto resuelve
    el asistente solo vs. cuanto pasa a un humano -- ver
    persistencia.tasa_escalamiento() y cli/reporte_escalamiento.py (la misma
    cuenta, corrida desde la terminal). Solo aparece si el backend respondio
    (data.escalamiento no es null): un fallo del calculo no debe tumbar la
    pantalla de agentes.
  -->
  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard
        label="Conversaciones (14 días)"
        value={String(data.escalamiento.total)}
        tone="slate"
      />
      <StatCard
        label="Escaladas a un humano"
        value={String(data.escalamiento.escaladas)}
        tone="clay"
        detail={`${Math.round(data.escalamiento.tasa * 100)}% del total`}
      />
      <StatCard
        label="Motivo principal"
        value={motivoPrincipal(data.escalamiento.por_motivo)}
        tone="ink"
      />
    </div>
  </div>
{/if}

{#if data.error}
  <p class="aviso-error">⚠️ {data.error}</p>
{:else if !data.agentes || data.agentes.length === 0}
  <p class="chat-vacio">No hay agentes configurados.</p>
{:else}
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
            <span class="marca-agente" aria-hidden="true"><ScanEye size={19} /></span>
            <div class="identidad">
              <h3>{agente.nombre}</h3>
              <p class="organizacion">Revisa conversaciones ya cerradas</p>
            </div>
            <span class="pill-orientacion pill-automatico">Automático</span>
          </div>

          <p class="descripcion">{agente.descripcion}</p>

          <p class="modelo-automatico">
            Modelo: <strong>{agente.modelo || 'hereda el del rol que cierra cada conversación'}</strong>
          </p>
        </div>
      {:else}
        {@const grupos = porLoQueHace(agente.herramientas)}
        <div class="tarjeta">
          <div class="encabezado-tarjeta">
            <!--
              Un icono de robot, no las iniciales del nombre: lo primero que
              tiene que decir la tarjeta es QUE ES, y lo que hay detras no es
              una persona. La variante distingue a quien le habla -- con globo
              de dialogo si atiende al cliente final, sin el si es interno --
              asi la diferencia se ve antes de leer la etiqueta.

              En tono piedra, nunca en ambar: el ambar esta reservado para
              accion y para lo que exige atencion (el grupo 'Actua' de abajo).
              Gastarlo aca de adorno se la quita justo donde importa.
            -->
            <span class="marca-agente" aria-hidden="true">
              {#if agente.orientado_a === 'cliente_final'}
                <BotMessageSquare size={19} />
              {:else}
                <Bot size={19} />
              {/if}
            </span>
            <div class="identidad">
              <h3>{agente.nombre}</h3>
              {#if agente.area || agente.cargo}
                <!-- El separador se arma en JS: puesto como texto dentro de un
                     {#if}, Svelte le come el espacio de adelante y quedaba
                     "Agente de Soporte· Atencion al Cliente". -->
                <p class="organizacion">
                  {[agente.cargo, agente.area].filter(Boolean).join(' · ')}
                </p>
              {/if}
            </div>
            <span class="pill-orientacion" class:cliente={agente.orientado_a === 'cliente_final'}>
              {agente.orientado_a === 'cliente_final' ? 'Cliente final' : 'Uso interno'}
            </span>
          </div>

          <p class="descripcion">{resumen(agente.descripcion)}</p>

          <!--
            Reemplaza al diagrama radial que estaba aca. Ese gastaba ~250px de
            alto para decir "tiene 8 herramientas" peor que una lista: la
            posicion de cada nodo no significaba nada (todas cuelgan del
            agente, es un hecho), los nombres se truncaban a 16 caracteres --
            'consultar_cliente' y 'consultar_cliente_por_cedula' quedaban
            IDENTICOS en pantalla-- y las dos cosas que de verdad importan
            para revisar un agente, que escribe y que campos ve, no aparecian.
          -->
          <div class="herramientas">
            {#each grupos as grupo (grupo.clave)}
              <div class="grupo" class:grupo-actua={grupo.clave === 'actua'}>
                <div class="grupo-titulo">
                  {#if grupo.clave === 'actua'}<AlertTriangle size={12} />{/if}
                  {grupo.titulo}
                  <span class="grupo-cuenta">{grupo.items.length}</span>
                </div>
                {#each grupo.items as h (h.nombre)}
                  <div class="herramienta" title={h.descripcion || h.nombre}>
                    <span class="herr-nombre">{h.nombre}</span>
                    <span class="herr-campos">
                      {h.campos_permitidos.length
                        ? `${h.campos_permitidos.length} campo${h.campos_permitidos.length === 1 ? '' : 's'}`
                        : '—'}
                    </span>
                  </div>
                  {#if grupo.clave === 'actua'}
                    <p class="herr-aviso">
                      Cambia algo real{h.requiere_confirmacion
                        ? ' · pide confirmación antes'
                        : ''}
                    </p>
                  {/if}
                {/each}
              </div>
            {:else}
              <p class="v2-sub" style="font-size:12px">Sin herramientas asignadas.</p>
            {/each}
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
    color: var(--v2-rust);
    font-size: 14px;
  }
  .chat-vacio {
    color: var(--v2-slate);
    font-size: 14px;
  }
  .grilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }
  .tarjeta {
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    background: var(--v2-card);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  /* Icono, identidad y etiqueta en una fila: el bloque que se lee primero. */
  .encabezado-tarjeta {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .marca-agente {
    flex: none;
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 9px;
    background: var(--v2-line-soft);
    border: 1px solid var(--v2-line);
    color: var(--v2-ink);
  }
  .identidad {
    min-width: 0;
    flex: 1;
  }
  /* 17px contra los 12px de la descripcion: sin ese salto la tarjeta se lee
     como una lista uniforme y el nombre no ancla nada. */
  .encabezado-tarjeta h3 {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
    line-height: 1.2;
    text-transform: capitalize;
    color: var(--v2-ink);
  }
  .organizacion {
    margin: 2px 0 0;
    font-size: 11.5px;
    color: var(--v2-slate);
  }
  .pill-orientacion {
    flex: none;
    align-self: center;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--v2-line-soft);
    border: 1px solid var(--v2-line);
    color: var(--v2-slate);
    white-space: nowrap;
  }
  /* El unico agente que le habla a alguien de afuera: se marca, pero con
     'moss' (positivo, uso moderado), no con ambar. */
  .pill-orientacion.cliente {
    color: var(--v2-moss);
    border-color: color-mix(in oklab, var(--v2-moss) 30%, transparent);
    background: color-mix(in oklab, var(--v2-moss) 8%, transparent);
  }
  .tarjeta-automatica {
    border-style: dashed;
    background: var(--v2-line-soft);
  }
  .modelo-automatico {
    font-size: 11px;
    color: var(--v2-slate);
    margin: 0;
  }
  .descripcion {
    font-size: 12px;
    line-height: 1.55;
    color: var(--v2-ink);
    opacity: 0.78;
    margin: 0;
  }
  .herramientas {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .grupo-titulo {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--v2-slate);
    margin-bottom: 5px;
  }
  .grupo-cuenta {
    font-weight: 400;
    opacity: 0.8;
  }
  /* 'Actua' es el unico grupo con consecuencias: se separa del resto en vez
     de distinguirse solo por color, que a un daltonico no le dice nada. */
  .grupo-actua {
    border-top: 1px solid var(--v2-line);
    padding-top: 10px;
  }
  .grupo-actua .grupo-titulo {
    color: var(--v2-ember);
  }
  .herramienta {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    font-size: 12px;
    padding: 2.5px 0;
  }
  .herr-nombre {
    color: var(--v2-ink);
    word-break: break-word;
  }
  .herr-campos {
    flex-shrink: 0;
    font-size: 11px;
    color: var(--v2-slate);
    font-variant-numeric: tabular-nums;
  }
  .herr-aviso {
    margin: 0 0 2px;
    font-size: 10.5px;
    color: var(--v2-ember);
  }
  .acciones-tarjeta {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-top: 4px;
    border-top: 1px solid var(--v2-line);
    margin-top: 4px;
  }
  .confirmar-borrado {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .recibe {
    border-top: 1px solid var(--v2-line);
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
    color: var(--v2-slate);
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
    color: var(--v2-ink);
    opacity: 0.82;
    background: var(--v2-line-soft);
    border-radius: 6px;
    padding: 7px 9px;
    max-height: 190px;
    overflow-y: auto;
  }
</style>
