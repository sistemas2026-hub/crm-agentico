<script>
  /**
   * SmartOLT: credenciales para el sondeo de solo lectura, mas un boton para
   * probarlas antes de guardarlas. Version simplificada de
   * settings/canales/whatsapp/+page.svelte (mismo patron de "un ojo por
   * campo" y "vaciar al guardar") -- sin toggle de canal ni URL de webhook,
   * porque esto todavia no es una integracion activa: es el primer paso
   * antes de escribir la skill 'smartolt-api' con hallazgos verificados.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { enhance } from '$app/forms';
  import { Eye, EyeOff, CircleCheck, CircleX } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const CAMPOS = [
    {
      clave: 'base_url',
      nombre: 'SMARTOLT_BASE_URL',
      etiqueta: 'Subdominio de la cuenta',
      ayuda: 'Con esquema y sin barra final -- ej. https://rapilink.smartolt.com',
      placeholder: 'https://tuempresa.smartolt.com'
    },
    {
      clave: 'api_key',
      nombre: 'SMARTOLT_API_KEY',
      etiqueta: 'API key',
      ayuda: 'Panel de SmartOLT -> Settings -> API.',
      placeholder: 'Pegar valor…'
    }
  ];

  function secretoDe(/** @type {string} */ clave) {
    return clave === 'base_url' ? data.baseUrl : data.apiKey;
  }

  /** @type {Record<string, boolean>} */
  let aLaVista = $state({});
  /** @type {Record<string, string>} */
  let pegado = $state({});

  function guardandoCredencial(/** @type {string} */ clave) {
    return () => async (/** @type {any} */ { update, result }) => {
      await update();
      if (result?.type === 'success') {
        pegado[clave] = '';
        aLaVista[clave] = false;
      }
    };
  }

  let probando = $state(false);
  const probandoConexion = () => {
    return async (/** @type {any} */ { update }) => {
      probando = true;
      await update({ reset: false });
      probando = false;
    };
  };
</script>

