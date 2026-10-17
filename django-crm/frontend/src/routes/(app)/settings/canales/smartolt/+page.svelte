<script>
  /**
   * SmartOLT: la clave que le da al asistente control de lectura y reinicio
   * de la ONU del cliente, y el subdominio de la instancia -- este software
   * es SaaS multi-tenant (muchas empresas se conectan, no solo Rapilink), asi
   * que un dato que varia por empresa tiene que poder cargarse desde aca, no
   * quedar fijo en un archivo que solo un desarrollador edita.
   *
   * Mismo criterio de seguridad que WhatsApp para la clave: el valor guardado
   * NUNCA se lee de vuelta, solo su pista (ultimos 4 caracteres) y cuando se
   * cargo. El subdominio SI se lee de vuelta -- no es secreto, es config.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { enhance } from '$app/forms';
  import { Check, Eye, EyeOff, Plug } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let smartolt = $derived(data.smartolt);
  let secreto = $derived(data.secretoApiKey);

  let subdominio = $state(data.smartolt?.subdominio ?? '');

  let aLaVista = $state(false);
  let pegado = $state('');

  const guardando = () => {
    return async (/** @type {any} */ { update, result }) => {
      await update();
      if (result?.type === 'success') {
        pegado = '';
        aLaVista = false;
      }
    };
  };

  // 'update()' por defecto resetea el campo al valor que tenia el input al
  // cargar la pagina -- bien para la clave (conviene vaciarla despues de
  // guardar), mal para el subdominio (volveria a lo que HABIA antes de
  // tocarlo, no a lo recien guardado, hasta el proximo refresh completo).
  const guardandoSubdominio = () => {
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
    };
  };

  const enviando = () => {
    return async (/** @type {any} */ { update }) => {
      await update();
    };
  };

  let probando = $state(false);
  const probandoConexion = () => {
    probando = true;
    return async (/** @type {any} */ { update }) => {
      await update();
      probando = false;
    };
  };
</script>

