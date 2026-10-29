<script>
  /**
   * Plantillas de WhatsApp (28/10/2026).
   *
   * Fuera de la ventana de 24 h WhatsApp solo deja escribirle a un cliente con
   * una plantilla aprobada por Meta. Hasta hoy se armaban en el panel de Meta y
   * Dexter solo las leía. Acá se ven en cualquier estado, se mandan a revisión
   * y se borran. Meta revisa cada una (de minutos a horas) y decide la
   * categoría final.
   *
   * Solo variables numeradas ({{1}}, {{2}}) y solo en el texto del mensaje: es
   * lo que el resto de Dexter sabe completar (lib/conversaciones/plantillas.js).
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { ChevronLeft, Plus, Trash2 } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const ESTADO = /** @type {Record<string, {texto: string, tono: 'moss'|'clay'|'rust'|'slate'}>} */ ({
    APPROVED: { texto: 'Aprobada', tono: 'moss' },
    PENDING: { texto: 'En revisión', tono: 'clay' },
    IN_APPEAL: { texto: 'En apelación', tono: 'clay' },
    REJECTED: { texto: 'Rechazada', tono: 'rust' },
    PAUSED: { texto: 'Pausada por Meta', tono: 'rust' },
    DISABLED: { texto: 'Desactivada', tono: 'rust' }
  });
  const CATEGORIA = /** @type {Record<string, string>} */ ({
    UTILITY: 'Servicio',
    MARKETING: 'Marketing',
    AUTHENTICATION: 'Autenticación'
  });

  /*
   * Dos puntos de partida, escritos para cualquier empresa: la salida del
   * ticket cuando la ventana está cerrada, y la encuesta al cerrar un caso.
   * Se pueden cambiar antes de mandarlas.
   */
  const SUGERENCIAS = [
    {
      titulo: 'Seguimiento de un caso',
      valores: {
        nombre: 'seguimiento_caso',
        categoria: 'UTILITY',
        encabezado: '',
        cuerpo:
          'Hola {{1}}, te escribimos por tu caso de soporte: {{2}}. Si necesitás algo más, respondé este mensaje.',
        pie: '',
        ejemplos: ['Juan', 'ya revisamos tu equipo y quedó funcionando'],
        botones: []
      }
    },
    {
      titulo: 'Encuesta de satisfacción',
      valores: {
        nombre: 'encuesta_satisfaccion',
        categoria: 'UTILITY',
        encabezado: '',
        cuerpo: 'Hola {{1}}, cerramos tu caso de soporte. ¿Cómo calificarías la atención que recibiste?',
        pie: 'Tu respuesta nos ayuda a mejorar',
        ejemplos: ['Juan'],
        botones: ['Excelente', 'Buena', 'Regular', 'Mala']
      }
    }
  ];

  const VACIA = {
    nombre: '',
    categoria: 'UTILITY',
    encabezado: '',
    cuerpo: '',
    pie: '',
    ejemplos: /** @type {string[]} */ ([]),
    botones: /** @type {string[]} */ ([])
  };

  let creando = $state(false);
  let valores = $state(structuredClone(VACIA));
  let enviando = $state(false);

  $effect(() => {
    if (form?.valores) {
      creando = true;
      valores = { ...structuredClone(VACIA), ...form.valores };
    }
  });

  //  Cuántas variables tiene el texto: una por cada {{n}} distinto.
  let cuantas = $derived(new Set([...(valores.cuerpo ?? '').matchAll(/\{\{(\d+)\}\}/g)].map((m) => m[1])).size);
  $effect(() => {
    if (valores.ejemplos.length !== cuantas) {
      valores.ejemplos = Array.from({ length: cuantas }, (_, i) => valores.ejemplos[i] ?? '');
    }
  });

  let previa = $derived(
    (valores.cuerpo ?? '').replace(/\{\{(\d+)\}\}/g, (_m, n) => valores.ejemplos[Number(n) - 1] || `{{${n}}}`)
  );

  /** @param {any} v */
  function usar(v) {
    valores = structuredClone(v);
    creando = true;
  }
