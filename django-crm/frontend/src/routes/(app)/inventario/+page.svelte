<script>
  /**
   * El inventario: qué hay, dónde, y por dónde pasó cada aparato.
   *
   * POR QUÉ LA PANTALLA EMPIEZA POR LAS EXISTENCIAS Y NO POR LOS FORMULARIOS
   * La pregunta que trae a alguien acá es «¿tengo con qué despachar?». Poner el
   * formulario arriba obliga a bajar para responderla, y después subir.
   *
   * LO QUE FALTA SE DICE, NO SE PINTA COMO CERO
   * Si la lectura falló, la pantalla lo dice en vez de mostrar bodegas vacías.
   * Un «0 conectores» falso manda a un técnico a la calle sin material, y desde
   * afuera no se distingue de una bodega de verdad vacía. Es la misma lección
   * que la franja del Centro de Mando: un cero inventado no obliga a
   * investigar; un «no disponible» sí.
   *
   * EL 409 SE MUESTRA COMPLETO
   * Cuando un despacho choca, el backend dice DÓNDE está el aparato. Ese texto
   * llega tal cual: «la serie X figura en la Custodia de Juan» resuelve el caso
   * en el acto, y un «no se pudo despachar» obliga a investigar de cero.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let existencias = $derived(data.existencias ?? []);
  let materiales = $derived(data.materiales ?? []);
  let ubicaciones = $derived(data.ubicaciones ?? []);
  let personas = $derived(data.personas ?? []);

  /** Las bodegas y vehículos: de acá sale y acá vuelve el material. */
  let internas = $derived(
    ubicaciones.filter((u) => u.tipo === 'bodega' || u.tipo === 'vehiculo')
  );

  let pestana = $state('existencias');

  /** El material elegido en cada formulario, para saber si pedir la serie. */
  let materialEntrada = $state('');
  let materialDespacho = $state('');
  let materialDevolucion = $state('');

  /** @param {string} codigo */
  function esSerializado(codigo) {
    return materiales.find((m) => m.codigo === codigo)?.es_serializado === true;
  }

  /**
   * Un número con tres decimales se lee mal cuando el material se cuenta en
   * unidades. La API manda un solo formato a propósito y acá se decide cómo
   * mostrarlo, que es donde se sabe la unidad.
   * @param {string} valor
   * @param {string} clase
   */
  function cantidad(valor, clase) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return valor;
    return clase === 'bobina' ? n.toFixed(2) : String(Math.round(n * 1000) / 1000);
  }
</script>

<svelte:head><title>Inventario</title></svelte:head>

<PageHeader title="Inventario" subtitle="Qué hay en bodega y qué tiene cada técnico" />

