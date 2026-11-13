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
  import { rotuloDe } from '$lib/conversaciones/rotulos.js';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import DocumentoSubirDialog from '$lib/components/manual/DocumentoSubirDialog.svelte';
  import CorregirAgente from '$lib/components/manual/CorregirAgente.svelte';
  import CasoDorado from '$lib/components/manual/CasoDorado.svelte';
  import { toast } from 'svelte-sonner';

  /** @type {{ data: any }} */
  let { data } = $props();

  // La palabra de la empresa si la tiene (lib/conversaciones/rotulos.js); un
  // caso recién agregado usa lo que la persona escribió.
  const etiqueta = (c) => rotuloDe(c, { ...rotulosGuardados, ...rotulosNuevos });
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
      version: doc.version,
      // El estado REAL que devolvio la carga, no 'vigente' fijo: desde que
      // existe la habilitacion, un documento subido entra PENDIENTE y no lo
      // recupera el asistente hasta que alguien lo habilite. Darlo por
      // vigente aca mostraria como publicado algo que esta invisible, que es
      // justo lo contrario de lo que la pantalla tiene que dejar claro.
      estado: doc.estado ?? 'pendiente',
      n_fragmentos: doc.fragmentos,
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

  /**
   * Los roles tildados que atienden a un CLIENTE FINAL.
   *
   * Es lo que decide si mostrar el aviso: el riesgo del corpus no es que
   * falle el filtro por rol -- vive en SQL y es fail-closed -- sino que
   * alguien tilde el rol equivocado al asignar. Los nombres se parecen
   * ('soporte' es el técnico en campo, 'soporte_tecnico_cliente' atiende por
   * WhatsApp) y el sistema hace exactamente lo que le dicen, sin error.
   *
   * @param {string} id
   */
  function rolesDeClienteElegidos(id) {
    const deCliente = new Set(data.rolesDeCliente || []);
    return Object.keys(rolesEnEdicion[id] || {})
      .filter((r) => rolesEnEdicion[id][r] && deCliente.has(r));
  }

  /** Los roles YA guardados de un documento que atienden clientes finales. */
  function rolesDeClienteDe(/** @type {any} */ doc) {
    const deCliente = new Set(data.rolesDeCliente || []);
    return (doc.roles_permitidos || []).filter((/** @type {string} */ r) => deCliente.has(r));
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

  /** @type {Record<string, boolean>} */
  let aprobando = $state({});

  /**
   * Habilita un documento pendiente para que el asistente pueda usarlo.
   *
   * Un documento subido queda PENDIENTE: se vectoriza pero match_chunks no
   * lo recupera (el filtro esta en SQL, ver supabase/202608231328_aprobacion_documentos). Sin este paso
   * intermedio, subir un archivo era publicarlo -- y una guia escrita para
   * un tecnico en campo, asignada por error a un rol de cliente, le diria a
   * alguien que abra conectores de fibra o mida potencia optica.
   */
  async function aprobarDocumento(/** @type {any} */ doc) {
    aprobando = { ...aprobando, [doc.id]: true };
    try {
      const resp = await fetch(`/api/corpus/documentos/${doc.id}/aprobar`, {
        method: 'POST'
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo aprobar el documento');
        return;
      }
      documentos = documentos.map((/** @type {any} */ d) =>
        d.id === doc.id ? { ...d, estado: 'vigente' } : d);
      toast.success('Habilitado. El asistente ya puede usarlo.');
    } finally {
      aprobando = { ...aprobando, [doc.id]: false };
    }
  }

  // Copia local mutable: quitar una marca la saca de la pantalla al toque,
  // sin esperar a recargar la pagina entera (ver quitarMarca abajo).
  let ejemplos = $state(data.ejemplos ?? []);

  // La lista viva de tipos de caso (editable mas abajo). Se declara antes de
  // 'porCaso' porque ese derived la lee.
  let casos = $state([...(data.casos ?? [])]);

  /**
   * LO ENSAYADO NO SE MEZCLA CON LO REAL (12/11/2026). Se marca un ejemplo
   * desde Conversaciones o desde el Simulador, y la pantalla los mostraba
   * iguales: una prueba del equipo se leía como algo que pasó con un cliente.
   * Real o no lo decide el motor (`real`, con la misma lista de canales que la
   * autonomía ganada); acá solo se rotula y, si se quiere, se oculta.
   */
  let ocultarSimuladas = $state(false);
  const visible = (/** @type {any} */ x) => !ocultarSimuladas || x.real !== false;

  const porCaso = $derived(
    (casos || []).map((caso) => ({
      caso,
      ejemplos: ejemplos.filter((e) => e.caso === caso && visible(e))
    }))
  );
  /**
   * El caso dorado abierto en pantalla: { clave, yaml, avisos } o un error.
   * Una sola clave a la vez (`ejemplos:<id>` / `revisiones:<id>`).
   * @type {Record<string, any>}
   */
  let casosDorados = $state({});

  /** @param {'ejemplos'|'revisiones'} tipo @param {string} id */
  async function convertirEnCasoDorado(tipo, id) {
    const clave = `${tipo}:${id}`;
    if (casosDorados[clave]) {
      casosDorados = { ...casosDorados, [clave]: undefined };
      return;
    }
    casosDorados = { ...casosDorados, [clave]: { cargando: true } };
    try {
      const resp = await fetch(`/api/manual/caso-dorado?tipo=${tipo}&id=${encodeURIComponent(id)}`);
      const datos = await resp.json().catch(() => ({}));
      casosDorados = {
        ...casosDorados,
        [clave]: resp.ok
          ? { yaml: datos.caso_dorado, avisos: datos.avisos ?? [], origen: datos.origen }
          : { error: datos.error || 'No se pudo armar el caso dorado.' }
      };
    } catch {
      casosDorados = { ...casosDorados, [clave]: { error: 'No se pudo contactar al asistente.' } };
    }
  }

  const totalMarcado = $derived(ejemplos.length);

  // --- Tipos de caso -------------------------------------------------------
  // Es la lista con la que el asistente clasifica CADA conversacion (queda en
  // la pildora de la bandeja). Se edita aca y no en un YAML porque cambia con
  // el uso del negocio: agregar "instalacion_nueva" no deberia necesitar a un
  // desarrollador.
  let editandoCasos = $state(false);
  let casoNuevo = $state('');
  /* Lo que la persona ESCRIBIÓ al agregar cada caso (29/10/2026). La clave se
     normaliza -- «Problema de TV» se guarda como `problema_de_tv` -- y lo
     escrito se tiraba, cuando es justamente cómo se lee. Viaja con el
     guardado para que la clave no nazca sin rótulo. */
  /** @type {Record<string, string>} */
  let rotulosNuevos = $state({});
  /** Los ya guardados; se reemplazan con lo que devuelve el motor al guardar. */
  /** @type {Record<string, string>} */
  let rotulosGuardados = $state({ ...(data.rotulos ?? {}) });
  let guardandoCasos = $state(false);
  // Copia de respaldo para poder cancelar sin recargar la pagina.
  let casosAntes = $state([]);

  function abrirEdicionCasos() {
    casosAntes = [...casos];
    casoNuevo = '';
    rotulosNuevos = {};
    editandoCasos = true;
  }

  function cancelarEdicionCasos() {
    casos = [...casosAntes];
    rotulosNuevos = {};
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
    // Si lo escrito dice algo más que la clave (una tilde, una mayúscula),
    // ése es su rótulo. Si es igual a la clave con espacios, no aporta nada.
    const escrito = casoNuevo.trim().replace(/\s+/g, ' ');
    if (escrito && escrito !== limpio.replaceAll('_', ' ')) {
      rotulosNuevos = { ...rotulosNuevos, [limpio]: escrito.slice(0, 60) };
    }
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
        body: JSON.stringify({
          casos,
          // Solo los de casos que siguen en la lista: uno agregado y quitado
          // antes de guardar no tiene nada que rotular.
          rotulos: Object.fromEntries(
            Object.entries(rotulosNuevos).filter(([k]) => casos.includes(k))
          )
        })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos.error || 'No se pudieron guardar los tipos de caso');
        return;
      }
      casos = datos.casos;
      if (datos.rotulos) rotulosGuardados = datos.rotulos;
      rotulosNuevos = {};
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
  const pendientes = $derived(revisiones.filter((r) => r.estado === 'pendiente' && visible(r)));
  const yaRevisadas = $derived(revisiones.filter((r) => r.estado !== 'pendiente' && visible(r)));
  let verRevisadas = $state(false);
  const nSimuladas = $derived(
    ejemplos.filter((e) => e.real === false).length
      + revisiones.filter((r) => r.real === false).length
  );

  /**
   * Aprobar una revisión TIENE UN EFECTO desde el 12/11/2026: la conversación
   * pasa a ser un caso dorado (la trae cli/importar_casos_dorados.py) y el
   * motor devuelve el caso ya armado, que se muestra en el momento. Solo se
   * aprueba una de buen ejemplo: el motor rechaza (409) la otra.
   */
  async function resolverRevision(r, accion) {
    const resp = await fetch(`/api/manual/revisiones/${r.id}/${accion}`, { method: 'POST' });
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      toast.error(datos?.error || 'No se pudo guardar.');
      return;
    }
    const estado = accion === 'aprobar' ? 'aprobado' : 'descartado';
    revisiones = revisiones.map((x) => (x.id === r.id ? { ...x, estado } : x));
    if (accion === 'aprobar') {
      if (datos.caso_dorado) {
        casosDorados = {
          ...casosDorados,
          [`revisiones:${r.id}`]: { yaml: datos.caso_dorado, avisos: datos.avisos ?? [], origen: datos.origen }
        };
        verRevisadas = true;
      }
      toast.success(datos.sin_caso
        ? `Aprobada. ${datos.sin_caso}`
        : 'Aprobada: ya es un caso dorado. Copialo o traelo con el importador.');
    }
  }
