<script>
  //  El catalogo de salas se lee del frontend y NO del motor: el motor
  //  sirve los NOMBRES de plantilla, la geometria -cuantas sillas tiene
  //  cada una y donde- vive aca. Es el mismo reparto que `AreaDeTrabajo.icono`.
  import { PLANTILLAS } from '$lib/centro-mando/plantillas.js';
  import { sugerirOcupantes, sentadosEnOtrosDepartamentos } from '$lib/centro-mando/sugerencias.js';

  /**
   * EL CONSTRUCTOR DE LA EMPRESA.
   *
   * Tres listas —pisos, departamentos y espacios— y un botón. Se manda el
   * documento ENTERO en cada guardado, igual que lo escribe el motor: un
   * organigrama no se edita campo a campo, y guardarlo de a trozos dejaría
   * estados intermedios inválidos (un departamento en un piso que todavía no
   * existe, dos salas con el mismo identificador).
   *
   * UNA FILA SE BORRA VACIANDO SU IDENTIFICADOR, y el botón de quitar hace
   * exactamente eso: sacarla de la lista. Así el formulario tiene un solo
   * camino hacia el servidor y no hay una segunda forma de decir «esto ya no
   * está» que haya que mantener aparte.
   *
   * LOS ERRORES DEL MOTOR SE MUESTRAN TAL CUAL. Son los que dicen qué regla se
   * rompió —«el área "Ventas" la reclaman comercial y ventas»—, y reemplazarlos
   * por «revisá los datos» dejaría a quien organiza la empresa adivinando.
   */
  let { data, form } = $props();

  const org = $derived(form?.organizacion ?? data.organizacion ?? {});
  const plantillas = data.organizacion?.plantillas ?? [];
  const agentes = data.organizacion?.agentes ?? [];

  //  Copias editables. Se siembran una vez: mientras alguien edita, lo que
  //  manda es lo que tiene en pantalla.
  let pisos = $state((data.organizacion?.pisos ?? []).map((p) => ({ ...p })));
  let departamentos = $state(
    (data.organizacion?.departamentos ?? []).map((d) => ({
      ...d,
      areas: (d.areas ?? []).join(', '),
      capacidades: (d.capacidades ?? []).join(', '),
      //  LAS OCUPACIONES SE EDITAN COMO LISTA, NO COMO UN CAMPO POR DEPARTAMENTO.
      //  Antes acá vivía un solo `agente` —el del puesto principal— y las demás
      //  ocupaciones viajaban escondidas. Eso ya costó un agente de verdad: el
      //  pie de la oficina pasó de «6 de 37» a «5 de 40» sin un error. Ahora la
      //  lista entera es el estado, se dibuja una silla por puesto, y lo que la
      //  plantilla elegida no tiene es lo único que viaja oculto.
      ocupaciones: (d.ocupaciones ?? []).map((o) => ({ ...o }))
    }))
  );
  let espacios = $state((data.organizacion?.espacios ?? []).map((e) => ({ ...e })));

  //  Qué se propuso en cada departamento, para decirlo debajo del botón. Es
  //  del momento y no se guarda: describe el gesto, no la empresa.
  let propuestas = $state({});

  const vacio = () => ({ id: '', rotulo: '', direccion: '', piso: pisos[0]?.nivel ?? 1,
                         plantilla: '', areas: '', capacidades: '', ocupaciones: [],
                         acento: '' });

  /** Los puestos de la plantilla elegida, o ninguno si todavía no eligió. */
  function puestosDe(nombre) {
    const pl = PLANTILLAS[String(nombre ?? '')];
    return pl ? pl.puestos : [];
  }

  /** Quién se sienta hoy en ese puesto, o cadena vacía. */
  function ocupante(dep, puesto) {
    return (dep.ocupaciones ?? []).find((o) => o.puesto === puesto)?.agente ?? '';
  }

  /**
   * La PERSONA del equipo que ocupa ese puesto.
   *
   * Un escritorio donde trabaja alguien se veía idéntico a uno vacío hasta el
   * 31/10/2026, así que la oficina decía que media empresa no existe. Es texto
   * libre: el motor no conoce las cuentas del CRM, y atarlo a un usuario
   * obligaría a que toda persona del organigrama tuviera cuenta — ya se midió
   * que los auxiliares de campo no la tienen.
   */
  function ocupantePersona(dep, puesto) {
    return (dep.ocupaciones ?? []).find((o) => o.puesto === puesto)?.persona ?? '';
  }

  /** Sentar (o levantar) a una persona. Mismo criterio que `sentar`. */
  function sentarPersona(dep, puesto, persona) {
    const otras = (dep.ocupaciones ?? []).filter((o) => o.puesto !== puesto);
    const texto = String(persona ?? '').trim();
    dep.ocupaciones = texto ? [...otras, { puesto, persona: texto }] : otras;
  }

  /**
   * Sentar (o desentar) a alguien. Vaciar QUITA la ocupación en vez de dejarla
   * con agente vacío: «ninguno» es la ausencia, y guardarla haría que un puesto
   * libre y uno que alguien vació se vieran distintos sin serlo.
   */
  function sentar(dep, puesto, agente) {
    const otras = (dep.ocupaciones ?? []).filter((o) => o.puesto !== puesto);
    //  Elegir un agente DESALOJA a la persona de ese puesto. No es un arbitraje
    //  silencioso: es lo que alguien acaba de pedir, en la silla que acaba de
    //  mirar. Dejar las dos cosas mandaria un documento que el motor rechaza y
    //  convertiria una eleccion normal en un error.
    dep.ocupaciones = agente ? [...otras, { puesto, agente }] : otras;
  }

  /**
   * Las ocupaciones de puestos que la plantilla elegida NO tiene. Son las que
   * no se pueden dibujar y por eso viajan en un campo oculto: la empresa pudo
   * declarar un puesto y después cambiar de sala, y el motor lo reporta como
   * «puesto desconocido» en vez de borrarlo.
   */
  function ocultas(dep) {
    const dibujados = new Set(puestosDe(dep.plantilla).map((p) => p.id));
    return JSON.stringify((dep.ocupaciones ?? []).filter((o) => !dibujados.has(o.puesto)));
  }

  /**
   * PROPONER, NO DECIDIR. Llena las sillas vacías con los agentes del área y
   * deja el formulario sin guardar: lo que queda escrito lo confirma una
   * persona apretando Guardar. Las reglas —no sentar una capacidad, no sentar
   * a nadie dos veces, no pisar lo elegido— viven en `sugerencias.js`.
   */
  function proponer(i) {
    const d = departamentos[i];
    const r = sugerirOcupantes(
      { areas: comas(d.areas), capacidades: comas(d.capacidades), ocupaciones: d.ocupaciones },
      agentes,
      puestosDe(d.plantilla),
      sentadosEnOtrosDepartamentos(departamentos, i)
    );
    d.ocupaciones = r.ocupaciones;
    propuestas = { ...propuestas, [i]: r };
  }

  const comas = (t) => String(t ?? '').split(',').map((x) => x.trim()).filter(Boolean);
  const nombreDe = (n) => agentes.find((a) => a.nombre === n)?.cargo || n;
