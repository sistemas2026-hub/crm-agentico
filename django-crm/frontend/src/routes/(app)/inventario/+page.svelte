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

  /**
   * La pestaña viene de la URL y no de un `$state`.
   *
   * Las secciones de Fase 2 y 3 se cargan en el servidor segun `?ver=`, asi que
   * una pestaña local mostraria la seccion vacia: el load no se vuelve a correr
   * al cambiar una variable. Y de paso una pestaña abierta se puede compartir
   * por link, que es lo que alguien hace cuando quiere mostrarle un descuadre a
   * otra persona.
   */
  let pestana = $derived(data.ver ?? 'existencias');
  let ubicacionElegida = $derived(data.ubicacionElegida ?? '');

  /** @param {string} ver */
  function enlace(ver) {
    const q = new URLSearchParams();
    q.set('ver', ver);
    if (ubicacionElegida) q.set('ubicacion', ubicacionElegida);
    return `?${q}`;
  }

  /** El material elegido en cada formulario, para saber si pedir la serie. */
  let materialEntrada = $state('');
  let materialDespacho = $state('');
  let materialDevolucion = $state('');
  let materialTraslado = $state('');
  let materialReserva = $state('');
  let materialCompra = $state('');

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

<PageHeader title="Inventario">
  {#snippet sub()}Qué hay en bodega, qué tiene cada técnico y por dónde pasó cada aparato{/snippet}
</PageHeader>

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
  <a href={enlace('existencias')} class:activa={pestana === 'existencias'}>Existencias</a>
  <a href={enlace('entrada')} class:activa={pestana === 'entrada'}>Registrar entrada</a>
  <a href={enlace('despacho')} class:activa={pestana === 'despacho'}>Despachar</a>
  <a href={enlace('devolucion')} class:activa={pestana === 'devolucion'}>Recibir devolución</a>
  <a href={enlace('traslado')} class:activa={pestana === 'traslado'}>Trasladar</a>
  <a href={enlace('reservas')} class:activa={pestana === 'reservas'}>Reservas</a>
  <a href={enlace('conteo')} class:activa={pestana === 'conteo'}>Conteo físico</a>
  <a href={enlace('compras')} class:activa={pestana === 'compras'}>Compras y valor</a>
  <a href={enlace('reportes')} class:activa={pestana === 'reportes'}>Reportes</a>
  <a href={enlace('serie')} class:activa={pestana === 'serie'}>Buscar un aparato</a>
</nav>

{#if data.errorExtra}
  <div class="aviso aviso--roto">
    <strong>No se pudo leer esta sección.</strong>
    Lo que sigue puede estar incompleto. No se muestran ceros porque no sabemos
    si son ceros.
  </div>
{/if}

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

{:else if pestana === 'traslado'}
  <section class="bloque">
    <h2>Trasladar entre ubicaciones</h2>
    <p class="ayuda">
      Mover material de una bodega a otra, o a una camioneta. Es lo que hace útil
      tener más de una bodega: sin traslado son dos sistemas separados.
    </p>
    <form method="POST" action="?/traslado" use:enhance class="formulario">
      <label>
        Sale de
        <select name="ubicacion_origen" required>
          <option value="">Elegí…</option>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>
      <label>
        Entra a
        <select name="ubicacion_destino" required>
          <option value="">Elegí…</option>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>
      <label>
        Material
        <select name="material" bind:value={materialTraslado} required>
          <option value="">Elegí un material…</option>
          {#each materiales as m (m.id)}
            <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
          {/each}
        </select>
      </label>
      {#if esSerializado(materialTraslado)}
        <label>Número de serie<input name="serie" required /></label>
        <input type="hidden" name="cantidad" value="1" />
      {:else}
        <label>
          Cantidad
          <input name="cantidad" type="number" step="0.001" min="0.001" required />
        </label>
      {/if}
      <label>
        Motivo <span class="tenue">(opcional)</span>
        <input name="motivo" placeholder="reparto semanal" />
      </label>
      <button type="submit" class="principal">Trasladar</button>
    </form>
  </section>

{:else if pestana === 'reservas'}
  <section class="bloque">
    <h2>Lo comprometido</h2>
    <p class="ayuda">
      La pregunta que importa no es cuánto hay, sino cuánto queda <strong>libre</strong>
      después de lo ya prometido. Sin esto dos despachadores prometen el mismo
      equipo y el segundo técnico llega a la bodega y no está.
    </p>

    <form method="GET" class="formulario formulario--linea">
      <input type="hidden" name="ver" value="reservas" />
      <label>
        Ubicación
        <select name="ubicacion" required>
          {#each internas as u (u.id)}
            <option value={u.id} selected={u.id === ubicacionElegida}>{u.nombre}</option>
          {/each}
        </select>
      </label>
      <button type="submit" class="principal">Ver</button>
    </form>

    {#if data.libre?.length}
      <div class="tabla-envoltura">
        <table>
          <thead>
            <tr>
              <th>Código</th><th>Material</th>
              <th class="num">Hay</th><th class="num">Comprometido</th>
              <th class="num">Libre</th><th>Unidad</th>
            </tr>
          </thead>
          <tbody>
            {#each data.libre as m (m.material_id)}
              <tr class:negativo={Number(m.libre) < 0}>
                <td class="mono">{m.codigo}</td>
                <td>{m.nombre}</td>
                <td class="num mono tenue">{cantidad(m.existencia, m.clase)}</td>
                <td class="num mono tenue">{cantidad(m.reservado, m.clase)}</td>
                <td class="num mono"><strong>{cantidad(m.libre, m.clase)}</strong></td>
                <td class="tenue">{m.unidad}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <!-- Las tres cifras juntas: "quedan 70" sin el 100 y el 30 no se entiende. -->
    {:else}
      <p class="vacio">Sin movimientos en esta ubicación todavía.</p>
    {/if}
  </section>

  <section class="bloque">
    <h2>Comprometer material</h2>
    <form method="POST" action="?/reservar" use:enhance class="formulario">
      <input type="hidden" name="ubicacion" value={ubicacionElegida} />
      <label>
        Material
        <select name="material" bind:value={materialReserva} required>
          <option value="">Elegí un material…</option>
          {#each materiales as m (m.id)}
            <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
          {/each}
        </select>
      </label>
      {#if esSerializado(materialReserva)}
        <label>
          Número de serie
          <input name="serie" required />
          <small>Reservar un aparato concreto.</small>
        </label>
        <input type="hidden" name="cantidad" value="1" />
      {:else}
        <label>
          Cantidad
          <input name="cantidad" type="number" step="0.001" min="0.001" required />
        </label>
      {/if}
      <label>
        Vence <span class="tenue">(opcional, pero recomendado)</span>
        <input name="vence_en" type="datetime-local" />
        <small>
          Sin plazo, una orden que se cae deja el material comprometido para
          siempre y quien lo reservó ya se fue a su casa.
        </small>
      </label>
      <label>
        Para qué <span class="tenue">(opcional)</span>
        <input name="motivo" placeholder="instalaciones de mañana" />
      </label>
      <button type="submit" class="principal">Reservar</button>
    </form>
  </section>

  {#if data.reservas?.length}
    <section class="bloque">
      <h2>Reservas activas</h2>
      <div class="tabla-envoltura">
        <table>
          <thead>
            <tr>
              <th>Material</th><th class="num">Cantidad</th><th>Serie</th>
              <th>Vence</th><th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.reservas as r (r.id)}
              <tr>
                <td><span class="mono">{r.material}</span> {r.nombre}</td>
                <td class="num mono">{r.cantidad}</td>
                <td class="mono tenue">{r.serie || '—'}</td>
                <td class="tenue">
                  {r.vence_en ? r.vence_en.slice(0, 16).replace('T', ' ') : 'sin plazo'}
                </td>
                <td>
                  <form method="POST" action="?/liberar" use:enhance>
                    <input type="hidden" name="reserva" value={r.id} />
                    <input name="motivo" placeholder="por qué se libera" class="mini" />
                    <button type="submit" class="secundario">Liberar</button>
                  </form>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="ayuda">
        Liberar no borra la reserva: queda con su motivo y su desenlace. Es lo que
        permite contestar después «por qué faltaron ONT el martes».
      </p>
    </section>
  {/if}

{:else if pestana === 'conteo'}
  <section class="bloque">
    <h2>Conteo físico</h2>
    <p class="ayuda">
      «El sistema dice 50 y tengo 48» no es un error del sistema: es un hecho que
      alguien tiene que explicar. Cerrar el conteo <strong>no reescribe el
      saldo</strong> — escribe un ajuste por cada diferencia, con su motivo.
    </p>

    <form method="POST" action="?/abrirConteo" use:enhance class="formulario formulario--linea">
      <label>
        Ubicación a contar
        <select name="ubicacion" required>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>
      <button type="submit" class="principal">Abrir conteo</button>
    </form>
  </section>

  {#if data.conteos?.length}
    <section class="bloque">
      <h2>Conteos</h2>
      <div class="tabla-envoltura">
        <table>
          <thead>
            <tr><th>Ubicación</th><th>Estado</th><th>Abierto</th><th class="num">Líneas</th></tr>
          </thead>
          <tbody>
            {#each data.conteos as c (c.id)}
              <tr>
                <td>{c.ubicacion}</td>
                <td><Pill>{c.estado}</Pill></td>
                <td class="tenue">{c.iniciado_en?.slice(0, 16)?.replace('T', ' ')}</td>
                <td class="num mono">{c.lineas}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    {#each data.conteos.filter((c) => c.estado === 'borrador') as abierto (abierto.id)}
      <section class="bloque">
        <h2>Anotar en el conteo de {abierto.ubicacion}</h2>
        <form method="POST" action="?/anotarConteo" use:enhance class="formulario">
          <input type="hidden" name="conteo" value={abierto.id} />
          <label>
            Material
            <select name="material" required>
              <option value="">Elegí un material…</option>
              {#each materiales as m (m.id)}
                <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
              {/each}
            </select>
          </label>
          <label>
            Cuánto hay de verdad
            <input name="cantidad" type="number" step="0.001" min="0" required />
          </label>
          <label>
            Motivo de la diferencia <span class="tenue">(si hay)</span>
            <input name="motivo" placeholder="faltaban cinco en el estante" />
            <small>
              Sin motivo, el ajuste queda marcado como diferencia sin explicar.
            </small>
          </label>
          <button type="submit" class="principal">Anotar</button>
        </form>

        <form method="POST" action="?/cerrarConteo" use:enhance class="cerrar">
          <input type="hidden" name="conteo" value={abierto.id} />
          <button type="submit" class="secundario">
            Cerrar el conteo y escribir los ajustes
          </button>
        </form>
      </section>
    {/each}
  {/if}

  {#if form?.lineasConteo?.length}
    <section class="bloque">
      <h2>Resultado del conteo</h2>
      <div class="tabla-envoltura">
        <table>
          <thead>
            <tr>
              <th>Material</th><th class="num">Contado</th>
              <th class="num">Decía el sistema</th><th class="num">Diferencia</th>
              <th>Ajuste</th>
            </tr>
          </thead>
          <tbody>
            {#each form.lineasConteo as l, i (i)}
              <tr class:negativo={Number(l.diferencia) !== 0}>
                <td class="mono">{l.material}</td>
                <td class="num mono">{l.contado}</td>
                <td class="num mono tenue">{l.segun_sistema}</td>
                <td class="num mono">{l.diferencia}</td>
                <td class="tenue">{l.ajuste ? 'se escribió' : 'cuadró'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="ayuda">
        Las líneas que cuadraron aparecen también: un conteo que solo muestra
        diferencias no deja ver cuánto se revisó.
      </p>
    </section>
  {/if}

{:else if pestana === 'compras'}
  <section class="bloque">
    <h2>Registrar una compra</h2>
    <p class="ayuda">
      Un lote que llegó, con su costo. No es una orden de compra: no hay pedido
      pendiente ni aprobación — esto registra lo que <strong>ya</strong> llegó, y
      es la única vía por la que entra un costo al sistema.
    </p>
    <form method="POST" action="?/compra" use:enhance class="formulario">
      <label>
        Entra a
        <select name="ubicacion_destino" required>
          <option value="">Elegí una bodega…</option>
          {#each internas as u (u.id)}<option value={u.id}>{u.nombre}</option>{/each}
        </select>
      </label>
      <label>
        Proveedor <span class="tenue">(opcional)</span>
        <select name="proveedor">
          <option value="">Sin proveedor identificado</option>
          {#each (data.proveedores ?? []) as p (p.id)}
            <option value={p.id}>{p.nombre}</option>
          {/each}
        </select>
      </label>
      <label>
        Factura o remisión
        <input name="referencia" placeholder="FAC-8891" />
      </label>
      <label>
        Material
        <select name="material" bind:value={materialCompra} required>
          <option value="">Elegí un material…</option>
          {#each materiales as m (m.id)}
            <option value={m.codigo}>{m.codigo} — {m.nombre}</option>
          {/each}
        </select>
      </label>
      {#if esSerializado(materialCompra)}
        <label>Número de serie<input name="serie" required /></label>
        <input type="hidden" name="cantidad" value="1" />
      {:else}
        <label>
          Cantidad
          <input name="cantidad" type="number" step="0.001" min="0.001" required />
        </label>
      {/if}
      <label>
        Costo unitario <span class="tenue">(opcional)</span>
        <input name="costo_unitario" type="number" step="0.0001" min="0" />
        <small>
          Vacío significa «no se sabe», que es distinto de cero: cero diría que
          es gratis y entraría al total como tal.
        </small>
      </label>
      <button type="submit" class="principal">Registrar compra</button>
    </form>
  </section>

  <section class="bloque">
    <h2>Proveedor nuevo</h2>
    <form method="POST" action="?/proveedor" use:enhance class="formulario">
      <label>Nombre<input name="nombre" required /></label>
      <label>
        Identificación <span class="tenue">(NIT, RUT — opcional)</span>
        <input name="identificacion" />
      </label>
      <label>
        Contacto <span class="tenue">(opcional)</span>
        <input name="contacto" />
      </label>
      <button type="submit" class="principal">Crear proveedor</button>
    </form>
  </section>

  {#if data.valorizacion}
    <section class="bloque">
      <h2>Cuánto vale lo que hay</h2>
      <p class="total">{data.valorizacion.total}</p>

      {#if data.valorizacion.advertencia}
        <div class="aviso aviso--ojo">
          <strong>El total no incluye todo.</strong>
          {data.valorizacion.advertencia}
          Un total que se come en silencio lo que no sabe valorizar es la forma
          más rápida de decidir con un número que parece completo.
          <ul>
            {#each data.valorizacion.sin_costo_conocido as m (m.material_id)}
              <li>
                <span class="mono">{m.codigo}</span> {m.nombre} ·
                {cantidad(m.existencia, m.clase)} {m.unidad} · sin costo conocido
              </li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if data.valorizacion.materiales?.length}
        <div class="tabla-envoltura">
          <table>
            <thead>
              <tr>
                <th>Código</th><th>Material</th><th class="num">Cantidad</th>
                <th class="num">Costo unit.</th><th class="num">Valor</th>
              </tr>
            </thead>
            <tbody>
              {#each data.valorizacion.materiales as m (m.material_id)}
                <tr>
                  <td class="mono">{m.codigo}</td>
                  <td>{m.nombre}</td>
                  <td class="num mono">{cantidad(m.existencia, m.clase)}</td>
                  <td class="num mono tenue">{m.costo_unitario}</td>
                  <td class="num mono">{m.valor}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <p class="ayuda">
          El costo es un <strong>promedio ponderado</strong> de lo que costó al
          entrar. Se dice cuál es el método porque FIFO, LIFO y promedio dan
          números distintos sobre los mismos datos.
        </p>
      {/if}
    </section>
  {/if}

{:else if pestana === 'reportes'}
  <section class="bloque">
    <h2>Reportes</h2>
    <nav class="sub">
      <a href="?ver=reportes&de=consumo" class:activa={data.reporte?.de === 'consumo'}>
        En qué se fue
      </a>
      <a href="?ver=reportes&de=tecnicos" class:activa={data.reporte?.de === 'tecnicos'}>
        Por técnico
      </a>
      <a href="?ver=reportes&de=descuadres" class:activa={data.reporte?.de === 'descuadres'}>
        Descuadres abiertos
      </a>
    </nav>

    {#if !data.reporte?.filas?.length}
      <p class="vacio">Nada que mostrar todavía en este reporte.</p>
    {:else if data.reporte.de === 'consumo'}
      <div class="tabla-envoltura">
        <table>
          <thead><tr><th>Código</th><th>Material</th><th class="num">Consumido</th><th>Unidad</th></tr></thead>
          <tbody>
            {#each data.reporte.filas as f, i (i)}
              <tr>
                <td class="mono">{f.codigo}</td><td>{f.nombre}</td>
                <td class="num mono">{f.consumido}</td><td class="tenue">{f.unidad}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if data.reporte.de === 'tecnicos'}
      {#each data.reporte.filas as f, i (i)}
        <div class="ficha">
          <h3>{f.nombre}</h3>
          <ul class="lista">
            {#each f.materiales as m, j (j)}
              <li><span class="mono">{m.codigo}</span> · {m.consumido}</li>
            {/each}
          </ul>
        </div>
      {/each}
      <p class="ayuda">
        Sin «eficiencia» calculada, a propósito: dos técnicos con distinto tipo de
        trabajo no son comparables por metros de fibra, y un número que parece
        comparable se usa como si lo fuera.
      </p>
    {:else}
      <div class="tabla-envoltura">
        <table>
          <thead>
            <tr>
              <th>Cuándo</th><th>Estado</th><th>Material</th>
              <th class="num">Cantidad</th><th>Persona</th><th>Motivo</th>
            </tr>
          </thead>
          <tbody>
            {#each data.reporte.filas as f, i (i)}
              <tr class="negativo">
                <td class="tenue">{f.en?.slice(0, 16)?.replace('T', ' ')}</td>
                <td><Pill>{f.estado}</Pill></td>
                <td class="mono">{f.material}</td>
                <td class="num mono">{f.cantidad}</td>
                <td>{f.persona ?? '—'}</td>
                <td class="tenue">{f.motivo}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="ayuda">
        Una lista y no un contador: un número en un tablero se mira una vez y se
        ignora; esto se puede resolver.
      </p>
    {/if}
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
  .pestanas a {
    background: none;
    border-bottom: 2px solid transparent;
    padding: 0.55rem 0.85rem;
    font: inherit;
    text-decoration: none;
    color: var(--text-muted, #6b7280);
  }
  .pestanas a.activa {
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
  .lista { margin: 0.3rem 0 0; padding-left: 1.1rem; font-size: 0.875rem; }
  .total { font-size: 1.7rem; font-weight: 700; margin: 0 0 0.75rem; font-variant-numeric: tabular-nums; }
  .sub { display: flex; gap: 0.75rem; margin: -0.25rem 0 1rem; font-size: 0.875rem; }
  .sub a { color: var(--text-muted, #6b7280); text-decoration: none; }
  .sub a.activa { color: var(--text, #111827); font-weight: 600; text-decoration: underline; }
  .mini { width: 11rem; padding: 0.3rem 0.4rem; font-size: 0.8rem; }
  .secundario {
    padding: 0.35rem 0.7rem; border: 1px solid var(--border, #d1d5db);
    border-radius: 6px; background: var(--surface, #fff); font: inherit;
    font-size: 0.8rem; cursor: pointer; color: inherit;
  }
  .cerrar { margin-top: 1rem; }
</style>
