<script>
  /**
   * Revision de lo marcado como "buen ejemplo" en Conversaciones y el
   * Simulador de WhatsApp (ver MarcarEjemplo.svelte), agrupado por
   * caso/proceso (tenant_config.manual.casos). Es la materia prima para
   * redactar el procedimiento de cada caso.
   *
   * "Documentos publicados" ya no es solo lectura: un ADMIN puede subir un
   * .docx nuevo (DocumentoSubirDialog, que fragmenta y vectoriza al momento)
   * y corregir a que roles se le muestra un documento ya cargado, sin
   * re-vectorizar (PUT /api/corpus/documentos/<id>/roles).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import DocumentoSubirDialog from '$lib/components/manual/DocumentoSubirDialog.svelte';
  import { toast } from 'svelte-sonner';

  /** @type {{ data: any }} */
  let { data } = $props();

  const etiqueta = (c) => c.replaceAll('_', ' ');
  const esAdmin = $derived(data.role === 'ADMIN');

  let dialogoSubirAbierto = $state(false);

  // Copia local mutable, mismo motivo que 'ejemplos' mas abajo: subir un
  // documento o cambiarle los roles actualiza la pantalla al toque.
  let documentos = $state(data.documentos ?? []);

  /** El POST de subida no devuelve la misma forma que el GET de listado
   * (ver nucleo/ingesta/corpus.py::ingerir) -- se traduce aca. 'yaExistia'
   * cubre el caso raro de resubir el mismo codigo+version: reemplaza la fila
   * en vez de duplicarla. */
  function alSubirDocumento(/** @type {any} */ doc) {
    const entrada = {
      id: doc.document_id, codigo: doc.codigo, titulo: doc.titulo,
      version: doc.version, estado: 'vigente', n_fragmentos: doc.fragmentos,
      roles_permitidos: doc.roles_permitidos, fecha_vigencia: null,
      creado_en: new Date().toISOString()
    };
    const yaExistia = documentos.some((/** @type {any} */ d) => d.id === entrada.id);
    documentos = yaExistia
      ? documentos.map((/** @type {any} */ d) => (d.id === entrada.id ? entrada : d))
      : [entrada, ...documentos];
  }

  /** @type {Record<string, boolean>} */
  let editandoRoles = $state({});
  /** @type {Record<string, Record<string, boolean>>} */
  let rolesEnEdicion = $state({});
  /** @type {Record<string, boolean>} */
  let guardandoRoles = $state({});

  function abrirEdicionRoles(/** @type {any} */ doc) {
    const actuales = new Set(doc.roles_permitidos || []);
    /** @type {Record<string, boolean>} */
    const marcados = {};
    for (const r of data.roles || []) marcados[r] = actuales.has(r);
    rolesEnEdicion = { ...rolesEnEdicion, [doc.id]: marcados };
    editandoRoles = { ...editandoRoles, [doc.id]: true };
  }

  function toggleRolEdicion(/** @type {string} */ id, /** @type {string} */ rol) {
    const actual = rolesEnEdicion[id] || {};
    rolesEnEdicion = { ...rolesEnEdicion, [id]: { ...actual, [rol]: !actual[rol] } };
  }

  async function guardarRoles(/** @type {any} */ doc) {
    guardandoRoles = { ...guardandoRoles, [doc.id]: true };
    try {
      const elegidos = Object.keys(rolesEnEdicion[doc.id] || {})
        .filter((r) => rolesEnEdicion[doc.id][r]);
      const resp = await fetch(`/api/corpus/documentos/${doc.id}/roles`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles: elegidos })
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudieron actualizar los roles');
        return;
      }
      documentos = documentos.map((/** @type {any} */ d) =>
        d.id === doc.id ? { ...d, roles_permitidos: datos.roles_permitidos } : d);
      editandoRoles = { ...editandoRoles, [doc.id]: false };
      toast.success('Roles actualizados.');
    } finally {
      guardandoRoles = { ...guardandoRoles, [doc.id]: false };
    }
  }

  // Copia local mutable: quitar una marca la saca de la pantalla al toque,
  // sin esperar a recargar la pagina entera (ver quitarMarca abajo).
  let ejemplos = $state(data.ejemplos ?? []);

  // La lista viva de tipos de caso (editable mas abajo). Se declara antes de
  // 'porCaso' porque ese derived la lee.
  let casos = $state([...(data.casos ?? [])]);

  const porCaso = $derived(
    (casos || []).map((caso) => ({
      caso,
      ejemplos: ejemplos.filter((e) => e.caso === caso)
    }))
  );

  const totalMarcado = $derived(ejemplos.length);

  // --- Tipos de caso -------------------------------------------------------
  // Es la lista con la que el asistente clasifica CADA conversacion (queda en
  // la pildora de la bandeja). Se edita aca y no en un YAML porque cambia con
  // el uso del negocio: agregar "instalacion_nueva" no deberia necesitar a un
  // desarrollador.
  let editandoCasos = $state(false);
  let casoNuevo = $state('');
  let guardandoCasos = $state(false);
  // Copia de respaldo para poder cancelar sin recargar la pagina.
  let casosAntes = $state([]);

  function abrirEdicionCasos() {
    casosAntes = [...casos];
    casoNuevo = '';
    editandoCasos = true;
  }

  function cancelarEdicionCasos() {
    casos = [...casosAntes];
    editandoCasos = false;
  }

  function agregarCaso() {
    // Se normaliza aca lo mismo que el motor exige, para que el error mas
    // comun (escribir "Problema de TV") se resuelva solo en vez de volver
    // como un rechazo del servidor.
    const limpio = casoNuevo.trim().toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    if (!limpio) return;
    if (casos.includes(limpio)) {
      toast.error(`'${limpio}' ya esta en la lista.`);
      return;
    }
    casos = [...casos, limpio];
    casoNuevo = '';
  }

  function quitarCaso(caso) {
    casos = casos.filter((c) => c !== caso);
  }

  /** Manda la lista completa: el motor valida el conjunto (que quede 'otro',
   * que no se borre un caso del que dependa el agendamiento automatico) y
   * devuelve el motivo exacto si algo no cierra. */
  async function guardarCasos() {
    guardandoCasos = true;
    try {
      const resp = await fetch('/api/manual/casos', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ casos })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos.error || 'No se pudieron guardar los tipos de caso');
        return;
      }
      casos = datos.casos;
      editandoCasos = false;
      toast.success('Tipos de caso actualizados');
    } catch (err) {
      toast.error('No se pudo contactar al asistente');
    } finally {
      guardandoCasos = false;
    }
  }


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

  // Copia local mutable, mismo motivo que 'ejemplos': aprobar/descartar
  // actualiza la pantalla al toque, sin recargar todo.
  let revisiones = $state(data.revisiones ?? []);
  const pendientes = $derived(revisiones.filter((r) => r.estado === 'pendiente'));
  const yaRevisadas = $derived(revisiones.filter((r) => r.estado !== 'pendiente'));
  let verRevisadas = $state(false);

  async function resolverRevision(r, accion) {
    const resp = await fetch(`/api/manual/revisiones/${r.id}/${accion}`, { method: 'POST' });
    if (resp.ok) {
      const estado = accion === 'aprobar' ? 'aprobado' : 'descartado';
      revisiones = revisiones.map((x) => (x.id === r.id ? { ...x, estado } : x));
    }
  }