</script>

<PageHeader title="Plantillas de WhatsApp">
  {#snippet crumb()}
    <a href="/settings/canales/whatsapp" class="volver"><ChevronLeft size={13} />WhatsApp</a>
  {/snippet}
  {#snippet sub()}
    Los únicos mensajes que se le pueden mandar a un cliente que no escribió en las últimas 24 h.
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:820px">
    {#if form?.creada}
      <p class="v2-card aviso-ok">
        «{form.creada.nombre}» quedó en revisión de Meta como
        {CATEGORIA[form.creada.categoria] ?? form.creada.categoria}. Suele tardar de minutos a unas
        horas; cuando la aprueben aparece como «Aprobada» y ya se puede mandar.
      </p>
    {:else if form?.borrada}
      <p class="v2-card aviso-ok">«{form.borrada}» se borró.</p>
    {:else if form?.uso}
      <p class="v2-card aviso-ok">
        «{form.uso.nombre}» {form.uso.enUso ? 'vuelve a estar en uso.' : 'quedó desactivada: no se ofrece ni se manda.'}
        {#if !form.uso.enUso && form.uso.momentos.length}
          <b>Ojo:</b> la usa{form.uso.momentos.length > 1 ? 'n' : ''}
          {form.uso.momentos.length} mensaje{form.uso.momentos.length > 1 ? 's' : ''} automático{form.uso.momentos.length > 1 ? 's' : ''}
          encendido{form.uso.momentos.length > 1 ? 's' : ''}, que no van a salir mientras esté desactivada
          (<a href="/settings/canales/whatsapp/mensajes">Mensajes automáticos</a>).
        {/if}
      </p>
    {/if}
    {#if form?.error && !form?.valores}
      <p class="v2-card aviso-mal">{form.error}</p>
    {/if}

    {#if data.can_edit}
      {#if !creando}
        <div class="acciones">
          <button type="button" class="v2-btn v2-btn-primary" onclick={() => usar(VACIA)}>
            <Plus size={14} /> Nueva plantilla
          </button>
          {#each SUGERENCIAS as s (s.titulo)}
            <button type="button" class="v2-btn" onclick={() => usar(s.valores)}>Usar «{s.titulo}»</button>
          {/each}
        </div>
      {:else}
        <form
          method="POST"
          action="?/crear"
          class="v2-card nueva"
          use:enhance={() => {
            enviando = true;
            return async ({ update, result }) => {
              await update({ reset: false });
              enviando = false;
              if (result.type === 'success') {
                creando = false;
                valores = structuredClone(VACIA);
              }
            };
          }}
        >
          <b style="font-size:14px">Nueva plantilla</b>
          {#if form?.error && form?.valores}
            <p class="aviso-mal-texto">{form.error}</p>
          {/if}
          <div class="par">
            <div class="v2-field" style="margin:0">
              <label for="f-nombre">Nombre</label>
              <input id="f-nombre" name="nombre" class="v2-input" bind:value={valores.nombre} placeholder="seguimiento_caso" />
              <p class="v2-hint">Minúsculas, números y guiones bajos. No lo ve el cliente.</p>
            </div>
            <div class="v2-field" style="margin:0">
              <label for="f-categoria">Categoría</label>
              <select id="f-categoria" name="categoria" class="v2-input" bind:value={valores.categoria}>
                <option value="UTILITY">Servicio (avisos sobre su cuenta o su caso)</option>
                <option value="MARKETING">Marketing (promociones, novedades)</option>
              </select>
              <p class="v2-hint">Meta decide la categoría final y cobra distinto cada una.</p>
            </div>
          </div>
          <input type="hidden" name="idioma" value="es" />
          <div class="v2-field" style="margin:0">
            <label for="f-encabezado">Título (opcional)</label>
            <input id="f-encabezado" name="encabezado" class="v2-input" maxlength="60" bind:value={valores.encabezado} />
          </div>
          <div class="v2-field" style="margin:0">
            <label for="f-cuerpo">Mensaje</label>
            <textarea id="f-cuerpo" name="cuerpo" class="v2-input" rows="4" maxlength="1024" bind:value={valores.cuerpo}></textarea>
            <p class="v2-hint">
              Para un dato que cambia en cada envío, escribí {'{{1}}'}, {'{{2}}'}… en orden. El mensaje no puede
              empezar ni terminar con uno.
            </p>
          </div>
          {#each valores.ejemplos as _, i (i)}
            <div class="v2-field" style="margin:0">
              <label for={`f-ej-${i}`}>Ejemplo para {`{{${i + 1}}}`}</label>
              <input id={`f-ej-${i}`} name="ejemplo" class="v2-input" bind:value={valores.ejemplos[i]} />
            </div>
          {/each}
          <div class="v2-field" style="margin:0">
            <label for="f-pie">Pie (opcional)</label>
            <input id="f-pie" name="pie" class="v2-input" maxlength="60" bind:value={valores.pie} />
          </div>
          <div class="v2-field" style="margin:0">
            <span class="etiqueta">Botones de respuesta (opcional)</span>
            {#each valores.botones as _, i (i)}
              <div class="boton">
                <input name="boton" class="v2-input" maxlength="25" bind:value={valores.botones[i]} aria-label={`Botón ${i + 1}`} />
                <button type="button" class="v2-btn v2-btn-sm" aria-label="Quitar botón" onclick={() => valores.botones.splice(i, 1)}>
                  <Trash2 size={13} />
                </button>
              </div>
            {/each}
            {#if valores.botones.length < 10}
              <button type="button" class="v2-btn v2-btn-sm" style="justify-self:start" onclick={() => valores.botones.push('')}>
                <Plus size={13} /> Agregar botón
              </button>
            {/if}
            <p class="v2-hint">El cliente responde tocando uno. Hasta 10, de hasta 25 letras.</p>
          </div>

          <div>
            <div class="v2-hint" style="margin:0 0 4px">Así lo va a leer el cliente</div>
            <div class="previa">
              {#if valores.encabezado}<b>{valores.encabezado}</b>{/if}
              <div>{previa || '…'}</div>
              {#if valores.pie}<small>{valores.pie}</small>{/if}
              {#if valores.botones.some((b) => b.trim())}
                <div class="previa-botones">
                  {#each valores.botones.filter((b) => b.trim()) as b (b)}<span>{b}</span>{/each}
                </div>
              {/if}
            </div>
          </div>

          <div class="acciones">
            <button class="v2-btn v2-btn-primary" type="submit" disabled={enviando}>
              {enviando ? 'Mandando…' : 'Mandar a revisión de Meta'}
            </button>
            <button type="button" class="v2-btn" onclick={() => (creando = false)}>Cancelar</button>
          </div>
        </form>
      {/if}
    {/if}

    <div class="v2-label" style="margin:22px 0 10px">Plantillas de la empresa</div>
    {#if data.plantillas === null}
      <p class="v2-card aviso-mal">
        No se pudieron leer las plantillas de Meta. Revisá en Ajustes → WhatsApp que el canal esté activo
        y el token vigente.
      </p>
    {:else if !data.plantillas.length}
      <p class="v2-card" style="padding:14px 16px;font-size:13px">Todavía no hay ninguna.</p>
    {:else}
      <div class="lista">
        {#each data.plantillas as p (p.nombre + p.idioma)}
          {@const est = ESTADO[p.estado] ?? { texto: p.estado, tono: 'slate' }}
          <div class="v2-card fila">
            <div class="fila-cabeza">
              <b>{p.nombre}</b>
              <Pill tone={est.tono} dot>{est.texto}</Pill>
              <span class="meta">{CATEGORIA[p.categoria] ?? p.categoria} · {p.idioma}</span>
              {#if p.en_uso === false}<Pill tone="slate">Desactivada</Pill>{/if}
              {#if data.can_edit}
                <form method="POST" action="?/uso" use:enhance class="uso">
                  <input type="hidden" name="nombre" value={p.nombre} />
                  <input type="hidden" name="en_uso" value={p.en_uso === false ? '1' : '0'} />
                  <button
                    type="submit"
                    class="interruptor"
                    class:encendido={p.en_uso !== false}
                    role="switch"
                    aria-checked={p.en_uso !== false}
                    aria-label={`${p.en_uso === false ? 'Activar' : 'Desactivar'} ${p.nombre}`}
                    title={p.en_uso === false ? 'Activar: se vuelve a ofrecer y a mandar' : 'Desactivar: deja de ofrecerse y de mandarse'}
                  >
                    <span class="perilla"></span>
                  </button>
                  <span class="uso-texto">{p.en_uso === false ? 'Sin usar' : 'En uso'}</span>
                </form>
              {/if}
              {#if data.can_edit}
                <form
                  method="POST"
                  action="?/borrar"
                  use:enhance={({ cancel }) => {
                    if (!confirm(`¿Borrar «${p.nombre}»? Si estaba aprobada, Meta no deja reusar el nombre por un tiempo.`)) cancel();
                  }}
                >
                  <input type="hidden" name="nombre" value={p.nombre} />
                  <button class="v2-btn v2-btn-sm" type="submit" aria-label={`Borrar ${p.nombre}`}><Trash2 size={13} /></button>
                </form>
              {/if}
            </div>
            {#if p.encabezado}<div class="texto"><b>{p.encabezado}</b></div>{/if}
            <div class="texto">{p.cuerpo}</div>
            {#if p.pie}<small class="meta">{p.pie}</small>{/if}
            {#if p.botones?.length}
              <div class="previa-botones">{#each p.botones as b (b)}<span>{b}</span>{/each}</div>
            {/if}
            {#if p.estado === 'REJECTED' && p.motivo_rechazo}
              <p class="aviso-mal-texto">Meta la rechazó: {p.motivo_rechazo}</p>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .volver {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    color: inherit;
    text-decoration: none;
  }
  .volver:hover {
    color: var(--v2-ink);
    text-decoration: underline;
  }
  .acciones {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .nueva {
    display: grid;
    gap: 14px;
    padding: 16px;
  }
  .par {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  @media (max-width: 640px) {
    .par {
      grid-template-columns: 1fr;
    }
  }
  .etiqueta {
    font-size: 12.5px;
    font-weight: 600;
  }
  .boton {
    display: flex;
    gap: 8px;
    max-width: 360px;
    margin-bottom: 6px;
  }
  .previa {
    display: grid;
    gap: 6px;
    padding: 12px 14px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    background: var(--v2-paper);
    font-size: 13px;
    line-height: 1.45;
    white-space: pre-wrap;
    max-width: 420px;
  }
  .previa small,
  .meta {
    color: var(--v2-slate);
    font-size: 12px;
  }
  .previa-botones {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .previa-botones span {
    padding: 4px 10px;
    border: 1px solid var(--v2-line);
    border-radius: 999px;
    font-size: 12px;
    background: var(--v2-card);
  }
  .lista {
    display: grid;
    gap: 10px;
  }
  .fila {
    display: grid;
    gap: 8px;
    padding: 14px 16px;
  }
  .fila-cabeza {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 13.5px;
  }
  .fila-cabeza .uso {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .uso-texto {
    font-size: 12px;
    color: var(--v2-slate);
    min-width: 52px;
  }
  /* El interruptor: un botón que se ve como tal (28/10/2026). */
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
  .texto {
    font-size: 13px;
    line-height: 1.45;
    white-space: pre-wrap;
  }
  .aviso-ok {
    padding: 12px 14px;
    margin: 0 0 16px;
    font-size: 13px;
    border-color: color-mix(in srgb, var(--v2-moss) 40%, var(--v2-line));
  }
  .aviso-mal {
    padding: 12px 14px;
    margin: 0 0 16px;
    font-size: 13px;
    color: var(--v2-rust);
  }
  .aviso-mal-texto {
    margin: 0;
    font-size: 13px;
    color: var(--v2-rust);
  }
</style>
