<script>
  /**
   * EL DINERO DE LOS TÉCNICOS (26/11/2026). Ver campo/dinero.py.
   *
   * El usuario: «falta registrar el dinero que recibe el técnico». El técnico
   * cobra en efectivo (instalación, equipos o material extra) y lo anota en la
   * orden; aquí la oficina ve cuánto tiene cada uno por entregar y lo recibe.
   * Lo que se recibe es la cifra que se ve: si cambió, no se recibe nada.
   */
  import { enhance } from '$app/forms';
  import { AlertTriangle, Banknote, CheckCircle2, Wallet } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let confirmando = $state('');
  let enviando = $state('');

  const pesos = new Intl.NumberFormat('es-CO', {
    style: 'currency', currency: 'COP', maximumFractionDigits: 0
  });
  const plata = (/** @type {number} */ n) => pesos.format(n ?? 0);
  const cuando = (/** @type {string} */ iso) =>
    iso
      ? new Date(iso).toLocaleString('es-CO', {
          timeZone: 'America/Bogota', day: '2-digit', month: 'short',
          hour: 'numeric', minute: '2-digit'
        })
      : '';

  /** Lo que se puede recibir de un técnico: lo que debe, orden por orden. Una
   *  orden donde la oficina recibió de más (el técnico corrigió a la baja
   *  después) no se recibe: se muestra aparte. */
  const porRecibir = (/** @type {any} */ t) => t.ordenes.filter((/** @type {any} */ o) => o.pendiente > 0);
  const totalDe = (/** @type {any} */ t) =>
    porRecibir(t).reduce((/** @type {number} */ s, /** @type {any} */ o) => s + o.pendiente, 0);
  const deMas = (/** @type {any} */ t) => t.ordenes.filter((/** @type {any} */ o) => o.pendiente < 0);
  const nombreCorto = (/** @type {string} */ n) => (n || 'el técnico').split(' ')[0];

  let totalGeneral = $derived(
    (data.tecnicos ?? []).reduce((/** @type {number} */ s, /** @type {any} */ t) => s + totalDe(t), 0)
  );
</script>

<svelte:head><title>Dinero de los técnicos</title></svelte:head>

