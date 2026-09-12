<script>
  /**
   * The calendar every response target is measured against.
   *
   * This page is small but it is the reason "answered in 4h" means anything.
   * A ticket opened at 17:20 on Friday and answered at 09:10 on Monday is
   * either fifteen hours late or fifty minutes early, and only this calendar
   * decides which. v1 hid it three levels into a settings dropdown, so the
   * analytics page reported numbers nobody could interpret.
   *
   * Closed days and holidays are shown, not omitted. A blank row for Saturday
   * reads as missing data; "Closed" reads as a decision.
   *
   * "Edit hours" and "Add" open the two panels below. `data.can_edit` only
   * decides whether those controls are offered: it is a display hint decoded
   * from the JWT, never the authorization decision. The backend re-derives
   * admin status from `request.profile` on every write and is what actually
   * refuses a non-admin.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import ConfirmAction from '$lib/v2/components/ConfirmAction.svelte';
  import { shortDate, relativeDays } from '$lib/v2/format.js';
  import { Plus, Clock } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let calendar = $derived(data.calendar);

  /** Hours a day is open, for the weekly total. */
  function hours(d) {
    if (!d.open || !d.close) return 0;
    const [oh, om] = d.open.split(':').map(Number);
    const [ch, cm] = d.close.split(':').map(Number);
    return (ch * 60 + cm - (oh * 60 + om)) / 60;
  }

  let weekly = $derived(calendar.days.reduce((a, d) => a + hours(d), 0));
  const todayName = new Intl.DateTimeFormat('en-GB', { weekday: 'long' }).format(new Date());

  // Display only. `d.day`/`row.day` stay the English weekday name from the
  // server (`business-hours.js`'s `WEEKDAYS`), because `key: d.day.toLowerCase()`
  // below derives the wire field prefix from it and `d.day === todayName` compares
  // it against `Intl.DateTimeFormat('en-GB', …)`. Translating the data itself
  // would break both; this only relabels what is shown.
  const DAY_LABEL = {
    Monday: 'Lunes',
    Tuesday: 'Martes',
    Wednesday: 'Miércoles',
    Thursday: 'Jueves',
    Friday: 'Viernes',
    Saturday: 'Sábado',
    Sunday: 'Domingo'
  };

  // `null` when the panel is closed. One panel for the week, so only one
  // edit can be in flight at a time.
  let editingHours = $state(false);

  // The week being edited, seeded from `calendar.days` when the panel opens.
  // A day's key is its own name lower-cased ("Monday" → "monday"), the same
  // prefix the model's fourteen flat fields use, so no separate label map is
  // needed here. `closed` drives both the checkbox and whether the two time
  // inputs are disabled; a closed day still carries a sensible default time
  // so re-opening it doesn't hand back a blank field.
  let hourRows = $state(
    /** @type {{ day: string, key: string, open: string, close: string, closed: boolean }[]} */ ([])
  );

  function openHoursEdit() {
    hourRows = calendar.days.map((d) => ({
      day: d.day,
      key: d.day.toLowerCase(),
      open: d.open ?? '09:00',
      close: d.close ?? '17:00',
      closed: !d.open
    }));
    editingHours = true;
  }

  // `null` when the panel is closed.
  let addingHoliday = $state(false);
</script>

