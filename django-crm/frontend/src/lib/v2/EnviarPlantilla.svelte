<script>
  /**
   * Mandar una plantilla aprobada de WhatsApp desde el ticket (28/10/2026).
   *
   * Es la salida cuando la respuesta de texto no le llega al cliente porque
   * pasaron más de 24 h desde su último mensaje: fuera de esa ventana WhatsApp
   * sólo acepta plantillas aprobadas por Meta. Las mismas reglas que la Bandeja
   * (lib/conversaciones/plantillas.js): la vista previa reparte los valores
   * igual que el envío, y una plantilla mixta no se ofrece.
   *
   * Las plantillas se piden recién al abrir: es una llamada en vivo a Meta.
   */
  import { invalidateAll } from '$app/navigation';
  import { MessageSquareText, X } from '@lucide/svelte';
  import {
    etiquetasDe,
    motivoDeBloqueo,
    sePuedeEnviar,
    vistaPrevia
  } from '$lib/conversaciones/plantillas.js';

  /** @type {{ casoId: string, abierta?: boolean }} */
  let { casoId, abierta = false } = $props();

  let abierto = $state(false);
  $effect(() => {
    if (abierta) abierto = true;
  });

  /** @type {any[] | null} */
  let plantillas = $state(null);
  let cargando = $state(false);
  let errorLista = $state('');
  let nombre = $state('');
  /** @type {string[]} */
  let valores = $state([]);
  let enviando = $state(false);
  /** @type {any} */
  let resultado = $state(null);
  //  Una por apertura: un doble clic no manda dos, otra apertura es otro mensaje.
  let clave = $state('');

  let elegida = $derived((plantillas ?? []).find((p) => p.nombre === nombre) ?? null);
  let etiquetas = $derived(elegida ? etiquetasDe(elegida) : []);
  let previa = $derived(elegida ? vistaPrevia(elegida, valores) : '');
  let bloqueo = $derived(motivoDeBloqueo(elegida));
  let listo = $derived(Boolean(elegida) && sePuedeEnviar(elegida, valores) && !enviando);

  $effect(() => {
    if (abierto && plantillas === null && !cargando) cargar();
  });

  async function cargar() {
    cargando = true;
    errorLista = '';
    clave = crypto.randomUUID();
    try {
      const r = await fetch('/api/canales/plantillas');
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d?.error || 'No se pudieron leer las plantillas.');
      plantillas = d.plantillas ?? [];
    } catch (/** @type {any} */ e) {
      errorLista = e?.message || 'No se pudieron leer las plantillas.';
      plantillas = null;
    } finally {
      cargando = false;
    }
  }

  function elegir(/** @type {string} */ n) {
    nombre = n;
    const p = (plantillas ?? []).find((x) => x.nombre === n);
    valores = p ? etiquetasDe(p).map(() => '') : [];
    resultado = null;
  }

  async function enviar() {
    if (!listo || !elegida) return;
    enviando = true;
    resultado = null;
    try {
      const r = await fetch(`/api/cases/${encodeURIComponent(casoId)}/plantilla`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ plantilla: elegida.nombre, variables: valores, clave_idempotencia: clave })
      });
      const d = await r.json().catch(() => ({}));
      resultado = { http: r.status, ...d };
      if (r.ok) await invalidateAll();
    } catch {
      resultado = { http: 0, incierto: true };
    } finally {
      enviando = false;
    }
  }

  let mensaje = $derived.by(() => {
    if (!resultado) return null;
    if (resultado.http === 201 || resultado.http === 200) {
      if (resultado.ya_existia) return { tono: 'ok', texto: 'Esa plantilla ya se había mandado.' };
      if (resultado.resultado === 'aceptado')
        return { tono: 'ok', texto: 'Enviada por WhatsApp y copiada al ticket de la operación.' };
      if (resultado.resultado === 'rechazado')
        return { tono: 'mal', texto: `WhatsApp no la aceptó${resultado.aviso ? `: ${resultado.aviso}` : '.'}` };
      return {
        tono: 'mal',
        texto: 'Quedó guardada, pero no se pudo confirmar que le llegó. No la mandes de nuevo: si salió, la recibiría dos veces.'
      };
    }
    if (resultado.incierto)
      return { tono: 'mal', texto: resultado.error || 'No se pudo confirmar el envío. No la mandes de nuevo.' };
    if (resultado.sin_conversacion)
      return { tono: 'mal', texto: 'Este ticket no tiene un chat de WhatsApp: no hay a quién mandársela.' };
    return { tono: 'mal', texto: resultado.error || 'No se pudo mandar la plantilla.' };
  });
