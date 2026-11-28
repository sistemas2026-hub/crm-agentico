<script>
  /**
   * AGENTES: QUIEN ATIENDE, A QUIEN LE HABLA Y QUE PUEDE CAMBIAR  --  13/11/2026
   *
   * Era una grilla de tarjetas de hasta 1.100px de alto (soporte tiene 28
   * herramientas) que se leia por una ventana de 460px: las cifras y los
   * agentes operativos quedaban fijos arriba y solo la grilla tenia scroll.
   * Ahora es UNA tabla, un renglon por agente, agrupada por a quien le habla,
   * y TODO comparte un solo scroll. El detalle de cada agente (herramientas,
   * lo que recibe, autonomia, bitacora, cambios) vive en /agentes/[nombre].
   *
   * Dos cosas que la pantalla anterior decia mal y esta no:
   *   · "pide confirmacion antes" en cada accion, leyendo un campo que el
   *     motor declara y no aplica. Ahora: la hace sola / espera aprobacion,
   *     del freno real (ver $lib/agentes/presentacion.js::modoDeAccion).
   *   · la clave del rol capitalizada ("Soporte_tecnico_cliente") como nombre.
   *
   * La logica vive en $lib/agentes/presentacion.js, que tiene sus pruebas.
   *
   * Sobre los comentarios: van aca y no como <!-- --> al principio de una rama
   * {#if}: eso choco con los marcadores de hidratacion de Svelte 5 (ver la
   * historia de este archivo).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import AgenteFormDialog from '$lib/components/agentes/AgenteFormDialog.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { Bot, BotMessageSquare, ScanEye, Radar, ChevronRight, PauseCircle, AlertTriangle } from '@lucide/svelte';
  import { AGENTES_OPERATIVOS } from '$lib/v2/agentes-operativos.js';
  import {
    agrupar, conteoDeAcciones, familia, indiceDeAutonomia, nombreDe, resumenDe,
    resumenGlobal, subtituloDe, textoEscalo, FAMILIAS
  } from '$lib/agentes/presentacion.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  const esAdmin = $derived(data.role === 'ADMIN');
  let dialogoAbierto = $state(false);

  const autonomiaDe = $derived(indiceDeAutonomia(data.autonomia));
  const resumen = $derived(resumenGlobal(data.agentes ?? [], autonomiaDe));

  //  Los operativos (Supervisor NOC IA) no vienen del motor: viven en el CRM.
  //  Se suman a la familia 'auto' como filas que llevan a su tablero, fuera
  //  de lo que depende del motor -- si el motor no responde, siguen ahi.
  const operativos = AGENTES_OPERATIVOS.map((o) => ({
    operativo: true, nombre: o.clave, nombre_visible: o.nombre, cargo: o.rotulo,
    resumen: o.descripcion, href: o.href, enlace: o.enlace
  }));
  const grupos = $derived(agrupar([...(data.agentes ?? []), ...operativos]));

  const desempenoDe = (/** @type {string} */ n) => data.desempeno?.agentes?.[n];
  const huecosDe = (/** @type {string} */ n) => data.huecosPorRol?.[n]?.length ?? 0;
  const pct = (/** @type {number} */ a, /** @type {number} */ b) => (b ? Math.round((a / b) * 100) : 0);

  /** Lo que dice "que puede hacer" de un agente conversacional. @param {any} a */
  function puede(a) {
    const c = conteoDeAcciones(a, autonomiaDe);
    const mira = [
      c.consultas && `${c.consultas} consulta${c.consultas === 1 ? '' : 's'}`,
      c.cuentas && `${c.cuentas} conteo${c.cuentas === 1 ? '' : 's'}`
    ].filter(Boolean).join(' · ') || 'Sin consultas';
    return { ...c, mira };
  }

  const hechosDelSupervisor = $derived(
    data.tareasSupervisor
      ? data.tareasSupervisor.delegadas.length
        ? `Hace solo ${data.tareasSupervisor.delegadas.length} de ${data.tareasSupervisor.total} tareas`
        : `Sus ${data.tareasSupervisor.total} tareas esperan a una persona`
      : null
  );
</script>