</script>

<PageHeader title="Manual">
  {#snippet sub()}
    Respuestas del agente marcadas como buen ejemplo, agrupadas por caso — base para redactar el
    procedimiento de cada una. Se marca desde Conversaciones o el Simulador de WhatsApp.
  {/snippet}
  {#snippet actions()}
    {#if esAdmin}
      <Button type="button" onclick={() => (dialogoSubirAbierto = true)}>Nuevo documento</Button>
    {/if}
  {/snippet}
</PageHeader>

{#if esAdmin}
  <DocumentoSubirDialog bind:open={dialogoSubirAbierto} roles={data.roles || []} onSubido={alSubirDocumento} />
{/if}

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
      {#if documentos.length > 0}
        <div class="v2-label" style="margin-bottom:10px">Documentos publicados</div>
        <div class="docs-lista">
          {#each documentos as doc (doc.id)}
            <details
              class="v2-card doc-detalle"
              ontoggle={(e) => e.currentTarget.open && cargarFragmentos(doc.id)}
            >
              <summary class="doc-resumen">
                <span class="doc-titulo">{doc.titulo}</span>
                <span class="v2-muted">{doc.codigo} · v{doc.version} · {doc.n_fragmentos} fragmento{doc.n_fragmentos === 1 ? '' : 's'}</span>
                <Pill tone={doc.estado === 'vigente' ? 'moss' : 'slate'}>{doc.estado}</Pill>
                {#if !doc.roles_permitidos || doc.roles_permitidos.length === 0}
                  <Pill tone="clay">sin roles</Pill>
                {/if}
              </summary>
              <div class="doc-cuerpo">
                <div class="doc-roles">
                  {#if !editandoRoles[doc.id]}
                    <span class="v2-sub">
                      {#if doc.roles_permitidos && doc.roles_permitidos.length > 0}
                        Visible para: {doc.roles_permitidos.join(', ')}
                      {:else}
                        Nadie lo puede consultar todavía — sin roles asignados.
                      {/if}
                    </span>
                    {#if esAdmin}
                      <button type="button" class="quitar-marca-link" onclick={() => abrirEdicionRoles(doc)}>
                        Editar roles
                      </button>
                    {/if}
                  {:else}
                    <div class="doc-roles-editor">
                      {#each data.roles || [] as rol (rol)}
                        <label class="doc-rol-check">
                          <input
                            type="checkbox"
                            checked={!!rolesEnEdicion[doc.id]?.[rol]}
                            onchange={() => toggleRolEdicion(doc.id, rol)}
                          />
                          {rol}
                        </label>
                      {/each}
                      <div class="doc-roles-acciones">
                        <button type="button" class="v2-btn v2-btn-sm" disabled={guardandoRoles[doc.id]}
                          onclick={() => guardarRoles(doc)}>
                          Guardar
                        </button>
                        <button type="button" class="v2-btn v2-btn-sm" disabled={guardandoRoles[doc.id]}
                          onclick={() => (editandoRoles = { ...editandoRoles, [doc.id]: false })}>
                          Cancelar
                        </button>
                      </div>
                    </div>
                  {/if}
                </div>
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

      <div class="v2-label" style="margin:24px 0 10px">
        Revisiones del supervisor
        <span class="v2-muted">({pendientes.length} pendiente{pendientes.length === 1 ? '' : 's'})</span>
      </div>
      {#if revisiones.length === 0}
        <p class="v2-sub" style="margin-bottom:16px">
          Todavía no hay conversaciones revisadas por el supervisor. Se generan solas cuando una
          conversación con un cliente termina resuelta.
        </p>
      {:else if pendientes.length === 0}
        <p class="v2-sub" style="margin-bottom:16px">Sin revisiones pendientes por ahora.</p>
      {:else}
        <div class="ejemplos-lista" style="margin-bottom:8px">
          {#each pendientes as r (r.id)}
            <div class="v2-card ejemplo-card">
              <div class="ejemplo-meta v2-sub" style="margin-top:0">
                <Pill tone={r.es_buen_ejemplo ? 'moss' : 'clay'}>
                  {r.es_buen_ejemplo ? 'Buen ejemplo' : 'Con problemas'}
                </Pill>
                {#if r.caso}<span style="margin-left:6px">{etiqueta(r.caso)}</span>{/if}
              </div>
              <div class="ejemplo-pregunta" style="margin-top:8px">
                <b>Cliente escribió:</b> {r.primer_mensaje || '—'}
              </div>
              <div class="ejemplo-respuesta"><b>Justificación:</b> {r.justificacion}</div>
              {#if r.aporte_sugerido}
                <div class="ejemplo-respuesta"><b>Aporte sugerido:</b> {r.aporte_sugerido}</div>
              {/if}
              <div class="ejemplo-meta v2-sub">
                {relativeTime(r.creado_en)} ·
                <a href="/conversaciones/{r.conversation_id}">Ver conversación completa</a> ·
                <button type="button" class="quitar-marca-link" style="color:var(--v2-moss,#15803d)"
                  onclick={() => resolverRevision(r, 'aprobar')}>
                  Aprobar
                </button> ·
                <button type="button" class="quitar-marca-link" onclick={() => resolverRevision(r, 'descartar')}>
                  Descartar
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
      {#if yaRevisadas.length > 0}
        <button type="button" class="v2-btn v2-btn-sm" style="margin-bottom:24px"
          onclick={() => (verRevisadas = !verRevisadas)}>
          {verRevisadas ? 'Ocultar' : 'Ver'} {yaRevisadas.length} ya revisada{yaRevisadas.length === 1 ? '' : 's'}
        </button>
        {#if verRevisadas}
          <div class="ejemplos-lista" style="margin-bottom:24px">
            {#each yaRevisadas as r (r.id)}
              <div class="v2-card ejemplo-card">
                <div class="ejemplo-meta v2-sub" style="margin-top:0">
                  <Pill tone={r.estado === 'aprobado' ? 'moss' : 'slate'}>{r.estado}</Pill>
                  {#if r.caso}<span style="margin-left:6px">{etiqueta(r.caso)}</span>{/if}
                </div>
                <div class="ejemplo-pregunta" style="margin-top:8px">
                  <b>Cliente escribió:</b> {r.primer_mensaje || '—'}
                </div>
                <div class="ejemplo-meta v2-sub">
                  {r.revisado_por ? `Por ${r.revisado_por} · ` : ''}{relativeTime(r.revisado_en || r.creado_en)} ·
                  <a href="/conversaciones/{r.conversation_id}">Ver conversación completa</a>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}

      <!-- Tipos de caso. Es la lista con la que el asistente etiqueta cada
           conversación sola; se edita acá para no tener que tocar la
           configuración del tenant a mano. -->
      <div class="v2-label casos-titulo" style="margin:24px 0 10px">
        <span>Tipos de caso</span>
        {#if esAdmin && !editandoCasos}
          <button class="casos-editar" onclick={abrirEdicionCasos}>Editar</button>
        {/if}
      </div>
      <p class="v2-sub" style="margin:-4px 0 12px">
        Con esta lista el asistente clasifica cada conversación por su cuenta y le pone
        la etiqueta en la bandeja. No hace falta que nadie la asigne a mano.
      </p>

      <div class="v2-card casos-caja">
        <div class="casos-lista">
          {#each casos as caso (caso)}
            <span class="caso-chip" class:editable={editandoCasos}>
              {etiqueta(caso)}
              {#if editandoCasos}
                <button
                  class="caso-quitar"
                  title={'Quitar ' + etiqueta(caso)}
                  aria-label={'Quitar ' + etiqueta(caso)}
                  onclick={() => quitarCaso(caso)}>×</button>
              {/if}
            </span>
          {/each}
        </div>

        {#if editandoCasos}
          <div class="casos-alta">
            <input
              class="caso-input"
              type="text"
              placeholder="Ej: instalación nueva"
              bind:value={casoNuevo}
              onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); agregarCaso(); } }}
            />
            <Button variant="outline" size="sm" onclick={agregarCaso}>Agregar</Button>
          </div>
          <p class="v2-sub casos-nota">
            Se guarda en minúscula y con guiones bajos. «otro» no se puede quitar: es lo que
            usa el asistente cuando ninguno encaja. Tampoco se puede quitar un caso del que
            dependa el agendamiento automático de visitas.
          </p>
          <div class="casos-acciones">
            <Button size="sm" onclick={guardarCasos} disabled={guardandoCasos}>
              {guardandoCasos ? 'Guardando…' : 'Guardar'}
            </Button>
            <Button variant="ghost" size="sm" onclick={cancelarEdicionCasos}>Cancelar</Button>
          </div>
        {/if}
      </div>

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
  .casos-titulo {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .casos-editar {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: var(--v2-accent, #b45309);
    cursor: pointer;
    text-transform: none;
    letter-spacing: 0;
  }
  .casos-editar:hover { text-decoration: underline; }
  .casos-caja { padding: 14px; margin-bottom: 8px; }
  .casos-lista { display: flex; flex-wrap: wrap; gap: 8px; }
  .caso-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    border: 1px solid var(--v2-linea, #e2e0db);
    font-size: 13px;
    line-height: 1.6;
  }
  .caso-chip.editable { padding-right: 5px; }
  .caso-quitar {
    background: none;
    border: none;
    padding: 0 2px;
    font-size: 15px;
    line-height: 1;
    cursor: pointer;
    color: var(--v2-sub, #7a736a);
  }
  .caso-quitar:hover { color: #b3261e; }
  .casos-alta { display: flex; gap: 8px; margin-top: 12px; }
  .caso-input {
    flex: 1;
    min-width: 0;
    padding: 5px 9px;
    border: 1px solid var(--v2-linea, #e2e0db);
    border-radius: 6px;
    font: inherit;
  }
  .casos-nota { margin: 8px 0 0; }
  .casos-acciones { display: flex; gap: 8px; margin-top: 12px; }

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

  .doc-roles {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 12px;
  }
  .doc-roles-editor {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    width: 100%;
  }
  .doc-rol-check {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12.5px;
  }
  .doc-roles-acciones {
    display: flex;
    gap: 6px;
    margin-left: auto;
  }
</style>