</script>

{#if !abierto}
  <button type="button" class="v2-btn v2-btn-sm plantilla-abrir" onclick={() => (abierto = true)}>
    <MessageSquareText size={13} aria-hidden="true" /> Mandar con plantilla de WhatsApp
  </button>
{:else}
  <div class="v2-card plantilla">
    <div class="plantilla-cabeza">
      <b>Mandar con plantilla de WhatsApp</b>
      <button type="button" class="v2-btn v2-btn-sm" aria-label="Cerrar" onclick={() => (abierto = false)}>
        <X size={13} />
      </button>
    </div>
    <p class="v2-hint" style="margin:0">
      Si pasaron más de 24 h desde el último mensaje del cliente, WhatsApp sólo deja mandar plantillas
      aprobadas por Meta. Cuando el cliente conteste, ya se le puede escribir normal.
    </p>

    {#if cargando}
      <p class="v2-sub plantilla-nota">Consultando las plantillas aprobadas…</p>
    {:else if errorLista}
      <p class="plantilla-mal">{errorLista}</p>
      <button type="button" class="v2-btn v2-btn-sm" onclick={cargar}>Probar de nuevo</button>
    {:else if plantillas && !plantillas.length}
      <p class="plantilla-mal">
        La empresa no tiene plantillas aprobadas en Meta. Se crean en Ajustes → WhatsApp → Plantillas.
      </p>
    {:else if plantillas}
      <div class="v2-field" style="margin:0">
        <label for="f-plantilla">Plantilla</label>
        <select id="f-plantilla" class="v2-input" value={nombre} onchange={(e) => elegir(e.currentTarget.value)}>
          <option value="">Elegí una</option>
          {#each plantillas as p (p.nombre)}
            <option value={p.nombre}>{p.nombre}</option>
          {/each}
        </select>
      </div>

      {#if elegida}
        {#if bloqueo}
          <p class="plantilla-mal">{bloqueo}</p>
        {:else}
          {#each etiquetas as et, i (et.parte + et.hueco)}
            <div class="v2-field" style="margin:0">
              <label for={`f-var-${i}`}>{et.titulo}{et.donde ? ` (${et.donde})` : ''}</label>
              <input id={`f-var-${i}`} class="v2-input" bind:value={valores[i]} placeholder={`Reemplaza ${et.reemplaza}`} />
            </div>
          {/each}
          <div>
            <div class="v2-hint" style="margin:0 0 4px">Así lo va a leer el cliente</div>
            <div class="plantilla-previa">{previa}</div>
          </div>
          <div>
            <button type="button" class="v2-btn v2-btn-primary v2-btn-sm" disabled={!listo} onclick={enviar}>
              {enviando ? 'Enviando…' : 'Enviar plantilla'}
            </button>
          </div>
        {/if}
      {/if}
    {/if}

    {#if mensaje}
      <p class={mensaje.tono === 'ok' ? 'plantilla-ok' : 'plantilla-mal'} aria-live="polite">{mensaje.texto}</p>
    {/if}
  </div>
{/if}

<style>
  .plantilla-abrir {
    margin-top: 10px;
  }
  .plantilla {
    display: grid;
    gap: 12px;
    padding: 14px 16px;
    margin-top: 12px;
  }
  .plantilla-cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 13.5px;
  }
  .plantilla-nota {
    margin: 0;
    font-size: 12.5px;
  }
  .plantilla-previa {
    white-space: pre-wrap;
    padding: 10px 12px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    background: var(--v2-paper);
    font-size: 13px;
    line-height: 1.45;
  }
  .plantilla-ok {
    margin: 0;
    font-size: 13px;
    color: var(--v2-moss);
  }
  .plantilla-mal {
    margin: 0;
    font-size: 13px;
    color: var(--v2-rust);
  }
</style>