<PageHeader title="Agentes">
  {#snippet sub()}
    Quién atiende, a quién le habla y qué puede cambiar.
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-sm" href="/agentes/permisos">Quién puede qué</a>
    <a class="v2-btn v2-btn-sm" href="/agentes/flujo">Flujo de derivación</a>
    {#if esAdmin}
      <a class="v2-btn v2-btn-sm" href="/team">Quién usa cada agente</a>
      <Button type="button" onclick={() => (dialogoAbierto = true)}>Nuevo agente</Button>
    {/if}
  {/snippet}
</PageHeader>

{#if esAdmin}
  <AgenteFormDialog bind:open={dialogoAbierto} modo="crear" agente={null}
    catalogo={data.catalogo || []} motivos={data.motivosEscalada || []} autonomia={data.autonomia} />
{/if}

<div class="v2-scroll">
  <div class="v2-pad pagina">
    {#if data.error}
      <p class="aviso-error" role="alert"><AlertTriangle size={15} /> {data.error}</p>
    {:else}
      <section class="resumen" aria-label="Resumen">
        <div class="cifra">
          <span class="cifra-icono neutro" aria-hidden="true"><Bot size={19} /></span>
          <span><strong>{(data.agentes?.length ?? 0) + operativos.length}</strong><span class="cifra-txt">agentes en total</span></span>
        </div>
        <div class="cifra fam-cliente">
          <span class="cifra-icono" aria-hidden="true"><BotMessageSquare size={19} /></span>
          <span><strong>{resumen.cliente}</strong><span class="cifra-txt">le hablan al cliente</span></span>
        </div>
        <div class="cifra ancha">
          <div class="ancha-cabeza">
            <span><strong class="acciones-n">{resumen.acciones}</strong> acciones que cambian algo real, en {resumen.conAcciones} agentes</span>
            <span class="v2-sub">
              {#if data.escalamiento?.total}
                {data.escalamiento.total} conversaciones en 14 días · {pct(data.escalamiento.escaladas, data.escalamiento.total)} % pasaron a una persona
              {:else if data.escalamiento}
                Sin conversaciones en 14 días
              {/if}
            </span>
          </div>
          {#if resumen.acciones}
            <div class="barra" role="img"
              aria-label="{resumen.solas} las hacen solos, {resumen.espera} esperan aprobación">
              <span class="barra-sola" style="width:{pct(resumen.solas, resumen.acciones)}%"></span>
              <span class="barra-espera" style="width:{pct(resumen.espera, resumen.acciones)}%"></span>
            </div>
            <div class="leyenda">
              <span class="ley-sola"><i></i><strong>{resumen.solas}</strong> las hacen solos</span>
              <span class="ley-espera"><i></i><strong>{resumen.espera}</strong> esperan que una persona apruebe</span>
              {#if resumen.sinDato}<span class="v2-sub">{resumen.sinDato} sin dato</span>{/if}
            </div>
          {/if}
        </div>
      </section>

      {#if data.errorAutonomia}
        <p class="v2-sub nota-dato">{data.errorAutonomia} Las acciones que piden aprobación se muestran esperando.</p>
      {/if}

      <section class="tabla" aria-label="Agentes">
        <div class="fila cabeza" aria-hidden="true">
          <span>Agente</span><span>Le habla a</span><span>Qué puede hacer</span>
          <span title="Conversaciones que pasaron a una persona. — = sin conversaciones en el periodo">Escaló · 30 d</span><span></span>
        </div>

        {#each grupos as g (g.clave)}
          <div class="grupo fam-{g.clave}">
            <span class="grupo-punto" aria-hidden="true"></span>
            <h2>{g.titulo}</h2>
            <span class="v2-sub">{g.items.length} · {g.nota}</span>
          </div>

          {#each g.items as a (a.nombre)}
            {@const fam = familia(a)}
            {@const p = a.operativo || a.automatico ? null : puede(a)}
            <a class="fila agente fam-{fam}" id="agente-{a.nombre}" href={a.operativo ? a.href : `/agentes/${encodeURIComponent(a.nombre)}`}>
              <span class="quien">
                <span class="icono" aria-hidden="true">
                  {#if a.operativo}<Radar size={19} />
                  {:else if a.automatico}<ScanEye size={19} />
                  {:else if fam === 'cliente'}<BotMessageSquare size={19} />
                  {:else}<Bot size={19} />{/if}
                </span>
                <span class="quien-txt">
                  <span class="nombre">
                    {nombreDe(a)}
                    {#if a.pausado}<span class="pausa"><PauseCircle size={12} /> En pausa</span>{/if}
                  </span>
                  <span class="sub">
                    {subtituloDe(a) || resumenDe(a)}
                    {#if !a.operativo}<span class="clave">· {a.nombre}</span>{/if}
                  </span>
                </span>
              </span>

              <span class="habla"><span class="pill-fam">{FAMILIAS[fam].habla}</span></span>

              <span class="puede">
                {#if a.operativo}
                  <span>{a.nombre === 'supervisor-noc' && hechosDelSupervisor ? hechosDelSupervisor : 'Propone acciones; no ejecuta'}</span>
                {:else if a.automatico}
                  <span>Propone aportes al manual</span>
                {:else if p}
                  <span class="mira">{p.mira}</span>
                  {#if p.solas}<span class="chip-sola">{p.solas} {p.solas === 1 ? 'sola' : 'solas'}</span>{/if}
                  {#if p.espera}<span class="chip-espera">{p.espera} con aprobación</span>{/if}
                  {#if p.sinDato}<span class="chip-neutro">{p.sinDato} sin dato</span>{/if}
                  {#if huecosDe(a.nombre)}<span class="chip-hueco" title="Le falta saber hacer algo: ver su página">{huecosDe(a.nombre)} por enseñar</span>{/if}
                {/if}
              </span>

              <span class="escalo">{a.operativo ? '' : textoEscalo(desempenoDe(a.nombre))}</span>
              <span class="chev" aria-hidden="true"><ChevronRight size={16} /></span>
            </a>
          {/each}
        {/each}
      </section>

      <p class="v2-sub pie">— en «Escaló» = no hubo conversaciones en el periodo, no cero escaladas. Cada fila abre la página del agente.</p>
    {/if}
  </div>
</div>

<style>
  .pagina { display: flex; flex-direction: column; gap: 16px; padding-top: 14px; padding-bottom: 40px; max-width: 1180px; }
  .aviso-error { display: inline-flex; gap: 6px; align-items: center; color: var(--v2-rust); font-size: 14px; margin: 0; }
  .nota-dato { margin: -6px 0 0; font-size: 12.5px; }
  .pie { font-size: 12px; margin: 0; }

  /* Familias: un color por a quien le habla (tokens en v2.css). */
  .fam-cliente { --fam: var(--v2-fam-cliente); --fam-soft: var(--v2-fam-cliente-soft); --fam-line: var(--v2-fam-cliente-line); }
  .fam-equipo { --fam: var(--v2-fam-equipo); --fam-soft: var(--v2-fam-equipo-soft); --fam-line: var(--v2-fam-equipo-line); }
  .fam-auto { --fam: var(--v2-fam-auto); --fam-soft: var(--v2-fam-auto-soft); --fam-line: var(--v2-fam-auto-line); }

  /* --- Resumen ---------------------------------------------------------- */
  .resumen { display: flex; flex-wrap: wrap; gap: 12px; }
  .cifra {
    flex: 1 1 190px; display: flex; gap: 12px; align-items: center; padding: 14px 16px;
    border: 1px solid var(--v2-line); border-radius: var(--v2-radius); background: var(--v2-card);
  }
  .cifra.fam-cliente { background: var(--fam-soft); border-color: var(--fam-line); }
  .cifra strong { display: block; font-size: 22px; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .cifra.fam-cliente strong, .cifra.fam-cliente .cifra-txt { color: var(--fam); }
  .cifra-txt { font-size: 13px; color: var(--v2-slate); }
  .cifra-icono {
    width: 38px; height: 38px; flex: none; display: grid; place-items: center; border-radius: 10px;
    color: var(--fam); background: color-mix(in srgb, var(--fam) 14%, transparent);
  }
  .cifra-icono.neutro { color: var(--v2-ink); background: var(--v2-line-soft); }
  .cifra.ancha { flex: 2.4 1 420px; flex-direction: column; align-items: stretch; gap: 8px; }
  .ancha-cabeza { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px 12px; font-size: 13.5px; }
  .ancha-cabeza .v2-sub { font-size: 12.5px; }
  .acciones-n { display: inline !important; font-size: 22px; color: var(--v2-ember-text); margin-right: 2px; }
  .barra { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--v2-line-soft); }
  .barra-sola { background: var(--v2-sola-fuerte); }
  .barra-espera { background: var(--v2-espera-fuerte); }
  .leyenda { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12.5px; }
  .leyenda span { display: inline-flex; align-items: center; gap: 6px; }
  .leyenda i { width: 9px; height: 9px; border-radius: 3px; display: inline-block; }
  .ley-sola { color: var(--v2-sola); } .ley-sola i { background: var(--v2-sola-fuerte); }
  .ley-espera { color: var(--v2-espera); } .ley-espera i { background: var(--v2-espera-fuerte); }

  /* --- Tabla ------------------------------------------------------------ */
  .tabla { border: 1px solid var(--v2-line); border-radius: var(--v2-radius); background: var(--v2-card); box-shadow: var(--v2-shadow); overflow: hidden; }
  .fila {
    display: grid; grid-template-columns: minmax(260px, 2.3fr) 110px minmax(240px, 2fr) 92px 20px;
    gap: 16px; align-items: center; padding: 10px 18px;
  }
  .cabeza {
    font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--v2-slate); background: var(--v2-line-soft); border-bottom: 1px solid var(--v2-line); padding-block: 9px;
  }
  .grupo { display: flex; align-items: center; gap: 10px; padding: 14px 18px 6px; border-top: 1px solid var(--v2-line-soft); flex-wrap: wrap; }
  .grupo h2 { margin: 0; font-size: 12.5px; font-weight: 700; letter-spacing: 0.03em; color: var(--fam); }
  .grupo .v2-sub { font-size: 12px; }
  .grupo-punto { width: 10px; height: 10px; border-radius: 3px; background: var(--fam); }

  .agente { text-decoration: none; color: inherit; border-top: 1px solid var(--v2-line-soft); transition: background 0.12s; }
  .agente:hover { background: var(--v2-hover); }
  .agente:hover .chev { color: var(--v2-ink); transform: translateX(2px); }
  .agente:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: -2px; }
  .quien { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .icono {
    width: 38px; height: 38px; flex: none; display: grid; place-items: center; border-radius: 10px;
    color: var(--fam); background: var(--fam-soft); border: 1px solid var(--fam-line);
  }
  .quien-txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .nombre { font-size: 14.5px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .sub { font-size: 12px; color: var(--v2-slate); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .clave { font-family: var(--v2-mono); font-size: 11px; opacity: 0.75; }
  .pausa {
    display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; padding: 1px 8px;
    border-radius: 999px; color: var(--v2-rust); background: var(--v2-critica-soft); border: 1px solid var(--v2-critica-line);
  }
  .pill-fam {
    display: inline-block; font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
    color: var(--fam); background: var(--fam-soft); border: 1px solid var(--fam-line);
  }
  .fam-auto .pill-fam { border-style: dashed; }
  .puede { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; font-size: 13px; }
  .mira { color: var(--v2-ink); opacity: 0.85; font-variant-numeric: tabular-nums; }
  .chip-sola, .chip-espera, .chip-neutro, .chip-hueco {
    font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; font-variant-numeric: tabular-nums;
  }
  .chip-sola { color: var(--v2-sola); background: var(--v2-sola-soft); border: 1px solid var(--v2-sola-line); }
  .chip-espera { color: var(--v2-espera); background: var(--v2-espera-soft); border: 1px solid var(--v2-espera-line); }
  .chip-neutro { color: var(--v2-slate); background: var(--v2-line-soft); border: 1px solid var(--v2-line); }
  .chip-hueco { color: var(--v2-clay); background: transparent; border: 1px dashed var(--v2-clay); font-weight: 500; }
  .escalo { font-size: 13px; color: var(--v2-slate); font-variant-numeric: tabular-nums; }
  .chev { color: var(--v2-slate); transition: transform 0.15s; display: grid; }

  /* En el celular cada agente es un renglon de dos lineas: nombre arriba y lo
     que puede hacer abajo. La cabecera de columnas no aplica. */
  @media (max-width: 760px) {
    .cabeza { display: none; }
    .fila.agente {
      grid-template-columns: 1fr 18px;
      grid-template-areas: 'quien chev' 'puede chev';
      gap: 6px 10px; padding: 12px 14px; min-height: 56px;
    }
    .quien { grid-area: quien; }
    .puede { grid-area: puede; padding-left: 50px; font-size: 12.5px; }
    .chev { grid-area: chev; }
    .habla, .escalo { display: none; }
    .grupo { padding-inline: 14px; }
  }
</style>