<PageHeader title="Horario laboral">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {calendar.name} · {calendar.timezone} ·
    <span class="v2-num">{weekly}</span> horas semanales
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && !editingHours}
      <button class="v2-btn v2-btn-primary" onclick={openHoursEdit}>Editar horario</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:18px;padding-bottom:32px">
    <div class="v2-split">
      <div>
        <div class="v2-label" style="margin-bottom:10px">Horario de apertura</div>

        {#if editingHours}
          <SettingsFormPanel
            title="Editar horario laboral"
            action="?/updateHours"
            error={form?.updateHours?.error}
            submitLabel="Guardar horario"
            oncancel={() => (editingHours = false)}
            ondone={() => (editingHours = false)}
          >
            {#snippet fields()}
              <div class="v2-field">
                <label for="bh-name">Nombre</label>
                <input
                  id="bh-name"
                  class="v2-input"
                  name="name"
                  maxlength="100"
                  required
                  value={calendar.name}
                />
              </div>

              <div class="v2-field">
                <label for="bh-timezone">Zona horaria</label>
                <input
                  id="bh-timezone"
                  class="v2-input"
                  name="timezone"
                  maxlength="64"
                  required
                  value={calendar.timezone}
                  placeholder="America/New_York"
                />
                <p class="v2-hint">Nombre de zona horaria IANA.</p>
              </div>

              <div class="v2-field v2-sfp-wide">
                <label for="bh-day-0-open">Semana</label>
                {#each hourRows as row, i (row.key)}
                  <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">
                    <span style="width:84px;font-size:13px;flex:none">{DAY_LABEL[row.day] ?? row.day}</span>
                    <label
                      style="display:flex;gap:6px;align-items:center;font-size:12px;font-weight:400;flex:none"
                    >
                      <input
                        type="checkbox"
                        name="{row.key}_closed"
                        value="true"
                        bind:checked={row.closed}
                      />
                      Cerrado
                    </label>
                    <input
                      id={i === 0 ? 'bh-day-0-open' : undefined}
                      class="v2-input"
                      type="time"
                      name="{row.key}_open"
                      bind:value={row.open}
                      disabled={row.closed}
                      style="width:auto"
                    />
                    <span class="v2-sub">a</span>
                    <input
                      class="v2-input"
                      type="time"
                      name="{row.key}_close"
                      bind:value={row.close}
                      disabled={row.closed}
                      style="width:auto"
                    />
                  </div>
                {/each}
              </div>
            {/snippet}
          </SettingsFormPanel>
        {/if}

        <div class="v2-card" style="overflow:hidden">
          {#each calendar.days as d (d.day)}
            <div class="v2-setting" style={d.day === todayName ? 'background:var(--v2-hover)' : ''}>
              <div class="v2-setting-body">
                <b>{DAY_LABEL[d.day] ?? d.day}</b>
                {#if d.day === todayName}
                  <span class="v2-sub" style="font-size:11px">hoy</span>
                {/if}
              </div>
              {#if d.open && d.close}
                <span class="v2-num" style="font-size:13px">{d.open} - {d.close}</span>
              {:else}
                <!-- Named, not blank. A blank cell reads as missing data. -->
                <span class="v2-sub" style="font-size:12.5px">Cerrado</span>
              {/if}
            </div>
          {/each}
        </div>

        {#if calendar.is_default}
          <p class="v2-sub" style="font-size:11.5px;margin-top:11px">
            Este es el calendario por defecto, así que aplica a todo ticket que no tenga uno más
            específico.
          </p>
        {/if}
      </div>

      <div>
        <div style="display:flex;align-items:baseline;margin-bottom:10px">
          <div class="v2-label">Feriados</div>
          {#if data.can_edit && !addingHoliday}
            <button
              class="v2-btn v2-btn-sm"
              style="margin-left:auto"
              onclick={() => (addingHoliday = true)}
            >
              <Plus size={12} />Agregar
            </button>
          {/if}
        </div>

        {#if addingHoliday}
          <SettingsFormPanel
            title="Agregar feriado"
            action="?/addHoliday"
            error={form?.addHoliday?.error}
            submitLabel="Agregar feriado"
            oncancel={() => (addingHoliday = false)}
            ondone={() => (addingHoliday = false)}
          >
            {#snippet fields()}
              <div class="v2-field">
                <label for="bh-holiday-date">Fecha</label>
                <input id="bh-holiday-date" class="v2-input" type="date" name="date" required />
              </div>
              <div class="v2-field">
                <label for="bh-holiday-name">Nombre</label>
                <input
                  id="bh-holiday-name"
                  class="v2-input"
                  name="name"
                  maxlength="100"
                  required
                  placeholder="Navidad"
                />
              </div>
            {/snippet}
          </SettingsFormPanel>
        {/if}

        {#if form?.removeHoliday?.error}
          <p class="v2-error" style="margin-bottom:12px">{form.removeHoliday.error}</p>
        {/if}

        <div class="v2-card" style="overflow:hidden">
          {#each calendar.holidays as h (h.id)}
            <div class="v2-setting">
              <div class="v2-setting-body">
                <b>{h.name}</b>
                <span class="v2-sub" style="font-size:11.5px">{relativeDays(h.date)}</span>
              </div>
              <span class="v2-num" style="font-size:12.5px">{shortDate(h.date)}</span>
              {#if data.can_edit}
                <ConfirmAction
                  action="?/removeHoliday"
                  label="Quitar"
                  confirmLabel="Quitar"
                  explain="Lo elimina. El día vuelve a contar como tiempo laboral."
                  hidden={{ holiday_id: h.id }}
                />
              {/if}
            </div>
          {:else}
            <p class="v2-sub" style="padding:14px 16px;font-size:12.5px;margin:0">
              No hay feriados configurados. Los objetivos van a seguir corriendo en los feriados.
            </p>
          {/each}
        </div>

        <div
          style="display:flex;gap:10px;align-items:flex-start;margin-top:18px;padding:14px 16px;border:1px solid var(--v2-line);border-radius:var(--v2-radius)"
        >
          <Clock size={16} style="color:var(--v2-slate);flex:none;margin-top:1px" />
          <div>
            <div style="font-weight:600;font-size:13px">Qué cambia esto</div>
            <p class="v2-sub" style="font-size:12px;margin:4px 0 0">
              Los objetivos de respuesta y resolución solo cuentan el tiempo dentro de este
              horario. Un ticket abierto a las 17:20 del viernes
              {#if calendar.days[0].open}
                arranca su reloj a las <span class="v2-num">{calendar.days[0].open}</span> del
                lunes,
              {:else}
                <!-- Monday can be marked closed from this page now, so the
                     fixed "Monday morning" framing can no longer assume an
                     open time exists to quote. -->
                arranca su reloj cuando vuelva a abrir la semana,
              {/if}
              así el fin de semana no consume un objetivo de cuatro horas.
            </p>
            <p class="v2-sub" style="font-size:12px;margin:8px 0 0">
              <a href="/tickets/analytics" style="color:inherit">Analítica de servicio</a> se mide con
              este calendario.
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
