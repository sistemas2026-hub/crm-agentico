<script>
  /**
   * Definirle la contraseña a otra persona.
   *
   * DOS CAMINOS, Y POR QUÉ LOS DOS
   * ------------------------------
   * Generarla es lo correcto casi siempre: nadie elige una contraseña mejor
   * que el azar. Pero una clave generada de dieciséis caracteres con guiones
   * se dicta mal por teléfono y se anota peor, y acá el caso real es alguien
   * en la calle que no puede entrar. Por eso se puede escribir una.
   *
   * Generar queda como opción por defecto: el campo arranca vacío y el botón
   * dice qué va a pasar si se deja así.
   *
   * NO VALIDA LA CONTRASEÑA
   * -----------------------
   * Qué se acepta lo decide el servidor, que ya tiene la regla y devuelve el
   * motivo cuando dice que no. Copiarla acá es garantizar que algún día las
   * dos no coincidan, y que la de la pantalla sea la equivocada.
   *
   * SE ARMA EN DOS PASOS
   * --------------------
   * Como todo lo que no se puede deshacer en esta tabla. Además le cierra las
   * sesiones abiertas: si esa persona está trabajando, se cae. Eso se dice
   * antes, no después.
   */
  import { enhance } from '$app/forms';

  /** @type {{
   *   userId: string,
   *   persona: string,
   *   disabled?: boolean
   * }} */
  let { userId, persona, disabled = false } = $props();

  let armed = $state(false);
  let busy = $state(false);
  let nueva = $state('');
  let verla = $state(false);

  function cerrar() {
    armed = false;
    nueva = '';
    verla = false;
  }
</script>

{#if armed}
  <form
    class="clave"
    method="POST"
    action="?/clave"
    use:enhance={() => {
      busy = true;
      return async (/** @type {any} */ { update }) => {
        await update();
        busy = false;
        cerrar();
      };
    }}
  >
    <input type="hidden" name="userId" value={userId} />
    <input type="hidden" name="persona" value={persona} />

    <span class="v2-sub" style="font-size:11.5px"> Se le cierran las sesiones abiertas. </span>

    <span class="campo">
      <!-- svelte-ignore a11y_autofocus -->
      <input
        class="v2-input v2-input-sm"
        type={verla ? 'text' : 'password'}
        name="nueva"
        autocomplete="new-password"
        placeholder="Dejalo vacío para generarla"
        aria-label={`Contraseña nueva para ${persona}`}
        bind:value={nueva}
        disabled={busy}
        autofocus
      />
      <button
        class="ojo"
        type="button"
        onclick={() => (verla = !verla)}
        aria-label={verla ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
        title={verla ? 'Ocultar' : 'Mostrar'}
        disabled={busy}
      >
        {verla ? 'Ocultar' : 'Ver'}
      </button>
    </span>

    <button class="v2-btn v2-btn-sm" type="submit" disabled={busy}>
      {nueva.trim() ? 'Poner esta clave' : 'Generar una'}
    </button>
    <button class="v2-btn v2-btn-sm" type="button" disabled={busy} onclick={cerrar}>
      Cancelar
    </button>
  </form>
{:else}
  <button
    class="v2-btn v2-btn-sm v2-btn-icono"
    type="button"
    {disabled}
    onclick={() => (armed = true)}
    aria-label={`Cambiar la contraseña de ${persona}`}
    title="Cambiar la contraseña"
  >
    <!-- Una llave. -->
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
      <path
        d="M14 7a4 4 0 1 1-3.87 5H7v2H5v2H2v-3l5.13-5.13A4 4 0 0 1 14 7Z"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linejoin="round"
      />
      <circle cx="15.5" cy="8.5" r="1.1" fill="currentColor" />
    </svg>
  </button>
{/if}

<style>
  .clave {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .campo {
    position: relative;
    display: inline-flex;
    align-items: center;
  }

  .campo input {
    padding-right: 52px;
    min-width: 200px;
  }

  /* El "ver" va dentro del campo: fuera, en una fila que ya tiene cuatro
     botones, parece una acción más de la persona y no del campo. */
  .ojo {
    position: absolute;
    right: 6px;
    border: 0;
    background: none;
    padding: 2px 4px;
    font-size: 11px;
    color: var(--v2-ink-soft, #667);
    cursor: pointer;
  }

  .ojo:hover:not(:disabled) {
    text-decoration: underline;
  }
</style>
