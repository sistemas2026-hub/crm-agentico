<script>
  /**
   * Programación — lo que quedó publicado un día (28/10/2026).
   *
   * El mismo dibujo que «Simular el día» en Despacho, a propósito: el simulacro
   * dice lo que el Supervisor HARÍA; esto, lo que QUEDÓ. Por cuadrilla, cada
   * orden con quién la asignó y a qué hora, y si al técnico le llegó el aviso.
   */
  import { enhance } from '$app/forms';
  import { goto } from '$app/navigation';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import {
    lineaDePersona,
    quienLaAsigno,
    textoDelAviso,
    textoDePrioridad,
    textoSinBajar
  } from '$lib/supervisor/dia-publicado.js';
  import {
    estadoDeCarga,
    lineaDeMaterial,
    opcionDelSupervisor,
    porQue,
    resumenDeLineas,
    tituloDelMaterial
  } from '$lib/supervisor/material-del-dia.js';
  import '../supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const publicado = $derived(data.publicado);
  const cuentas = $derived(publicado?.cuentas ?? {});

  //  EL MATERIAL DEL DÍA (28/10/2026): la propuesta, por jornada, para
  //  dibujarla dentro de la tarjeta de cada cuadrilla.
  const material = $derived(data.material);
  const materialPor = $derived(
    new Map((material?.cuadrillas ?? []).map((/** @type {any} */ m) => [m.jornada, m]))
  );
  const faltantes = $derived(
    (material?.bodegas ?? []).filter((/** @type {any} */ b) => Number(b.falta) > 0)
  );
  const conf = $derived(data.configuracion);

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

            <!-- EL MATERIAL DEL DÍA (28/10/2026, SPEC/objetivos/material-del-dia.md).
                 Fase 1: propone. Nada de esto mueve material todavía. -->
            <div class="snoc-pila-xs" style="border-top:1px solid var(--snoc-outline-variant); padding-top:var(--snoc-sm);">
              <span class="snoc-label">{tituloDelMaterial(material?.cuadrillas ?? [])}</span>
              {#if data.errorMaterial}
                <p class="snoc-body-sm snoc-error-txt">
                  No se pudo calcular el material. No es que no haga falta: no se sabe.
                </p>
              {:else if material}
                <p class="snoc-body-sm">
                  {material.cuentas.completas} de {material.cuentas.cuadrillas} cuadrillas con el kit
                  completo{#if material.cuentas.con_faltantes} · {material.cuentas.con_faltantes} con
                    faltantes{/if}{#if material.cuentas.sin_carga} · {material.cuentas.sin_carga} sin
                    carga{/if}
                </p>
                {#each faltantes as b (b.bodega + b.material)}
                  <p class="snoc-body-sm snoc-error-txt">
                    {b.bodega}: faltan {b.falta} {b.unidad} de {b.material} (hay {b.disponible}
                    libres; se piden {b.pedido}).
                  </p>
                {/each}
              {/if}
              {#if conf}
                <!-- EL SUPERVISOR ELIGE SOLO (28/10/2026: «la idea era que lo
                     hiciera el Supervisor»). Esto es para corregirlo: lo que
                     queda en «Que elija el Supervisor» lo deduce él. -->
                <details>
                  <summary class="snoc-body-sm">
                    Corregir lo que eligió el Supervisor (kit de cada labor, bodega de cada cuadrilla)
                  </summary>
                  <form method="POST" action="?/material" use:enhance class="snoc-pila-xs" style="padding-top:var(--snoc-xs);">
                    <span class="snoc-label">Kit de cada labor</span>
                    {#each conf.labores as l (l.codigo)}
                      <label class="snoc-pila-xs">
                        <span class="snoc-fila-sep" style="gap:var(--snoc-sm); flex-wrap:wrap;">
                          <span class="snoc-body-sm">{l.nombre}</span>
                          <select class="snoc-select" name={`kit:${l.codigo}`} value={l.kit ?? ''}>
                            <option value="">{opcionDelSupervisor(l.elige_el_supervisor)}</option>
                            {#each conf.kits as k (k.id)}<option value={k.id}>{k.nombre}</option>{/each}
                          </select>
                        </span>
                        {#if !l.kit}<span class="snoc-body-sm snoc-secundario">{l.motivo}</span>{/if}
                      </label>
                    {/each}
                    <span class="snoc-label">Bodega de cada cuadrilla</span>
                    {#each conf.cuadrillas as c (c.id)}
                      <label class="snoc-pila-xs">
                        <span class="snoc-fila-sep" style="gap:var(--snoc-sm); flex-wrap:wrap;">
                          <span class="snoc-body-sm">{c.nombre}</span>
                          <select class="snoc-select" name={`bodega:${c.id}`} value={c.bodega ?? ''}>
                            <option value="">{opcionDelSupervisor(c.elige_el_supervisor)}</option>
                            {#each conf.bodegas as b (b.id)}<option value={b.id}>{b.nombre}</option>{/each}
                          </select>
                        </span>
                        {#if !c.bodega}<span class="snoc-body-sm snoc-secundario">{c.motivo}</span>{/if}
                      </label>
                    {/each}
                    <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
                      <button class="snoc-btn" type="submit">Guardar</button>
                      {#if form?.hecho}<span class="snoc-body-sm">{form.hecho}</span>{/if}
                      {#if form?.error}<span class="snoc-body-sm snoc-error-txt">{form.error}</span>{/if}
                    </div>
                  </form>
                </details>
              {/if}
            </div>

            {#if !publicado.cuadrillas.length}
              <p class="snoc-body-sm snoc-secundario">No hay cuadrillas armadas para este día.</p>
            {/if}
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap:var(--snoc-sm);">
              {#each publicado.cuadrillas as c (c.jornada)}
                {@const m = materialPor.get(c.jornada)}
                <div class="snoc-tarjeta snoc-pila-xs" style="min-width:0; justify-content:flex-start;">
                  <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-xs);">
                    <strong>{c.cuadrilla}</strong>
                    <span class="snoc-mono">{c.ordenes.length} de {c.tope}</span>
                  </div>
                  <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                    {#if c.labor}<span class="snoc-tag">{c.labor}</span>{/if}
                    {#each c.zonas as z (z)}<span class="snoc-body-sm snoc-secundario">{z}</span>{/each}
                  </div>
                  <!-- POR PERSONA: lo que la app de cada uno debería tener. La
                       tarjeta cuenta las de toda la cuadrilla; la app, las de la
                       cuenta con que se entró (28/10/2026). -->
                  {#each c.personas ?? [] as p, i (i)}
                    <p class="snoc-body-sm snoc-secundario">{lineaDePersona(p, data.dia)}</p>
                    {#if p.sin_bajar}
                      <p class="snoc-body-sm snoc-error-txt">{textoSinBajar(p)}</p>
                    {/if}
                  {/each}
                  <!-- EL MATERIAL QUE SE LE CARGARÍA (propuesta, 28/10/2026). -->
                  {#if m && (m.lineas.length || m.avisos.length)}
                    <div class="snoc-pila-xs" style="border-top:1px solid var(--snoc-outline-variant); padding-top:var(--snoc-xs);">
                      <span class="snoc-label">Material{#if m.kit} · {m.kit}{/if}</span>
                      {#if estadoDeCarga(m)}
                        <p class="snoc-body-sm">{estadoDeCarga(m)}</p>
                      {/if}
                      {#if m.kit}
                        <p class="snoc-body-sm snoc-secundario">Kit: {porQue(m.kit_por)}</p>
                      {/if}
                      {#if m.lineas.length}
                        <p class="snoc-body-sm snoc-secundario">
                          Desde {m.bodega} ({porQue(m.bodega_por)}) · a {m.lider}
                        </p>
                      {/if}
                      {#each m.avisos as a (a)}
                        <p class="snoc-body-sm snoc-error-txt">{a}</p>
                      {/each}
                      <!-- PLEGADO (28/10/2026): la lista entera empachaba la
                           tarjeta; se abre cuando hace falta. -->
                      {#if m.lineas.length}
                        <details>
                          <summary class="snoc-body-sm">{resumenDeLineas(m.lineas)}</summary>
                          {#each m.lineas as l (l.material)}
                            <p class="snoc-body-sm">{lineaDeMaterial(l)}</p>
                          {/each}
                        </details>
                      {/if}
                    </div>
                  {/if}
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
                Órdenes sin nadie. Cada una dice por qué, con la misma cuenta con la que publica el
                Supervisor: la carga de cada cuadrilla, su tope, sus zonas y su labor.
              </p>
              {#each publicado.esperan as o (o.id)}
                <div class="snoc-pila-xs" style="border-top:1px solid var(--snoc-outline-variant); padding-top:var(--snoc-xs);">
                  <p class="snoc-body-sm">
                    <span class="snoc-mono">#{o.numero}</span> {o.tipo} · {textoDePrioridad(o.prioridad)} · {o.barrio}
                  </p>
                  {#if o.por_que}
                    <p class="snoc-body-sm snoc-secundario">{o.por_que}</p>
                  {/if}
                </div>
              {/each}
            {/if}
          {/if}
        </section>
      {/if}
    </div>
  </div>
</div>
