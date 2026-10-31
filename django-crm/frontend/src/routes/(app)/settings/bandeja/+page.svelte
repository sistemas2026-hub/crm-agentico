<script>
  /**
   * Los dos números con los que la Bandeja se permite emitir un veredicto.
   *
   * POR QUE ESTA PANTALLA EXISTE
   * ----------------------------
   * Los dos valores ya se guardaban por tenant y se leían desde el motor, pero
   * sólo se podían cambiar por API. Eso los convertía en lo que la regla
   * multi-tenant del proyecto prohíbe: config que "sólo un desarrollador sabe
   * editar". La próxima empresa que se conecte no debería necesitar una sesión
   * de código para dos enteros.
   *
   * POR QUE MUESTRA LA CONSECUENCIA Y NO SOLO EL CAMPO
   * --------------------------------------------------
   * Un formulario de ajustes que enseña el campo pero no lo que provoca deja
   * el número como una adivinanza para siempre. Acá los dos tienen una
   * consecuencia concreta y verificable en el código:
   *
   *   plazo   -> `plazoDeToma()` devuelve null si el objetivo es 0, y entonces
   *              la fila de la cola no dibuja ningún chip de plazo.
   *   umbral  -> `NetworkPanel` deja `atenuado` en null sin umbral, y muestra
   *              la potencia cruda sin decir si está bien o mal.
   *
   * VACIO NO ES UN HUECO
   * --------------------
   * "Sin definir" es una respuesta legítima y es el default. Un umbral
   * inventado convierte una lectura correcta en un veredicto falso, y el valor
   * correcto depende del despliegue óptico de cada ISP. Por eso la pantalla no
   * empuja a completarlos ni marca su ausencia como advertencia.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import { Timer, Activity, PlugZap, Tag } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let editando = $state(false);
  let editandoRotulos = $state(false);

  /* Los rótulos de motivos, etiquetas y casos (29/10/2026). Las claves son
     identificadores y la Bandeja las mostraba sin tildes; acá cada empresa
     escribe cómo se leen. Vacío = se muestra la clave con espacios. */
  let r = $derived(data.rotulos);
  const FAMILIAS = [
    { id: 'motivos', titulo: 'Motivos de escalamiento' },
    { id: 'etiquetas', titulo: 'Etiquetas' },
    { id: 'casos', titulo: 'Casos' }
  ];
  const totalClaves = $derived(
    r ? FAMILIAS.reduce((n, f) => n + (r.claves?.[f.id]?.length ?? 0), 0) : 0
  );
  /* Las que faltan, las calcula el motor (editor.claves_sin_rotulo): la misma
     cuenta que avisa en Ajustes y al cargar el YAML. */
  const faltan = $derived(
    r ? FAMILIAS.flatMap((f) => r.sin_rotulo?.[f.id] ?? []) : []
  );
  const conRotulo = $derived(totalClaves - faltan.length);
  const comoClave = (/** @type {string} */ k) => k.replaceAll('_', ' ');

  let a = $derived(data.ajustes);

  const tieneSla = $derived(!!a && Number(a.sla_toma_minutos) > 0);
  const tieneUmbral = $derived(
    !!a && a.umbral_rx_dbm !== null && a.umbral_rx_dbm !== undefined
  );
  /* Guarda anti-limbo (26/09/2026): vacío = la banda "Sin resolución
     registrada" no existe. No se inventa un valor por defecto: se vería igual
     que uno decidido. */
  // El umbral guardado y el que de verdad usa la banda pueden diferir si el
  // par entró por el YAML (el editor lo rechaza). Mostrarlo es la diferencia
  // entre un operador que entiende la cola y uno que cree que el campo miente.
  const efectivoAcotado = $derived(
    !!a &&
      a.sin_gestion_horas !== null &&
      a.sin_gestion_horas !== undefined &&
      a.sin_gestion_horas_efectivas !== null &&
      a.sin_gestion_horas_efectivas !== undefined &&
      a.sin_gestion_horas_efectivas !== a.sin_gestion_horas
  );
  const tieneSinGestion = $derived(
    !!a && a.sin_gestion_horas !== null && a.sin_gestion_horas !== undefined
  );

  /* El plazo se guarda en minutos porque es lo que consume `plazoDeToma()`,
     pero 90 minutos se lee peor que "1 h 30 min". Se traduce sólo para
     mostrar; el campo sigue siendo minutos, que es lo que se edita. */
  function enHoras(minutos) {
    const m = Number(minutos) || 0;
    if (m < 60) return `${m} min`;
    const h = Math.floor(m / 60);
    const resto = m % 60;
    return resto === 0 ? `${h} h` : `${h} h ${resto} min`;
  }

  /* El aviso "por vencer" arranca en el último TERCIO, no en un porcentaje
     redondo. Se calcula acá para no repetir el número a mano: si `sla.js`
     cambia la fracción, esta línea queda mintiendo y hay que moverla igual --
     pero al menos dice de dónde sale. */
  const avisoDesde = $derived(
    tieneSla ? Math.round(Number(a.sla_toma_minutos) / 3) : 0
  );
