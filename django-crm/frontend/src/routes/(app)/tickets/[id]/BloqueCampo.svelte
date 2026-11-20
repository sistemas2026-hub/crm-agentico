<script>
  /*
   * EL BLOQUE «CAMPO» DEL TICKET (12/11/2026, auditoría del menú §2 «Tickets»).
   *
   * «¿Hay técnico asignado?» no se contestaba desde el ticket: la orden lo
   * nombraba solo por texto. Desde campo/0049 la orden está unida a su caso y
   * esto la muestra: estado, quién va, con qué cuadrilla y qué día, con el
   * enlace a la orden cuando quien mira la puede abrir.
   *
   * Se pide aparte (ruta `campo/`) para no demorar la apertura del ticket ni
   * tocar su `load`. Todo lo que dibuja lo calcula el backend.
   */
  import { onMount } from 'svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { tonoDeEstado, rotuloDeOrden, diaLegible, quienVa } from '$lib/v2/hilo-del-cliente.js';

  /** @type {{ casoId: string, servicio?: string | null }} */
  let { casoId, servicio = null } = $props();

  /** @type {{ estado: 'cargando' | 'listo' | 'error', ordenes: any[], mensaje: string }} */
  let campo = $state({ estado: 'cargando', ordenes: [], mensaje: '' });
  /** El servicio que trae el backend, por si la página no lo tenía. */
  let servicioDelCaso = $state(/** @type {string | null} */ (null));
  let servicioDeLaFicha = $derived(servicio || servicioDelCaso);

  onMount(async () => {
    try {
      const r = await fetch(`/tickets/${casoId}/campo`);
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        campo = { estado: 'error', ordenes: [], mensaje: d?.error || 'No se pudieron leer las visitas.' };
        return;
      }
      campo = { estado: 'listo', ordenes: d?.ordenes ?? [], mensaje: '' };
      servicioDelCaso = d?.servicio ?? null;
    } catch {
      campo = { estado: 'error', ordenes: [], mensaje: 'No se pudieron leer las visitas.' };
    }
  });
</script>

<div class="v2-label v2-rail-head">Campo</div>
{#if campo.estado === 'cargando'}
  <div class="v2-sub campo-nota">Buscando visitas…</div>
{:else if campo.estado === 'error'}
  <div class="v2-sub campo-nota">{campo.mensaje}</div>
{:else if campo.ordenes.length === 0}
  <!-- Lo normal en un ticket que se resolvió sin ir a la casa. -->
  <div class="v2-sub campo-nota">Sin visitas de campo para este ticket.</div>
{:else}
  <ul class="campo-lista">
    {#each campo.ordenes as o (o.id)}
      <li class="campo-orden">
        <div class="campo-cabeza">
          {#if o.puede_abrir}
            <a href="/ordenes/{o.id}" class="campo-ot">{rotuloDeOrden(o.numero)}</a>
          {:else}
            <span class="campo-ot">{rotuloDeOrden(o.numero)}</span>
          {/if}
          <span class="v2-sub">{o.tipo}</span>
          <span class="campo-estado"><Pill tone={tonoDeEstado(o.estado_operativo)}>{o.estado_etiqueta}</Pill></span>
        </div>
        <div class="campo-detalle">{quienVa(o)}</div>
        {#if o.fecha}
          <div class="v2-sub campo-detalle">Para el {diaLegible(o.fecha)}</div>
        {/if}
      </li>
    {/each}
  </ul>
{/if}
{#if servicioDeLaFicha}
  <a class="campo-ficha" href="/clientes/{encodeURIComponent(servicioDeLaFicha)}">Ver ficha del cliente</a>
{/if}

<style>
  .campo-nota {
    font-size: 12px;
  }
  .campo-lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 9px;
  }
  .campo-orden {
    font-size: 12.5px;
  }
  .campo-cabeza {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .campo-ot {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  a.campo-ot,
  .campo-ficha {
    color: var(--v2-ember-text);
    text-decoration: none;
  }
  a.campo-ot:hover,
  .campo-ficha:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .campo-estado {
    margin-left: auto;
  }
  .campo-detalle {
    margin-top: 2px;
  }
  .campo-ficha {
    display: inline-block;
    margin-top: 9px;
    font-size: 12.5px;
    font-weight: 600;
  }
</style>
