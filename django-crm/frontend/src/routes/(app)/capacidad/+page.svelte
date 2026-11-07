<script>
  /**
   * Capacidad: cuánto trabajo le resolvió Dexter a la empresa (PRD §2 y §8.17).
   *
   * Tres reglas de la pantalla, que vienen de la del motor:
   *
   *   - La resolución sin persona NUNCA se muestra sola: el recontacto y la
   *     satisfacción van al lado, porque subir la primera cerrando casos sin
   *     resolverlos es la trampa que este tablero tiene que dejar a la vista.
   *   - Un null es un null: se dibuja "—" con el motivo que manda el motor,
   *     nunca un 0. Un cero se lee como un resultado.
   *   - Los números los calcula el motor. Acá solo se formatean.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { Info } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const t = $derived(data.tablero);
  const pct = (/** @type {number|null|undefined} */ x) =>
    x === null || x === undefined ? null : Math.round(x * 1000) / 10 + '%';
  const num = (/** @type {number|null|undefined} */ x) =>
    x === null || x === undefined ? null : Number(x).toLocaleString('es-CO');
  const fecha = (/** @type {string} */ s) =>
    new Date(s).toLocaleDateString('es-CO', { day: 'numeric', month: 'short', timeZone: 'America/Bogota' });
  const horas = (/** @type {number|null} */ min) =>
    min === null || min === undefined ? null
      : min >= 120 ? (min / 60).toFixed(1).replace('.', ',') + ' h' : Math.round(min) + ' min';
</script>

