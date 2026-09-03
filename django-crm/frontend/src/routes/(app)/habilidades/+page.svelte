<script>
  /**
   * Habilidades: procedimientos que un agente carga cuando le hacen falta.
   * Ver nucleo/habilidades/catalogo.py.
   *
   * Tres bloques:
   *   1. HUECOS -- que le falta saber hacer a cada agente, segun la
   *      operacion real (escaladas repetidas, "no tengo el procedimiento").
   *      Se pide bajo demanda: recorre conversaciones y puede tardar.
   *   2. PENDIENTES -- borradores sin aprobar, propios o del analista. Nunca
   *      entran al prompt de nadie hasta que se aprueban aca.
   *   3. VIGENTES -- las que ya operan, con cuantas veces se cargaron.
   *
   * Mismo patron que /configuracion-guiada y /manual: proponer y decidir
   * viven en la misma pantalla porque son parte del mismo flujo.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { toast } from 'svelte-sonner';

  /** @type {{ data: any }} */
  let { data } = $props();

  let habilidades = $state(data.habilidades ?? []);
  const roles = data.roles ?? [];

  const pendientes = $derived(habilidades.filter((/** @type {any} */ h) => h.estado === 'propuesta'));
  const vigentes = $derived(habilidades.filter((/** @type {any} */ h) => h.estado === 'vigente'));
  const obsoletas = $derived(habilidades.filter((/** @type {any} */ h) => h.estado === 'obsoleta'));
  let verObsoletas = $state(false);

  let huecos = $state(/** @type {any[] | null} */ (null));
  let buscandoHuecos = $state(false);
  let diasHuecos = $state(30);

  /** @type {Record<string, boolean>} */
  let ocupado = $state({});
  let proponiendo = $state(false);

  let creando = $state(false);
  let borrador = $state({ codigo: '', nombre: '', cuando_usarla: '', pasos: '' });

  /** Roles elegidos por habilidad, antes de aprobar -- separado de los datos
   *  del servidor para no mutar la lista mientras se edita. */
  /** @type {Record<string, string[]>} */
  let rolesElegidos = $state({});

  function rolesDe(/** @type {any} */ h) {
    if (!rolesElegidos[h.id]) rolesElegidos = { ...rolesElegidos, [h.id]: h.roles_permitidos ?? [] };
    return rolesElegidos[h.id];
  }

  function alternarRol(/** @type {any} */ h, /** @type {string} */ rol) {
    const actuales = rolesDe(h);
    const nuevos = actuales.includes(rol) ? actuales.filter((r) => r !== rol) : [...actuales, rol];
    rolesElegidos = { ...rolesElegidos, [h.id]: nuevos };
  }

  async function recargar() {
    try {
      const resp = await fetch('/api/habilidades');
      if (resp.ok) habilidades = (await resp.json()).habilidades ?? [];
    } catch {
      // El resto de la pantalla sigue viva; no vale un toast por un refresh.
    }
  }

  async function buscarHuecos() {
    buscandoHuecos = true;
    try {
      const resp = await fetch(`/api/habilidades?huecos=1&dias=${diasHuecos}`);
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo analizar.');
        return;
      }
      huecos = datos.huecos ?? [];
      if (huecos.length === 0) {
        toast.success('Ningún patrón alcanza el piso de casos en ese período.');
      }
    } finally {
      buscandoHuecos = false;
    }
  }

  async function proponerDesdeHuecos() {
    proponiendo = true;
    try {
      const resp = await fetch('/api/habilidades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion: 'proponer', dias: diasHuecos })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudieron redactar propuestas.');
        return;
      }
      const escritas = (datos.resultados ?? []).filter((/** @type {any} */ r) => r.propuesta);
      const sinRedactar = (datos.resultados ?? []).length - escritas.length;
      if (escritas.length) {
        toast.success(
          `${escritas.length} borrador(es) nuevo(s), pendiente(s) de revisión.` +
            (sinRedactar ? ` ${sinRedactar} patrón(es) sin redactar.` : '')
        );
      } else {
        toast.error('No se pudo redactar ningún borrador. Puede ser que al rol le falte una herramienta, no un procedimiento.');
      }
      await recargar();
      huecos = null;
    } finally {
      proponiendo = false;
    }
  }

  async function crearHabilidad() {
    if (!borrador.codigo.trim() || !borrador.nombre.trim() ||
        !borrador.cuando_usarla.trim() || !borrador.pasos.trim()) {
      toast.error('Completá los cuatro campos.');
      return;
    }
    creando = true;
    try {
      const resp = await fetch('/api/habilidades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion: 'crear', ...borrador })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo crear.');
        return;
      }
      toast.success('Guardada como propuesta. Asignale roles y aprobala abajo.');
      borrador = { codigo: '', nombre: '', cuando_usarla: '', pasos: '' };
      await recargar();
    } finally {
      creando = false;
    }
  }

  async function aprobar(/** @type {any} */ h) {
    const roles_permitidos = rolesDe(h);
    if (roles_permitidos.length === 0) {
      toast.error('Asignale al menos un rol antes de aprobar: sin rol no la ve ningún agente.');
      return;
    }
    ocupado = { ...ocupado, [h.id]: true };
    try {
      const resp = await fetch('/api/habilidades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion: 'aprobar', id: h.id, roles_permitidos })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo aprobar.');
        return;
      }
      toast.success('Procedimiento vigente. Ya está disponible para esos roles.');
      await recargar();
    } finally {
      ocupado = { ...ocupado, [h.id]: false };
    }
  }

  async function retirar(/** @type {any} */ h) {
    ocupado = { ...ocupado, [h.id]: true };
    try {
      const resp = await fetch('/api/habilidades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion: 'retirar', id: h.id })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo retirar.');
        return;
      }
      toast.success('Retirada. Ya no la puede cargar ningún agente.');
      await recargar();
    } finally {
      ocupado = { ...ocupado, [h.id]: false };
    }
  }
