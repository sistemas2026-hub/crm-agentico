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
  import EsperanCuadrilla from '$lib/supervisor/EsperanCuadrilla.svelte';
  import FaltantesDelDia from '$lib/supervisor/FaltantesDelDia.svelte';
  import OrdenCerrada from '$lib/supervisor/OrdenCerrada.svelte';
  import MaterialDeLaCuadrilla from '$lib/supervisor/MaterialDeLaCuadrilla.svelte';
  import NovedadesDeLaCuadrilla from '$lib/supervisor/NovedadesDeLaCuadrilla.svelte';
  import SeguimientoDeCuadrillas from '$lib/supervisor/SeguimientoDeCuadrillas.svelte';
  import OrdenDelDia from '$lib/supervisor/OrdenDelDia.svelte';
  import PorRevisar from '$lib/supervisor/PorRevisar.svelte';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import {
    lineaDePersona,
    quienLaAsigno,
    textoDeLaSiguiente,
    textoDelDiaDeLaCuadrilla,
    textoSinBajar
  } from '$lib/supervisor/dia-publicado.js';
  import { opcionDelSupervisor, tituloDelMaterial } from '$lib/supervisor/material-del-dia.js';
  import '../supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  //  PROGRAMACIÓN VIVA (30/10/2026). El usuario: «estas tarjetas tienen que
  //  estar vivas: si manda un reporte desde la app, que no se tenga que
  //  recargar ni presionar un botón; solo y sin que se vea». Cada 15 s, con
  //  la pestaña a la vista (y al volver a ella), se pide lo publicado del día
  //  y se cambia en su lugar: las tarjetas se conservan por su id, así que un
  //  log abierto sigue abierto. Sin respuesta, queda lo último que se vio.
  let vivo = $state(/** @type {any} */ (null));
  let vivoDe = $state('');
  const publicado = $derived(vivo && vivoDe === data.dia ? vivo : data.publicado);
  const cuentas = $derived(publicado?.cuentas ?? {});

  //  Un load nuevo (otro día, o después de aprobar o devolver) trae lo más
  //  fresco: lo vivo de antes ya no manda.
  $effect(() => {
    data.publicado;
    vivo = null;
  });

  $effect(() => {
    if (!data.puedeVer || data.vista !== 'hoy') return;
    const dia = data.dia;
    let parado = false;
    async function refrescar() {
      if (document.visibilityState !== 'visible') return;
      try {
        const r = await fetch(`/supervisor-noc/programacion/vivo?dia=${encodeURIComponent(dia)}`);
        if (!r.ok) return;
        const d = await r.json();
        if (!parado && d?.publicado) {
          vivo = d.publicado;
          vivoDe = dia;
        }
      } catch {
        //  Sin red: queda lo último que se vio.
      }
    }
    const intervalo = setInterval(refrescar, 15000);
    document.addEventListener('visibilitychange', refrescar);
    window.addEventListener('focus', refrescar);
    return () => {
      parado = true;
      clearInterval(intervalo);
      document.removeEventListener('visibilitychange', refrescar);
      window.removeEventListener('focus', refrescar);
    };
  });

  const enlaceDe = (/** @type {string} */ vista, /** @type {string} */ rango = 'hoy') =>
    vista === 'cerradas'
      ? `/supervisor-noc/programacion?dia=${data.dia}&vista=cerradas&rango=${rango}`
      : `/supervisor-noc/programacion?dia=${data.dia}`;
  const RANGOS = [
    { clave: 'hoy', nombre: 'Hoy' },
    { clave: 'ayer', nombre: 'Ayer' },
    { clave: '7d', nombre: 'Últimos 7 días' }
  ];

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

      {#if data.puedeVer}
        <!-- HOY / CERRADAS (30/10/2026): lo de hoy, y lo que ya se cerró. -->
        <nav class="snoc-fila" aria-label="Vista" style="gap:var(--snoc-xs); flex-wrap:wrap;">
          <a class="snoc-pildora" class:snoc-pildora-activa={data.vista === 'hoy'}
             aria-current={data.vista === 'hoy' ? 'page' : undefined} href={enlaceDe('hoy')}>Hoy</a>
          <a class="snoc-pildora" class:snoc-pildora-activa={data.vista === 'cerradas'}
             aria-current={data.vista === 'cerradas' ? 'page' : undefined} href={enlaceDe('cerradas')}>Cerradas</a>
        </nav>
      {/if}

      {#if !data.puedeVer}
        <section class="snoc-panel">
          <p class="snoc-body">Esta pantalla es para quien gestiona el trabajo de campo.</p>
        </section>
      {:else if data.vista === 'cerradas'}
        <!-- ============ LAS CERRADAS (30/10/2026) ============ -->
        <section class="snoc-panel" style="gap:var(--snoc-sm);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            <div class="snoc-fila" role="group" aria-label="Rango" style="gap:var(--snoc-xs); flex-wrap:wrap;">
              {#each RANGOS as r (r.clave)}
                <a class="snoc-pildora" class:snoc-pildora-activa={data.rango === r.clave}
                   aria-current={data.rango === r.clave ? 'page' : undefined} href={enlaceDe('cerradas', r.clave)}>{r.nombre}</a>
              {/each}
            </div>
            {#if data.cerradas}
              <p class="snoc-body-sm">
                {data.cerradas.cuentas.cerradas} {data.cerradas.cuentas.cerradas === 1 ? 'cerrada' : 'cerradas'}
                · {data.cerradas.cuentas.por_una_persona} por una persona
                · {data.cerradas.cuentas.por_el_supervisor} por el Supervisor
                {#if data.cerradas.cuentas.ticket_sin_cerrar}
                  · <span class="snoc-error-txt">{data.cerradas.cuentas.ticket_sin_cerrar} con el ticket del ISP sin cerrar</span>
                {/if}
              </p>
            {/if}
          </div>
          {#if data.errorCerradas}
            <p class="snoc-aviso snoc-error-txt">No se pudieron leer las cerradas. No es que no haya: no se sabe.</p>
          {:else if data.cerradas && !data.cerradas.ordenes.length}
            <p class="snoc-body-sm snoc-secundario">No se cerró ninguna orden en estos días.</p>
          {:else if data.cerradas}
            <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(min(100%, 380px), 1fr)); gap:var(--snoc-sm); align-items:start;">
              {#each data.cerradas.ordenes as o (o.id)}
                <OrdenCerrada orden={o} />
              {/each}
            </div>
          {/if}
        </section>
      {:else}
        <!-- ============ EL SEGUIMIENTO DE LAS CUADRILLAS (30/10/2026) ============
             Arriba de todo: en qué está cada una, hace cuánto, y su log del día. -->
        <!-- Lo que pasó al aprobar o devolver un cierre (30/10/2026). -->
        {#if form?.de === 'revision'}
          <p class="snoc-body-sm" class:snoc-error-txt={!!form?.error} role="status">{form?.hecho ?? form?.error}</p>
        {/if}
        <!-- POR REVISAR (31/10/2026): lo terminado de días anteriores que nadie
             cerró. Antes no salía en ningún lado (la OT #4 en producción). -->
        <PorRevisar ordenes={publicado?.por_revisar ?? []} dia={data.dia} />

        {#if publicado?.cuadrillas?.length}
          <section class="snoc-panel" style="gap:var(--snoc-sm);">
            <span class="snoc-label">Seguimiento de las cuadrillas</span>
            <SeguimientoDeCuadrillas cuadrillas={publicado.cuadrillas} />
            {#if data.seguimiento}
              <!-- LO QUE EL SUPERVISOR HACE SOLO (30/10/2026). Que cierre solo
                   NO se enciende acá: se le delega desde su chat, con el nivel
                   3 y el interruptor de emergencia, como las otras tareas. -->
              <details>
                <summary class="snoc-body-sm">Lo que el Supervisor hace solo</summary>
                <form method="POST" action="?/seguimiento" use:enhance class="snoc-pila-xs" style="padding-top:var(--snoc-xs);">
                  <label class="snoc-body-sm">
                    <input type="checkbox" name="recordar_al_tecnico" checked={data.seguimiento.recordar_al_tecnico} />
                    Le recuerda al técnico, en su teléfono, la orden que pasa la ventana sin reporte
                  </label>
                  <span class="snoc-body-sm snoc-secundario">
                    Para que apruebe y cierre solo las órdenes que da por buenas, pedíselo en su chat («aprobá y cerrá las órdenes que des por buenas»). Necesita el nivel 3 de autonomía, y el ticket del ISP lo cierra solo si el motor lo deja: hoy esa herramienta exige aprobación humana.
                  </span>
                  <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
                    <button class="snoc-btn" type="submit">Guardar</button>
                    {#if form?.de === 'seguimiento'}<span class="snoc-body-sm" class:snoc-error-txt={!!form?.error}>{form?.hecho ?? form?.error}</span>{/if}
                  </div>
                </form>
              </details>
            {/if}
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
                      {#if form?.hecho && !form?.de}<span class="snoc-body-sm">{form.hecho}</span>{/if}
                      {#if form?.error && !form?.de}<span class="snoc-body-sm snoc-error-txt">{form.error}</span>{/if}
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

            <!-- PLEGADAS Y POR MOTIVO (30/10/2026): «que se puedan contraer». -->
            <EsperanCuadrilla esperan={publicado.esperan} />
          {/if}
        </section>
      {/if}
    </div>
  </div>
</div>
