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
  import { Timer, Activity, PlugZap } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let editando = $state(false);

  let a = $derived(data.ajustes);

  const tieneSla = $derived(!!a && Number(a.sla_toma_minutos) > 0);
  const tieneUmbral = $derived(
    !!a && a.umbral_rx_dbm !== null && a.umbral_rx_dbm !== undefined
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
          {/snippet}
        </SettingsFormPanel>
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
