<script>
  /**
   * Un momento de «Mensajes automáticos»: qué plantilla usa, qué dato va en
   * cada {{n}} y si está encendido. Como en el CRM que se reemplaza, pero
   * mostrando el texto con los datos puestos, y sin dejar encender un armado
   * que Meta rechazaría (eso lo vuelve a comprobar el motor).
   *
   * DOS FORMULARIOS (28/10/2026): el interruptor de la cabecera enciende o
   * apaga AL INSTANTE con lo que ya está guardado; «Guardar» cambia la
   * plantilla y los datos sin tocar si está encendido.
   */
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { etiquetasDe, vistaPrevia } from '$lib/conversaciones/plantillas.js';

  /** @type {{ evento: any, campos: Record<string, {etiqueta: string, ejemplo: string}>,
   *   plantillas: any[], canEdit: boolean, form: any }} */
  let { evento, campos, plantillas, canEdit, form } = $props();

  //  untrack: se parte de lo guardado, y después manda lo que se edita.
  let plantilla = $state(untrack(() => evento.config.plantilla));
  /** @type {string[]} */
  let datos = $state(untrack(() => [...evento.config.datos]));
  let guardando = $state(false);
  let cambiando = $state(false);

  //  Solo las aprobadas y en uso: una que la empresa desactivó no se ofrece.
  let aprobadas = $derived(
    plantillas.filter((p) => (p.estado || '').toUpperCase() === 'APPROVED' && p.en_uso !== false)
  );
  let ficha = $derived(plantillas.find((p) => p.nombre === plantilla) ?? null);
  let lugares = $derived(ficha ? etiquetasDe(ficha) : []);
  //  Tantos lugares como pide la plantilla: si cambia, se acomoda la lista.
  //  Si es la sugerida de este momento y no hay nada elegido, sus datos vienen
  //  puestos en el orden con que se escribió (29/10/2026).
  $effect(() => {
    if (!ficha) return;
    const sug = evento.sugerencia;
    if (
      sug && ficha.nombre === sug.nombre && sug.datos.length === lugares.length &&
      untrack(() => datos.every((d) => !d))
    ) {
      datos = [...sug.datos];
    } else if (datos.length !== lugares.length) {
      datos = Array.from({ length: lugares.length }, (_, i) => datos[i] ?? '');
    }
  });
  //  La sugerida de este momento todavía no existe en Meta: se ofrece crearla.
  let falta_sugerida = $derived(
    Boolean(evento.sugerencia) && !plantillas.some((p) => p.nombre === evento.sugerencia.nombre)
  );
  let previa = $derived(
    ficha ? vistaPrevia(ficha, datos.map((d) => (d ? campos[d]?.ejemplo ?? d : '…'))) : ''
  );
  let pausada = $derived(Boolean(ficha) && (ficha.estado || '').toUpperCase() !== 'APPROVED');
  let desactivada = $derived(Boolean(ficha) && ficha.en_uso === false);
  let completo = $derived(
    Boolean(ficha) && !pausada && !desactivada && datos.length === lugares.length && datos.every(Boolean)
  );
  let encendido = $derived(Boolean(evento.config.activo));
  //  Modo prueba (29/10/2026): con números, sale SOLO a esos. Lo decide el
  //  motor; acá se muestra y se edita. Un momento manual no lo tiene: lo
  //  manda una persona que ya eligió a quién.
  let admitePrueba = $derived(evento.disparo !== 'manual');
  let prueba = $derived(admitePrueba ? (evento.config.solo_a ?? []) : []);
  let soloA = $state(untrack(() => (evento.config.solo_a ?? []).join('\n')));
  let mio = $derived(form?.evento === evento.clave || form?.guardado === evento.clave);
</script>

