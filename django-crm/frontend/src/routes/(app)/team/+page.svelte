<script>
  /**
   * Who can get in, and how much they can do.
   *
   * ROLE IS DISPLAYED HERE, DECIDED ON THE SERVER.
   * `role` comes from the Profile the API returned. This page renders it and
   * offers to change it; the server decides whether the change is allowed. Two
   * rules the endpoint enforces and this page mirrors as hints only, nobody
   * changes their own role, and the org keeps at least one admin. Mirroring
   * them is a courtesy so a button does not 400; it is not the control. The
   * real enforcement is in common/views/user_views.py, because anyone can skip
   * this page entirely with curl, which is exactly how a member used to PATCH
   * themselves to admin before that path was closed.
   *
   * The row that matters most is the quiet one: a deactivated account with a
   * not-yet-revoked API token. Deactivating a login already stops that token at
   * the door; resolve_valid_pat rejects a token whose profile.is_active is
   * false, but it is dormant, not revoked, and would authenticate again the
   * moment the account is reactivated. That is why the count is here: an
   * offboarding to-do, not a live breach.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import { count, relativeDays } from '$lib/v2/format.js';
  import { ROLE_LABEL, ROLE_TONE } from '$lib/v2/enums.js';
  import { enhance } from '$app/forms';
  import {
    UserPlus,
    KeyRound,
    Pencil,
    Check,
    X,
    ShieldCheck,
    ShieldMinus,
    UserX,
    UserCheck,
    Eye,
    EyeOff
  } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  import { toast } from 'svelte-sonner';

  let { data, form } = $props();

  let inviting = $state(false);
  let externoElegido = $state('');
  let areaElegida = $state('');

  // Mostrar u ocultar lo que se escribe en los dos campos de clave. Arrancan
  // ocultos: el alta se hace con la persona al lado y a veces con alguien mas
  // mirando la pantalla. El ojito esta porque una clave escrita a ciegas y mal
  // se descubre recien cuando la persona no puede entrar.
  let verClaveAlta = $state(false);
  let verClaveFila = $state(false);

  // 'busy' bloquea los botones mientras hay un envio en curso, y 'working' es
  // el callback que use:enhance necesita para levantar y bajar esa bandera.
  // Los formularios de rol y estado los usan.
  let busy = $state(false);
  /** @type {import('@sveltejs/kit').SubmitFunction} */
  const working = () => {
    busy = true;
    return async ({ update }) => {
      await update();
      busy = false;
    };
  };

  /** El formulario de alta se cierra solo cuando la creacion salio bien. */
  const inviteSubmit = () => {
    busy = true;
    return async ({ result, update }) => {
      await update();
      busy = false;
      if (result?.type === 'success' && result?.data?.invited) inviting = false;
    };
  };

  // Los agentes que precarga el area elegida EN EL ALTA (la edicion por fila
  // usa 'borrador', que es otra cosa).
  const agentesDelArea = $derived(
    data.areasTrabajo?.find((/** @type {any} */ a) => a.nombre === areaElegida)?.agentes ?? []
  );

  // El nombre del usuario externo elegido en el alta, para mandarlo junto al
  // id y no tener que reconsultar la API externa despues.
  const nombreExterno = $derived(
    data.externos?.find((/** @type {any} */ e) => e.identificador === externoElegido)
      ?.nombre_visible ?? ''
  );

  // Lo que cada persona tiene hoy. Solo se lee: el borrador de abajo es lo
  // que se toca mientras se edita.
  /** @type {Record<string, {area: string, agentes: string[], externo: string}>} */
  let fila = $state(
    Object.fromEntries(
      [...(data.active ?? []), ...(data.inactive ?? [])].map((/** @type {any} */ m) => [
        m.id,
        {
          area: data.areasPorPersona?.[m.id] ?? '',
          agentes: data.asignaciones?.[m.id] ?? [],
          externo: data.identidades?.[m.id]?.identificador ?? ''
        }
      ])
    )
  );

  // Que fila esta en edicion (null = ninguna) y su borrador.
  //
  // Una sola a la vez, y con Guardar/Cancelar explicitos. La primera version
  // guardaba en cada clic sobre controles siempre activos: un clic mal dado
  // cambiaba los permisos de alguien sin confirmar nada, y sin forma de
  // deshacerlo salvo acordarse de como estaba.
  /** @type {string | null} */
  let editando = $state(null);
  let borrador = $state({
    name: '',
    email: '',
    role: 'USER',
    activo: true,
    area: '',
    agentes: /** @type {string[]} */ ([]),
    externo: '',
    // Vacia SIEMPRE al abrir la edicion, y vacia significa "no la toques".
    // Nunca se precarga con nada: no hay forma de leer la clave de alguien, y
    // un campo que muestre algo (aunque sean puntitos de relleno) invita a
    // guardarlo tal cual y pisarle la clave a quien solo venia a que le
    // corrigieran el area.
    password: ''
  });
  let guardandoFila = $state(false);

  const etiquetaArea = (/** @type {string} */ nombre) =>
    data.areasTrabajo?.find((/** @type {any} */ a) => a.nombre === nombre)?.etiqueta ?? '';

  function editar(/** @type {any} */ m) {
    editando = m.id;
    borrador = {
      name: m.name ?? '',
      email: m.email ?? '',
      role: m.role ?? 'USER',
      activo: !!m.is_active,
      area: fila[m.id]?.area ?? '',
      agentes: [...(fila[m.id]?.agentes ?? [])],
      externo: fila[m.id]?.externo ?? '',
      password: ''
    };
    verClaveFila = false;
  }

  const nombreExternoDe = (/** @type {string} */ id) =>
    data.externos?.find((/** @type {any} */ e) => e.identificador === id)?.nombre_visible ?? '';

  function cancelar() {
    editando = null;
  }

  // Cambiar el area recarga sus agentes tambien al corregir, no solo al dar
  // de alta: es lo que hace util al preset cuando alguien cambia de area. Se
  // pueden desmarcar antes de guardar.
  function recargarAgentes() {
    const sug = data.areasTrabajo?.find(
      (/** @type {any} */ a) => a.nombre === borrador.area
    )?.agentes;
    if (sug) borrador = { ...borrador, agentes: [...sug] };
  }

  function alternarAgente(/** @type {string} */ agente) {
    borrador = {
      ...borrador,
      agentes: borrador.agentes.includes(agente)
        ? borrador.agentes.filter((a) => a !== agente)
        : [...borrador.agentes, agente]
    };
  }

  /**
   * El submit de la fila. Cierra la edicion solo si el servidor confirmo, y
   * recarga los datos para que la tabla muestre lo que quedo guardado y no lo
   * que se pidio.
   */
  const edicionSubmit = () => {
    guardandoFila = true;
    return async (/** @type {any} */ { result, update }) => {
      await update({ reset: false });
      guardandoFila = false;
      if (result?.type === 'success' && result?.data?.editado) {
        editando = null;
        if (result.data.avisoEdicion) toast.error(result.data.avisoEdicion);
        else if (result.data.claveCambiada)
          toast.success(`${result.data.editado}: guardado, con contraseña nueva.`);
        else toast.success(`${result.data.editado}: guardado.`);
      } else if (result?.data?.edicion?.error) {
        toast.error(result.data.edicion.error);
      }
    };
  };