</script>

<PageHeader title="Manual">
  {#snippet sub()}
    Respuestas del agente marcadas como buen ejemplo, agrupadas por caso — base para redactar el
    procedimiento de cada una. Se marca desde Conversaciones o el Simulador de WhatsApp. Cada ejemplo
    y cada revisión aprobada se convierte en un caso dorado: la prueba con la que se mide al agente.
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
                <Pill
                  tone={doc.estado === 'vigente'
                    ? 'moss'
                    : doc.estado === 'pendiente'
                      ? 'clay'
                      : 'slate'}
                >
                  {doc.estado === 'pendiente' ? 'sin habilitar' : doc.estado}
                </Pill>
                {#if !doc.roles_permitidos || doc.roles_permitidos.length === 0}
                  <Pill tone="clay">sin roles</Pill>
                {/if}
              </summary>
              <div class="doc-cuerpo">
                {#if doc.estado === 'pendiente'}
                  <!--
                    Se habla de HABILITAR, no de aprobar. Un documento de la
                    empresa ya viene aprobado por su propio circuito de
                    calidad antes de llegar acá; lo que se decide en esta
                    pantalla es otra cosa, que nadie decidió antes: que el
                    asistente lo use, y con qué roles. La guía técnica de un
                    ISP puede estar perfectamente aprobada y aun así ser
                    peligrosa si se la muestra a un cliente.
                  -->
                  <div class="doc-pendiente">
                    <b>El asistente todavía no puede usar este documento.</b>
                    <p>
                      Está cargado y procesado, pero no se va a recuperar en ninguna conversación
                      hasta que lo habilites. Esto no aprueba el documento — eso lo hace el circuito
                      de calidad de la empresa — sino que decide que el asistente puede usarlo, y
                      para qué roles.
                      {#if rolesDeClienteDe(doc).length > 0}
                        Va a quedar visible para <b>{rolesDeClienteDe(doc).join(', ')}</b>, que
                        atiende clientes finales: desplegá los fragmentos y leé lo que el asistente
                        les diría.
                      {/if}
                    </p>
                    {#if esAdmin}
                      <button
                        type="button"
                        class="v2-btn v2-btn-primary v2-btn-sm"
                        disabled={aprobando[doc.id]}
                        onclick={() => aprobarDocumento(doc)}
                      >
                        {aprobando[doc.id] ? 'Habilitando…' : 'Habilitar para el asistente'}
                      </button>
                    {:else}
                      <span class="v2-sub">Lo tiene que habilitar un administrador.</span>
                    {/if}
                  </div>
                {/if}
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
                        <label
                          class="doc-rol-check"
                          class:doc-rol-cliente={(data.rolesDeCliente || []).includes(rol)}
                        >
                          <input
                            type="checkbox"
                            checked={!!rolesEnEdicion[doc.id]?.[rol]}
                            onchange={() => toggleRolEdicion(doc.id, rol)}
                          />
                          {rol}
                        </label>
                      {/each}
                      {#if rolesDeClienteElegidos(doc.id).length > 0}
                        <!--
                          Aparece SOLO cuando se le va a dar el documento a un
                          rol que atiende clientes finales, no en cada
                          edicion. Un aviso que sale siempre se deja de leer;
                          este sale en la accion que de verdad importa.

                          El riesgo no es que el filtro por rol falle -- esta
                          en SQL y es fail-closed -- sino que alguien tilde el
                          rol equivocado: 'soporte' es el tecnico en campo y
                          'soporte_tecnico_cliente' atiende por WhatsApp, y
                          el sistema hace exactamente lo que le dicen.
                        -->
                        <p class="doc-aviso-cliente">
                          Le estás dando este documento a
                          <b>{rolesDeClienteElegidos(doc.id).join(', ')}</b>, que
                          {rolesDeClienteElegidos(doc.id).length === 1 ? 'atiende' : 'atienden'}
                          clientes finales. Revisá que su contenido no sean instrucciones para
                          personal técnico — abrir cajas, manipular fibra, medir señal — porque el
                          asistente se las puede repetir a un cliente. Podés desplegar los
                          fragmentos acá abajo para leer exactamente lo que recuperaría.
                        </p>
                      {/if}
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

      {#if nSimuladas > 0}
        <label class="v2-sub filtro-simuladas">
          <input type="checkbox" bind:checked={ocultarSimuladas} />
          Ocultar lo que viene del simulador ({nSimuladas})
        </label>
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
                {#if r.real === false}<Pill tone="slate">simulador</Pill>{/if}
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
                <a href="/conversaciones/{r.conversation_id}">Ver conversación completa</a>
                {#if esAdmin}
                  · <a href="/simulador-whatsapp?reproducir={r.conversation_id}">Reproducir en el simulador</a>
                  ·
                  {#if r.es_buen_ejemplo}
                    <!-- Aprobar = queda como caso dorado (12/11/2026). Antes
                         el botón guardaba un estado que no leía nadie. -->
                    <button type="button" class="quitar-marca-link" style="color:var(--v2-moss,#15803d)"
                      title="Queda como caso dorado: la prueba con la que se mide al agente"
                      onclick={() => resolverRevision(r, 'aprobar')}>
                      Aprobar como caso dorado
                    </button> ·
                  {/if}
                  <button type="button" class="quitar-marca-link" onclick={() => resolverRevision(r, 'descartar')}>
                    Descartar
                  </button>
                {/if}
              </div>
              {#if esAdmin && !r.es_buen_ejemplo}
                <!-- Una con problemas no se aprueba: su traza no es lo que
                     debería pasar. Lo útil es escribirle al agente el
                     procedimiento que le faltó (queda propuesto en Habilidades)
                     y después descartarla. -->
                <div class="revision-corregir">
                  <CorregirAgente
                    rol={r.rol_efectivo ?? null}
                    textoDeLaRespuesta={r.aporte_sugerido || r.justificacion || ''}
                    conversacionId={r.conversation_id}
                  />
                </div>
              {/if}
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
                  {#if r.real === false}<Pill tone="slate">simulador</Pill>{/if}
                  {#if r.caso}<span style="margin-left:6px">{etiqueta(r.caso)}</span>{/if}
                </div>
                <div class="ejemplo-pregunta" style="margin-top:8px">
                  <b>Cliente escribió:</b> {r.primer_mensaje || '—'}
                </div>
                <div class="ejemplo-meta v2-sub">
                  {r.revisado_por ? `Por ${r.revisado_por} · ` : ''}{relativeTime(r.revisado_en || r.creado_en)} ·
                  <a href="/conversaciones/{r.conversation_id}">Ver conversación completa</a>
                  {#if esAdmin && r.estado === 'aprobado' && r.es_buen_ejemplo}
                    ·
                    <button type="button" class="caso-dorado-link"
                      onclick={() => convertirEnCasoDorado('revisiones', r.id)}>
                      {casosDorados[`revisiones:${r.id}`] ? 'Ocultar el caso dorado' : 'Ver el caso dorado'}
                    </button>
                  {/if}
                </div>
                {#if casosDorados[`revisiones:${r.id}`]}
                  <CasoDorado estado={casosDorados[`revisiones:${r.id}`]} nombreArchivo={`caso-revision-${r.id.slice(0, 8)}.yaml`} />
                {/if}
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
            Escribilo como se lee («Problema de TV»): así aparece en la Bandeja, y por
            dentro se guarda en minúscula y con guiones bajos. «otro» no se puede quitar: es lo que
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
                  {#if e.real === false}
                    <div style="margin-bottom:6px"><Pill tone="slate">simulador</Pill></div>
                  {/if}
                  <div class="ejemplo-pregunta"><b>Cliente:</b> {e.pregunta || '—'}</div>
                  <div class="ejemplo-respuesta"><b>Agente:</b> {e.respuesta}</div>
                  <div class="ejemplo-meta v2-sub">
                    {#if e.marcado_por}Marcado por {e.marcado_por} ·{/if}
                    {relativeTime(e.creado_en)} ·
                    <a href="/conversaciones/{e.conversation_id}">Ver conversación completa</a> ·
                    <button type="button" class="quitar-marca-link" onclick={() => quitarMarca(e)}>
                      Quitar marca
                    </button>
                    {#if esAdmin}
                      ·
                      <button type="button" class="caso-dorado-link"
                        onclick={() => convertirEnCasoDorado('ejemplos', e.id)}>
                        {casosDorados[`ejemplos:${e.id}`] ? 'Ocultar el caso dorado' : 'Convertir en caso dorado'}
                      </button>
                      · <a href="/simulador-whatsapp?reproducir={e.conversation_id}">Reproducir en el simulador</a>
                    {/if}
                  </div>
                  {#if casosDorados[`ejemplos:${e.id}`]}
                    <CasoDorado estado={casosDorados[`ejemplos:${e.id}`]} nombreArchivo={`caso-ejemplo-${String(e.id).slice(0, 8)}.yaml`} />
                  {/if}
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
    color: var(--v2-rust);
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
    color: var(--v2-ember-text);
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
    border: 1px solid var(--v2-line);
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
    color: var(--v2-slate);
  }
  .caso-quitar:hover { color: var(--v2-rust); }
  .casos-alta { display: flex; gap: 8px; margin-top: 12px; }
  .caso-input {
    flex: 1;
    min-width: 0;
    padding: 5px 9px;
    border: 1px solid var(--v2-line-strong);
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
  .filtro-simuladas {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    margin-top: 16px;
  }
  .caso-dorado-link {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    font-size: 11.5px;
    color: var(--v2-ember-text);
    cursor: pointer;
    text-decoration: underline;
  }
  .revision-corregir {
    margin-top: 8px;
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
    border-top: 1px solid var(--v2-line);
  }
  .doc-seccion {
    font-size: 12px;
    font-weight: 600;
    color: var(--v2-slate);
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

  /* Un documento sin aprobar no es un detalle mas de la ficha: es la razon
     por la que ese documento todavia no hace nada. Va arriba y se distingue
     del resto del cuerpo. */
  .doc-pendiente {
    background: color-mix(in oklab, var(--v2-clay, #b4642e) 8%, transparent);
    border: 1px solid color-mix(in oklab, var(--v2-clay, #b4642e) 35%, transparent);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 14px;
  }
  .doc-pendiente b {
    font-size: 12.5px;
  }
  .doc-pendiente p {
    font-size: 12px;
    line-height: 1.5;
    color: var(--v2-slate);
    margin: 6px 0 10px;
    max-width: 68ch;
  }

  /* Un rol que atiende clientes finales se distingue de los internos en la
     propia lista: es la diferencia que hay que ver ANTES de tildar, no
     después. */
  .doc-rol-cliente {
    color: var(--v2-clay, #b4642e);
    font-weight: 550;
  }

  .doc-aviso-cliente {
    flex-basis: 100%;
    background: color-mix(in oklab, var(--v2-clay, #b4642e) 8%, transparent);
    border: 1px solid color-mix(in oklab, var(--v2-clay, #b4642e) 30%, transparent);
    border-radius: 8px;
    padding: 10px 12px;
    margin: 4px 0 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--v2-slate);
    max-width: 70ch;
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