</script>

<svelte:head><title>Organización de la empresa · Dexter</title></svelte:head>

<div class="pagina">
  <header>
    <h1>Organización de la empresa</h1>
    <p>
      Qué departamentos tiene, cómo se llaman y en qué piso están. Es lo que
      dibuja la oficina virtual.
      {#if org?.origen === 'por_defecto'}
        <strong class="aviso">
          Ahora mismo se está usando la estructura por defecto del producto:
          esta empresa todavía no declaró la suya. Guardar acá la declara.
        </strong>
      {/if}
    </p>
  </header>

  {#if !data.organizacion}
    <p class="roto">
      No se pudo leer la organización: el asistente no responde o esta empresa
      no tiene uno configurado.
    </p>
  {:else}
    {#if form?.update?.error}
      <p class="roto" data-prueba="error">{form.update.error}</p>
    {:else if form?.update?.ok}
      <p class="ok" data-prueba="guardado">Organización guardada.</p>
    {/if}

    <form method="POST" action="?/update">
      <section>
        <h2>Pisos</h2>
        <p class="nota">
          De arriba hacia abajo es como se lee el edificio. Un piso declarado y
          sin salas aparece igual: es un nivel libre, no un error.
        </p>
        {#each pisos as p, i (i)}
          <div class="fila">
            <label>Nivel <input type="number" name="piso:{i}:nivel" bind:value={p.nivel} /></label>
            <label class="ancho">Nombre <input name="piso:{i}:rotulo" bind:value={p.rotulo} /></label>
            <button type="button" onclick={() => (pisos = pisos.filter((_, j) => j !== i))}>Quitar</button>
          </div>
        {/each}
        <button type="button" class="agregar"
          onclick={() => (pisos = [...pisos, { nivel: (Math.max(0, ...pisos.map((x) => x.nivel)) + 1), rotulo: '' }])}>
          Agregar piso
        </button>
      </section>

      <section>
        <h2>Departamentos</h2>
        <p class="nota">
          Un departamento existe aunque no tenga ningún agente. «Áreas» son las
          etiquetas con las que los roles dicen a qué pertenecen, separadas por
          comas: hay dos vocabularios y no coinciden, así que se declaran todas
          las escrituras que este departamento reclama.
        </p>
        <p class="nota">
          Quién se sienta se <strong>elige</strong>, silla por silla. «Sugerir
          ocupantes» propone a los agentes del área en los puestos libres, pero
          no guarda nada: lo confirma quien apriete Guardar. Las capacidades no
          se proponen — son roles que se le asignan a una persona real, no
          empleados con escritorio.
        </p>
        {#each departamentos as d, i (i)}
          <div class="tarjeta">
            <div class="fila">
              <label>Identificador <input name="dep:{i}:id" bind:value={d.id} placeholder="recursos_humanos" /></label>
              <label class="ancho">Nombre <input name="dep:{i}:rotulo" bind:value={d.rotulo} /></label>
              <label>Piso
                <select name="dep:{i}:piso" bind:value={d.piso}>
                  {#each pisos as p (p.nivel)}<option value={p.nivel}>{p.nivel}</option>{/each}
                </select>
              </label>
            </div>
            <div class="fila">
              <label>Sala
                <select name="dep:{i}:plantilla" bind:value={d.plantilla}>
                  <option value="">— elegir —</option>
                  {#each plantillas as pl (pl.nombre)}
                    <option value={pl.nombre}>{pl.rotulo} ({pl.puestos} puestos)</option>
                  {/each}
                </select>
              </label>
              <label>Dirección <input name="dep:{i}:direccion" bind:value={d.direccion} /></label>
            </div>
            <div class="fila">
              <label class="ancho">Áreas <input name="dep:{i}:areas" bind:value={d.areas} placeholder="operativo, Operaciones" /></label>
              <label class="ancho">Capacidades <input name="dep:{i}:capacidades" bind:value={d.capacidades} /></label>
              <label>Color <input name="dep:{i}:acento" bind:value={d.acento} placeholder="#4f46e5" /></label>
              <input type="hidden" name="dep:{i}:otras" value={ocultas(d)} />
              <button type="button" onclick={() => (departamentos = departamentos.filter((_, j) => j !== i))}>Quitar</button>
            </div>

            <div class="puestos">
              {#if !d.plantilla}
                <p class="nota">Elegí una sala arriba y acá aparecen sus puestos.</p>
              {:else}
                <div class="fila">
                  {#each puestosDe(d.plantilla) as p (p.id)}
                    <label class="silla">
                      {p.nombre}{p.principal ? ' · principal' : ''}
                      <select name="dep:{i}:ocupa_{p.id}"
                              value={ocupante(d, p.id)}
                              onchange={(e) => sentar(d, p.id, e.currentTarget.value)}>
                        <option value="">— libre —</option>
                        {#each agentes as a (a.nombre)}
                          <option value={a.nombre}>{a.cargo || a.nombre}</option>
                        {/each}
                      </select>
                      <!-- O una persona. Son excluyentes y el motor lo
                           rechaza diciendo cuál es el problema; la pantalla no
                           arbitra en silencio. -->
                      <input class="persona" name="dep:{i}:persona_{p.id}"
                             placeholder="o una persona"
                             value={ocupantePersona(d, p.id)}
                             onchange={(e) => sentarPersona(d, p.id, e.currentTarget.value)} />
                    </label>
                  {/each}
                  <button type="button" class="proponer" onclick={() => proponer(i)}>
                    Sugerir ocupantes
                  </button>
                </div>
                {#if propuestas[i]}
                  <p class="propuesta" data-prueba="propuesta-{i}">
                    {#if propuestas[i].sentados.length}
                      Propuesto: {propuestas[i].sentados.map(nombreDe).join(', ')}.
                      Revisalo y guardá para confirmarlo.
                    {:else}
                      Nada que proponer: no quedan puestos libres o ningún agente
                      del área está disponible.
                    {/if}
                    {#if propuestas[i].sinSilla.length}
                      <strong>Sin silla:</strong>
                      {propuestas[i].sinSilla.map(nombreDe).join(', ')} —
                      pertenecen a este departamento y la sala no tiene más puestos.
                    {/if}
                    {#if propuestas[i].ocupadoEnOtra.length}
                      <strong>Ya sentados en otro departamento:</strong>
                      {propuestas[i].ocupadoEnOtra.map(nombreDe).join(', ')}.
                    {/if}
                  </p>
                {/if}
              {/if}
            </div>
          </div>
        {/each}
        <button type="button" class="agregar"
          onclick={() => (departamentos = [...departamentos, vacio()])}>Agregar departamento</button>
      </section>

      <section>
        <h2>Espacios</h2>
        <p class="nota">
          Recepción, dirección, una sala de reuniones. No son departamentos: no
          agrupan áreas ni agentes, y a una recepción no se le asignan
          responsabilidades.
        </p>
        {#each espacios as e, i (i)}
          <div class="fila">
            <label>Identificador <input name="esp:{i}:id" bind:value={e.id} /></label>
            <label class="ancho">Nombre <input name="esp:{i}:rotulo" bind:value={e.rotulo} /></label>
            <label>Piso
              <select name="esp:{i}:piso" bind:value={e.piso}>
                {#each pisos as p (p.nivel)}<option value={p.nivel}>{p.nivel}</option>{/each}
              </select>
            </label>
            <label>Sala
              <select name="esp:{i}:plantilla" bind:value={e.plantilla}>
                <option value="">— elegir —</option>
                {#each plantillas as pl (pl.nombre)}<option value={pl.nombre}>{pl.rotulo}</option>{/each}
              </select>
            </label>
            <button type="button" onclick={() => (espacios = espacios.filter((_, j) => j !== i))}>Quitar</button>
          </div>
        {/each}
        <button type="button" class="agregar"
          onclick={() => (espacios = [...espacios, { id: '', rotulo: '', piso: pisos[0]?.nivel ?? 1, plantilla: '', acento: '' }])}>
          Agregar espacio
        </button>
      </section>

      {#if data.can_edit}
        <button type="submit" class="guardar">Guardar organización</button>
      {:else}
        <p class="nota">Solo un administrador puede reorganizar la empresa.</p>
      {/if}
    </form>
  {/if}
</div>

<style>
  .pagina { padding: 1.5rem; max-width: 1100px; }
  h1 { margin: 0 0 0.25rem; font-size: 1.3rem; }
  header p { margin: 0 0 1.5rem; color: #6b7280; font-size: 0.9rem; }
  .aviso { display: block; margin-top: 0.4rem; color: #92400e; }
  section { margin-bottom: 2rem; }
  h2 { font-size: 1rem; margin: 0 0 0.3rem; }
  .nota { color: #6b7280; font-size: 0.82rem; margin: 0 0 0.8rem; }
  .fila { display: flex; gap: 0.6rem; align-items: flex-end; margin-bottom: 0.5rem; flex-wrap: wrap; }
  .tarjeta { border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.8rem; margin-bottom: 0.8rem; }
  label { display: flex; flex-direction: column; font-size: 0.78rem; color: #374151; gap: 0.2rem; }
  label.ancho { flex: 1; min-width: 180px; }
  input, select { padding: 0.35rem 0.5rem; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.85rem; }
  button { padding: 0.35rem 0.7rem; border: 1px solid #d1d5db; background: #fff; border-radius: 6px; cursor: pointer; font-size: 0.82rem; }
  .agregar { border-style: dashed; }
  .puestos { border-top: 1px dashed #e5e7eb; padding-top: 0.6rem; margin-top: 0.2rem; }
  label.silla { gap: 0.25rem; }
  .persona { font-size: 0.78rem; max-width: 160px; }
  .proponer { align-self: flex-end; border-color: #4f46e5; color: #4f46e5; }
  .propuesta { font-size: 0.8rem; color: #374151; background: #f8fafc; padding: 0.5rem 0.7rem;
               border-radius: 6px; margin: 0.4rem 0 0; }
  .propuesta strong { color: #92400e; }
  .guardar { background: #4f46e5; color: #fff; border-color: #4f46e5; padding: 0.5rem 1.1rem; }
  .roto { color: #b42318; background: #fef3f2; padding: 0.6rem 0.8rem; border-radius: 6px; }
  .ok { color: #166534; background: #f0fdf4; padding: 0.6rem 0.8rem; border-radius: 6px; }
</style>