<PageHeader title="SmartOLT">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if !smartolt?.instalado}
      No está en el catálogo de este agente
    {:else if secreto}
      Clave cargada
    {:else}
      Falta cargar la clave
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:760px">
    {#if !smartolt}
      <div class="v2-card" style="padding:20px 22px">
        <b style="font-size:13px">No se pudo leer la configuración</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          El motor no está respondiendo. Si otras pantallas de ajustes tampoco cargan, es el motor.
        </p>
      </div>
    {:else if !smartolt.instalado}
      <div class="v2-card" style="padding:20px 22px">
        <b style="font-size:13px">Este agente todavía no tiene SmartOLT en su catálogo</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          Las herramientas de consulta y reinicio de ONU se declaran en la configuración del
          tenant. Si esperabas verlas acá, confirmá con quien mantiene esa configuración.
        </p>
      </div>
    {:else}
      <div class="v2-label" style="margin-bottom:10px">Instancia</div>
      <div class="v2-card" style="padding:16px">
        {#if !smartolt.subdominio_ref}
          <p class="v2-sub" style="font-size:12.5px;margin:0;line-height:1.5">
            Esta herramienta no declara de dónde sacar el subdominio (falta
            <span class="v2-num">base_url_ref</span> en el catálogo) — no hay dónde guardarlo
            todavía.
          </p>
        {:else}
          <form
            method="POST"
            action="?/guardarSubdominio"
            use:enhance={guardandoSubdominio}
            style="display:flex;flex-direction:column;gap:10px"
          >
            <input type="hidden" name="nombre" value={smartolt.subdominio_ref} />
            <div class="v2-field" style="margin:0">
              <label for="f-subdominio" style="font-size:11.5px">Subdominio de SmartOLT</label>
              <input
                id="f-subdominio"
                class="v2-input"
                type="text"
                name="valor"
                placeholder="https://tuempresa.smartolt.com"
                bind:value={subdominio}
                disabled={!data.can_edit}
              />
              <p class="v2-hint">
                El asistente arma cada consulta y cada reinicio de ONU contra esta URL. Se genera
                en tu cuenta de SmartOLT — es el mismo dominio con el que entrás a su panel.
              </p>
            </div>
            {#if form?.subdominioError}<p class="v2-error" style="font-size:12px">
                {form.subdominioError}
              </p>{/if}
            {#if form?.subdominioGuardado}<p class="cred-ok"><Check size={12} /> Guardado</p>{/if}
            {#if data.can_edit}
              <button
                class="v2-btn v2-btn-primary v2-btn-sm"
                type="submit"
                style="align-self:flex-start"
              >
                Guardar
              </button>
            {/if}
          </form>
        {/if}
      </div>

      <div class="v2-label" style="margin:22px 0 10px">Clave de API</div>
      <div class="v2-card" style="padding:16px">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
          {#if secreto}
            <Pill tone="moss" dot>Cargada</Pill>
          {:else}
            <Pill tone="clay">Sin cargar</Pill>
          {/if}
        </div>
        <p class="v2-sub" style="font-size:11.5px;margin:5px 0 0;line-height:1.5">
          Se genera en SmartOLT → Settings → API. Con esto el asistente puede ver el estado y la
          señal de la ONU del cliente, y reiniciarla — nunca sin haber revisado antes que la señal
          está bien y que el equipo responde al ping (ver la descripción de la herramienta
          «reiniciar_ont» en el catálogo: no hay paso de aprobación humana, la condición está en
          código).
        </p>
        {#if secreto}
          <p class="v2-sub" style="font-size:11px;margin:8px 0 0">
            Termina en <span class="v2-num">…{secreto.pista}</span> · actualizada {shortAge(
              secreto.actualizado_en
            )}
          </p>
        {/if}
        {#if form?.error}<p class="v2-error" style="font-size:11.5px;margin:8px 0 0">
            {form.error}
          </p>{/if}
        {#if form?.guardado}<p class="cred-ok"><Check size={12} /> Guardada</p>{/if}

        {#if data.can_edit}
          <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
            <form method="POST" action="?/guardar" use:enhance={guardando} style="flex:1;min-width:220px">
              <div class="cred-campo">
                <input
                  class="v2-input"
                  type={aLaVista ? 'text' : 'password'}
                  name="valor"
                  autocomplete="off"
                  placeholder={secreto
                    ? `••••••••••••${secreto.pista} — pegá otra para reemplazar`
                    : 'Pegar la clave…'}
                  required
                  bind:value={pegado}
                  style="width:100%"
                />
                {#if pegado}
                  <button
                    type="button"
                    class="cred-ojo"
                    onclick={() => (aLaVista = !aLaVista)}
                    aria-label={aLaVista ? 'Ocultar' : 'Mostrar lo que pegaste'}
                    title={aLaVista ? 'Ocultar' : 'Mostrar lo que pegaste'}
                  >
                    {#if aLaVista}<EyeOff size={14} />{:else}<Eye size={14} />{/if}
                  </button>
                {/if}
              </div>
              <button class="v2-btn v2-btn-sm v2-btn-primary" type="submit" style="margin-top:8px">
                {secreto ? 'Actualizar' : 'Guardar'}
              </button>
            </form>
            {#if secreto}
              <form method="POST" action="?/borrar" use:enhance={enviando}>
                <button class="v2-btn v2-btn-sm v2-btn-quiet" type="submit">Borrar</button>
              </form>
            {/if}
          </div>
        {/if}
      </div>

      <div class="v2-label" style="margin:22px 0 10px">Probar conexión</div>
      <div class="v2-card" style="padding:16px">
        <p class="v2-sub" style="font-size:11.5px;margin:0 0 10px;line-height:1.5">
          Llama a SmartOLT en el momento con el subdominio y la clave que tenés escritos arriba —
          sirve para confirmar que valen ANTES de guardarlos, sin ida y vuelta.
        </p>
        {#if !pegado}
          <p class="v2-sub" style="font-size:11.5px;margin:0">
            Pegá la clave de API arriba para poder probar.
          </p>
        {:else if data.can_edit}
          <form method="POST" action="?/probarConexion" use:enhance={probandoConexion}>
            <input type="hidden" name="subdominio" value={subdominio} />
            <input type="hidden" name="api_key" value={pegado} />
            <button class="v2-btn v2-btn-sm" type="submit" disabled={probando}>
              <Plug size={13} />
              {probando ? 'Probando…' : 'Probar conexión'}
            </button>
          </form>
        {/if}
        {#if form?.pruebaError}<p class="v2-error" style="font-size:11.5px;margin:10px 0 0">
            {form.pruebaError}
          </p>{/if}
        {#if form?.prueba}
          <p
            class="v2-sub"
            style="font-size:11.5px;margin:10px 0 0;font-weight:600"
            style:color={form.prueba.ok ? 'var(--v2-moss)' : 'var(--v2-clay)'}
          >
            {form.prueba.detalle}
          </p>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .cred-campo {
    position: relative;
    display: flex;
  }
  .cred-campo input {
    padding-right: 30px;
    font-size: 12.5px;
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
    margin: 8px 0 0;
    font-size: 11.5px;
    color: var(--v2-moss);
    font-weight: 550;
  }
</style>
