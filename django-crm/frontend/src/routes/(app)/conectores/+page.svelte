<script>
  /**
   * Conectar un sistema conocido eligiéndolo de una lista.
   *
   * El eje de la pantalla es que se pueda VER QUÉ VA A PASAR antes de que
   * pase. Aplicar un conector escribe herramientas que acceden a datos de
   * clientes y decide qué campos ve cada rol — la superficie más sensible de
   * toda la configuración. Por eso el botón principal no es "Aplicar" sino
   * "Ver qué haría", y aplicar solo aparece después de mirar.
   *
   * El mapeo área → rol es la decisión de la persona: un conector no sabe cómo
   * se llaman los roles de esta empresa, y un área sin mapear no entra.
   *
   * Nota de estado (Svelte 5): ninguna función llamada desde la plantilla
   * escribe estado. Eso rompió la pantalla de habilidades con
   * `state_unsafe_mutation`, que no falla el componente: no monta la página.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { toast } from 'svelte-sonner';
  import { PlugZap, ShieldAlert, KeyRound, Check } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  const conectores = data.conectores ?? [];
  const roles = data.roles ?? [];

  /** El conector abierto. null = la lista. */
  let abierto = $state(/** @type {any} */ (null));
  /** área del conector -> rol del tenant. Vacío = no entra. */
  let mapa = $state(/** @type {Record<string,string>} */ ({}));
  let plan = $state(/** @type {any} */ (null));
  let trabajando = $state(false);
  let aplicado = $state(/** @type {any} */ (null));

  const hayMapeo = $derived(Object.values(mapa).some((r) => r));

  function abrir(/** @type {any} */ c) {
    abierto = c;
    plan = null;
    aplicado = null;
    // Se propone el rol que se llama igual que el área, si existe. Es una
    // sugerencia, no una decisión: queda visible y se puede cambiar.
    /** @type {Record<string,string>} */
    const sugerido = {};
    for (const area of c.areas) {
      sugerido[area] = roles.some((/** @type {any} */ r) => r.nombre === area) ? area : '';
    }
    mapa = sugerido;
  }

  function volver() {
    abierto = null;
    plan = null;
    aplicado = null;
  }

  async function llamar(/** @type {'preparar'|'aplicar'} */ accion) {
    trabajando = true;
    try {
      const areas = Object.fromEntries(Object.entries(mapa).filter(([, r]) => r));
      const resp = await fetch('/api/conectores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion, id: abierto.id, areas })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo procesar.');
        return null;
      }
      return datos;
    } finally {
      trabajando = false;
    }
  }

  async function verQueHaria() {
    plan = await llamar('preparar');
  }

  async function aplicar() {
    const r = await llamar('aplicar');
    if (r) {
      aplicado = r;
      plan = null;
      toast.success(`${r.agregadas.length} herramientas conectadas.`);
    }
  }
</script>

