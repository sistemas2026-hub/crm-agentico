<script>
  /**
   * Un momento de «Mensajes automáticos»: qué plantilla usa, qué dato va en
   * cada {{n}} y si está encendido. Como en el CRM que se reemplaza, pero
   * mostrando el texto con los datos puestos, y sin dejar guardar encendido un
   * armado que Meta rechazaría (eso lo vuelve a comprobar el motor).
   */
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { etiquetasDe, vistaPrevia } from '$lib/conversaciones/plantillas.js';

  /** @type {{ evento: any, campos: Record<string, {etiqueta: string, ejemplo: string}>,
   *   plantillas: any[], canEdit: boolean, form: any }} */
  let { evento, campos, plantillas, canEdit, form } = $props();

  //  untrack: se parte de lo guardado, y despues manda lo que se edita.
  let plantilla = $state(untrack(() => evento.config.plantilla));
  /** @type {string[]} */
  let datos = $state(untrack(() => [...evento.config.datos]));
  let activo = $state(untrack(() => evento.config.activo));
  let guardando = $state(false);

  let aprobadas = $derived(plantillas.filter((p) => (p.estado || '').toUpperCase() === 'APPROVED'));
  let ficha = $derived(plantillas.find((p) => p.nombre === plantilla) ?? null);
  let lugares = $derived(ficha ? etiquetasDe(ficha) : []);
  //  Tantos lugares como pide la plantilla: si cambia, se acomoda la lista.
  $effect(() => {
    if (ficha && datos.length !== lugares.length) {
      datos = Array.from({ length: lugares.length }, (_, i) => datos[i] ?? '');
    }
  });
  let previa = $derived(
    ficha ? vistaPrevia(ficha, datos.map((d) => (d ? campos[d]?.ejemplo ?? d : '…'))) : ''
  );
  let pausada = $derived(ficha && (ficha.estado || '').toUpperCase() !== 'APPROVED');
  let completo = $derived(Boolean(ficha) && !pausada && datos.length === lugares.length && datos.every(Boolean));
  let mio = $derived(form?.evento === evento.clave || form?.guardado === evento.clave);
</script>

<form
  method="POST"
  action="?/guardar"
  class="v2-card momento"
  use:enhance={() => {
    guardando = true;
    return async ({ update }) => {
      await update({ reset: false });
      guardando = false;
    };
  }}
>
  <input type="hidden" name="evento" value={evento.clave} />
  <div class="cabeza">
    <b>{evento.etiqueta}</b>
    <Pill tone={evento.config.activo ? 'moss' : 'slate'} dot>
      {evento.config.activo ? 'Encendido' : 'Apagado'}
    </Pill>
    {#if !evento.listo}<Pill tone="clay">Todavía no se manda</Pill>{/if}
  </div>
  <p class="v2-sub desc">
    {evento.descripcion}
    {#if !evento.listo}
      Se puede dejar armado; empieza a salir cuando su disparador esté construido.
    {:else if evento.disparo === 'manual'}
      Al mandarla desde un ticket, Dexter llena estos datos y quien la manda escribe el resto.
    {/if}
  </p>

  <div class="v2-field" style="margin:0">
    <label for={`p-${evento.clave}`}>Plantilla</label>
    <select id={`p-${evento.clave}`} name="plantilla" class="v2-input" style="max-width:420px" bind:value={plantilla} disabled={!canEdit}>
      <option value="">Ninguna</option>
      {#each aprobadas as p (p.nombre)}
        <option value={p.nombre}>{p.nombre}</option>
      {/each}
      {#if ficha && pausada}
        <option value={ficha.nombre}>{ficha.nombre} (no aprobada)</option>
      {/if}
    </select>
    {#if pausada}
      <p class="mal">Meta tiene esta plantilla como «{ficha.estado}»: así no se puede mandar.</p>
    {/if}
  </div>

  {#if ficha && lugares.length}
    <div class="lugares">
      {#each lugares as l, i (l.parte + l.hueco)}
        <div class="v2-field" style="margin:0">
          <label for={`d-${evento.clave}-${i}`}>Qué va en {l.reemplaza}{l.donde ? ` (${l.donde})` : ''}</label>
          <select id={`d-${evento.clave}-${i}`} name="dato" class="v2-input" bind:value={datos[i]} disabled={!canEdit}>
            <option value="">Elegí un dato</option>
            {#each evento.campos as c (c)}
              <option value={c}>{campos[c]?.etiqueta ?? c}</option>
            {/each}
          </select>
        </div>
      {/each}
    </div>
  {:else if ficha}
    <p class="v2-hint" style="margin:0">Esta plantilla no lleva datos variables.</p>
  {/if}

  {#if ficha}
    <div>
      <div class="v2-hint" style="margin:0 0 4px">Así le llega (con datos de ejemplo)</div>
      <div class="previa">{previa}</div>
    </div>
  {/if}

  {#if canEdit}
    <div class="pie">
      <label class="interruptor">
        <input type="checkbox" name="activo" bind:checked={activo} disabled={!completo && !activo} />
        Encendido
      </label>
      <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit" disabled={guardando}>
        {guardando ? 'Guardando…' : 'Guardar'}
      </button>
      {#if mio && form?.error}<span class="mal">{form.error}</span>{/if}
      {#if mio && form?.guardado}<span class="ok">Guardado.</span>{/if}
    </div>
    {#if activo && evento.destinatario === 'cliente' && evento.disparo !== 'manual'}
      <p class="v2-hint" style="margin:0">
        Si otro sistema todavía manda este aviso, apagalo allá el mismo día: si no, el cliente lo recibe dos
        veces, y los bloqueos que eso provoca bajan la calidad del número.
      </p>
    {/if}
  {/if}
</form>

<style>
  .momento {
    display: grid;
    gap: 12px;
    padding: 16px;
  }
  .cabeza {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }
  .desc {
    margin: -4px 0 0;
    font-size: 12.5px;
    line-height: 1.45;
  }
  .lugares {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px 14px;
  }
  .previa {
    white-space: pre-wrap;
    padding: 10px 12px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    background: var(--v2-paper);
    font-size: 13px;
    line-height: 1.45;
    max-width: 520px;
  }
  .pie {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  .interruptor {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
  }
  .mal {
    margin: 0;
    font-size: 12.5px;
    color: var(--v2-rust);
  }
  .ok {
    font-size: 12.5px;
    color: var(--v2-moss);
  }
</style>