<div class="v2-scroll">
<div class="hoja" data-privado>
  <header>
    <h1>Dinero de los técnicos</h1>
    <p class="bajada">
      Lo que cada técnico cobró en efectivo en la casa del cliente y todavía no ha entregado.
      Cuéntalo, y marca que lo recibiste.
    </p>
  </header>

  {#if data.sinPermiso}
    <section class="vacio" role="status">
      <AlertTriangle size={26} />
      <h2>Esta pantalla es de gestión</h2>
      <p>{data.error}</p>
    </section>
  {:else if data.error}
    <div class="alerta"><AlertTriangle size={16} /><span>{data.error}</span></div>
  {/if}
  {#if form?.error}
    <div class="alerta"><AlertTriangle size={16} /><span>{form.error}</span></div>
  {/if}
  {#if form?.recibido}
    <div class="ok">
      <CheckCircle2 size={16} />
      <span>Recibido: {plata(form.total)} de {form.recibidas === 1 ? 'una orden' : `${form.recibidas} órdenes`}.</span>
    </div>
  {/if}

  {#if !data.error && !data.configurado}
    <section class="vacio" role="status">
      <Wallet size={26} />
      <h2>Ninguna plantilla anota dinero todavía</h2>
      <p>
        En <a href="/supervisor-noc/plantillas">Plantillas</a>, marca como «dinero que recibe el técnico»
        los datos de número donde anota lo que cobra (por ejemplo, el valor de la instalación).
      </p>
    </section>
  {:else if !data.error && !(data.tecnicos ?? []).length}
    <section class="vacio" role="status">
      <CheckCircle2 size={26} />
      <h2>Nadie tiene dinero por entregar</h2>
      <p>Cuando un técnico anote un cobro en una orden, aparece aquí.</p>
    </section>
  {:else if (data.tecnicos ?? []).length}
    <div class="resumen">
      <span class="resumen-rotulo">Por entregar, entre todos</span>
      <span class="resumen-cifra">{plata(totalGeneral)}</span>
    </div>
  {/if}

  {#each data.tecnicos ?? [] as t (t.tecnico.id ?? t.tecnico.nombre)}
    {@const total = totalDe(t)}
    <article class="tarjeta">
      <div class="encabezado">
        <div class="quien">
          <span class="icono"><Banknote size={18} /></span>
          <div>
            <h2>{t.tecnico.nombre}</h2>
            <p class="meta">{porRecibir(t).length === 1 ? 'una orden' : `${porRecibir(t).length} órdenes`}</p>
          </div>
        </div>
        <div class="debe">
          <span class="debe-rotulo">Tiene por entregar</span>
          <span class="debe-cifra">{plata(total)}</span>
        </div>
      </div>

      <ul class="ordenes">
        {#each porRecibir(t) as o (o.orden_id)}
          <li>
            <div class="orden-cabeza">
              <span class="ot">OT-{o.numero}</span>
              <span class="cliente">{o.cliente}</span>
              <span class="monto">{plata(o.pendiente)}</span>
            </div>
            <div class="conceptos">
              {#each o.conceptos as c}
                <span>{c.titulo} <b>{plata(c.valor)}</b></span>
              {/each}
              {#if o.entregado > 0}
                <span class="ya">ya entregó {plata(o.entregado)} de {plata(o.cobrado)}</span>
              {/if}
            </div>
          </li>
        {/each}
      </ul>

      {#each deMas(t) as o (o.orden_id)}
        <p class="de-mas">
          <AlertTriangle size={14} />
          <span>OT-{o.numero}: la oficina recibió {plata(-o.pendiente)} de más (el técnico corrigió la cifra después de entregar).</span>
        </p>
      {/each}

      {#if total > 0 && t.tecnico.id}
        {#if confirmando === t.tecnico.id}
          <form method="POST" action="?/recibir" class="confirmar" use:enhance={() => {
            enviando = t.tecnico.id;
            return async ({ update }) => { await update({ reset: false }); enviando = ''; confirmando = ''; };
          }}>
            <input type="hidden" name="tecnico_id" value={t.tecnico.id} />
            <input type="hidden" name="ordenes"
                   value={JSON.stringify(porRecibir(t).map((/** @type {any} */ o) => ({ orden_id: o.orden_id, monto: o.pendiente })))} />
            <p>¿Contaste <b>{plata(total)}</b> en efectivo de {t.tecnico.nombre}?</p>
            <div class="botones">
              <button type="submit" class="recibir" disabled={enviando === t.tecnico.id}>
                {enviando === t.tecnico.id ? 'Guardando…' : 'Sí, lo recibí'}
              </button>
              <button type="button" class="cancelar" onclick={() => (confirmando = '')}>Cancelar</button>
            </div>
          </form>
        {:else}
          <button type="button" class="recibir" onclick={() => (confirmando = t.tecnico.id)}>
            Recibí {plata(total)} de {nombreCorto(t.tecnico.nombre)}
          </button>
        {/if}
      {/if}
    </article>
  {/each}

  {#if (data.ultimas ?? []).length}
    <section class="historial">
      <h2>Últimas entregas</h2>
      <table>
        <thead><tr><th>Cuándo</th><th>Orden</th><th>Técnico</th><th class="num">Monto</th><th>Recibió</th></tr></thead>
        <tbody>
          {#each data.ultimas as u}
            <tr>
              <td>{cuando(u.recibido_en)}</td>
              <td>OT-{u.orden_numero}</td>
              <td>{u.tecnico || '—'}</td>
              <td class="num">{plata(u.monto)}</td>
              <td>{u.recibido_por || '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</div>
</div>

<style>
  .hoja { max-width: 820px; padding: 24px 20px 60px; display: flex; flex-direction: column; gap: 14px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -.02em; }
  .bajada { color: var(--v2-slate); margin: 0; max-width: 62ch; }

  .resumen {
    display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
    padding: 12px 16px; border-radius: 10px; background: var(--v2-paper); border: 1px solid var(--v2-line);
  }
  .resumen-rotulo { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: var(--v2-slate); }
  .resumen-cifra { font-size: 1.35rem; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--v2-ink); }

  .tarjeta {
    background: var(--v2-card); border: 1px solid var(--v2-line); border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 12px;
  }
  .encabezado { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
  .quien { display: flex; gap: 10px; align-items: center; }
  .icono {
    width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center;
    background: color-mix(in srgb, var(--v2-moss) 12%, var(--v2-card)); color: var(--v2-moss);
  }
  .encabezado h2 { font-size: 1.05rem; margin: 0; }
  .meta { margin: 2px 0 0; font-size: .84rem; color: var(--v2-slate); }
  .debe { display: flex; flex-direction: column; align-items: flex-end; }
  .debe-rotulo { font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--v2-slate); }
  .debe-cifra { font-size: 1.3rem; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--v2-ink); }

  .ordenes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .ordenes li { padding: 9px 0; border-top: 1px solid var(--v2-line); display: flex; flex-direction: column; gap: 4px; }
  .orden-cabeza { display: flex; gap: 10px; align-items: baseline; }
  .ot { font-weight: 700; font-variant-numeric: tabular-nums; }
  .cliente { flex: 1; min-width: 0; color: var(--v2-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .monto { font-weight: 650; font-variant-numeric: tabular-nums; }
  .conceptos { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .83rem; color: var(--v2-slate); }
  .conceptos b { color: var(--v2-ink); font-weight: 600; font-variant-numeric: tabular-nums; }
  .ya { color: var(--v2-clay); }
  .de-mas { display: flex; gap: 7px; align-items: flex-start; margin: 0; font-size: .83rem; color: var(--v2-clay); }

  .confirmar {
    display: flex; flex-direction: column; gap: 9px; padding: 12px; border-radius: 8px;
    background: color-mix(in srgb, var(--v2-moss) 8%, var(--v2-card));
    border: 1px solid color-mix(in srgb, var(--v2-moss) 30%, var(--v2-card));
  }
  .confirmar p { margin: 0; }
  .botones { display: flex; flex-wrap: wrap; gap: 8px; }
  .recibir {
    align-self: flex-start; font: inherit; font-weight: 650; border-radius: 8px; padding: 9px 16px;
    cursor: pointer; background: var(--v2-moss); color: #fff; border: 1px solid transparent;
  }
  .cancelar {
    font: inherit; font-weight: 600; background: var(--v2-card);
    border: 1px solid var(--v2-line-strong); border-radius: 8px; padding: 9px 16px; cursor: pointer;
  }
  button:disabled { opacity: .6; cursor: default; }
  button:focus-visible, a:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: 2px; }

  .historial h2 { font-size: 1rem; margin: 8px 0; }
  table { width: 100%; border-collapse: collapse; font-size: .85rem; }
  th { text-align: left; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--v2-slate); font-weight: 600; padding: 6px 8px; border-bottom: 1px solid var(--v2-line); }
  td { padding: 7px 8px; border-bottom: 1px solid var(--v2-line); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }

  .vacio {
    text-align: center; color: var(--v2-slate); background: var(--v2-card); border: 1px solid var(--v2-line);
    border-radius: 10px; padding: 40px 24px; display: flex; flex-direction: column; align-items: center; gap: 8px;
  }
  .vacio h2 { margin: 0; font-size: 1.05rem; color: var(--v2-ink); }
  .vacio p { margin: 0; max-width: 46ch; font-size: .9rem; }
  .vacio a { color: var(--v2-ember-text); }

  .alerta, .ok { display: flex; gap: 9px; align-items: center; border-radius: 8px; padding: 11px 13px; font-size: .9rem; }
  .alerta {
    background: color-mix(in srgb, var(--v2-rust) 10%, var(--v2-card));
    border: 1px solid color-mix(in srgb, var(--v2-rust) 35%, var(--v2-card));
    color: var(--v2-rust);
  }
  .ok {
    background: color-mix(in srgb, var(--v2-moss) 10%, var(--v2-card));
    border: 1px solid color-mix(in srgb, var(--v2-moss) 35%, var(--v2-card));
    color: var(--v2-moss);
  }

  @media (max-width: 560px) {
    .hoja { padding: 18px 16px 48px; }
    .debe { align-items: flex-start; }
    table { font-size: .8rem; }
    th:nth-child(5), td:nth-child(5) { display: none; }
  }
</style>