<div class="v2-card momento">
  <div class="cabeza">
    <b>{evento.etiqueta}</b>
    {#if !evento.listo}<Pill tone="clay">Todavía no se manda</Pill>{/if}
    {#if canEdit}
      <form
        method="POST"
        action="?/encender"
        class="encender"
        use:enhance={() => {
          cambiando = true;
          return async ({ update }) => {
            await update({ reset: false });
            cambiando = false;
          };
        }}
      >
        <input type="hidden" name="evento" value={evento.clave} />
        <input type="hidden" name="activo" value={encendido ? '0' : '1'} />
        <input type="hidden" name="plantilla" value={evento.config.plantilla} />
        {#each evento.config.datos as d, i (i)}<input type="hidden" name="dato" value={d} />{/each}
        <span class="estado">
          {encendido ? (prueba.length ? 'Encendido · solo prueba' : 'Encendido') : 'Apagado'}
        </span>
        <button
          type="submit"
          class="interruptor"
          class:encendido
          role="switch"
          aria-checked={encendido}
          aria-label={`${encendido ? 'Apagar' : 'Encender'} ${evento.etiqueta}`}
          disabled={cambiando}
        >
          <span class="perilla"></span>
        </button>
      </form>
    {:else}
      <Pill tone={encendido ? (prueba.length ? 'clay' : 'moss') : 'slate'} dot>
        {encendido ? (prueba.length ? 'Encendido · solo prueba' : 'Encendido') : 'Apagado'}
      </Pill>
    {/if}
  </div>

  <p class="v2-sub desc">
    {evento.descripcion}
    {#if !evento.listo}
      Se puede dejar armado; empieza a salir cuando su disparador esté construido.
    {:else if evento.disparo === 'manual'}
      Al mandarla desde un ticket, Dexter llena estos datos y quien la manda escribe el resto.
    {/if}
  </p>

  <form
    method="POST"
    action="?/guardar"
    class="armado"
    use:enhance={() => {
      guardando = true;
      return async ({ update }) => {
        await update({ reset: false });
        guardando = false;
      };
    }}
  >
    <input type="hidden" name="evento" value={evento.clave} />
    <!-- Guardar no cambia si está encendido: eso lo hace el interruptor. -->
    {#if encendido}<input type="hidden" name="activo" value="on" />{/if}

    <div class="v2-field" style="margin:0">
      <label for={`p-${evento.clave}`}>Plantilla</label>
      <select id={`p-${evento.clave}`} name="plantilla" class="v2-input" style="max-width:420px"
        bind:value={plantilla} disabled={!canEdit}>
        <option value="">Ninguna</option>
        {#each aprobadas as p (p.nombre)}
          <option value={p.nombre}>{p.nombre}</option>
        {/each}
        {#if ficha && (pausada || desactivada)}
          <option value={ficha.nombre}>{ficha.nombre} ({desactivada ? 'desactivada' : 'no aprobada'})</option>
        {/if}
      </select>
      {#if !ficha && falta_sugerida && canEdit}
        <p class="v2-hint" style="margin:4px 0 0">
          Para este momento hay una plantilla sugerida:
          <a href={`/settings/canales/whatsapp/plantillas?sugerida=${evento.clave}`}>crearla en Plantillas</a>.
          Cuando Meta la apruebe, aparece acá con sus datos en orden.
        </p>
      {/if}
      {#if pausada}
        <p class="mal">Meta tiene esta plantilla como «{ficha.estado}»: así no se puede mandar.</p>
      {:else if desactivada}
        <p class="mal">
          Esta plantilla está desactivada en <a href="/settings/canales/whatsapp/plantillas">Plantillas</a>:
          mientras lo esté, este mensaje no sale.
        </p>
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

    {#if admitePrueba}
      <div class="v2-field" style="margin:0">
        <label for={`s-${evento.clave}`}>Solo a estos números (modo prueba)</label>
        <textarea
          id={`s-${evento.clave}`}
          name="solo_a"
          class="v2-input"
          rows="2"
          style="max-width:320px"
          placeholder="573001234567"
          bind:value={soloA}
          disabled={!canEdit}
        ></textarea>
        <p class="v2-hint" style="margin:0">
          Con el indicativo del país, uno por línea. Mientras haya alguno, este mensaje le llega
          <b>solo</b> a esos números, aunque esté encendido. Vacío: les llega a todos los
          {evento.destinatario === 'tecnico' ? 'técnicos' : 'clientes'}.
        </p>
      </div>
    {/if}

    {#if canEdit}
      <div class="pie">
        <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit"
          disabled={guardando || (encendido && !completo)}>
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
        {#if encendido && !completo}
          <span class="v2-hint" style="margin:0">Encendido, cada lugar tiene que tener su dato.</span>
        {/if}
        {#if mio && form?.error}<span class="mal">{form.error}</span>{/if}
        {#if mio && form?.guardado}<span class="ok">Guardado.</span>{/if}
      </div>
      {#if encendido && evento.destinatario === 'cliente' && evento.disparo !== 'manual'}
        <p class="v2-hint" style="margin:0">
          Si otro sistema todavía manda este aviso, apagalo allá el mismo día: si no, el cliente lo recibe dos
          veces, y los bloqueos que eso provoca bajan la calidad del número.
        </p>
      {/if}
    {/if}
  </form>
</div>

<style>
  .momento {
    display: grid;
    gap: 12px;
    padding: 16px;
  }
  .armado {
    display: grid;
    gap: 12px;
  }
  .cabeza {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }
  .encender {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .estado {
    font-size: 12.5px;
    color: var(--v2-slate);
  }
  .interruptor {
    position: relative;
    width: 36px;
    height: 20px;
    border-radius: 999px;
    border: 0;
    padding: 0;
    background: var(--v2-line-strong);
    cursor: pointer;
    transition: background 0.15s;
  }
  .interruptor.encendido {
    background: var(--v2-moss);
  }
  .interruptor:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .perilla {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 2px rgb(0 0 0 / 0.25);
    transition: transform 0.15s;
  }
  .interruptor.encendido .perilla {
    transform: translateX(16px);
  }
  .interruptor:focus-visible {
    outline: 2px solid var(--v2-ember);
    outline-offset: 2px;
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