</script>

<!--
  Escape cancela la edicion.

  No es un adorno de teclado: la fila en edicion es ancha y, segun el ancho de
  la ventana, hubo un momento en que ni Guardar ni Cancelar se alcanzaban. La
  barra de abajo lo resuelve, pero una salida que no depende de encontrar un
  boton vale igual -- es la tecla que cualquiera prueba cuando quiere salir de
  algo, y aca la alternativa era recargar la pagina.

  No dispara mientras se esta guardando: ahi la peticion ya salio y cerrar el
  formulario solo escondería lo que el servidor todavia va a contestar.
-->
<svelte:window
  onkeydown={(e) => {
    if (e.key === 'Escape' && editando !== null && !guardandoFila) cancelar();
  }}
/>

{#if data.forbidden}
  <PageHeader title="Equipo y acceso" />
  <div class="v2-pad" style="padding-top:40px">
    <NextAction
      label="Solo administradores"
      text="Gestionar personas, roles y accesos está limitado a administradores de la organización. Pedile a un administrador de tu equipo si necesitás agregar a alguien o cambiar un rol."
    />
  </div>
{:else}
  <PageHeader title="Equipo y acceso">
    {#snippet sub()}
      <span class="v2-num">{count(data.totals.count)}</span> personas ·
      <span class="v2-num">{count(data.totals.admins)}</span> administradores
    {/snippet}
    {#snippet actions()}
      <button class="v2-btn v2-btn-primary" onclick={() => (inviting = !inviting)}>
        <UserPlus />Agregar persona
      </button>
    {/snippet}
  </PageHeader>

  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard label="Personas activas" value={count(data.totals.count)} tone="ink" />
      <StatCard
        label="Administradores"
        value={count(data.totals.admins)}
        tone="clay"
        detail="Pueden cambiar roles y configuración de la organización"
      />
      <StatCard
        label="Nunca inició sesión"
        value={count(data.totals.never_signed_in)}
        tone={data.totals.never_signed_in ? 'clay' : 'slate'}
        detail={data.totals.never_signed_in ? 'Creado, todavía sin entrar' : 'Todos iniciaron sesión'}
      />
      <StatCard label="Desactivados" value={count(data.totals.deactivated)} tone="slate" />
    </div>
  </div>

  <div class="v2-scroll">
    <div class="v2-pad" style="padding-bottom:32px">
      {#if inviting}
        <form
          method="POST"
          action="?/invite"
          use:enhance={inviteSubmit}
          class="v2-card"
          style="padding:14px 15px;margin-bottom:18px;display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap"
        >
          <div style="flex:1;min-width:170px">
            <label class="v2-label" for="invite-name" style="display:block;margin-bottom:4px">
              Nombre
            </label>
            <input
              id="invite-name"
              name="name"
              type="text"
              class="v2-input"
              style="width:100%"
              placeholder="Nombre y apellido"
            />
          </div>
          <div style="flex:1;min-width:200px">
            <label class="v2-label" for="invite-email" style="display:block;margin-bottom:4px">
              Correo de la persona
            </label>
            <input
              id="invite-email"
              name="email"
              type="email"
              required
              class="v2-input"
              style="width:100%"
              placeholder="nombre@empresa.com"
            />
          </div>
          <div>
            <label class="v2-label" for="invite-role" style="display:block;margin-bottom:4px">
              Rol
            </label>
            <select id="invite-role" name="role" class="v2-input" style="width:130px">
              <option value="USER">Miembro</option>
              <option value="ADMIN">Administrador</option>
            </select>
          </div>
          <!--
            La clave, opcional. Vacia se comporta como siempre: el servidor
            genera una al azar y la muestra UNA vez en el cartel de abajo.

            Se ofrece escribirla porque el alta casi siempre se hace con la
            persona al lado o al telefono, y dictar "K7mQ2-xR4vT-9wLpZa" termina
            en un intento fallido y una llamada mas. Lo que se escriba pasa por
            los mismos validadores de Django que cualquier otra clave, del lado
            del servidor: aca no se repite ninguna regla de largo ni de forma,
            porque dos lugares con la misma regla es un lugar donde la regla va
            a quedar vieja.
          -->
          <div>
            <label class="v2-label" for="invite-password" style="display:block;margin-bottom:4px">
              Contraseña <span style="font-weight:400;text-transform:none">(opcional)</span>
            </label>
            <span style="display:inline-flex;gap:5px">
              <input
                id="invite-password"
                name="password"
                type={verClaveAlta ? 'text' : 'password'}
                class="v2-input"
                style="width:165px"
                autocomplete="new-password"
                placeholder="Se genera sola"
              />
              <button
                type="button"
                class="v2-btn ico"
                style="width:36px;min-width:36px"
                onclick={() => (verClaveAlta = !verClaveAlta)}
                title={verClaveAlta ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
                aria-label={verClaveAlta ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
              >
                {#if verClaveAlta}<EyeOff />{:else}<Eye />{/if}
              </button>
            </span>
          </div>
          <!--
            El area va en el MISMO formulario a proposito. Antes eran dos
            pantallas para una sola decision: se creaba la persona aca y habia
            que ir a /agentes/asignaciones a decirle con que agente trabaja.
            Quien se saltaba el segundo paso dejaba a alguien creado y sin
            poder hacer nada, sin ninguna señal de que faltaba algo.

            Sigue siendo opcional: si el asistente no responde, 'areas' llega
            vacio y el selector no se muestra -- invitar tiene que funcionar
            igual.
          -->
          {#if data.areasTrabajo?.length}
            <div>
              <label class="v2-label" for="invite-area" style="display:block;margin-bottom:4px">
                Área de trabajo
              </label>
              <select
                id="invite-area"
                name="area"
                class="v2-input"
                style="width:160px"
                bind:value={areaElegida}
              >
                <option value="">Sin área</option>
                {#each data.areasTrabajo as a (a.nombre)}
                  <option value={a.nombre}>{a.etiqueta}</option>
                {/each}
              </select>
            </div>
            <!--
              Los agentes que trae el area, visibles y desmarcables. Mostrarlos
              es la diferencia entre un preset y una caja negra: quien da de
              alta ve que capacidades le esta dando, y puede ajustar antes de
              crear.
            -->
            <div style="min-width:150px">
              <span class="v2-label" style="display:block;margin-bottom:4px">Agentes</span>
              <div style="display:flex;gap:8px;flex-wrap:wrap;padding-top:4px">
                {#each data.areas as agente (agente)}
                  <label style="font-size:12.5px;display:flex;align-items:center;gap:3px">
                    <input
                      type="checkbox"
                      name="agentes"
                      value={agente}
                      checked={agentesDelArea.includes(agente)}
                    />
                    {agente}
                  </label>
                {/each}
              </div>
            </div>
          {/if}
          <div>
            <label class="v2-label" for="invite-activo" style="display:block;margin-bottom:4px">
              Estado
            </label>
            <select id="invite-activo" name="activo" class="v2-input" style="width:105px">
              <option value="si">Activo</option>
              <option value="no">Inactivo</option>
            </select>
          </div>
          <!--
            A nombre de quien se le asigna el trabajo en el sistema operativo.
            Es una LISTA y no un campo de texto a proposito: escribir el
            nombre a mano invita a un typo, y un typo aca manda tickets a la
            persona equivocada -- de los errores que se descubren tarde.

            Va el nombre en un campo oculto ademas del id: la pantalla que lo
            muestre despues necesita poder decir un nombre sin volver a
            preguntarle a la API externa por cada fila.
          -->
          {#if data.externos?.length}
            <div>
              <label class="v2-label" for="invite-externo" style="display:block;margin-bottom:4px">
                {data.etiquetaExterna || 'Usuario externo'}
              </label>
              <select
                id="invite-externo"
                name="externo"
                class="v2-input"
                style="width:190px"
                bind:value={externoElegido}
              >
                <option value="">Sin vincular</option>
                {#each data.externos as ex}
                  <option value={ex.identificador}>{ex.nombre_visible}</option>
                {/each}
              </select>
              <input type="hidden" name="externo_nombre" value={nombreExterno} />
            </div>
          {/if}
          <button class="v2-btn v2-btn-primary" disabled={busy}>Agregar</button>
          <button type="button" class="v2-btn" disabled={busy} onclick={() => (inviting = false)}>
            Cancelar
          </button>
          {#if form?.invite?.error}
            <p
              class="v2-sub"
              style="color:var(--v2-rust);font-size:12px;flex-basis:100%;margin:2px 0 0"
            >
              {form.invite.error}
            </p>
          {/if}
        </form>
      {/if}

      <!-- El area fallo pero la persona SI se creo: se avisa sin teñir de
           error toda la invitacion, y se dice donde arreglarlo. -->
      {#if form?.avisoArea}
        <p
          class="v2-sub"
          style="color:var(--v2-rust);font-size:12.5px;margin:0 0 10px"
        >
          {form.avisoArea} Podés asignársela desde Agentes → Asignaciones.
        </p>
      {/if}

      <!-- La clave se muestra UNA vez: no se guarda legible en ningun lado y
           no hay forma de recuperarla despues. Si se pierde, se regenera. -->
      {#if form?.clave}
        <div
          style="border:1px solid var(--v2-rust);border-radius:7px;padding:12px 14px;margin:0 0 16px;background:color-mix(in srgb, var(--v2-rust) 7%, transparent)"
        >
          <p
            style="font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--v2-rust);font-weight:700;margin:0 0 4px"
          >
            Se muestra una sola vez
          </p>
          <p style="margin:0 0 8px;font-size:13px">
            {form.invited} ya puede entrar con ese correo. Pasale esta clave y pedile que la cambie
            al entrar.
          </p>
          <code
            style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:15px;letter-spacing:.04em;border:1px solid var(--v2-line,#ddd);border-radius:5px;padding:5px 9px;display:inline-block"
            >{form.clave}</code
          >
        </div>
      {/if}

      {#if form?.invited}
        <p
          class="v2-sub"
          style="color:var(--v2-moss);font-size:12.5px;margin:0 0 16px;font-weight:550"
        >
          {form.invited} ya es miembro. Aparece abajo como “nunca” inició sesión hasta que entre con
          ese correo.
        </p>
      {:else if form?.error}
        <div style="margin-bottom:16px">
          <NextAction label="Eso no funcionó" text={form.error} tone="rust" />
        </div>
      {/if}

      {#if data.totals.tokens_on_deactivated}
        <!--
          A dormant liability, not a live one. Deactivating a profile already
          stops its tokens at login (resolve_valid_pat checks profile.is_active),
          but it does not revoke the PersonalAccessToken rows. They would
          authenticate again if the account were reactivated. Worth clearing as
          part of offboarding, hence clay rather than rust.
        -->
        <div style="margin-bottom:20px">
          <NextAction
            label="Cabo suelto"
            text={`${data.totals.tokens_on_deactivated} ${data.totals.tokens_on_deactivated === 1 ? 'token de API pertenece' : 'tokens de API pertenecen'} a una cuenta desactivada. Desactivarla ya los detiene al iniciar sesión, pero no quedan revocados. Reactivar la cuenta los volvería a habilitar. Revocalos para cerrar ese cabo suelto.`}
            action="Revisar tokens"
            href="/settings/api-tokens"
          />
        </div>
      {/if}

      <div class="v2-label" style="margin-bottom:10px">Personas</div>
      <div class="v2-table-wrap" style="margin-bottom:26px">
        <table class="v2-table">
          <thead>
            <tr>
              <!-- Todo lo de una persona se lee Y se edita aca. Estaba
                   partido en /agentes/asignaciones, que obligaba a crear en un
                   lugar y corregir en otro.

                   Los valores se muestran EN REPOSO y se cambian con "Editar".
                   La primera version tenia listas y casillas siempre activas,
                   guardando en cada clic: un clic mal dado le cambiaba los
                   permisos a alguien sin confirmar nada. Para datos de acceso
                   eso esta mal. -->
              <th>Persona</th>
              <th>Área</th>
              <th>Agentes</th>
              {#if data.externos?.length}<th>{data.etiquetaExterna || 'Externo'}</th>{/if}
              <th>Rol</th>
              <th>Estado</th>
              <th data-m="hide">Tokens</th>
              <th class="v2-r">Gestionar</th>
            </tr>
          </thead>
          <tbody>
            {#each [...data.active, ...data.inactive] as m (m.id)}
              {@const isLastAdmin = m.user_id === data.last_admin_id}
              <tr style={m.is_active ? '' : 'opacity:.62'}>
                <td>
                  <span style="display:flex;gap:9px;align-items:center">
                    <Avatar name={m.name} size={27} />
                    <span style="min-width:0">
                      {#if editando === m.id}
                        <input
                          class="v2-input"
                          style="width:150px;font-size:12px;padding:2px 5px;margin-bottom:3px"
                          bind:value={borrador.name}
                          aria-label="Nombre"
                        />
                        <input
                          class="v2-input"
                          style="width:190px;font-size:12px;padding:2px 5px"
                          type="email"
                          bind:value={borrador.email}
                          aria-label="Correo"
                        />
                        <!--
                          Vacia = no se toca. Es la unica forma de que un campo
                          de clave dentro de un formulario que guarda OTRAS
                          cosas no le resetee la clave a alguien cada vez que
                          se le corrige el correo o el area.

                          Sin bind:value a proposito: Svelte no deja combinar
                          two-way binding con un 'type' que cambia, y el type
                          cambia porque el ojito es lo que evita escribir una
                          clave mal a ciegas y enterarse cuando la persona no
                          puede entrar.
                        -->
                        <span style="display:flex;gap:4px;margin-top:3px">
                          <input
                            class="v2-input"
                            style="width:150px;font-size:12px;padding:2px 5px"
                            type={verClaveFila ? 'text' : 'password'}
                            value={borrador.password}
                            oninput={(e) =>
                              (borrador.password = /** @type {HTMLInputElement} */ (
                                e.currentTarget
                              ).value)}
                            autocomplete="new-password"
                            placeholder="Contraseña nueva"
                            aria-label="Contraseña nueva de {m.name}; vacía deja la que ya tiene"
                          />
                          <button
                            type="button"
                            class="v2-btn v2-btn-sm ico"
                            onclick={() => (verClaveFila = !verClaveFila)}
                            title={verClaveFila ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
                            aria-label={verClaveFila
                              ? 'Ocultar la contraseña'
                              : 'Mostrar la contraseña'}
                          >
                            {#if verClaveFila}<EyeOff />{:else}<Eye />{/if}
                          </button>
                        </span>
                      {:else}
                        <span class="v2-table-primary">
                          {m.name}{#if m.is_you}<span class="v2-sub" style="font-weight:400">,
                              vos</span
                            >{/if}
                        </span>
                        <span class="v2-table-secondary" style="display:block">{m.email}</span>
                      {/if}
                    </span>
                  </span>
                </td>
                <td>
                  {#if editando === m.id}
                    <select
                      class="v2-input"
                      style="width:135px;font-size:12px;padding:2px 5px"
                      bind:value={borrador.area}
                      onchange={recargarAgentes}
                      aria-label="Área de {m.name}"
                    >
                      <option value="">Sin área</option>
                      {#each data.areasTrabajo ?? [] as a (a.nombre)}
                        <option value={a.nombre}>{a.etiqueta}</option>
                      {/each}
                    </select>
                  {:else}
                    {etiquetaArea(fila[m.id]?.area) || '—'}
                  {/if}
                </td>
                <td>
                  {#if editando === m.id}
                    <span style="display:flex;gap:7px;flex-wrap:wrap">
                      {#each data.areas ?? [] as agente (agente)}
                        <label style="font-size:11.5px;display:flex;align-items:center;gap:3px">
                          <input
                            type="checkbox"
                            checked={borrador.agentes.includes(agente)}
                            onchange={() => alternarAgente(agente)}
                          />
                          {agente}
                        </label>
                      {/each}
                    </span>
                  {:else if (fila[m.id]?.agentes ?? []).length}
                    <span style="display:flex;gap:4px;flex-wrap:wrap">
                      {#each fila[m.id].agentes as a (a)}
                        <Pill tone="slate">{a}</Pill>
                      {/each}
                    </span>
                  {:else}
                    <span class="v2-muted">—</span>
                  {/if}
                </td>
                {#if data.externos?.length}
                  <td>
                    {#if editando === m.id}
                      <select
                        class="v2-input"
                        style="width:150px;font-size:12px;padding:2px 5px"
                        bind:value={borrador.externo}
                        aria-label="Usuario externo de {m.name}"
                      >
                        <option value="">Sin vincular</option>
                        {#each data.externos as ex (ex.identificador)}
                          <option value={ex.identificador}>{ex.nombre_visible}</option>
                        {/each}
                      </select>
                    {:else}
                      <span class="v2-table-secondary"
                        >{data.identidades?.[m.id]?.nombre_visible || '—'}</span
                      >
                    {/if}
                  </td>
                {/if}
                <td data-m="tag">
                  {#if editando === m.id}
                    <select
                      class="v2-input"
                      style="width:120px;font-size:12px;padding:2px 5px"
                      bind:value={borrador.role}
                      disabled={m.role === 'ADMIN' && isLastAdmin}
                      aria-label="Rol de {m.name}"
                    >
                      <option value="USER">Miembro</option>
                      <option value="ADMIN">Administrador</option>
                    </select>
                  {:else}
                    <Pill tone={m.is_active ? ROLE_TONE[m.role] : 'slate'}>
                      {ROLE_LABEL[m.role]}
                    </Pill>
                  {/if}
                </td>
                <td>
                  {#if editando === m.id}
                    <select
                      class="v2-input"
                      style="width:105px;font-size:12px;padding:2px 5px"
                      bind:value={borrador.activo}
                      aria-label="Estado de {m.name}"
                    >
                      <option value={true}>Activo</option>
                      <option value={false}>Inactivo</option>
                    </select>
                  {:else}
                    <Pill tone={m.is_active ? 'moss' : 'slate'}>
                      {m.is_active ? 'Activo' : 'Inactivo'}
                    </Pill>
                    {#if m.is_active && !m.last_login}
                      <span class="v2-table-secondary" style="display:block">nunca entró</span>
                    {/if}
                  {/if}
                </td>
                <td data-m="hide">
                  {#if m.active_token_count}
                    <a
                      href="/settings/api-tokens"
                      style="display:inline-flex;gap:5px;align-items:center;color:{m.is_active
                        ? 'inherit'
                        : 'var(--v2-clay)'};font-weight:{m.is_active ? 400 : 600}"
                    >
                      <KeyRound size={13} />
                      <span class="v2-num">{m.active_token_count}</span>
                    </a>
                  {:else}
                    <span class="v2-muted">—</span>
                  {/if}
                </td>
                <td class="v2-r">
                  {#if editando === m.id}
                    <!-- Guardar y Cancelar NO estan aca: viven en la barra de
                         abajo. Estaban en esta celda y quedaban fuera de la
                         pantalla apenas la fila entraba en edicion -- los
                         campos la ensanchan, y .v2-table-wrap recorta con
                         overflow:hidden, asi que no habia siquiera scroll para
                         alcanzarlos. Se podia escribir una contraseña y no
                         tener como aplicarla ni como salir. -->
                    <span class="v2-muted" style="font-size:11.5px">editando</span>
                  {:else if m.is_you}
                    <!-- Sobre uno mismo tampoco se edita area ni agentes: es
                         el mismo criterio con el que el servidor no deja
                         cambiarse el propio rol. -->
                    <span class="v2-muted" style="font-size:11.5px">—</span>
                  {:else}
                    <span
                      style="display:inline-flex;gap:6px;justify-content:flex-end;flex-wrap:wrap"
                    >
                      <button
                        class="v2-btn v2-btn-sm ico"
                        disabled={busy || editando !== null}
                        onclick={() => editar(m)}
                        title="Editar a {m.name}"
                        aria-label="Editar a {m.name}"
                      >
                        <Pencil />
                      </button>
                      <!-- Role toggle. Two roles, so one button naming the
                           destination is clearer than a picker. The last admin
                           cannot be demoted; the server enforces it too. -->
                      <form method="POST" action="?/setRole" use:enhance={working}>
                        <input type="hidden" name="userId" value={m.user_id} />
                        <input
                          type="hidden"
                          name="role"
                          value={m.role === 'ADMIN' ? 'USER' : 'ADMIN'}
                        />
                        <button
                          class="v2-btn v2-btn-sm ico"
                          disabled={busy || (m.role === 'ADMIN' && isLastAdmin)}
                          title={m.role === 'ADMIN' && isLastAdmin
                            ? 'La organización debe mantener al menos un administrador'
                            : m.role === 'ADMIN'
                              ? `Quitarle el rol de administrador a ${m.name}`
                              : `Hacer administrador a ${m.name}`}
                          aria-label={m.role === 'ADMIN'
                            ? `Hacer miembro a ${m.name}`
                            : `Hacer administrador a ${m.name}`}
                        >
                          {#if m.role === 'ADMIN'}<ShieldMinus />{:else}<ShieldCheck />{/if}
                        </button>
                      </form>
                      <!-- Activate / deactivate. The last active admin cannot
                           be deactivated; the server refuses it with a 400. -->
                      <form method="POST" action="?/setStatus" use:enhance={working}>
                        <input type="hidden" name="userId" value={m.user_id} />
                        <input
                          type="hidden"
                          name="status"
                          value={m.is_active ? 'Inactive' : 'Active'}
                        />
                        <button
                          class="v2-btn v2-btn-sm ico"
                          disabled={busy || (m.is_active && isLastAdmin)}
                          title={m.is_active && isLastAdmin
                            ? 'La organización debe mantener al menos un administrador activo'
                            : m.is_active
                              ? `Desactivar a ${m.name}: deja de entrar y su trabajo pasa a su área`
                              : `Reactivar a ${m.name}`}
                          aria-label={m.is_active ? `Desactivar a ${m.name}` : `Reactivar a ${m.name}`}
                          style={m.is_active ? 'color:var(--v2-rust)' : ''}
                        >
                          {#if m.is_active}<UserX />{:else}<UserCheck />{/if}
                        </button>
                      </form>
                    </span>
                  {/if}
                </td>
              </tr>
              <!--
                LA BARRA DE ACCIONES, EN SU PROPIA FILA.

                Guardar y Cancelar vivian en la ultima celda. Con la fila en
                reposo entraban; en edicion no: los campos ensanchan la tabla y
                .v2-table-wrap recorta con overflow:hidden, asi que la columna
                "Gestionar" se iba de pantalla y no quedaba ni scroll para
                llegar. Alguien podia escribir una contraseña nueva y no tener
                donde aplicarla, ni como salir sin recargar la pagina.

                Una fila aparte con colspan empieza en el borde IZQUIERDO, que
                es el que nunca se recorta, y por eso se ve a cualquier ancho.
                El colspan sigue a la columna opcional del sistema externo: si
                se desfasa, el navegador desalinea la tabla entera.
              -->
              {#if editando === m.id}
                <tr>
                  <td
                    colspan={data.externos?.length ? 8 : 7}
                    style="padding-top:2px;background:var(--v2-line-soft)"
                  >
                    <form
                      method="POST"
                      action="?/actualizar"
                      use:enhance={edicionSubmit}
                      style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"
                    >
                      <input type="hidden" name="userId" value={m.user_id} />
                      <input type="hidden" name="profileId" value={m.id} />
                      <input type="hidden" name="name" value={borrador.name} />
                      <input type="hidden" name="email" value={borrador.email} />
                      <input type="hidden" name="role" value={borrador.role} />
                      <input type="hidden" name="activo" value={borrador.activo ? 'si' : 'no'} />
                      <input type="hidden" name="eraActivo" value={m.is_active ? 'si' : 'no'} />
                      <input type="hidden" name="area" value={borrador.area} />
                      <input type="hidden" name="externo" value={borrador.externo} />
                      <input type="hidden" name="password" value={borrador.password} />
                      <input
                        type="hidden"
                        name="externo_nombre"
                        value={nombreExternoDe(borrador.externo)}
                      />
                      {#each borrador.agentes as a (a)}
                        <input type="hidden" name="agentes" value={a} />
                      {/each}
                      <button class="v2-btn v2-btn-sm v2-btn-primary" disabled={guardandoFila}>
                        <Check />{guardandoFila ? 'Guardando…' : `Guardar a ${m.name}`}
                      </button>
                      <!-- Cancelar es TEXTO, no un icono como los de reposo: es
                           la salida de un estado con cambios sin guardar, y una
                           X chiquita pegada a un tilde chiquito se aprieta mal.
                           Lo compacto sirve para la fila en reposo; para
                           deshacer no. -->
                      <button
                        type="button"
                        class="v2-btn v2-btn-sm"
                        disabled={guardandoFila}
                        onclick={cancelar}
                      >
                        <X />Cancelar
                      </button>
                      <!-- Dicho donde se decide, no en la nota al pie. La
                           regla no es adivinable: un campo de clave en blanco
                           dentro de un formulario que guarda otras cosas puede
                           significar "borrala" tanto como "no la toques". -->
                      <span class="v2-sub" style="font-size:11.5px">
                        {borrador.password
                          ? 'Al guardar se le aplica la contraseña nueva.'
                          : 'Contraseña vacía: se le deja la que ya tiene.'}
                        Escape cancela.
                      </span>
                    </form>
                  </td>
                </tr>
              {/if}
            {/each}
          </tbody>
        </table>
      </div>

      <div class="v2-label" style="margin-bottom:10px">Equipos</div>
      <div class="v2-card" style="overflow:hidden;margin-bottom:14px">
        {#each data.teams as t (t.id)}
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>{t.name}</b>
              <span class="v2-sub" style="font-size:11.5px">{t.description}</span>
            </div>
            <span class="v2-sub v2-num" style="font-size:12px">
              {t.member_count}
              {t.member_count === 1 ? 'miembro' : 'miembros'}
            </span>
          </div>
        {:else}
          <div class="v2-setting">
            <span class="v2-sub" style="font-size:12px">Todavía no hay equipos.</span>
          </div>
        {/each}
      </div>

      <p class="v2-sub" style="font-size:11.5px">
        Los roles son Administrador y Miembro, los únicos dos que reconoce la API. Los
        administradores pueden invitar personas, cambiar roles y editar la configuración de la
        organización; el servidor no permite que nadie cambie su propio rol ni desactive al último
        administrador. La contraseña se puede definir al agregar a alguien y cambiar después desde
        Editar: dejarla vacía deja la que ya tenía, y el servidor rechaza las demasiado cortas o
        demasiado comunes. Cambiarla no cierra las sesiones que esa persona ya tenga abiertas ni
        revoca sus tokens de API: si la razón es que se filtró, desactivá la cuenta o revocá sus
        tokens además. Editar la membresía de los equipos todavía no está disponible acá.
      </p>
    </div>
  </div>
{/if}

<style>
  /*
    Boton de SOLO icono, para la columna "Gestionar".

    La columna tenia tres botones de texto por fila ("Editar", "Hacer
    administrador", "Desactivar") y ya en 1440px se partia en dos lineas: la
    fila quedaba del doble de alto y la accion destructiva caia debajo,
    desalineada respecto de la de al lado. Con iconos entran los tres en una
    linea y la tabla vuelve a leerse como una tabla.

    Lo que el icono no dice va en `title` y en `aria-label`, los dos, siempre:
    para el puntero y para un lector de pantalla. Un icono sin ninguna de las
    dos es una adivinanza, y estos tres cambian el acceso de una persona.

    El ancho es el mismo que el alto minimo de .v2-btn-sm (32px), asi que
    queda cuadrado sin fijar una altura propia que despues pelee con la regla
    de puntero grueso que los agranda para tocar.
  */
  .ico {
    width: 32px;
    min-width: 32px;
    padding: 0;
    justify-content: center;
  }
</style>
