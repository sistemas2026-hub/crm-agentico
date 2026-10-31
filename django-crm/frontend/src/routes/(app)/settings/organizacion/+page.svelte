<script>
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
      agente: (d.ocupaciones ?? []).find((o) => o.puesto === 'principal')?.agente ?? '',
      //  Lo que esta pantalla no edita y no puede perder. Ver el comentario de
      //  `otrasOcupaciones` en el traductor: guardar sólo el principal borró a
      //  un agente de verdad, y el síntoma fue un número en el pie.
      otras: JSON.stringify((d.ocupaciones ?? []).filter((o) => o.puesto !== 'principal'))
    }))
  );
  let espacios = $state((data.organizacion?.espacios ?? []).map((e) => ({ ...e })));

  const vacio = () => ({ id: '', rotulo: '', direccion: '', piso: pisos[0]?.nivel ?? 1,
                         plantilla: '', areas: '', capacidades: '', agente: '',
                         otras: '[]', acento: '' });
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
              <label>Agente del puesto principal
                <select name="dep:{i}:agente" bind:value={d.agente}>
                  <option value="">— ninguno —</option>
                  {#each agentes as a (a.nombre)}
                    <option value={a.nombre}>{a.cargo || a.nombre}</option>
                  {/each}
                </select>
              </label>
              <label>Dirección <input name="dep:{i}:direccion" bind:value={d.direccion} /></label>
            </div>
            <div class="fila">
              <label class="ancho">Áreas <input name="dep:{i}:areas" bind:value={d.areas} placeholder="operativo, Operaciones" /></label>
              <label class="ancho">Capacidades <input name="dep:{i}:capacidades" bind:value={d.capacidades} /></label>
              <label>Color <input name="dep:{i}:acento" bind:value={d.acento} placeholder="#4f46e5" /></label>
              <input type="hidden" name="dep:{i}:otras" value={d.otras} />
              <button type="button" onclick={() => (departamentos = departamentos.filter((_, j) => j !== i))}>Quitar</button>
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
  .guardar { background: #4f46e5; color: #fff; border-color: #4f46e5; padding: 0.5rem 1.1rem; }
  .roto { color: #b42318; background: #fef3f2; padding: 0.6rem 0.8rem; border-radius: 6px; }
  .ok { color: #166534; background: #f0fdf4; padding: 0.6rem 0.8rem; border-radius: 6px; }
</style>
