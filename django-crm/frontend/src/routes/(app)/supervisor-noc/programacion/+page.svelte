<script>
  /**
   * Programación — lo que quedó publicado un día (28/10/2026).
   *
   * El mismo dibujo que «Simular el día» en Despacho, a propósito: el simulacro
   * dice lo que el Supervisor HARÍA; esto, lo que QUEDÓ. Por cuadrilla, cada
   * orden con quién la asignó y a qué hora, y si al técnico le llegó el aviso.
   */
  import { goto } from '$app/navigation';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import { quienLaAsigno, textoDelAviso, textoDePrioridad } from '$lib/supervisor/dia-publicado.js';
  import '../supervisor-noc.css';

  /** @type {{ data: any }} */
  let { data } = $props();

  const publicado = $derived(data.publicado);
  const cuentas = $derived(publicado?.cuentas ?? {});

  /** @param {Event} e */
  function cambiarDia(e) {
    const v = /** @type {HTMLInputElement} */ (e.currentTarget).value;
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) goto(`/supervisor-noc/programacion?dia=${v}`, { keepFocus: true });
  }
</script>

<svelte:head>
  <title>Programación · Supervisor NOC</title>
</svelte:head>

<div class="snoc">
  <div class="v2-scroll">
    <div class="snoc-lienzo">
      <!-- ============ CABECERA ============ -->
      <section class="snoc-panel" style="gap:var(--snoc-md);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-md);">
          <div class="snoc-pila-xs">
            <h1 class="snoc-h1">PROGRAMACIÓN</h1>
            <p class="snoc-body snoc-secundario">
              Lo que quedó publicado para el día: a quién le tocó cada orden, quién se la
              asignó —el Supervisor o una persona— y si al técnico le llegó el aviso.
            </p>
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
            <PestanasNoc activa="programacion" />
          </div>
        </div>
      </section>

      {#if !data.puedeVer}
        <section class="snoc-panel">
          <p class="snoc-body">Esta pantalla es para quien gestiona el trabajo de campo.</p>
        </section>
      {:else}
        <section class="snoc-panel" style="gap:var(--snoc-sm);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Día</span>
              <input class="snoc-campo" type="date" value={data.dia} onchange={cambiarDia} />
            </label>
            <a class="snoc-pildora" href="/supervisor-noc/planes-semanales">Planes semanales</a>
          </div>

          {#if data.error}
            <p class="snoc-aviso snoc-error-txt">
              No se pudo leer lo publicado. No es que no haya nada: no se sabe.
            </p>
          {:else if publicado}
            <p class="snoc-body-sm">
              {cuentas.publicadas} {cuentas.publicadas === 1 ? 'orden publicada' : 'órdenes publicadas'}:
              {cuentas.por_el_supervisor} por el Supervisor · {cuentas.por_personas} por una persona{#if cuentas.sin_registro}
                · {cuentas.sin_registro} sin registro de quién{/if}
              · {cuentas.avisadas} con aviso enviado al teléfono
              {#if cuentas.esperan}· {cuentas.esperan} esperan cuadrilla{/if}
            </p>

            {#if !publicado.cuadrillas.length}
              <p class="snoc-body-sm snoc-secundario">No hay cuadrillas armadas para este día.</p>
            {/if}
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap:var(--snoc-sm);">
              {#each publicado.cuadrillas as c (c.jornada)}
                <div class="snoc-tarjeta snoc-pila-xs" style="min-width:0; justify-content:flex-start;">
                  <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-xs);">
                    <strong>{c.cuadrilla}</strong>
                    <span class="snoc-mono">{c.ordenes.length} de {c.tope}</span>
                  </div>
                  <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                    {#if c.labor}<span class="snoc-tag">{c.labor}</span>{/if}
                    {#each c.zonas as z (z)}<span class="snoc-body-sm snoc-secundario">{z}</span>{/each}
                  </div>
                  {#if !c.ordenes.length}
                    <p class="snoc-body-sm snoc-secundario">Sin órdenes publicadas.</p>
                  {/if}
                  {#each c.ordenes as o (o.id)}
                    <div class="snoc-pila-xs" style="border-top:1px solid var(--snoc-outline-variant); padding-top:var(--snoc-xs);">
                      <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                        <span class="snoc-mono">#{o.numero}</span>
                        <span style="min-width:0;">{o.tipo}</span>
                        <span class="snoc-body-sm">{textoDePrioridad(o.prioridad)}</span>
                        <span class="snoc-body-sm snoc-secundario">{o.barrio}</span>
                      </div>
                      <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                        <span class="snoc-tag">{o.estado_texto}</span>
                        <span class="snoc-body-sm snoc-secundario">{o.tecnicos.join(', ')}</span>
                      </div>
                      <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                        <span class="snoc-body-sm">Asignó: {quienLaAsigno(o, data.dia)}</span>
                        <span class="snoc-body-sm snoc-secundario">· {textoDelAviso(o.aviso)}</span>
                      </div>
                    </div>
                  {/each}
                </div>
              {/each}
            </div>

            {#if publicado.con_alguien_que_no_sale.length}
              <span class="snoc-label">
                Con alguien que este día no sale ({publicado.con_alguien_que_no_sale.length})
              </span>
              <p class="snoc-body-sm snoc-secundario">
                Las tiene alguien que no está en ninguna cuadrilla del día. Si el Supervisor publica
                solo, las libera en su próxima vuelta.
              </p>
              {#each publicado.con_alguien_que_no_sale as o (o.id)}
                <p class="snoc-body-sm">
                  <span class="snoc-mono">#{o.numero}</span> {o.tipo} · {o.barrio} · {o.tecnicos.join(', ')}
                  · {o.estado_texto} · Asignó: {quienLaAsigno(o, data.dia)}
                </p>
              {/each}
            {/if}

            {#if publicado.esperan.length}
              <span class="snoc-label">Esperan cuadrilla ({publicado.esperan.length})</span>
              <p class="snoc-body-sm snoc-secundario">
                Órdenes sin nadie: no entraron por el cupo, o su zona no tiene cuadrilla ese día.
              </p>
              {#each publicado.esperan as o (o.id)}
                <p class="snoc-body-sm">
                  <span class="snoc-mono">#{o.numero}</span> {o.tipo} · {textoDePrioridad(o.prioridad)} · {o.barrio}
                </p>
              {/each}
            {/if}
          {/if}
        </section>
      {/if}
    </div>
  </div>
</div>