</script>

<PageHeader title="Bandeja">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if !a}
      El asistente no respondió
    {:else if tieneSla && tieneUmbral}
      Plazo de toma {enHoras(a.sla_toma_minutos)} · umbral óptico {a.umbral_rx_dbm} dBm
    {:else if tieneSla}
      Plazo de toma {enHoras(a.sla_toma_minutos)} · sin umbral óptico
    {:else if tieneUmbral}
      Sin plazo de toma · umbral óptico {a.umbral_rx_dbm} dBm
    {:else}
      Sin plazo de toma y sin umbral óptico
    {/if}
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && a && !editando}
      <button class="v2-btn v2-btn-primary" onclick={() => (editando = true)}>
        Editar ajustes
      </button>
    {/if}
  {/snippet}
</PageHeader>

{#if !a}
  <!-- El motor es otro servicio. Que no conteste no es un error de esta
       pantalla ni algo que el operador pueda arreglar desde acá, así que se
       dice qué pasa y dónde mirar, sin ofrecer un formulario que no podría
       guardar nada. -->
  <div class="v2-scroll">
    <div class="v2-pad" style="padding-top:16px">
      <div class="v2-card" style="padding:16px">
        <p class="v2-sub" style="margin:0 0 6px">Sin conexión con el asistente</p>
        <p class="v2-hint" style="margin:0">
          Estos dos ajustes viven en la configuración del asistente, que es otro
          servicio. No se pudieron leer: o no está desplegado, o no está
          respondiendo. Los valores que ya tenga siguen vigentes — esta pantalla
          no los borró.
        </p>
      </div>
    </div>
  </div>
{:else}
  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard
        label="Plazo de toma"
        value={tieneSla ? enHoras(a.sla_toma_minutos) : 'Sin definir'}
        tone={tieneSla ? 'ink' : 'slate'}
        detail={tieneSla
          ? 'Una escalada sin dueño muestra cuánto le queda'
          : 'Las escaladas no muestran ningún plazo'}
      />
      <StatCard
        label="Umbral óptico"
        value={tieneUmbral ? `${a.umbral_rx_dbm} dBm` : 'Sin definir'}
        tone={tieneUmbral ? 'ink' : 'slate'}
        detail={tieneUmbral
          ? 'Debajo de este valor la potencia se marca como baja'
          : 'La potencia se muestra sin decir si está bien'}
      />
    </div>
  </div>

  <div class="v2-scroll">
    <div class="v2-pad" style="padding-bottom:32px">
      {#if editando}
        <SettingsFormPanel
          title="Ajustes de la Bandeja"
          action="?/update"
          error={form?.update?.error}
          submitLabel="Guardar ajustes"
          oncancel={() => (editando = false)}
          ondone={() => (editando = false)}
        >
          {#snippet fields()}
            <div class="v2-field">
              <label for="f-sla">Plazo de toma, en minutos</label>
              <input
                id="f-sla"
                class="v2-input"
                type="number"
                name="sla_toma_minutos"
                min="0"
                max="1440"
                step="1"
                placeholder="Sin definir"
                value={tieneSla ? a.sla_toma_minutos : ''}
              />
              <p class="v2-hint">
                Vacío o 0 significa que no hay plazo y la cola no muestra ninguna
                cuenta regresiva. Máximo 1440 (24 h).
              </p>
            </div>

            <div class="v2-field">
              <label for="f-umbral">Umbral óptico, en dBm</label>
              <input
                id="f-umbral"
                class="v2-input"
                type="number"
                name="umbral_rx_dbm"
                min="-40"
                max="0"
                step="0.1"
                placeholder="Sin definir"
                value={tieneUmbral ? a.umbral_rx_dbm : ''}
              />
              <p class="v2-hint">
                Negativo — la potencia recibida en GPON siempre lo es. Vacío
                significa que la Bandeja muestra la lectura sin emitir veredicto.
              </p>
            </div>

            <div class="v2-field">
              <label for="f-sin-gestion">Horas sin resolución registrada</label>
              <input
                id="f-sin-gestion"
                class="v2-input"
                type="number"
                name="sin_gestion_horas"
                min="1"
                max="720"
                step="1"
                placeholder="Sin definir"
                value={tieneSinGestion ? a.sin_gestion_horas : ''}
              />
              <p class="v2-hint">
                Una conversación que el asistente dejó sin derivar, sin escalar y
                sin caso, y en la que el cliente no volvió a escribir en estas
                horas, entra a la cola como «Sin resolución registrada» para que
                alguien la mire. Mientras esté ahí no se cierra sola por
                inactividad. Vacío significa que esa banda no existe.
              </p>
              {#if efectivoAcotado}
                <p class="v2-hint aviso-acotado">
                  Guardado: {a.sin_gestion_horas} h — pero la banda aparece a las
                  {a.sin_gestion_horas_efectivas} h, porque desde ahí el cierre por
                  inactividad deja de actuar y esperar más dejaría la conversación
                  sin cerrarse y sin verse. Guardá un valor de
                  {a.sin_gestion_horas_efectivas} h o menos para que lo que se
                  muestra sea lo que pasa.
                </p>
              {/if}
            </div>
          {/snippet}
        </SettingsFormPanel>
      {/if}

      <!-- ── CÓMO SE LEEN LOS MOTIVOS ───────────────────────────────────── -->
      {#if r}
        {#if editandoRotulos}
          <SettingsFormPanel
            title="Cómo se leen en la Bandeja"
            action="?/rotulos"
            error={form?.rotulos?.error}
            submitLabel="Guardar rótulos"
            oncancel={() => (editandoRotulos = false)}
            ondone={() => (editandoRotulos = false)}
          >
            {#snippet fields()}
              <!-- Cada familia ocupa TODO el ancho del panel, con sus propias dos
                   columnas adentro. Sueltos, los campos se repartían en la
                   grilla del panel fila por fila y las familias se mezclaban:
                   «Soporte técnico» quedaba debajo de los motivos y el
                   encabezado «Etiquetas» en la otra columna (29/10/2026). -->
              {#each FAMILIAS as f (f.id)}
                {#if r.claves?.[f.id]?.length}
                  <section class="v2-sfp-wide grupo-rotulos" aria-labelledby="fam-{f.id}">
                    <p class="familia" id="fam-{f.id}">{f.titulo}</p>
                    <div class="grupo-campos">
                      {#each r.claves[f.id] as k (k)}
                        <div class="v2-field fila-rotulo">
                          <label for="r-{f.id}-{k}" class="clave">{k}</label>
                          <input
                            id="r-{f.id}-{k}"
                            class="v2-input"
                            name="rotulo:{k}"
                            maxlength="60"
                            value={r.rotulos?.[k] ?? ''}
                            placeholder={comoClave(k)}
                          />
                        </div>
                      {/each}
                    </div>
                  </section>
                {/if}
              {/each}
              <p class="v2-hint v2-sfp-wide">
                Vacío: la Bandeja muestra la clave con espacios, como hasta ahora.
              </p>
            {/snippet}
          </SettingsFormPanel>
        {:else}
          <div class="v2-card rotulos-resumen">
            <p class="titulo"><Tag size={14} /> Cómo se leen los motivos, etiquetas y casos</p>
            <p class="cuerpo">
              {conRotulo} de {totalClaves} tienen un rótulo propio. El resto se muestra
              como su clave, sin tildes: «frustracion detectada» en vez de
              «Frustración detectada».
            </p>
            {#if faltan.length}
              <p class="cuerpo faltan">
                Sin rótulo: {#each faltan as k, i (k)}<code>{k}</code>{i < faltan.length - 1 ? ', ' : ''}{/each}
              </p>
            {/if}
            {#if data.can_edit}
              <button class="v2-btn v2-btn-sm" onclick={() => (editandoRotulos = true)}>
                Editar rótulos
              </button>
            {/if}
          </div>
        {/if}
      {/if}

      <!-- ── REINCIDENCIA ───────────────────────────────────────────────── -->
      {#if r}
        <form method="POST" action="?/reincidencia" class="v2-card rotulos-resumen">
          <p class="titulo"><Tag size={14} /> Aviso de reincidencia</p>
          <p class="cuerpo">
            La conversación muestra cuántas veces escribió ese número en los últimos días, y
            por qué: «3 en 30 días · Internet lento ×2». Es un dato, no un veredicto. 0 lo apaga.
          </p>
          <div class="fila-reincidencia">
            <label for="f-reincidencia">Días que mira</label>
            <input
              id="f-reincidencia"
              class="v2-input"
              type="number"
              name="reincidencia_dias"
              min="0"
              max="365"
              value={r.reincidencia_dias ?? 30}
              disabled={!data.can_edit}
            />
            {#if data.can_edit}
              <button class="v2-btn v2-btn-sm" type="submit">Guardar</button>
            {/if}
          </div>
          {#if form?.reincidencia?.error}<p class="v2-error">{form.reincidencia.error}</p>{/if}
          {#if form?.reincidenciaGuardada}<p class="v2-hint">Guardado.</p>{/if}
        </form>
      {/if}

      <!-- ── QUE HACE CADA UNO ──────────────────────────────────────────── -->
      <div class="v2-card explica">
        <div class="bloque">
          <p class="titulo"><Timer size={14} /> Plazo de toma</p>
          <p class="cuerpo">
            Cuánto puede esperar una conversación <b>escalada y sin dueño</b>
            antes de que alguien la tome. No se aplica a las que ya tienen dueño,
            ni a las que atiende la IA, ni a las cerradas: en esos casos no hay
            nadie a quien apurar.
          </p>
          {#if tieneSla}
            <p class="cuerpo">
              Con {enHoras(a.sla_toma_minutos)}, la fila muestra cuánto queda;
              en los últimos <b>{enHoras(avisoDesde)}</b> el chip pasa a aviso, y
              cumplido el plazo dice <b>Vencido</b> y sigue contando hacia arriba.
            </p>
          {:else}
            <p class="cuerpo apagado">
              Hoy está sin definir: ninguna conversación muestra plazo. Es un
              default deliberado — un plazo inventado convierte en urgente algo
              que la empresa nunca decidió que lo fuera.
            </p>
          {/if}
        </div>

        <div class="bloque">
          <p class="titulo"><Activity size={14} /> Umbral óptico</p>
          <p class="cuerpo">
            La potencia RX por debajo de la cual la Bandeja afirma que la señal
            está baja. Lo usa la pestaña <b>Red</b> al leer la ONU del cliente.
          </p>
          {#if tieneUmbral}
            <p class="cuerpo">
              Con {a.umbral_rx_dbm} dBm, una lectura peor se marca en rojo como
              atenuada; una mejor, en verde. El número medido se muestra siempre,
              con umbral o sin él.
            </p>
          {:else}
            <p class="cuerpo apagado">
              Hoy está sin definir: la potencia se muestra tal como la devuelve
              SmartOLT, sin decir si está bien o mal. El valor correcto depende
              del despliegue óptico de cada red, y uno inventado convertiría una
              lectura correcta en un veredicto falso.
            </p>
          {/if}
        </div>

        <div class="bloque">
          <p class="titulo"><PlugZap size={14} /> Dónde se guardan</p>
          <p class="cuerpo">
            En la configuración de esta empresa, no en el código. Cada empresa
            conectada tiene los suyos, y cambiarlos acá no afecta a ninguna otra.
          </p>
        </div>
      </div>

      {#if !data.can_edit}
        <p class="v2-hint" style="margin-top:12px">
          Sólo un administrador puede cambiar estos valores.
        </p>
      {/if}
    </div>
  </div>
{/if}

<style>
  /* El umbral guardado y el efectivo difieren: es un aviso, no una ayuda. */
  .aviso-acotado {
    border-left: 3px solid var(--v2-clay);
    padding-left: 10px;
    margin-top: 8px;
  }

  .rotulos-resumen {
    padding: 16px;
    margin-top: 16px;
  }
  .fila-reincidencia {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .fila-reincidencia input {
    width: 6rem;
  }
  .faltan code {
    font-family: var(--v2-mono, ui-monospace, monospace);
    font-size: 11.5px;
  }
  .familia {
    margin: 8px 0 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--v2-slate);
  }
  .grupo-campos {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 24px;
  }
  .fila-rotulo {
    display: grid;
    grid-template-columns: minmax(0, 12rem) minmax(0, 1fr);
    align-items: center;
    gap: 12px;
  }
  .clave {
    font-family: var(--v2-mono, ui-monospace, monospace);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  @media (max-width: 640px) {
    .grupo-campos {
      grid-template-columns: 1fr;
    }
    .fila-rotulo {
      grid-template-columns: 1fr;
      gap: 4px;
    }
  }

  .explica {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-top: 16px;
  }
  .bloque + .bloque {
    padding-top: 16px;
    border-top: 1px solid var(--v2-line-soft);
  }
  .titulo {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0 0 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--v2-ink);
  }
  /* `--v2-ink` y `--v2-slate` son los dos tokens de texto que v2.css define de
     verdad. Se comprobó: no existen `--v2-ink-soft` ni `--v2-muted`, y usarlos
     con fallback habría pintado siempre por fuera del sistema de tokens sin
     que se notara. */
  .cuerpo {
    margin: 0 0 6px;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--v2-ink);
  }
  .cuerpo:last-child {
    margin-bottom: 0;
  }
  /* Lo que está sin definir se explica igual, pero no se grita: no es una
     falta que haya que ir a corregir. */
  .apagado {
    color: var(--v2-slate);
  }
</style>