<PageHeader title="SmartOLT">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    Credenciales para el sondeo de solo lectura -- todavía no hay ninguna herramienta activa que
    las use.
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:760px">
    <div class="v2-label" style="margin-bottom:10px">Credenciales</div>
    <div class="v2-card" style="overflow:hidden">
      {#each CAMPOS as c, i (c.clave)}
        {@const secreto = secretoDe(c.clave)}
        <div class="cred-fila" class:cred-borde={i > 0}>
          <div class="cred-info">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <b style="font-size:13px">{c.etiqueta}</b>
              {#if secreto}
                <Pill tone="moss" dot>Cargado</Pill>
              {:else}
                <Pill tone="clay">Sin cargar</Pill>
              {/if}
            </div>
            <p class="v2-sub" style="font-size:11.5px;margin:5px 0 0;line-height:1.5">{c.ayuda}</p>
            {#if secreto}
              <p class="v2-sub" style="font-size:11px;margin:5px 0 0">
                Termina en <span class="v2-num">…{secreto.pista}</span> · actualizado
                {shortAge(secreto.actualizado_en)}
              </p>
            {/if}
            {#if form?.campo === c.nombre && form?.error}
              <p class="v2-error" style="font-size:11.5px;margin:6px 0 0">{form.error}</p>
            {/if}
          </div>

          {#if data.can_edit}
            <div class="cred-accion">
              <form
                method="POST"
                action="?/guardarCredencial"
                use:enhance={guardandoCredencial(c.clave)}
                class="cred-form"
              >
                <input type="hidden" name="nombre" value={c.nombre} />
                <input type="hidden" name="descripcion" value={c.etiqueta} />
                <div class="cred-campo">
                  <input
                    class="v2-input"
                    type={aLaVista[c.clave] ? 'text' : 'password'}
                    name="valor"
                    autocomplete="off"
                    placeholder={secreto
                      ? secreto.pista
                        ? `••••••••••••${secreto.pista}`
                        : 'Cargado — pegá otro para reemplazar'
                      : c.placeholder}
                    required
                    bind:value={pegado[c.clave]}
                  />
                  {#if pegado[c.clave]}
                    <button
                      type="button"
                      class="cred-ojo"
                      onclick={() => (aLaVista[c.clave] = !aLaVista[c.clave])}
                      aria-label={aLaVista[c.clave] ? 'Ocultar' : 'Mostrar lo que pegaste'}
                      title={aLaVista[c.clave] ? 'Ocultar' : 'Mostrar lo que pegaste'}
                    >
                      {#if aLaVista[c.clave]}<EyeOff size={14} />{:else}<Eye size={14} />{/if}
                    </button>
                  {/if}
                </div>
                <button class="v2-btn v2-btn-sm" type="submit">
                  {secreto ? 'Actualizar' : 'Guardar'}
                </button>
              </form>

              {#if form?.guardado === c.nombre}
                <p class="cred-ok"><CircleCheck size={12} /> Guardado</p>
              {/if}

              {#if secreto}
                <form method="POST" action="?/borrarCredencial" use:enhance={() => async ({ update }) => update()}>
                  <input type="hidden" name="nombre" value={c.nombre} />
                  <button class="v2-btn v2-btn-sm v2-btn-quiet" type="submit">Borrar</button>
                </form>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!-- ── probar conexión ─────────────────────────────────────────────── -->
    <div class="v2-label" style="margin:22px 0 10px">Probar conexión</div>
    <div class="v2-card" style="padding:16px">
      <p class="v2-sub" style="font-size:11.5px;margin:0 0 12px;line-height:1.5">
        Prueba con lo que pegaste arriba en este momento, sin necesidad de guardarlo antes — así
        se corrige un dato mal pegado sin ida y vuelta.
      </p>
      <form method="POST" action="?/probarConexion" use:enhance={probandoConexion} style="display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap">
        <input type="hidden" name="base_url" value={pegado['base_url'] ?? ''} />
        <input type="hidden" name="api_key" value={pegado['api_key'] ?? ''} />
        <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit" disabled={probando}>
          {probando ? 'Probando…' : 'Probar conexión'}
        </button>
      </form>

      {#if form?.pruebaError}
        <p class="v2-error" style="font-size:12px;margin-top:10px">{form.pruebaError}</p>
      {/if}

      {#if form?.prueba}
        <div
          class="prueba-resultado"
          class:prueba-ok={form.prueba.ok}
          class:prueba-mal={!form.prueba.ok}
        >
          {#if form.prueba.ok}
            <CircleCheck size={14} />
          {:else}
            <CircleX size={14} />
          {/if}
          <span>{form.prueba.detalle}</span>
        </div>
      {/if}

      <p class="v2-sub" style="font-size:11px;margin-top:12px;line-height:1.5">
        El endpoint que se prueba (<span class="v2-num">/api/network/olts</span>) es la mejor
        hipótesis de la documentación pública de SmartOLT, todavía sin confirmar contra esta
        cuenta. Si da 404 con credenciales que sabés correctas, es la ruta la que está mal, no el
        dato pegado.
      </p>
    </div>
  </div>
</div>

<style>
  .cred-fila {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    padding: 16px;
    flex-wrap: wrap;
  }
  .cred-borde {
    border-top: 1px solid var(--v2-line-soft);
  }
  .cred-info {
    flex: 1;
    min-width: 260px;
  }
  .cred-accion {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: none;
    width: 260px;
  }
  .cred-form {
    display: flex;
    gap: 6px;
  }
  .cred-campo {
    position: relative;
    flex: 1;
    min-width: 0;
    display: flex;
  }
  .cred-campo input {
    flex: 1;
    min-width: 0;
    font-size: 12.5px;
  }
  .cred-campo:has(.cred-ojo) input {
    padding-right: 30px;
  }
  .cred-ojo {
    position: absolute;
    right: 1px;
    top: 1px;
    bottom: 1px;
    width: 28px;
    display: grid;
    place-items: center;
    border: 0;
    background: none;
    color: var(--v2-slate);
    cursor: pointer;
    border-radius: 0 7px 7px 0;
  }
  .cred-ojo:hover {
    color: var(--v2-ink);
  }
  .cred-ok {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 2px 0 0;
    font-size: 11.5px;
    color: var(--v2-moss);
    font-weight: 550;
  }
  .prueba-resultado {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: var(--v2-radius);
    font-size: 12.5px;
    border: 1px solid var(--v2-line);
  }
  .prueba-ok {
    color: var(--v2-moss);
    border-color: color-mix(in srgb, var(--v2-moss) 40%, var(--v2-line));
    background: color-mix(in srgb, var(--v2-moss) 8%, transparent);
  }
  .prueba-mal {
    color: var(--v2-clay);
    border-color: color-mix(in srgb, var(--v2-clay) 40%, var(--v2-line));
    background: color-mix(in srgb, var(--v2-clay) 8%, transparent);
  }

  @media (max-width: 640px) {
    .cred-accion {
      width: 100%;
    }
  }
</style>
