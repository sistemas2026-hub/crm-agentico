<script>
  /**
   * LA PAGINA DE UN AGENTE  --  13/11/2026
   *
   * Cinco pestañas, en el orden en que alguien revisa a un agente:
   *   Resumen       como le va: conversaciones, cuantas pasaron a una persona
   *                 y por que, herramientas que fallan o que no usa
   *   Herramientas  LO QUE PUEDE CAMBIAR primero (la hace sola / espera
   *                 aprobacion, del freno real) y despues lo que consulta
   *   Bitacora      lo que cambio en el mundo real y quien lo decidio
   *   Que recibe    las piezas del prompt con su peso
   *   Cambios       sus versiones, con la diferencia y restaurar
   *
   * Arriba: probar, pausar/reanudar, editar, eliminar.
   *
   * La logica de presentacion vive en $lib/agentes/presentacion.js (probada).
   * Comentarios aca y no como <!-- --> al principio de una rama {#if}: eso
   * choca con la hidratacion de Svelte 5 (ver routes/(app)/agentes).
   */
  import { enhance } from '$app/forms';
  import { goto, invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    ArrowLeft, Bot, BotMessageSquare, ScanEye, Play, PauseCircle, AlertTriangle, ChevronRight
  } from '@lucide/svelte';
  import AgenteFormDialog from '$lib/components/agentes/AgenteFormDialog.svelte';
  import AutonomiaDeAccion from '$lib/components/agentes/AutonomiaDeAccion.svelte';
  import { textoDelHueco } from '$lib/components/manual/entrenar.js';
  import {
    conteoDeAcciones, cuandoCorto, familia, formatoNumero, humanizar, indiceDeAutonomia, modoDeAccion,
    MODOS, nombreDe, pesoDelPrompt, porLoQueHace, resumenDe, subtituloDe, textoDeBitacora, FAMILIAS, vaSola
  } from '$lib/agentes/presentacion.js';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const a = $derived(data.agente);
  const fam = $derived(familia(a));
  const autonomiaDe = $derived(indiceDeAutonomia(data.autonomia));
  const grupos = $derived(porLoQueHace(a.herramientas));
  const conteo = $derived(conteoDeAcciones(a, autonomiaDe));
  const peso = $derived(pesoDelPrompt(a.prompt_piezas));
  const d = $derived(data.desempeno);
  const conDatos = $derived(!!d && !d.sin_conversaciones && d.conversaciones > 0);

  //  La pestaña inicial sigue al formulario que se acaba de mandar: quien
  //  cambio la autonomia de una accion vuelve a ver esa accion, no el resumen.
  const PESTANAS = /** @type {const} */ (['resumen', 'herramientas', 'bitacora', 'recibe', 'cambios']);
  let pestana = $state(
    form?.autonomia ? 'herramientas' : form?.restaurar ? 'cambios' : 'resumen'
  );
  const titulos = $derived({
    resumen: 'Resumen',
    herramientas: `Herramientas · ${(a.herramientas ?? []).length}`,
    bitacora: 'Bitácora',
    recibe: 'Qué recibe',
    cambios: 'Cambios'
  });

  let dialogoAbierto = $state(false);
  let confirmandoPausa = $state(false);
  let borradoArmado = $state(false);
  /** @type {Record<string, boolean>} */
  let abierta = $state({});
  /** @type {Record<number, boolean>} */
  let diffAbierto = $state({});
  let filtro = $state('todas');

  const pct = (/** @type {number} */ x, /** @type {number} */ y) => (y ? Math.round((x / y) * 100) : 0);
  const MOTIVO_COLORES = ['#ef4444', '#3b82f6', '#8b5cf6', '#f59e0b', '#14b8a6', '#64748b'];
  const motivos = $derived(
    Object.entries(d?.por_motivo ?? {}).sort((x, y) => y[1] - x[1])
  );
  const fallan = $derived(
    Object.entries(d?.herramientas ?? {})
      .filter(([, h]) => h.fallos > 0)
      .sort((x, y) => y[1].fallos - x[1].fallos)
  );
  const bitacoraFiltrada = $derived(
    (data.bitacora ?? []).filter((/** @type {any} */ f) =>
      filtro === 'todas' ? true
      : filtro === 'fallaron' ? f.resultado === 'fallo'
      : filtro === 'rechazadas' ? f.decidio === 'rechazo'
      : f.decidio === 'espera')
  );

  //  El simulador SIEMPRE entra por el agente de entrada (el router): no se
  //  puede abrir directo con un especialista. Se dice, en vez de prometer otra
  //  cosa. Los internos se prueban desde el Asistente.
  const probar = $derived(
    fam === 'cliente'
      ? { href: '/simulador-whatsapp', titulo: 'Abre el simulador de WhatsApp: entra por la recepción, que le deriva según el tema' }
      : { href: '/asistente', titulo: 'Abre el Asistente interno' }
  );

  async function borrar() {
    if (!borradoArmado) { borradoArmado = true; return; }
    const res = await fetch(`/api/agentes/${encodeURIComponent(a.nombre)}`, { method: 'DELETE' });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      toast.error(e?.error || 'No se pudo borrar el agente');
      borradoArmado = false;
      return;
    }
    toast.success('Agente borrado.');
    await goto('/agentes', { invalidateAll: true });
  }

  /** enhance que avisa y recarga, sin perder la pestaña. */
  const conAviso = (/** @type {string} */ ok) => () => async ({ result, update }) => {
    if (result.type === 'success') toast.success(ok);
    else if (result.type === 'failure') toast.error(result.data?.pausa?.error || result.data?.restaurar?.error || 'No se pudo.');
    await update({ reset: true });
    confirmandoPausa = false;
  };