<PageHeader title="Conectar un sistema">
  {#snippet sub()}
    Sistemas ya verificados contra su API. Traen los filtros que funcionan, los que
    la API ignora, y qué campos puede ver cada área.
  {/snippet}
</PageHeader>

{#if data.error}
  <p class="aviso-error">⚠️ {data.error}</p>
{:else}
  <div class="v2-pad" style="padding-top:14px;padding-bottom:32px;display:flex;flex-direction:column;gap:16px">

    {#if !abierto}
      <!-- ===== la lista ============================================= -->
      {#if conectores.length === 0}
        <div class="v2-card" style="padding:20px">
          <p class="v2-sub" style="margin:0;font-size:13px">
            No hay conectores disponibles todavía.
          </p>
        </div>
      {:else}
        <div class="rejilla">
          {#each conectores as c (c.id)}
            <button class="v2-card tarjeta" onclick={() => abrir(c)}>
              <div class="cabeza">
                <span class="icono"><PlugZap size={17} /></span>
                <span style="font-weight:700;font-size:14.5px">{c.nombre}</span>
              </div>
              <p class="v2-sub" style="margin:6px 0 0;font-size:12.5px;line-height:1.5">
                {c.descripcion}
              </p>
              <div class="cifras">
                <span><strong>{c.n_herramientas}</strong> herramientas</span>
                <span><strong>{c.areas.length}</strong> áreas</span>
              </div>
            </button>
          {/each}
        </div>
      {/if}

    {:else if aplicado}
      <!-- ===== después de aplicar =================================== -->
      <div class="v2-card" style="padding:18px 20px">
        <div style="display:flex;align-items:center;gap:9px;margin-bottom:10px">
          <Check size={18} style="color:var(--v2-moss)" />
          <span style="font-weight:700;font-size:14.5px">
            {abierto.nombre} conectado
          </span>
        </div>
        <p style="margin:0 0 12px;font-size:13px">
          Se agregaron <strong>{aplicado.agregadas.length}</strong> herramientas al catálogo.
          {#if aplicado.salteadas?.length}
            Se saltearon {aplicado.salteadas.length} que ya existían.
          {/if}
        </p>

        <!-- Sin esto las herramientas están pero fallan al primer uso, y el
             síntoma no dice que faltaba una credencial. -->
        <div class="pendiente">
          <div style="display:flex;gap:8px;align-items:flex-start">
            <KeyRound size={15} style="flex:none;margin-top:2px" />
            <div>
              <div style="font-weight:700;font-size:13px">Falta cargar las credenciales</div>
              <p style="margin:4px 0 0;font-size:12.5px;line-height:1.5">
                Sin esto las herramientas están en el catálogo pero fallan la primera vez
                que se usen.
              </p>
              <ul class="lista-pendiente">
                {#each aplicado.faltan_secretos ?? [] as s}
                  <li><span class="v2-num">{s}</span> — en Ajustes → Secretos</li>
                {/each}
                {#each aplicado.faltan_variables ?? [] as v}
                  <li><span class="v2-num">{v}</span> — en Ajustes → Variables</li>
                {/each}
              </ul>
            </div>
          </div>
        </div>

        <button class="v2-btn" style="margin-top:14px" onclick={volver}>Volver a la lista</button>
      </div>

    {:else}
      <!-- ===== el mapeo ============================================= -->
      <div class="v2-card" style="padding:18px 20px">
        <div class="cabeza" style="margin-bottom:4px">
          <span class="icono"><PlugZap size={17} /></span>
          <span style="font-weight:700;font-size:15px">{abierto.nombre}</span>
        </div>
        <p class="v2-sub" style="margin:0 0 16px;font-size:12.5px">
          {abierto.n_herramientas} herramientas verificadas contra su API.
        </p>

        <div class="v2-label" style="margin-bottom:6px">¿Qué rol atiende cada área?</div>
        <p class="v2-sub" style="margin:0 0 12px;font-size:12.5px;line-height:1.5">
          Un conector no sabe cómo se llaman los roles de esta empresa. Un área
          <strong>sin asignar no entra</strong>: es mejor conectar la mitad a propósito que
          darle datos de clientes a un rol que nadie eligió.
        </p>

        <div class="mapeo">
          {#each abierto.areas as area (area)}
            <label>
              <span class="area">{area}</span>
              <select class="v2-input" bind:value={mapa[area]}>
                <option value="">— no conectar —</option>
                {#each roles as r (r.nombre)}
                  <option value={r.nombre}>{r.nombre}</option>
                {/each}
              </select>
            </label>
          {/each}
        </div>

        <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
          <button class="v2-btn v2-btn-primary" onclick={verQueHaria}
                  disabled={trabajando || !hayMapeo}>
            {trabajando ? 'Calculando…' : 'Ver qué haría'}
          </button>
          <button class="v2-btn" onclick={volver} disabled={trabajando}>Cancelar</button>
        </div>
        {#if !hayMapeo}
          <p class="v2-sub" style="margin:8px 0 0;font-size:12px">
            Asigná al menos un área para continuar.
          </p>
        {/if}
      </div>

      {#if plan}
        <!-- ===== la revisión, antes de escribir nada ================ -->
        <div class="v2-card" style="padding:18px 20px">
          <div class="v2-label" style="margin-bottom:10px">Esto es lo que haría</div>

          {#if plan.nuevas.length === 0}
            <p style="margin:0;font-size:13px">
              Nada que agregar: todas las herramientas de este conector ya están en el
              catálogo, o ningún área quedó asignada.
            </p>
          {:else}
            <p style="margin:0 0 12px;font-size:13px">
              Agregar <strong>{plan.nuevas.length}</strong> herramientas.
              {#if plan.salteadas.length}
                Saltear <strong>{plan.salteadas.length}</strong> que ya existen.
              {/if}
            </p>

            {#if plan.nuevas.some((/** @type {any} */ h) => h.escritura)}
              <div class="aviso-escritura">
                <ShieldAlert size={15} style="flex:none;margin-top:2px" />
                <div>
                  <strong>{plan.nuevas.filter((/** @type {any} */ h) => h.escritura).length}</strong>
                  de estas herramientas <strong>escriben</strong> en el sistema externo
                  (crean tickets, registran pagos). Las que son sensibles exigen aprobación
                  humana antes de ejecutarse.
                </div>
              </div>
            {/if}

            <div style="overflow-x:auto;margin-top:12px">
              <table class="tabla">
                <thead>
                  <tr><th>Herramienta</th><th>Roles que la van a usar</th><th></th></tr>
                </thead>
                <tbody>
                  {#each plan.nuevas as h (h.nombre)}
                    <tr>
                      <td class="v2-num" style="font-size:12px">{h.nombre}</td>
                      <td class="v2-sub" style="font-size:12px">{h.roles.join(', ')}</td>
                      <td>{#if h.escritura}<Pill tone="clay">escribe</Pill>{/if}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>

            {#if Object.keys(plan.campos_por_rol ?? {}).length}
              <div class="v2-label" style="margin:16px 0 6px">Campos que gana cada rol</div>
              <p class="v2-sub" style="margin:0 0 8px;font-size:12px;line-height:1.5">
                Lista blanca: cada rol ve solo estos campos de cada herramienta. Un registro
                de cliente trae más de 50, incluidas contraseñas — lo que no está acá, no pasa.
              </p>
              <ul class="campos">
                {#each Object.entries(plan.campos_por_rol) as [rol, porHerr]}
                  <li>
                    <span class="v2-num">{rol}</span>:
                    {Object.keys(porHerr).length} herramientas con campos definidos
                  </li>
                {/each}
              </ul>
            {/if}

            <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
              <button class="v2-btn v2-btn-primary" onclick={aplicar} disabled={trabajando}>
                {trabajando ? 'Conectando…' : `Conectar ${abierto.nombre}`}
              </button>
              <button class="v2-btn" onclick={() => (plan = null)} disabled={trabajando}>
                Cambiar el mapeo
              </button>
            </div>
          {/if}
        </div>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .aviso-error {
    margin: 16px 18px; padding: 10px 14px; border-radius: 6px;
    background: color-mix(in srgb, var(--v2-rust) 10%, transparent);
    color: var(--v2-rust); font-size: 13px;
  }

  .rejilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
  .tarjeta {
    padding: 16px 18px; text-align: left; cursor: pointer;
    border: 1px solid var(--v2-line-soft); background: var(--v2-surface, #fff);
    font: inherit; color: inherit;
  }
  .tarjeta:hover { border-color: color-mix(in srgb, var(--v2-accent, #2563eb) 40%, transparent); }

  .cabeza { display: flex; align-items: center; gap: 9px; }
  .icono {
    display: grid; place-items: center; width: 30px; height: 30px; flex: none;
    border-radius: 7px; color: var(--v2-accent, #2563eb);
    background: color-mix(in srgb, var(--v2-accent, #2563eb) 10%, transparent);
  }

  .cifras {
    display: flex; gap: 14px; margin-top: 12px;
    font-size: 12px; color: var(--v2-slate);
  }

  .mapeo { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
  .mapeo label { display: flex; flex-direction: column; gap: 4px; }
  .area {
    font-size: 11.5px; color: var(--v2-slate);
    text-transform: uppercase; letter-spacing: .4px;
  }

  .aviso-escritura {
    display: flex; gap: 8px; padding: 10px 12px; border-radius: 6px; font-size: 12.5px;
    line-height: 1.5;
    background: color-mix(in srgb, var(--v2-clay) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--v2-clay) 28%, transparent);
  }

  .pendiente {
    padding: 12px 14px; border-radius: 6px;
    background: color-mix(in srgb, var(--v2-accent, #2563eb) 6%, transparent);
    border: 1px solid color-mix(in srgb, var(--v2-accent, #2563eb) 22%, transparent);
  }
  .lista-pendiente { margin: 8px 0 0; padding-left: 18px; font-size: 12.5px; line-height: 1.7; }

  .campos { margin: 0; padding-left: 18px; font-size: 12.5px; line-height: 1.7; }

  .tabla { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  .tabla th {
    text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px;
    color: var(--v2-slate); padding: 8px 12px 8px 0;
    border-bottom: 1px solid var(--v2-line-soft); white-space: nowrap;
  }
  .tabla td { padding: 8px 12px 8px 0; border-bottom: 1px solid var(--v2-line-soft); }
  .tabla tr:last-child td { border-bottom: none; }
</style>