</script>

<PageHeader title="Habilidades">
  {#snippet sub()}
    Procedimientos que un agente carga cuando la situación lo pide. No son documentos del corpus:
    llegan enteros, o no llegan. Ninguno entra al prompt de nadie sin aprobarse acá.
  {/snippet}
</PageHeader>

{#if data.error}
  <p class="aviso-error">⚠️ {data.error}</p>
{:else}
  <div class="v2-pad" style="padding-top:14px;padding-bottom:32px;display:flex;flex-direction:column;gap:20px">

    <!-- === HUECOS ============================================== -->
    <section class="v2-card" style="padding:16px 18px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:space-between">
        <div>
          <div class="v2-label">¿Qué le falta a los agentes?</div>
          <p class="v2-sub" style="font-size:12.5px;margin:4px 0 0">
            Mira conversaciones reales de los últimos días: escaladas repetidas por el mismo motivo,
            y veces que el agente dijo no tener el procedimiento. No llama a ningún modelo todavía.
          </p>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <label class="v2-sub" style="font-size:12px;display:flex;gap:6px;align-items:center">
            Últimos
            <input class="v2-input" type="number" min="1" max="365" bind:value={diasHuecos}
              style="width:62px;text-align:center" />
            días
          </label>
          <button class="v2-btn v2-btn-primary" onclick={buscarHuecos} disabled={buscandoHuecos}>
            {buscandoHuecos ? 'Analizando…' : 'Buscar huecos'}
          </button>
        </div>
      </div>

      {#if huecos !== null}
        <div style="margin-top:14px;display:flex;flex-direction:column;gap:8px">
          {#if huecos.length === 0}
            <p class="v2-sub" style="font-size:12.5px">
              Ningún patrón alcanza el piso de casos en ese período. Puede ser buena señal, o que
              todavía no hay suficiente historial.
            </p>
          {:else}
            {#each huecos as hu}
              <div class="fila-hueco">
                <Pill tone={hu.senal === 'habilidad_insuficiente' ? 'rust' : 'slate'}>{hu.rol}</Pill>
                <div style="flex:1;min-width:0">
                  <span class="v2-num" style="font-weight:700">{hu.n_casos} casos</span>
                  <span class="v2-sub" style="font-size:12.5px">
                    — {hu.senal === 'escalada_repetida' ? `escaló por "${hu.motivo}"`
                      : hu.senal === 'sin_procedimiento' ? 'dijo no tener el procedimiento'
                      : `${hu.codigo_habilidad} no alcanzó`}
                  </span>
                </div>
              </div>
            {/each}
            <button class="v2-btn v2-btn-primary" style="align-self:flex-start;margin-top:4px"
              onclick={proponerDesdeHuecos} disabled={proponiendo}>
              {proponiendo ? 'Redactando (puede tardar)…' : `Redactar ${huecos.length} borrador(es)`}
            </button>
            <p class="v2-sub" style="font-size:11.5px;margin:0">
              Una llamada al modelo por patrón. Ninguno queda activo: se guardan como propuestas abajo.
            </p>
          {/if}
        </div>
      {/if}
    </section>

    <!-- === PENDIENTES ============================================ -->
    <section>
      <div class="v2-label" style="margin-bottom:10px">
        Pendientes de aprobar
        <span class="v2-muted">({pendientes.length})</span>
      </div>

      {#if pendientes.length === 0}
        <p class="v2-sub" style="font-size:12.5px">No hay ninguna esperando revisión.</p>
      {:else}
        <div style="display:flex;flex-direction:column;gap:10px">
          {#each pendientes as h (h.id)}
            <div class="v2-card tarjeta-propuesta">
              <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
                <div>
                  <span class="v2-num" style="font-size:11px;color:var(--v2-slate)">{h.codigo}</span>
                  <div style="font-weight:700;font-size:13.5px">{h.nombre}</div>
                </div>
                <Pill tone={h.origen === 'analisis' ? 'clay' : 'slate'}>
                  {h.origen === 'analisis' ? 'propuesta por el analista' : 'escrita a mano'}
                </Pill>
              </div>

              <div style="margin-top:8px">
                <div class="v2-sub" style="font-size:11px;text-transform:uppercase;letter-spacing:.4px">
                  Cuándo usarla
                </div>
                <div style="font-size:13px">{h.cuando_usarla}</div>
              </div>

              <details style="margin-top:8px">
                <summary class="v2-sub" style="font-size:12px;cursor:pointer">Ver los pasos</summary>
                <pre class="bloque-pasos">{h.pasos}</pre>
              </details>

              {#if h.evidencia?.n_casos}
                <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">
                  Motivada por {h.evidencia.n_casos} caso(s) reales
                  {#if h.evidencia.motivo} — {h.evidencia.motivo}{/if}
                  en los últimos {h.evidencia.dias_analizados ?? '?'} días.
                </p>
              {/if}

              <div style="margin-top:10px">
                <div class="v2-sub" style="font-size:11px;margin-bottom:5px">
                  Roles que la van a poder cargar
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  {#each roles as rol}
                    <button
                      type="button"
                      class="chip-rol"
                      class:activo={rolesDe(h).includes(rol)}
                      onclick={() => alternarRol(h, rol)}
                    >{rol}</button>
                  {/each}
                </div>
              </div>

              <div style="display:flex;gap:8px;margin-top:12px">
                <button class="v2-btn v2-btn-primary" onclick={() => aprobar(h)} disabled={ocupado[h.id]}>
                  Aprobar
                </button>
                <button class="v2-btn" onclick={() => retirar(h)} disabled={ocupado[h.id]}>
                  Descartar
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <!-- === CREAR A MANO =========================================== -->
    <section class="v2-card" style="padding:16px 18px">
      <div class="v2-label" style="margin-bottom:10px">Escribir un procedimiento</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <input class="v2-input" placeholder="Código (ej: HAB-RECLAMO-DUPLICADO)"
          bind:value={borrador.codigo} />
        <input class="v2-input" placeholder="Nombre" bind:value={borrador.nombre} />
        <textarea class="v2-input" rows="2"
          placeholder="Cuándo usarla — la condición que dispara el procedimiento"
          bind:value={borrador.cuando_usarla}></textarea>
        <textarea class="v2-input" rows="5"
          placeholder="Pasos, numerados: 1. ... 2. ..."
          bind:value={borrador.pasos}></textarea>
        <button class="v2-btn v2-btn-primary" style="align-self:flex-start"
          onclick={crearHabilidad} disabled={creando}>
          {creando ? 'Guardando…' : 'Guardar como propuesta'}
        </button>
      </div>
    </section>

    <!-- === VIGENTES =============================================== -->
    <section>
      <div class="v2-label" style="margin-bottom:10px">
        Vigentes
        <span class="v2-muted">({vigentes.length})</span>
      </div>
      {#if vigentes.length === 0}
        <p class="v2-sub" style="font-size:12.5px">Ningún agente tiene un procedimiento cargado todavía.</p>
      {:else}
        <div class="v2-card" style="padding:0;overflow:hidden">
          <table class="v2-table">
            <thead>
              <tr>
                <th>Código</th><th>Nombre</th><th>Roles</th><th>Usos</th><th></th>
              </tr>
            </thead>
            <tbody>
              {#each vigentes as h (h.id)}
                <tr>
                  <td class="v2-num" style="font-size:11.5px">{h.codigo}</td>
                  <td>{h.nombre}</td>
                  <td class="v2-sub" style="font-size:12px">{(h.roles_permitidos ?? []).join(', ')}</td>
                  <td class="v2-num">{h.usos}</td>
                  <td>
                    <button class="v2-btn v2-btn-sm" onclick={() => retirar(h)} disabled={ocupado[h.id]}>
                      Retirar
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>

    {#if obsoletas.length > 0}
      <button class="v2-btn v2-btn-sm" style="align-self:flex-start"
        onclick={() => (verObsoletas = !verObsoletas)}>
        {verObsoletas ? 'Ocultar' : 'Ver'} retiradas ({obsoletas.length})
      </button>
      {#if verObsoletas}
        <div style="display:flex;flex-direction:column;gap:6px">
          {#each obsoletas as h}
            <div class="v2-sub" style="font-size:12px">{h.codigo} — {h.nombre}</div>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .aviso-error {
    margin: 16px 18px;
    padding: 10px 14px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--v2-rust) 10%, transparent);
    color: var(--v2-rust);
    font-size: 13px;
  }

  .fila-hueco {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    background: var(--v2-surface-soft, rgba(0, 0, 0, 0.02));
    border-radius: 6px;
  }

  .tarjeta-propuesta {
    padding: 14px 16px;
  }

  .bloque-pasos {
    margin: 6px 0 0;
    padding: 10px 12px;
    background: var(--v2-surface-soft, rgba(0, 0, 0, 0.03));
    border-radius: 6px;
    font-family: ui-monospace, monospace;
    font-size: 12px;
    white-space: pre-wrap;
    line-height: 1.5;
  }

  .chip-rol {
    font-size: 11.5px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid var(--v2-line-soft);
    background: transparent;
    color: var(--v2-slate);
    cursor: pointer;
  }
  .chip-rol.activo {
    background: var(--v2-accent, #2563eb);
    border-color: var(--v2-accent, #2563eb);
    color: #fff;
  }

  .v2-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .v2-table th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: var(--v2-slate);
    padding: 10px 14px;
    border-bottom: 1px solid var(--v2-line-soft);
  }
  .v2-table td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--v2-line-soft);
    vertical-align: middle;
  }
  .v2-table tr:last-child td {
    border-bottom: none;
  }
</style>