</script>

<svelte:head><title>{nombreDe(a)} · Agentes</title></svelte:head>

<div class="v2-scroll">
  <div class="v2-pad pagina fam-{fam}">
    <a class="volver" href="/agentes"><ArrowLeft size={15} /> Agentes</a>

    <header class="cabecera">
      <div class="identidad">
        <span class="icono" aria-hidden="true">
          {#if a.automatico}<ScanEye size={28} />{:else if fam === 'cliente'}<BotMessageSquare size={28} />{:else}<Bot size={28} />{/if}
        </span>
        <div class="identidad-txt">
          <div class="titulo">
            <h1>{nombreDe(a)}</h1>
            <span class="pill-fam">{fam === 'cliente' ? 'Le habla al cliente' : fam === 'equipo' ? 'Uso interno' : 'Automático'}</span>
            {#if a.pausado}<span class="pill-pausa"><PauseCircle size={13} /> En pausa</span>{/if}
          </div>
          <span class="clave">{a.nombre}{subtituloDe(a) ? ` · ${subtituloDe(a)}` : ''}</span>
          {#if resumenDe(a)}
            <p class="resumen">{resumenDe(a)}</p>
          {:else if data.esAdmin}
            <p class="resumen vacio">Sin una frase que diga qué hace. Agregala en Editar → «Qué hace, en una frase».</p>
          {/if}
        </div>
      </div>

      {#if !a.automatico}
        <div class="botones">
          <a class="v2-btn" href={probar.href} title={probar.titulo}><Play size={14} /> Probar</a>
          {#if data.esAdmin}
            {#if a.pausado}
              <form method="POST" action="?/reanudar" use:enhance={conAviso('Agente reanudado: vuelve a atender.')}>
                <button class="v2-btn" type="submit">Reanudar</button>
              </form>
            {:else}
              <button class="v2-btn" type="button" onclick={() => (confirmandoPausa = !confirmandoPausa)}>
                <PauseCircle size={14} /> Pausar
              </button>
            {/if}
            <button class="v2-btn" type="button" onclick={() => (dialogoAbierto = true)}>Editar</button>
            <button class="v2-btn eliminar" type="button" onclick={borrar}>
              {borradoArmado ? 'Confirmar: no se puede deshacer' : 'Eliminar'}
            </button>
          {/if}
        </div>
      {/if}
    </header>

    {#if confirmandoPausa && !a.pausado}
      <div class="aviso" role="region" aria-label="Confirmar pausa">
        <p>
          Mientras esté en pausa, las conversaciones que le lleguen pasan a una persona del equipo: no
          se llama al modelo y el cliente recibe un aviso una sola vez. No se borra nada; se reanuda con
          un clic.
        </p>
        <div class="aviso-botones">
          <button class="v2-btn" type="button" onclick={() => (confirmandoPausa = false)}>Cancelar</button>
          <form method="POST" action="?/pausar" use:enhance={conAviso('Agente en pausa: sus conversaciones van a una persona.')}>
            <button class="v2-btn v2-btn-primary" type="submit">Pausar ahora</button>
          </form>
        </div>
      </div>
    {/if}
    {#if a.pausado}
      <p class="banda-pausa" role="status">
        <PauseCircle size={16} /> En pausa: no atiende. Las conversaciones que le llegan quedan marcadas para una persona del equipo.
      </p>
    {/if}

    {#if a.automatico}
      <section class="caja">
        <p>{a.descripcion}</p>
        <p class="v2-sub">Modelo: <strong>{a.modelo || 'hereda el del rol que cierra cada conversación'}</strong></p>
        <a class="enlace" href="/manual">Ver sus aportes pendientes en el manual <ChevronRight size={14} /></a>
      </section>
    {:else}
      <div class="pestanas" role="tablist" aria-label="Secciones del agente">
        {#each PESTANAS as p (p)}
          <button type="button" role="tab" aria-selected={pestana === p} class:activa={pestana === p}
            onclick={() => (pestana = p)}>{titulos[p]}</button>
        {/each}
      </div>

      {#if pestana === 'resumen'}
        <section class="hechos" aria-label="En resumen">
          <div><span class="et fam">Le habla a</span><span>{fam === 'cliente' ? 'El cliente, por WhatsApp' : 'El equipo, desde el Asistente'}</span></div>
          <div><span class="et">{fam === 'cliente' ? 'Atiende' : 'Cargo'}</span><span>{(fam === 'cliente' ? a.atiende : subtituloDe(a)) || '—'}</span></div>
          <div>
            <span class="et cambia">Puede cambiar</span>
            <span>
              {#if conteo.acciones}
                <strong>{conteo.acciones} {conteo.acciones === 1 ? 'cosa' : 'cosas'}</strong>:
                <span class="txt-sola">{conteo.solas} {conteo.solas === 1 ? 'sola' : 'solas'}</span>,
                <span class="txt-espera">{conteo.espera} con aprobación</span>
              {:else}
                Nada: solo consulta
              {/if}
            </span>
          </div>
          <div><span class="et">Recibe en cada turno</span><span>{formatoNumero(peso)} caracteres</span></div>
        </section>

        <section class="caja" aria-labelledby="t-des">
          <h2 id="t-des">Cómo le va · últimos {data.dias} días</h2>
          {#if d === null}
            <p class="v2-sub">No se pudo leer el desempeño ahora. Lo demás de la página está al día.</p>
          {:else if !conDatos}
            <p class="v2-sub">Sin conversaciones en el periodo: no hay con qué medirlo todavía.</p>
          {:else}
            <div class="cifras">
              <div><strong class="n-azul">{formatoNumero(d.conversaciones)}</strong><span>conversaciones atendidas</span></div>
              <div>
                <strong class="n-verde">{pct(d.resueltas_sin_persona, d.conversaciones)} %</strong>
                <span>las resolvió sin una persona</span>
                <span class="mini-barra" role="img" aria-label="{pct(d.resueltas_sin_persona, d.conversaciones)} por ciento">
                  <span style="width:{pct(d.resueltas_sin_persona, d.conversaciones)}%"></span>
                </span>
              </div>
              <div><strong class="n-ambar">{formatoNumero(d.escaladas)}</strong><span>pasaron a una persona</span></div>
            </div>
            {#if motivos.length}
              <h3>Por qué pasaron a una persona</h3>
              <ul class="motivos">
                {#each motivos as [motivo, n], i (motivo)}
                  <li>
                    <span>{humanizar(motivo)}</span>
                    <span class="motivo-barra"><span style="width:{pct(n, motivos[0][1])}%; background:{MOTIVO_COLORES[i % MOTIVO_COLORES.length]}"></span></span>
                    <span class="num">{n}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          {/if}
        </section>

        {#if conDatos && (fallan.length || d.sin_uso?.length)}
          <div class="dos">
            <section class="caja" aria-labelledby="t-fal">
              <h2 id="t-fal">Herramientas que fallan</h2>
              <p class="v2-sub">Si escala porque falló el proveedor, no es culpa del agente.</p>
              {#each fallan as [nombre, h] (nombre)}
                <div class="renglon"><span>{humanizar(nombre)}</span><span class="txt-ambar num">{h.fallos} de {h.usos}{h.error_mas_comun ? ` · ${h.error_mas_comun}` : ''}</span></div>
              {:else}
                <p class="v2-sub">Ninguna falló en el periodo.</p>
              {/each}
            </section>
            <section class="caja" aria-labelledby="t-sin">
              <h2 id="t-sin">Sin usar en {data.dias} días</h2>
              <p class="v2-sub">Quitarlas reduce riesgo y acorta lo que recibe en cada turno. Se quitan en Editar.</p>
              {#each d.sin_uso ?? [] as nombre (nombre)}
                <div class="renglon"><span>{humanizar(nombre)}</span><span class="clave">{nombre}</span></div>
              {:else}
                <p class="v2-sub">Usó todas.</p>
              {/each}
            </section>
          </div>
        {/if}

        {#if data.huecos.length}
          <section class="caja hueco" aria-labelledby="t-hue">
            <h2 id="t-hue">Le falta saber hacer · {data.huecos.length}</h2>
            <ul class="lista">
              {#each data.huecos.slice(0, 5) as h (h.senal + h.motivo)}
                <li><span class="num">{h.n_casos}</span> {textoDelHueco(h)}</li>
              {/each}
            </ul>
            <a class="enlace" href="/habilidades">Enseñarle en Habilidades <ChevronRight size={14} /></a>
          </section>
        {/if}
      {:else if pestana === 'herramientas'}
        <section class="caja actua" aria-labelledby="t-act">
          <h2 id="t-act">Lo que puede cambiar · {grupos.actua.length}</h2>
          <p class="v2-sub">
            Una persona aprueba solo lo crítico: mover dinero, dejar sin servicio sin que vuelva solo,
            afectar a muchos clientes, exponer datos o comprometer a la empresa con un tercero.
          </p>
          {#if data.errorAutonomia}<p class="txt-ambar">{data.errorAutonomia}</p>{/if}
          {#each grupos.actua as h (h.nombre)}
            {@const modo = modoDeAccion(h, autonomiaDe, a.nombre)}
            <div class="accion">
              <div class="accion-cabeza">
                <span class="accion-nombre">{humanizar(h.nombre)}</span>
                <span class="chip {MODOS[modo ?? 'sin_dato'].tono}">{MODOS[modo ?? 'sin_dato'].texto}</span>
                {#if h.critica === false}<span class="chip sola-suave">No crítica</span>{/if}
                {#if h.irreversible}<span class="chip critica">Irreversible</span>{/if}
              </div>
              <span class="clave">{h.nombre}{h.campos_permitidos?.length ? ` · ve ${h.campos_permitidos.length} campo${h.campos_permitidos.length === 1 ? '' : 's'}` : ''}</span>
              {#if h.resumen}<p class="accion-desc">{h.resumen}</p>{/if}
              {#if h.descripcion}
                <details class="para-modelo">
                  <summary>Lo que le dice al modelo</summary>
                  <p>{h.descripcion}</p>
                </details>
              {/if}
              {#if autonomiaDe?.[h.nombre]}
                <AutonomiaDeAccion accion={autonomiaDe[h.nombre]} agente={a.nombre} esAdmin={data.esAdmin}
                  resultado={form?.autonomia ?? null} mostrarEstado={false} />
              {:else if !vaSola(modo) && modo === 'espera'}
                <p class="v2-sub">Una persona la aprueba antes de que se ejecute.</p>
              {/if}
            </div>
          {:else}
            <p class="v2-sub">No puede cambiar nada: solo consulta.</p>
          {/each}
        </section>

        {#each [['consulta', 'Lo que consulta', 'solo lee, no cambia nada'], ['cuenta', 'Lo que cuenta', 'totales, sin datos de un cliente']] as [clave, titulo, nota] (clave)}
          {#if grupos[clave].length}
            <section class="caja" aria-label={titulo}>
              <h2>{titulo} · {grupos[clave].length} <span class="v2-sub nota-h">{nota}</span></h2>
              {#each grupos[clave] as h (h.nombre)}
                <div class="consulta">
                  <button type="button" class="consulta-fila" aria-expanded={!!abierta[h.nombre]}
                    onclick={() => (abierta = { ...abierta, [h.nombre]: !abierta[h.nombre] })}>
                    <span class="giro" class:abierto={abierta[h.nombre]}><ChevronRight size={14} /></span>
                    <span>{humanizar(h.nombre)}</span>
                    <span class="v2-sub num">
                      {h.campos_permitidos?.length ? `${h.campos_permitidos.length} campo${h.campos_permitidos.length === 1 ? '' : 's'}` : 'sin datos del cliente'}
                    </span>
                    {#if h.resumen}<span class="consulta-resumen">{h.resumen}</span>{/if}
                  </button>
                  {#if abierta[h.nombre]}
                    <div class="consulta-detalle">
                      <span class="clave">{h.nombre}</span>
                      {#if h.resumen}<p class="accion-desc">{h.resumen}</p>{/if}
                      {#if h.descripcion}
                        <details class="para-modelo">
                          <summary>Lo que le dice al modelo</summary>
                          <p>{h.descripcion}</p>
                        </details>
                      {/if}
                      {#if h.campos_permitidos?.length}
                        <div class="campos">{#each h.campos_permitidos as c (c)}<code>{c}</code>{/each}</div>
                      {/if}
                    </div>
                  {/if}
                </div>
              {/each}
            </section>
          {/if}
        {/each}
      {:else if pestana === 'bitacora'}
        <section class="caja" aria-labelledby="t-bit">
          <div class="caja-cabeza">
            <div>
              <h2 id="t-bit">Lo que cambió en el mundo real · {data.dias} días</h2>
              <p class="v2-sub">Cada vez que usó una herramienta que cambia algo: quién lo decidió y qué pasó. El cliente, a cuatro dígitos.</p>
            </div>
            <div class="filtros" role="group" aria-label="Filtrar">
              {#each [['todas', 'Todas'], ['fallaron', 'Fallaron'], ['rechazadas', 'Rechazadas'], ['esperan', 'Esperan']] as [v, t] (v)}
                <button type="button" class:activo={filtro === v} aria-pressed={filtro === v} onclick={() => (filtro = v)}>{t}</button>
              {/each}
            </div>
          </div>
          {#if data.bitacora === null}
            <p class="v2-sub">No se pudo leer la bitácora ahora.</p>
          {:else if !bitacoraFiltrada.length}
            <p class="v2-sub">{data.bitacora.length ? 'Nada con ese filtro.' : 'No cambió nada en el periodo.'}</p>
          {:else}
            <div class="tabla-scroll">
              <table class="bitacora">
                <thead><tr><th>Cuándo</th><th>Qué hizo</th><th>Cliente</th><th>Quién decidió</th><th>Resultado</th></tr></thead>
                <tbody>
                  {#each bitacoraFiltrada as f, i (f.cuando + f.herramienta + i)}
                    {@const t = textoDeBitacora(f)}
                    <tr>
                      <td class="num">{cuandoCorto(f.cuando)}</td>
                      <td class="fuerte">{humanizar(f.herramienta)}</td>
                      <td class="num">{f.cliente}</td>
                      <td>{t.decidio}</td>
                      <td class="res-{t.tono}">{t.resultado}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </section>
      {:else if pestana === 'recibe'}
        <section class="caja recibe" aria-labelledby="t-rec">
          <h2 id="t-rec">Qué recibe en cada turno</h2>
          <p class="v2-sub">
            {a.prompt_piezas?.length ?? 0} bloques, {formatoNumero(peso)} caracteres. La barra muestra cuánto pesa
            cada uno; cada bloque dice dónde se edita.
          </p>
          {#each a.prompt_piezas ?? [] as p (p.titulo)}
            <details class="pieza">
              <summary>
                <span class="pieza-cabeza">
                  <span class="fuerte">{p.titulo}</span>
                  <span class="v2-sub num">{formatoNumero(p.texto?.length ?? 0)} car.</span>
                </span>
                <span class="peso"><span style="width:{Math.max(1.5, pct(p.texto?.length ?? 0, peso))}%"
                  class:grande={(p.texto?.length ?? 0) > peso * 0.4}></span></span>
                <span class="v2-sub origen" class:fijo={!p.editable}>{p.origen}</span>
              </summary>
              <pre>{p.texto}</pre>
            </details>
          {/each}
          <p class="v2-sub">Además recibe la descripción de cada herramienta y, si la pregunta coincide con el manual, sus fragmentos.</p>
        </section>
      {:else if pestana === 'cambios'}
        <section class="caja" aria-labelledby="t-cam">
          <h2 id="t-cam">Cambios a este agente</h2>
          <p class="v2-sub">Cada versión en que cambió, la más nueva primero. Restaurar guarda una versión nueva con lo de antes: nada se pierde. Las versiones anteriores al 13/11/2026 no registran quién las hizo.</p>
          {#if form?.restaurar?.error}<p class="txt-rojo">{form.restaurar.error}</p>{/if}
          {#if data.historial === null}
            <p class="v2-sub">No se pudo leer el historial ahora.</p>
          {:else if !data.historial.length}
            <p class="v2-sub">Sin cambios registrados desde que existe el historial.</p>
          {:else}
            {#each data.historial as c (c.version)}
              <div class="cambio">
                <div class="cambio-ver">
                  <strong class="num">v{c.version}</strong>
                  {#if c.actual}<span class="chip sola">Actual</span>{/if}
                  <span class="v2-sub num">{cuandoCorto(c.creado_en)}</span>
                  <span class="autor" class:sin-autor={!c.autor}>{c.autor ? `por ${c.autor}` : 'autor sin registro'}</span>
                </div>
                <ul class="cambio-que">{#each c.resumen as frase, i (i)}<li>{frase}</li>{/each}</ul>
                <div class="cambio-botones">
                  {#if c.diff_instrucciones}
                    <button class="v2-btn v2-btn-sm" type="button" onclick={() => (diffAbierto = { ...diffAbierto, [c.version]: !diffAbierto[c.version] })}>
                      {diffAbierto[c.version] ? 'Ocultar diferencia' : 'Ver diferencia'}
                    </button>
                  {/if}
                  {#if data.esAdmin && !c.actual && c.restaurable}
                    <form method="POST" action="?/restaurar" class="restaurar" use:enhance={conAviso(`Volvió a la versión ${c.version}.`)}>
                      <input type="hidden" name="version" value={c.version} />
                      <label class="v2-sub"><input type="checkbox" name="confirmo" value="si" required /> confirmo</label>
                      <button class="v2-btn v2-btn-sm" type="submit">Restaurar</button>
                    </form>
                  {/if}
                </div>
                {#if diffAbierto[c.version]}
                  <pre class="diff">{#each c.diff_instrucciones.split('\n') as linea, i (i)}<span class:mas={linea.startsWith('+') && !linea.startsWith('+++')} class:menos={linea.startsWith('-') && !linea.startsWith('---')}>{linea}
</span>{/each}</pre>
                {/if}
              </div>
            {/each}
          {/if}
        </section>
      {/if}
    {/if}
  </div>
</div>

{#if data.esAdmin && !a.automatico}
  <AgenteFormDialog bind:open={dialogoAbierto} modo="editar" agente={a}
    catalogo={data.catalogo} motivos={data.motivosEscalada} autonomia={data.autonomia} onSaved={() => invalidateAll()} />
{/if}

<style>
  .pagina { display: flex; flex-direction: column; gap: 16px; padding-top: 12px; padding-bottom: 48px; max-width: 1120px; }
  .fam-cliente { --fam: var(--v2-fam-cliente); --fam-soft: var(--v2-fam-cliente-soft); --fam-line: var(--v2-fam-cliente-line); }
  .fam-equipo { --fam: var(--v2-fam-equipo); --fam-soft: var(--v2-fam-equipo-soft); --fam-line: var(--v2-fam-equipo-line); }
  .fam-auto { --fam: var(--v2-fam-auto); --fam-soft: var(--v2-fam-auto-soft); --fam-line: var(--v2-fam-auto-line); }
  .num { font-variant-numeric: tabular-nums; }
  .fuerte { font-weight: 600; }
  .clave { font-family: var(--v2-mono); font-size: 11.5px; color: var(--v2-slate); }
  h2 { margin: 0; font-size: 15px; font-weight: 600; }
  h3 { margin: 6px 0 0; font-size: 11.5px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--v2-slate); }

  .volver { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--v2-slate); text-decoration: none; align-self: flex-start; padding: 4px 0; }
  .volver:hover { color: var(--v2-ink); }

  /* Cabecera: una banda del color de su familia. */
  .cabecera {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 16px;
    padding: 20px 22px; border-radius: 14px; background: var(--fam-soft); border: 1px solid var(--fam-line);
  }
  .identidad { display: flex; gap: 16px; align-items: flex-start; min-width: 0; flex: 1 1 420px; }
  .icono {
    width: 56px; height: 56px; flex: none; border-radius: 14px; display: grid; place-items: center;
    color: #fff; background: var(--fam); box-shadow: 0 4px 12px color-mix(in srgb, var(--fam) 30%, transparent);
  }
  :global(.dark) .icono { color: var(--v2-paper); }
  .identidad-txt { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .titulo { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.015em; }
  .pill-fam {
    font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
    color: var(--fam); background: color-mix(in srgb, var(--fam) 12%, var(--v2-card)); border: 1px solid var(--fam-line);
  }
  .pill-pausa {
    display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 600; padding: 3px 10px;
    border-radius: 999px; color: var(--v2-rust); background: var(--v2-critica-soft); border: 1px solid var(--v2-critica-line);
  }
  .resumen { margin: 2px 0 0; font-size: 15px; line-height: 1.55; max-width: 70ch; }
  .resumen.vacio { font-size: 13px; color: var(--v2-slate); font-style: italic; }
  .botones { display: flex; flex-wrap: wrap; gap: 8px; }
  .botones form { display: contents; }
  .eliminar { color: var(--v2-rust); }

  .aviso {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px;
    padding: 12px 16px; border: 1px solid var(--v2-line); border-radius: var(--v2-radius); background: var(--v2-card);
  }
  .aviso p { margin: 0; font-size: 13.5px; line-height: 1.45; max-width: 72ch; }
  .aviso-botones { display: flex; gap: 8px; }
  .banda-pausa {
    display: flex; align-items: center; gap: 8px; margin: 0; padding: 12px 16px; border-radius: var(--v2-radius);
    font-size: 13.5px; color: var(--v2-rust); background: var(--v2-critica-soft); border: 1px solid var(--v2-critica-line);
  }

  .pestanas { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--v2-line); }
  .pestanas button {
    border: 0; background: transparent; font: inherit; font-size: 14px; color: var(--v2-slate); cursor: pointer;
    padding: 10px 12px; min-height: 44px; margin-bottom: -1px; border-bottom: 2px solid transparent;
  }
  .pestanas button:hover { color: var(--v2-ink); }
  .pestanas button.activa { color: var(--fam); font-weight: 600; border-bottom-color: var(--fam); }

  .caja {
    display: flex; flex-direction: column; gap: 10px; padding: 16px 18px;
    border: 1px solid var(--v2-line); border-radius: var(--v2-radius); background: var(--v2-card); box-shadow: var(--v2-shadow);
  }
  .caja p { margin: 0; }
  .caja-cabeza { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: flex-start; }
  .enlace { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 600; color: var(--v2-ember-text); text-decoration: none; align-self: flex-start; }
  .dos { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .renglon { display: flex; justify-content: space-between; gap: 10px; font-size: 13.5px; padding-top: 7px; border-top: 1px solid var(--v2-line-soft); }

  .hechos {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    border: 1px solid var(--v2-line); border-radius: var(--v2-radius); background: var(--v2-card);
  }
  .hechos > div { display: flex; flex-direction: column; gap: 3px; padding: 14px 16px; border-right: 1px solid var(--v2-line-soft); font-size: 14px; }
  .hechos > div:last-child { border-right: 0; }
  .et { font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--v2-slate); }
  .et.fam { color: var(--fam); }
  .et.cambia { color: var(--v2-ember-text); }
  .txt-sola { color: var(--v2-sola); font-weight: 600; }
  .txt-espera { color: var(--v2-espera); font-weight: 600; }
  .txt-ambar { color: var(--v2-clay); }
  .txt-rojo { color: var(--v2-rust); }

  .cifras { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }
  .cifras > div { display: flex; flex-direction: column; gap: 3px; font-size: 13px; color: var(--v2-slate); }
  .cifras strong { font-size: 28px; font-weight: 700; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .n-azul { color: var(--v2-fam-cliente); }
  .n-verde { color: var(--v2-sola-fuerte); }
  .n-ambar { color: var(--v2-clay); }
  .mini-barra { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--v2-espera-soft); margin-top: 4px; }
  .mini-barra span { background: var(--v2-sola-fuerte); }
  .motivos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .motivos li { display: grid; grid-template-columns: minmax(160px, 260px) 1fr 40px; gap: 12px; align-items: center; font-size: 13.5px; }
  .motivo-barra { height: 8px; border-radius: 4px; background: var(--v2-line-soft); display: block; }
  .motivo-barra span { display: block; height: 8px; border-radius: 4px; }
  .motivos .num { text-align: right; }
  .hueco { border-color: color-mix(in srgb, var(--v2-clay) 40%, var(--v2-line)); }
  .lista { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; font-size: 13.5px; }
  .lista .num { display: inline-block; min-width: 1.6em; font-weight: 600; }

  /* Herramientas */
  .actua { border-color: var(--v2-ember-line); }
  .accion { display: flex; flex-direction: column; gap: 4px; padding-top: 12px; border-top: 1px solid var(--v2-line-soft); }
  .accion-cabeza { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .accion-nombre { font-size: 14px; font-weight: 600; }
  .accion-desc { font-size: 13px; color: var(--v2-ink); opacity: 0.85; margin: 0; max-width: 80ch; }
  .chip { font-size: 11.5px; font-weight: 600; padding: 2px 9px; border-radius: 999px; }
  .chip.sola { color: var(--v2-sola); background: var(--v2-sola-soft); border: 1px solid var(--v2-sola-line); }
  .chip.sola-suave { color: var(--v2-sola); background: transparent; border: 1px dashed var(--v2-sola-line); font-weight: 500; }
  .chip.espera { color: var(--v2-espera); background: var(--v2-espera-soft); border: 1px solid var(--v2-espera-line); }
  .chip.critica { color: var(--v2-rust); background: var(--v2-critica-soft); border: 1px solid var(--v2-critica-line); }
  .chip.neutro { color: var(--v2-slate); background: var(--v2-line-soft); border: 1px solid var(--v2-line); }
  .nota-h { font-weight: 400; font-size: 13px; }
  .consulta { border-top: 1px solid var(--v2-line-soft); }
  .consulta-fila {
    width: 100%; display: grid; grid-template-columns: 16px 1fr auto; gap: 10px; align-items: center;
    padding: 9px 2px; border: 0; background: transparent; font: inherit; font-size: 13.5px; text-align: left;
    color: var(--v2-ink); cursor: pointer; min-height: 40px;
  }
  .consulta-fila:hover { background: var(--v2-hover); }
  .giro { display: grid; color: var(--v2-slate); transition: transform 0.15s; }
  .giro.abierto { transform: rotate(90deg); }
  .consulta-detalle { padding: 0 2px 12px 28px; display: flex; flex-direction: column; gap: 6px; }
  .campos { display: flex; flex-wrap: wrap; gap: 6px; }
  /* La descripcion que lee el modelo, plegada: sirve para depurar, no para
     entender que hace la herramienta (para eso esta 'resumen'). */
  .para-modelo { font-size: 12px; color: var(--v2-slate); }
  .para-modelo summary { cursor: pointer; width: fit-content; }
  .para-modelo p {
    margin: 6px 0 0; padding: 7px 9px; border-radius: 8px; background: var(--v2-line-soft);
    white-space: pre-wrap; line-height: 1.5; max-width: 90ch;
  }
  .consulta-resumen { grid-column: 2 / -1; font-size: 12.5px; color: var(--v2-slate); margin-top: -2px; }
  .autor { font-size: 12px; color: var(--v2-ink); }
  .autor.sin-autor { color: var(--v2-slate); font-style: italic; }
  .campos code {
    font-family: var(--v2-mono); font-size: 11.5px; padding: 3px 7px; border-radius: 6px;
    background: var(--v2-line-soft); border: 1px solid var(--v2-line);
  }

  /* Bitacora */
  .filtros { display: flex; gap: 6px; flex-wrap: wrap; }
  .filtros button {
    font: inherit; font-size: 12.5px; padding: 5px 12px; border-radius: 999px; cursor: pointer;
    border: 1px solid var(--v2-line); background: var(--v2-card); color: var(--v2-ink);
  }
  .filtros button.activo { background: var(--v2-ink); color: var(--v2-card); border-color: var(--v2-ink); }
  .tabla-scroll { overflow-x: auto; }
  .bitacora { width: 100%; min-width: 680px; border-collapse: collapse; font-size: 13.5px; }
  .bitacora th { text-align: left; font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--v2-slate); padding: 8px 10px; border-bottom: 1px solid var(--v2-line); }
  .bitacora td { padding: 9px 10px; border-bottom: 1px solid var(--v2-line-soft); }
  .res-sola { color: var(--v2-sola-fuerte); font-weight: 600; }
  .res-critica { color: var(--v2-rust); font-weight: 600; }
  .res-neutro { color: var(--v2-slate); }

  /* Que recibe */
  .pieza { border-top: 1px solid var(--v2-line-soft); padding: 8px 0; }
  .pieza summary { cursor: pointer; display: flex; flex-direction: column; gap: 4px; list-style: none; }
  .pieza summary::-webkit-details-marker { display: none; }
  .pieza-cabeza { display: flex; justify-content: space-between; gap: 10px; font-size: 13.5px; }
  .peso { height: 4px; border-radius: 2px; background: var(--v2-line-soft); display: block; }
  .peso span { display: block; height: 4px; border-radius: 2px; background: color-mix(in srgb, var(--fam) 55%, transparent); }
  .peso span.grande { background: var(--fam); }
  .origen { font-size: 12px; }
  .origen.fijo { font-style: italic; }
  .pieza pre, .diff {
    margin: 8px 0 0; font-family: inherit; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
    background: var(--v2-line-soft); border-radius: 8px; padding: 8px 10px; max-height: 260px; overflow-y: auto;
  }

  /* Cambios */
  .cambio { display: grid; grid-template-columns: 150px minmax(0, 1fr) auto; gap: 8px 14px; padding-top: 12px; border-top: 1px solid var(--v2-line-soft); align-items: start; }
  .cambio-ver { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; font-size: 13px; }
  .cambio-que { margin: 0; padding-left: 16px; font-size: 13.5px; display: grid; gap: 2px; }
  .cambio-botones { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
  .restaurar { display: flex; gap: 6px; align-items: center; }
  .restaurar label { display: inline-flex; gap: 4px; align-items: center; font-size: 12px; }
  .diff { grid-column: 1 / -1; font-family: var(--v2-mono); font-size: 11.5px; }
  .diff .mas { color: var(--v2-sola); background: var(--v2-sola-soft); display: block; }
  .diff .menos { color: var(--v2-rust); background: var(--v2-critica-soft); display: block; }

  @media (max-width: 760px) {
    .cabecera { padding: 16px; }
    .icono { width: 44px; height: 44px; }
    h1 { font-size: 21px; }
    .motivos li { grid-template-columns: 1fr 60px 32px; }
    .cambio { grid-template-columns: 1fr; }
    .cambio-botones { justify-content: flex-start; }
  }
</style>
