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
  import FaltantesDelDia from '$lib/supervisor/FaltantesDelDia.svelte';
  import MaterialDeLaCuadrilla from '$lib/supervisor/MaterialDeLaCuadrilla.svelte';
  import NovedadesDeLaCuadrilla from '$lib/supervisor/NovedadesDeLaCuadrilla.svelte';
  import SeguimientoDeCuadrillas from '$lib/supervisor/SeguimientoDeCuadrillas.svelte';
  import OrdenDelDia from '$lib/supervisor/OrdenDelDia.svelte';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import {
    lineaDePersona,
    quienLaAsigno,
    textoDeLaSiguiente,
    textoDelDiaDeLaCuadrilla,
    textoDePrioridad,
    textoSinBajar
  } from '$lib/supervisor/dia-publicado.js';
  import { opcionDelSupervisor, tituloDelMaterial } from '$lib/supervisor/material-del-dia.js';
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
        <!-- ============ EL SEGUIMIENTO DE LAS CUADRILLAS (30/10/2026) ============
             Arriba de todo: en qué está cada una, hace cuánto, y su log del día. -->
        <!-- Lo que pasó al aprobar o devolver un cierre (30/10/2026). -->
        {#if form?.de === 'revision'}
          <p class="snoc-body-sm" class:snoc-error-txt={!!form?.error} role="status">{form?.hecho ?? form?.error}</p>
        {/if}
        {#if publicado?.cuadrillas?.length}
          <section class="snoc-panel" style="gap:var(--snoc-sm);">
            <span class="snoc-label">Seguimiento de las cuadrillas</span>
            <SeguimientoDeCuadrillas cuadrillas={publicado.cuadrillas} />
          </section>
        {/if}

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
                <!-- Las cuentas en pastillas y una línea por bodega, con la
                     tabla plegada (29/10/2026: eran trece líneas rojas iguales). -->
                <FaltantesDelDia cuentas={material.cuentas} {faltantes} />
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
                          <!-- SI SE TOMA DE APOYO (30/10/2026): una cuadrilla con
                               cupo libre recibe órdenes de esta labor. La obra de
                               red arranca en «no»: pide equipo de empalme. -->
                          <select class="snoc-select" name={`apoyo:${l.codigo}`}
                                  value={l.de_apoyo === false ? 'no' : 'si'}
                                  aria-label={`¿${l.nombre} se toma de apoyo?`}>
                            <option value="si">Se toma de apoyo</option>
                            <option value="no">No se toma de apoyo</option>
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
                  <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-xs); align-items:baseline;">
                    <strong style="font-size:15px;">{c.cuadrilla}</strong>
                    <span class="snoc-body-sm snoc-secundario">{c.ordenes.length} de {c.tope} órdenes</span>
                  </div>
                  <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap; align-items:center;">
                    {#if c.labor}<span style="padding:0 8px; border-radius:999px; background:var(--snoc-surface-container); color:var(--snoc-on-surface-variant); font-size:12px; line-height:20px; font-weight:600;">{c.labor}</span>{/if}
                    <!-- La de apoyo (30/10/2026): con el cupo libre, órdenes de esta otra. -->
                    {#if c.apoyo}<span style="padding:0 8px; border-radius:999px; border:1px dashed var(--snoc-outline-variant); color:var(--snoc-secondary); font-size:12px; line-height:20px; font-weight:600;">Apoyo: {c.apoyo}</span>{/if}
                    {#each c.zonas as z (z)}<span class="snoc-body-sm snoc-secundario">{z}</span>{/each}
                  </div>
                  <!-- EL DÍA EN UNA LÍNEA (30/10/2026): a qué hora salió, cuántas
                       lleva y en cuál está. -->
                  {#if c.resumen_del_dia}
                    <span class="snoc-body-sm snoc-secundario">{textoDelDiaDeLaCuadrilla(c.resumen_del_dia)}</span>
                  {/if}
                  <!-- LO QUE AVISÓ LA CUADRILLA (30/10/2026): «se pinchó la llanta». -->
                  <NovedadesDeLaCuadrilla novedades={c.novedades ?? []} />
                  <!-- POR PERSONA: lo que la app de cada uno debería tener. La
                       tarjeta cuenta las de toda la cuadrilla; la app, las de la
                       cuenta con que se entró (28/10/2026). -->
                  {#each c.personas ?? [] as p, i (i)}
                    <p class="snoc-body-sm snoc-secundario">{lineaDePersona(p, data.dia)}</p>
                    {#if p.sin_bajar}
                      <p class="snoc-body-sm snoc-error-txt">{textoSinBajar(p)}</p>
                    {/if}
                  {/each}
                  <!-- EL MATERIAL: compacto, con los avisos y la lista plegados
                       (29/10/2026). Ver MaterialDeLaCuadrilla.svelte. -->
                  {#if m && (m.lineas.length || m.avisos.length)}
                    <MaterialDeLaCuadrilla {m} />
                  {/if}
                  {#if !c.ordenes.length}
                    <p class="snoc-body-sm snoc-secundario">Sin órdenes publicadas.</p>
                  {/if}
                  <!-- Las órdenes, cada una en su tarjeta y en el orden del día
                       que arma el Supervisor y sigue la app (29/10/2026). -->
                  {#if c.ordenes.length}
                    <div class="snoc-pila-xs" style="gap:var(--snoc-sm); padding-top:var(--snoc-xs);">
                      {#each c.ordenes as o (o.id)}
                        <OrdenDelDia orden={o} dia={data.dia} marca={textoDeLaSiguiente(c.ordenes)} />
                      {/each}
                    </div>
                  {/if}
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
