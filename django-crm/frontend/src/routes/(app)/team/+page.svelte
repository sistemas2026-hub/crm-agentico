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
  import { UserPlus, KeyRound } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  import { toast } from 'svelte-sonner';

  let { data, form } = $props();

  let inviting = $state(false);
  let externoElegido = $state('');
  let areaElegida = $state('');

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
  let borrador = $state({ area: '', agentes: /** @type {string[]} */ ([]), externo: '' });
  let guardandoFila = $state(false);

  const etiquetaArea = (/** @type {string} */ nombre) =>
    data.areasTrabajo?.find((/** @type {any} */ a) => a.nombre === nombre)?.etiqueta ?? '';

  function editar(/** @type {string} */ id) {
    editando = id;
    borrador = { ...fila[id], agentes: [...(fila[id]?.agentes ?? [])] };
  }

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

  async function guardarFila(/** @type {string} */ id, /** @type {string} */ nombre) {
    guardandoFila = true;
    try {
      const nombreExt =
        data.externos?.find((/** @type {any} */ e) => e.identificador === borrador.externo)
          ?.nombre_visible ?? '';
      const resp = await fetch(`/api/agentes/asignaciones/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          area: borrador.area,
          roles: borrador.agentes,
          identidad_externa: { identificador: borrador.externo, nombre_visible: nombreExt }
        })
      });
      const d = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        toast.error(d?.error || 'No se pudo guardar');
        return;
      }
      // La pantalla refleja lo que el servidor CONFIRMO, no lo que se pidio.
      fila = { ...fila, [id]: { ...borrador, agentes: d.roles ?? borrador.agentes } };
      editando = null;
      toast.success(`${nombre}: guardado.`);
    } finally {
      guardandoFila = false;
    }
  }
</script>

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
                      <span class="v2-table-primary">
                        {m.name}{#if m.is_you}<span class="v2-sub" style="font-weight:400">,
                            vos</span
                          >{/if}
                      </span>
                      <span class="v2-table-secondary" style="display:block">{m.email}</span>
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
                  <Pill tone={m.is_active ? ROLE_TONE[m.role] : 'slate'}>{ROLE_LABEL[m.role]}</Pill>
                </td>
                <td>
                  <Pill tone={m.is_active ? 'moss' : 'slate'}>
                    {m.is_active ? 'Activo' : 'Inactivo'}
                  </Pill>
                  {#if m.is_active && !m.last_login}
                    <span class="v2-table-secondary" style="display:block">nunca entró</span>
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
                    <!-- En edicion, la fila ofrece SOLO guardar o cancelar.
                         Dejar los otros botones activos invita a cambiarle el
                         rol a alguien con un borrador a medio hacer. -->
                    <span style="display:inline-flex;gap:6px;justify-content:flex-end">
                      <button
                        class="v2-btn v2-btn-sm v2-btn-primary"
                        disabled={guardandoFila}
                        onclick={() => guardarFila(m.id, m.name)}
                      >
                        Guardar
                      </button>
                      <button class="v2-btn v2-btn-sm" disabled={guardandoFila} onclick={cancelar}>
                        Cancelar
                      </button>
                    </span>
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
                        class="v2-btn v2-btn-sm"
                        disabled={busy || editando !== null}
                        onclick={() => editar(m.id)}
                      >
                        Editar
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
                          class="v2-btn v2-btn-sm"
                          disabled={busy || (m.role === 'ADMIN' && isLastAdmin)}
                          title={m.role === 'ADMIN' && isLastAdmin
                            ? 'La organización debe mantener al menos un administrador'
                            : ''}
                        >
                          {m.role === 'ADMIN' ? 'Hacer miembro' : 'Hacer administrador'}
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
                          class="v2-btn v2-btn-sm"
                          disabled={busy || (m.is_active && isLastAdmin)}
                          title={m.is_active && isLastAdmin
                            ? 'La organización debe mantener al menos un administrador activo'
                            : ''}
                          style={m.is_active ? 'color:var(--v2-rust)' : ''}
                        >
                          {m.is_active ? 'Desactivar' : 'Reactivar'}
                        </button>
                      </form>
                    </span>
                  {/if}
                </td>
              </tr>
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
        administrador. Editar la membresía de los equipos todavía no está disponible acá.
      </p>
    </div>
  </div>
{/if}
