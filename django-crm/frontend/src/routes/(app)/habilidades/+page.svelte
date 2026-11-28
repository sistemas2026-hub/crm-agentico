<script>
  import { codigoDesde } from '$lib/components/manual/entrenar.js';

  /**
   * Guarda derivando el código del nombre cuando nadie lo escribió.
   *
   * No valida ni decide nada más: `crearHabilidad` sigue siendo quien habla
   * con el servidor y maneja el error. Esto solo le saca a la persona un
   * campo que no tiene por qué inventar.
   */
  function crearConCodigo() {
    if (!(borrador.codigo || '').trim() && (borrador.nombre || '').trim()) {
      borrador.codigo = codigoDesde(borrador.nombre);
    }
    return crearHabilidad();
  }
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

  /**
   * Los roles elegidos para esta habilidad, o los que ya tenía si nadie tocó
   * nada todavía.
   *
   * SOLO LEE. La primera versión escribía `rolesElegidos` acá para "sembrar"
   * el valor inicial — y como esto se llama desde la plantilla, Svelte 5 lo
   * corta con `state_unsafe_mutation` y la página entera no carga. El estado
   * se escribe únicamente cuando alguien hace clic (`alternarRol`).
   *
   * `pnpm check` no lo detecta: es un error de ejecución, no de tipos. Se ve
   * abriendo la página.
   */
  function rolesDe(/** @type {any} */ h) {
    return rolesElegidos[h.id] ?? h.roles_permitidos ?? [];
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

  /**
   * Los usos de una habilidad vigente, pedidos al abrir el detalle
   * (12/11/2026). La tabla decía «N usos» y nada más: no se podía ver en qué
   * conversaciones se cargó ni si escaló igual, que es justo lo que dice si el
   * procedimiento sirve. Los totales vienen calculados del motor.
   *
   * @type {Record<string, any>}
   */
  let usos = $state({});

  async function verUsos(/** @type {any} */ h) {
    if (usos[h.id] && usos[h.id] !== 'error') {
      usos = { ...usos, [h.id]: undefined };
      return;
    }
    usos = { ...usos, [h.id]: 'cargando' };
    try {
      const resp = await fetch(`/api/habilidades?usos=${encodeURIComponent(h.id)}`);
      const datos = await resp.json();
      usos = { ...usos, [h.id]: resp.ok ? datos : 'error' };
      if (!resp.ok) toast.error(datos?.error || 'No se pudieron leer los usos.');
    } catch {
      usos = { ...usos, [h.id]: 'error' };
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
<!-- Scroll propio: el contenedor de la app corta lo que se sale (.v2-main,
     overflow hidden). Sin esto la pantalla no bajaba (02/11/2026). -->
<div class="v2-scroll">

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
                  {#if (hu.conversaciones ?? []).length > 0}
                    <div class="casos-enlaces">
                      {#each hu.conversaciones.slice(0, 5) as cid, i (cid)}
                        <a href="/conversaciones/{cid}">caso {i + 1}</a>
                      {/each}
                      {#if hu.conversaciones.length > 5}
                        <span class="v2-muted">y {hu.conversaciones.length - 5} más</span>
                      {/if}
                    </div>
                  {/if}
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
                <!-- LA EVIDENCIA SE PUEDE ABRIR (12/11/2026). El motor guarda
                     hasta 20 conversaciones por propuesta y la pantalla solo
                     decía cuántas: quien aprueba lo que el agente seguirá «al
                     pie de la letra» decidía sin poder leer los casos. -->
                {#if (h.evidencia.conversaciones ?? []).length > 0}
                  <details class="evidencia">
                    <summary class="v2-sub">Leer los casos que la motivaron ({h.evidencia.conversaciones.length})</summary>
                    <ul>
                      {#each h.evidencia.conversaciones as cid, i (cid)}
                        <li>
                          <a href="/conversaciones/{cid}">Caso {i + 1}</a>
                          · <a class="v2-muted" href="/simulador-whatsapp?reproducir={cid}"
                            title="Reenvía lo que escribió el cliente a una conversación simulada nueva">reproducir en el simulador</a>
                        </li>
                      {/each}
                    </ul>
                  </details>
                {/if}
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
      <div class="v2-label" style="margin-bottom:10px">Enseñarle algo</div>
      <!-- EL CODIGO NO SE PIDE MAS (06/11/2026). El usuario: «para que el
           entrenamiento sea más fácil para cualquier persona». Pedirle a
           alguien de operaciones que invente un «HAB-RECLAMO-DUPLICADO»
           antes de poder escribir lo que sabe es la barrera, no un dato.

           `codigoDesde` lo deriva del nombre y ya existía: la usa el botón
           «Corregir» desde el 02/11, y esta pantalla la ignoraba. Eran dos
           formas distintas de hacer lo mismo, y la difícil era la que estaba
           a la vista. Se sigue pudiendo escribir uno a mano, plegado, para
           quien quiera elegirlo. -->
      <div style="display:flex;flex-direction:column;gap:8px">
        <input class="v2-input" placeholder="¿Qué tiene que saber hacer? (ej: Reclamo por cobro duplicado)"
          bind:value={borrador.nombre} />
        <textarea class="v2-input" rows="2"
          placeholder="¿Cuándo lo usa? — qué le tiene que decir el cliente para que aplique"
          bind:value={borrador.cuando_usarla}></textarea>
        <textarea class="v2-input" rows="5"
          placeholder="¿Qué tiene que hacer, paso por paso?&#10;1. Pedir el número de factura&#10;2. Verificar en el sistema&#10;3. Si está duplicado, derivar a facturación"
          bind:value={borrador.pasos}></textarea>
        <details style="font-size:12px">
          <summary class="v2-muted" style="cursor:pointer">Elegir el código a mano</summary>
          <input class="v2-input" style="margin-top:6px"
            placeholder={borrador.nombre ? codigoDesde(borrador.nombre) : 'Se arma solo con el nombre'}
            bind:value={borrador.codigo} />
        </details>
        <button class="v2-btn v2-btn-primary" style="align-self:flex-start"
          onclick={crearConCodigo} disabled={creando}>
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
                  <td class="v2-num">
                    {#if h.usos > 0}
                      <button type="button" class="usos-boton" onclick={() => verUsos(h)}
                        aria-expanded={!!usos[h.id] && usos[h.id] !== 'error'}>
                        {h.usos}
                      </button>
                    {:else}
                      {h.usos}
                    {/if}
                  </td>
                  <td>
                    <button class="v2-btn v2-btn-sm" onclick={() => retirar(h)} disabled={ocupado[h.id]}>
                      Retirar
                    </button>
                  </td>
                </tr>
                {#if usos[h.id] === 'cargando'}
                  <tr><td colspan="5" class="v2-sub">Leyendo los usos…</td></tr>
                {:else if usos[h.id] && usos[h.id] !== 'error'}
                  <tr>
                    <td colspan="5" class="usos-detalle">
                      <p class="v2-sub" style="margin:0 0 6px">
                        {usos[h.id].usos} uso(s) · {usos[h.id].usos_reales} con clientes ·
                        <b>{usos[h.id].escalo_igual_reales} escalaron igual</b>
                        {#if usos[h.id].usos > usos[h.id].usos_reales}
                          · el resto es del simulador o del asistente interno
                        {/if}
                      </p>
                      <ul>
                        {#each usos[h.id].detalle as u, i (i)}
                          <li>
                            {#if u.conversation_id}
                              <a href="/conversaciones/{u.conversation_id}">{relativeTime(u.creado_en)}</a>
                            {:else}
                              {relativeTime(u.creado_en)}
                            {/if}
                            · {u.rol ?? '—'}
                            {#if !u.real}<Pill tone="slate">{u.canal ?? 'sin canal'}</Pill>{/if}
                            {#if u.escalo}<Pill tone="rust">escaló igual</Pill>{/if}
                          </li>
                        {/each}
                      </ul>
                    </td>
                  </tr>
                {/if}
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
</div>

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
    background: var(--v2-paper);
    border-radius: 6px;
  }

  .tarjeta-propuesta {
    padding: 14px 16px;
  }

  .bloque-pasos {
    margin: 6px 0 0;
    padding: 10px 12px;
    background: var(--v2-paper);
    border-radius: 6px;
    font-family: ui-monospace, monospace;
    font-size: 12px;
    white-space: pre-wrap;
    line-height: 1.5;
  }

  .evidencia {
    margin-top: 6px;
    font-size: 12px;
  }
  .evidencia summary {
    cursor: pointer;
    font-size: 11.5px;
  }
  .evidencia ul,
  .usos-detalle ul {
    margin: 6px 0 0;
    padding-left: 18px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 12px;
  }
  .casos-enlaces {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    font-size: 11.5px;
    margin-top: 2px;
  }
  .usos-boton {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: var(--v2-ember-text);
    text-decoration: underline;
    cursor: pointer;
  }
  .usos-detalle {
    background: var(--v2-paper);
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
    background: var(--v2-ember);
    border-color: var(--v2-ember);
    color: var(--v2-on-ember);
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
