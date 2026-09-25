<script>
  /**
   * Cerrar un caso a mano: en qué terminó, y opcionalmente una nota (B6, T17).
   *
   * POR QUÉ ESTO REEMPLAZA AL `confirm()` DE ANTES
   * Antes cerrar era un «¿seguro?» y listo. La conversación se cerraba y de
   * lo que le había pasado al cliente no quedaba nada: ni si era la ONT, ni
   * si era facturación, ni si lo había resuelto él solo. Con cincuenta casos
   * cerrados por semana eso es cincuenta veces que nadie aprende nada.
   *
   * NINGUNA OPCIÓN VIENE ELEGIDA, y es la regla de este panel. Ni la primera
   * de la lista, ni la última que usó esta persona. Un valor por defecto
   * convierte cerrar en dos clics y llena la columna con lo que eligió el
   * formulario en vez de lo que pasó — y esa columna existe justo para poder
   * contar lo que pasó.
   *
   * LA LISTA VIENE DEL MOTOR, no de un array acá: una empresa puede agregar
   * códigos propios desde la configuración, y una copia en la pantalla se
   * desincroniza el día que alguien lo hace.
   */
  import { MAX_NOTA, motivoParaNoCerrar, categoriaVisible } from '$lib/conversaciones/desenlaces.js';

  let {
    catalogo = [],
    errorCatalogo = '',
    guardando = false,
    error = '',
    onCerrar = undefined,
    onCancelar = undefined
  } = $props();

  let codigo = $state('');
  let nota = $state('');

  const impedimento = $derived(motivoParaNoCerrar({ codigo, nota, catalogo }));
</script>

<form
  class="cierre"
  onsubmit={(e) => {
    e.preventDefault();
    if (!impedimento) onCerrar?.({ codigo, nota });
  }}
>
  <h3 class="titulo">¿En qué terminó?</h3>
  <p class="nota-guia">
    Se cierra la conversación. El próximo mensaje del cliente abre una nueva.
  </p>

  {#if errorCatalogo}
    <p class="aviso-mal">{errorCatalogo}</p>
  {/if}

  <ul class="opciones">
    {#each catalogo as d (d.codigo)}
      {@const categoria = categoriaVisible(d)}
      <li>
        <label class:elegida={codigo === d.codigo}>
          <input type="radio" name="desenlace" value={d.codigo} bind:group={codigo} />
          <span class="nombre">{d.nombre}</span>
          {#if categoria}<span class="categoria">{categoria}</span>{/if}
        </label>
      </li>
    {/each}
  </ul>

  <label class="campo-nota">
    <span>Nota (opcional)</span>
    <textarea
      bind:value={nota}
      maxlength={MAX_NOTA}
      rows="2"
      placeholder="Qué pasó, en una línea. Sin datos personales del cliente."
    ></textarea>
  </label>

  <div class="pie">
    <button type="button" class="v2-btn v2-btn-sm v2-btn-quiet" onclick={() => onCancelar?.()}>
      Cancelar
    </button>
    <!-- Deshabilitado CON el motivo al lado: un botón apagado y mudo hace que
         alguien recargue la página tres veces antes de preguntar. -->
    <button
      type="submit"
      class="v2-btn v2-btn-sm"
      disabled={!!impedimento || guardando}
      aria-busy={guardando}
    >
      {guardando ? 'Cerrando…' : 'Cerrar el caso'}
    </button>
    {#if impedimento && !guardando}<span class="impedimento">{impedimento}</span>{/if}
  </div>

  {#if error}<p class="aviso-mal">{error}</p>{/if}
</form>

<style>
  .cierre {
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
    padding: 0.75rem 0.9rem;
    margin-top: 0.6rem;
    background: var(--bandeja-superficie-suave);
  }
  .titulo {
    margin: 0 0 0.15rem;
    font-size: 0.9rem;
    font-weight: 600;
  }
  .nota-guia {
    margin: 0 0 0.6rem;
    font-size: 0.78rem;
    color: var(--bandeja-texto-2);
  }
  .opciones {
    list-style: none;
    margin: 0 0 0.7rem;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 0.2rem 0.6rem;
  }
  .opciones label {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.28rem 0.4rem;
    border-radius: 5px;
    font-size: 0.82rem;
    cursor: pointer;
  }
  .opciones label:hover,
  .opciones label.elegida {
    background: var(--bandeja-humano-fondo);
  }
  .categoria {
    font-size: 0.72rem;
    color: var(--bandeja-texto-2);
  }
  .campo-nota {
    display: block;
    font-size: 0.78rem;
    color: var(--bandeja-texto-2);
  }
  .campo-nota textarea {
    width: 100%;
    margin-top: 0.2rem;
    font: inherit;
    font-size: 0.82rem;
    padding: 0.35rem 0.45rem;
    border: 1px solid var(--bandeja-borde);
    border-radius: 5px;
    resize: vertical;
  }
  .pie {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.7rem;
    flex-wrap: wrap;
  }
  .impedimento {
    font-size: 0.78rem;
    color: var(--bandeja-texto-2);
  }
  .aviso-mal {
    margin: 0.5rem 0 0;
    font-size: 0.8rem;
    color: var(--bandeja-error);
  }
</style>