{#if data.noSePudoLeer}
  <div class="aviso aviso--roto">
    <strong>No se pudo leer el inventario.</strong>
    Lo que sigue puede estar incompleto: no se muestran ceros porque no sabemos
    si son ceros. Reintentá, y si sigue así avisá a soporte.
  </div>
{/if}

{#if form?.hecho}
  <div class="aviso aviso--bien">{form.hecho}</div>
{/if}
{#if form?.error}
  <div class="aviso aviso--roto">{form.error}</div>
{/if}
{#if form?.incidencias?.length}
  <div class="aviso aviso--ojo">
    <strong>Quedó una diferencia abierta.</strong>
    La devolución se registró por lo que llegó, y lo que falta quedó como
    incidencia — no se absorbió en un ajuste:
    <ul>
      {#each form.incidencias as i (i.id)}
        <li><span class="mono">{i.material}</span> · faltan {i.cantidad} · {i.motivo}</li>
      {/each}
    </ul>
  </div>
{/if}

<nav class="pestanas">
  <button class:activa={pestana === 'existencias'} onclick={() => (pestana = 'existencias')}>
    Existencias
  </button>
  <button class:activa={pestana === 'entrada'} onclick={() => (pestana = 'entrada')}>
    Registrar entrada
  </button>
  <button class:activa={pestana === 'despacho'} onclick={() => (pestana = 'despacho')}>
    Despachar
  </button>
  <button class:activa={pestana === 'devolucion'} onclick={() => (pestana = 'devolucion')}>
    Recibir devolución
  </button>
  <button class:activa={pestana === 'serie'} onclick={() => (pestana = 'serie')}>
    Buscar un aparato
  </button>
</nav>

{#if pestana === 'existencias'}
  {#if existencias.length === 0}
    <p class="vacio">
      Todavía no hay ninguna ubicación con movimientos. Empezá registrando una
      entrada: hasta que el material entre al sistema, no hay nada que despachar.
    </p>
  {/if}

  {#each existencias as bloque (bloque.ubicacion.id)}
    <section class="bloque">
      <h2>
        {bloque.ubicacion.nombre}
        <Pill>{bloque.ubicacion.tipo}</Pill>
      </h2>

      {#if bloque.materiales.length === 0}
        <p class="vacio">Sin movimientos todavía.</p>
      {:else}
        <div class="tabla-envoltura">
          <table>
            <thead>
              <tr>
                <th>Código</th><th>Material</th><th>Categoría</th>
                <th class="num">Existencia</th><th>Unidad</th>
              </tr>
            </thead>
            <tbody>
              {#each bloque.materiales as m (m.material_id)}
                <tr class:negativo={Number(m.existencia) < 0}>
                  <td class="mono">{m.codigo}</td>
                  <td>{m.nombre}</td>
                  <td class="tenue">{m.categoria || '—'}</td>
                  <td class="num mono">{cantidad(m.existencia, m.clase)}</td>
                  <td class="tenue">{m.unidad}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <!-- Un negativo se muestra, no se tapa: es lo que hay que poder ver. -->
      {/if}
    </section>
  {/each}

{:else if pestana === 'entrada'}
  <section class="bloque">
    <h2>Material que entra</h2>
    <p class="ayuda">
      Una compra que llega, o un equipo retirado de un cliente. Es el único
      movimiento sin origen: el material entra al sistema acá.
    </p>
    <form method="POST" action="?/entrada" use:enhance class="formulario">
      <label>
        Material
        <select name="material" bind:value={materialEntrada} required>
          <option value="">Elegí un material…</option>
          {#each materiales as m (m.id)}
            <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
          {/each}
        </select>
      </label>

      {#if esSerializado(materialEntrada)}
        <label>
          Número de serie
          <input name="serie" required placeholder="HWTCA6FB5263" />
          <small>Este material es serializado: una serie, una unidad.</small>
        </label>
        <input type="hidden" name="cantidad" value="1" />
      {:else}
        <label>
          Cantidad
          <input name="cantidad" type="number" step="0.001" min="0.001" required />
        </label>
      {/if}

      <label>
        Entra a
        <select name="ubicacion_destino" required>
          <option value="">Elegí una bodega…</option>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>

      <label>
        Referencia <span class="tenue">(factura, remisión — opcional)</span>
        <input name="origen_ref" placeholder="FAC-001" />
      </label>

      <button type="submit" class="principal">Registrar entrada</button>
    </form>
  </section>

{:else if pestana === 'despacho'}
  <section class="bloque">
    <h2>Despachar a un técnico</h2>
    <p class="ayuda">
      Lo que sale de la bodega queda a cargo de una persona. Si el aparato está
      en otras manos, el sistema lo dice y no lo entrega: primero hay que
      registrar su devolución.
    </p>
    <form method="POST" action="?/despacho" use:enhance class="formulario">
      <label>
        Sale de
        <select name="ubicacion_origen" required>
          <option value="">Elegí una bodega…</option>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>

      <label>
        Se le entrega a
        <select name="profile_destino" required>
          <option value="">Elegí una persona…</option>
          {#each personas as p (p.id)}
            <option value={p.id}>{p.nombre}{#if p.rol} · {p.rol}{/if}</option>
          {/each}
        </select>
      </label>

      <label>
        Material
        <select name="material" bind:value={materialDespacho} required>
          <option value="">Elegí un material…</option>
          {#each materiales as m (m.id)}
            <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
          {/each}
        </select>
      </label>

      {#if esSerializado(materialDespacho)}
        <label>
          Número de serie
          <input name="serie" required />
          <small>Sin el número no se sabe qué aparato se entregó.</small>
        </label>
        <input type="hidden" name="cantidad" value="1" />
      {:else}
        <label>
          Cantidad
          <input name="cantidad" type="number" step="0.001" min="0.001" required />
        </label>
      {/if}

      <label>
        Acta <span class="tenue">(opcional)</span>
        <input name="acta" placeholder="K-0412" />
      </label>

      <button type="submit" class="principal">Despachar</button>
    </form>
  </section>

{:else if pestana === 'devolucion'}
  <section class="bloque">
    <h2>Recibir una devolución</h2>
    <p class="ayuda">
      El material vuelve a existir en la bodega. Una devolución no corrige el
      consumo de ayer: es un hecho nuevo, y los dos quedan registrados.
    </p>
    <form method="POST" action="?/devolucion" use:enhance class="formulario">
      <label>
        Devuelve
        <select name="profile_origen" required>
          <option value="">Elegí una persona…</option>
          {#each personas as p (p.id)}
            <option value={p.id}>{p.nombre}{#if p.rol} · {p.rol}{/if}</option>
          {/each}
        </select>
      </label>

      <label>
        Vuelve a
        <select name="ubicacion_destino" required>
          <option value="">Elegí una bodega…</option>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>

      <label>
        Material
        <select name="material" bind:value={materialDevolucion} required>
          <option value="">Elegí un material…</option>
          {#each materiales as m (m.id)}
            <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
          {/each}
        </select>
      </label>

      {#if esSerializado(materialDevolucion)}
        <label>Número de serie<input name="serie" required /></label>
        <input type="hidden" name="cantidad" value="1" />
      {:else}
        <label>
          Cantidad
          <input name="cantidad" type="number" step="0.001" min="0.001" required />
        </label>
      {/if}

      <label>
        Se esperaba <span class="tenue">(opcional — cuánto debía volver)</span>
        <input name="esperado" type="number" step="0.001" min="0" />
        <small>
          Si vuelve menos de lo que se esperaba, se abre una incidencia por la
          diferencia. Vacío significa entrega parcial: no se abre nada.
        </small>
      </label>

      <label>
        Nota <span class="tenue">(por qué vuelve — opcional)</span>
        <input name="notas" placeholder="el cliente canceló, vuelve sin instalar" />
      </label>

      <button type="submit" class="principal">Registrar devolución</button>
    </form>
  </section>

{:else if pestana === 'serie'}
  <section class="bloque">
    <h2>Buscar un aparato</h2>
    <p class="ayuda">
      Quién lo tuvo, dónde está, cuándo salió y por qué. Es la pregunta que este
      módulo existe para responder.
    </p>
    <form method="GET" class="formulario formulario--linea">
      <label>
        Número de serie
        <input name="serie" value={data.serieConsultada ?? ''} placeholder="HWTCA6FB5263" required />
      </label>
      <button type="submit" class="principal">Buscar</button>
    </form>

    {#if data.consulta?.noExiste}
      <p class="vacio">
        No hay ningún aparato con la serie <span class="mono">{data.serieConsultada}</span>
        en esta empresa. No es un error de consulta: nunca entró al sistema.
      </p>
    {:else if data.consulta?.error}
      <p class="aviso aviso--roto">No se pudo consultar. Reintentá.</p>
    {:else if data.consulta}
      {#each data.consulta.activos as a (a.serie + a.material.codigo)}
        <div class="ficha">
          <h3>
            <span class="mono">{a.serie}</span>
            <span class="tenue">{a.material.nombre}</span>
          </h3>
          <p>Ahora está en: <strong>{a.donde_esta}</strong></p>

          {#if !a.cuadra_con_el_libro}
            <p class="aviso aviso--roto">
              <strong>Atención:</strong> el índice de posición y el libro de
              movimientos no coinciden para este aparato. Lo que manda es el
              libro, que está abajo. Hay que revisarlo.
            </p>
          {/if}

          <ol class="historia">
            {#each a.historia as h, i (i)}
              <li>
                <span class="tenue">{h.en?.slice(0, 16)?.replace('T', ' ') ?? '—'}</span>
                <strong>{h.tipo}</strong>
                {#if h.desde}desde {h.desde}{/if}
                {#if h.hacia}→ {h.hacia}{:else}<span class="tenue">→ fuera de custodia</span>{/if}
                {#if h.motivo}<span class="tenue">· {h.motivo}</span>{/if}
                {#if h.estado !== 'aceptado'}<Pill>{h.estado}</Pill>{/if}
              </li>
            {/each}
          </ol>
        </div>
      {/each}
    {/if}
  </section>
{/if}

<style>
  .pestanas {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    border-bottom: 1px solid var(--border, #e5e7eb);
    margin: 1rem 0 1.25rem;
  }
  .pestanas button {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 0.55rem 0.85rem;
    font: inherit;
    color: var(--text-muted, #6b7280);
    cursor: pointer;
  }
  .pestanas button.activa {
    color: var(--text, #111827);
    border-bottom-color: var(--accent, #2563eb);
    font-weight: 600;
  }

  .bloque {
    background: var(--surface, #fff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 10px;
    padding: 1rem 1.15rem;
    margin-bottom: 1rem;
  }
  .bloque h2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1rem;
    margin: 0 0 0.75rem;
  }

  .ayuda {
    color: var(--text-muted, #6b7280);
    font-size: 0.875rem;
    margin: -0.25rem 0 1rem;
    max-width: 62ch;
  }

  .tabla-envoltura { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--border, #f3f4f6); }
  th { font-weight: 600; color: var(--text-muted, #6b7280); }
  .num { text-align: right; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .tenue { color: var(--text-muted, #6b7280); }
  tr.negativo .num { color: #b91c1c; font-weight: 700; }

  .formulario { display: grid; gap: 0.85rem; max-width: 34rem; }
  .formulario--linea { grid-template-columns: 1fr auto; align-items: end; }
  .formulario label { display: grid; gap: 0.3rem; font-size: 0.875rem; font-weight: 600; }
  .formulario input, .formulario select {
    font: inherit;
    font-weight: 400;
    padding: 0.5rem 0.6rem;
    border: 1px solid var(--border, #d1d5db);
    border-radius: 7px;
    background: var(--surface, #fff);
    color: inherit;
  }
  .formulario small { font-weight: 400; color: var(--text-muted, #6b7280); }
  .principal {
    justify-self: start;
    padding: 0.55rem 1.1rem;
    border: none;
    border-radius: 7px;
    background: var(--accent, #2563eb);
    color: #fff;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }

  .aviso { padding: 0.7rem 0.9rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.9rem; }
  .aviso--roto { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
  .aviso--bien { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
  /* Ni error ni exito: algo que hay que MIRAR. Un faltante en verde se lee
     como "todo bien" y en rojo como "fallo la operacion"; ninguna de las dos
     es cierta. */
  .aviso--ojo { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
  .aviso--ojo ul { margin: 0.4rem 0 0; padding-left: 1.1rem; }

  .vacio { color: var(--text-muted, #6b7280); font-size: 0.9rem; max-width: 62ch; }

  .ficha { border-top: 1px solid var(--border, #e5e7eb); margin-top: 1rem; padding-top: 1rem; }
  .ficha h3 { display: flex; gap: 0.6rem; align-items: baseline; font-size: 0.95rem; margin: 0 0 0.4rem; }
  .historia { margin: 0.6rem 0 0; padding-left: 1.2rem; display: grid; gap: 0.35rem; font-size: 0.875rem; }
</style>