<PageHeader title="Capacidad">
  {#snippet sub()}
    Cuánto trabajo resolvió Dexter sin una persona, y si lo resolvió de verdad.
  {/snippet}
</PageHeader>

<!-- El contenedor de la app corta lo que se sale (.v2-main, overflow hidden):
     cada pantalla hace su propio scroll en .v2-scroll, como Configuracion. Sin
     esto /capacidad no bajaba y la autonomia ganada quedaba fuera de alcance
     (02/11/2026). -->
<div class="v2-scroll">
<div class="v2-pad" style="padding-top:14px;padding-bottom:32px;display:flex;flex-direction:column;gap:14px">
  <nav class="periodos" aria-label="Período">
    {#each data.periodos as d (d)}
      <a href="?dias={d}" class="v2-btn" class:v2-btn-primary={d === data.dias}
         aria-current={d === data.dias ? 'page' : undefined}>Últimos {d} días</a>
    {/each}
  </nav>

  {#if data.error || !t}
    <p class="aviso-error">⚠️ {data.error ?? 'No hay datos del tablero.'}</p>
  {:else}
    {#if t.aviso}
      <p class="aviso"><Info size={14} /> {t.aviso}</p>
    {/if}
    <p class="pie">Del {fecha(t.desde)} al {fecha(t.hasta)} · solo conversaciones de clientes por WhatsApp.</p>

    <div class="v2-card tarjeta destacada">
      <div class="rotulo">Casos resueltos por persona del equipo</div>
      {#if t.casos_por_persona.valor === null}
        <div class="cifra apagada">—</div>
        <div class="pie">{t.casos_por_persona.motivo}</div>
      {:else}
        <div class="cifra">{num(t.casos_por_persona.valor)}</div>
        <div class="pie">{num(t.casos_por_persona.casos)} casos cerrados entre {num(t.casos_por_persona.personas)} personas que atendieron</div>
      {/if}
    </div>

    <div class="grupo">
      <div class="v2-card tarjeta">
        <div class="rotulo">Resueltas sin persona</div>
        <div class="cifra" class:apagada={t.resolucion_sin_persona.tasa === null}>
          {pct(t.resolucion_sin_persona.tasa) ?? '—'}
        </div>
        <div class="pie">{num(t.resolucion_sin_persona.resueltas)} de {num(t.resolucion_sin_persona.cerradas)} conversaciones cerradas, sin que una persona escribiera, tomara el caso o aprobara algo</div>
      </div>
      <div class="v2-card tarjeta contrapeso">
        <div class="rotulo">Volvieron a escribir en {t.recontacto.ventana_horas} h</div>
        <div class="cifra" class:apagada={t.recontacto.tasa_sin_persona === null}>
          {pct(t.recontacto.tasa_sin_persona) ?? '—'}
        </div>
        <div class="pie">de las resueltas sin persona ({num(t.recontacto.recontactos_sin_persona)}). Si sube, se están cerrando casos sin resolverlos.</div>
      </div>
      <div class="v2-card tarjeta contrapeso">
        <div class="rotulo">Satisfacción</div>
        <div class="cifra" class:apagada={t.satisfaccion.promedio === null}>
          {t.satisfaccion.promedio === null ? '—' : String(t.satisfaccion.promedio).replace('.', ',') + ' / 5'}
        </div>
        <div class="pie">{num(t.satisfaccion.respondidas)} respuestas de {num(t.satisfaccion.enviadas)} encuestas enviadas</div>
      </div>
    </div>

    <div class="grupo">
      <div class="v2-card tarjeta">
        <div class="rotulo">Visitas evitadas</div>
        {#if t.visitas_evitadas.valor === null}
          <div class="cifra apagada">—</div>
          <div class="pie">{t.visitas_evitadas.motivo}</div>
        {:else}
          <div class="cifra">{num(t.visitas_evitadas.valor)}</div>
          <div class="pie">de {num(t.visitas_evitadas.reinicios_confirmados)} reinicios remotos confirmados, sin visita al mismo cliente en {t.visitas_evitadas.dias_sin_visita} días. Es una estimación.</div>
        {/if}
      </div>
      <div class="v2-card tarjeta">
        <div class="rotulo">Tiempo ahorrado al equipo</div>
        {#if t.minutos_ahorrados.total === null}
          <div class="cifra apagada">—</div>
        {:else}
          <div class="cifra">{horas(t.minutos_ahorrados.total)}</div>
        {/if}
        {#if t.minutos_ahorrados.motivo}
          <div class="pie">Falta que la empresa declare cuánto le cuesta cada caso: {t.minutos_ahorrados.motivo.replace('la empresa no declaro: ', '')}.</div>
        {/if}
      </div>
      <div class="v2-card tarjeta">
        <div class="rotulo">Tiempo hasta resolver</div>
        <div class="cifra" class:apagada={t.tiempo_hasta_resolucion.mediana_minutos === null}>
          {horas(t.tiempo_hasta_resolucion.mediana_minutos) ?? '—'}
        </div>
        <div class="pie">mediana, del primer al último mensaje de cada conversación cerrada</div>
      </div>
    </div>

    <form method="POST" action="?/declarar" use:enhance class="v2-card declarar">
      <div class="rotulo">Lo que declara la empresa</div>
      <p class="pie">Sin estos números el tablero no inventa: muestra "—". Los minutos son cuánto le cuesta al equipo atender una conversación o hacer una visita; las personas, cuántas atienden a los clientes.</p>
      <div class="campos">
        <label>Minutos por conversación
          <input type="number" min="1" name="minutos_por_conversacion" class="v2-input"
                 value={t.declarado?.minutos_por_conversacion ?? ''} /></label>
        <label>Minutos por visita
          <input type="number" min="1" name="minutos_por_visita" class="v2-input"
                 value={t.declarado?.minutos_por_visita ?? ''} /></label>
        <label>Personas del equipo
          <input type="number" min="1" name="personas_del_equipo" class="v2-input"
                 value={t.declarado?.personas_del_equipo ?? ''} /></label>
      </div>
      {#if form?.declarar?.error}<p class="aviso-error">{form.declarar.error}</p>{/if}
      {#if form?.declarar?.ok}<p class="pie">Guardado. El tablero ya lo usa.</p>{/if}
      <div><button class="v2-btn v2-btn-primary" type="submit">Guardar</button></div>
    </form>
  {/if}

  <!-- LA AUTONOMÍA GANADA (31/10/2026, PRD §2, Ola 3). Qué acciones que hoy
       aprueba una persona podrían hacerse solas, con la evidencia de ESTA
       empresa. Solo se muestra: subir lo decide una persona; bajar, el código. -->
  <!--
    Lo que cada agente hace solo se decide en /agentes, agente por agente
    (02/11/2026). Aca vivia "Autonomia ganada", para toda la empresa; el
    usuario: "eso deberia ir en cada agente... con un agente si pueda reiniciar
    y otro no". Capacidad queda para MEDIR.
  -->
  <section class="v2-card declarar">
    <div class="rotulo">Lo que hace solo cada agente</div>
    <p class="pie">
      Qué acciones hace solo cada agente, y cuáles esperan a una persona, se decide ahora en
      <a href="/agentes">Agentes</a>, al lado de las herramientas de cada uno.
    </p>
  </section>
</div>
</div>

<style>
  .periodos { display: flex; gap: 8px; flex-wrap: wrap; }
  .aviso-error {
    margin: 0; padding: 10px 14px; border-radius: 6px;
    background: color-mix(in srgb, var(--v2-rust) 10%, transparent);
    color: var(--v2-rust); font-size: 13px;
  }
  .aviso {
    margin: 0; display: flex; align-items: center; gap: 6px; padding: 8px 12px; border-radius: 6px;
    background: color-mix(in srgb, var(--v2-clay) 10%, transparent); font-size: 12.5px;
  }
  .grupo { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  .tarjeta { padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; }
  .tarjeta.destacada { border-color: color-mix(in srgb, var(--v2-ember) 35%, transparent); }
  .tarjeta.contrapeso { border-style: dashed; }
  .rotulo {
    font-size: 11.5px; color: var(--v2-slate);
    text-transform: uppercase; letter-spacing: .4px;
  }
  .cifra { font-size: 26px; font-weight: 700; letter-spacing: -.5px; font-variant-numeric: tabular-nums; }
  .cifra.apagada { color: var(--v2-slate); font-size: 22px; }
  .pie { margin: 0; font-size: 11.5px; color: var(--v2-slate); line-height: 1.45; }
  .declarar { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
  .campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
  .campos label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
</style>
