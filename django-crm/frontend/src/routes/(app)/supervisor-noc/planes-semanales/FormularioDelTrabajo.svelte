<script>
  /**
   * Lo que llenó el técnico: el formulario del trabajo y las fotos del
   * checklist (18/10/2026).
   *
   * Se guardaban y la ficha de la orden solo contaba «Evidencias: N». El
   * backend lo manda ya leído con la plantilla —título, «Otro» con su texto,
   * qué falta— dentro de la bitácora (`formulario_del_trabajo`): acá se
   * dibuja, no se interpreta. Las fotos de un reporte no están: ya se ven
   * dentro de ese reporte, en la línea de tiempo.
   *
   * Vive aparte de la página para poder dibujarlo en una prueba: la página
   * importa `$app/*`, que el entorno de pruebas no resuelve.
   */
  /** @type {{ form: { campos?: any[], fotos?: any[] } }} */
  let { form } = $props();
</script>

<div class="snoc-pila-xs">
  <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">
    Lo que llenó el técnico
  </span>
  {#if !(form.campos ?? []).length && !(form.fotos ?? []).length}
    <p class="snoc-body-sm snoc-tenue" style="margin:0;">
      Este tipo de trabajo no pide formulario ni fotos.
    </p>
  {/if}
  {#if (form.campos ?? []).length}
    <div class="snoc-meta">
      {#each form.campos as c (c.id)}
        <div>
          <span>{c.titulo}:</span>
          {#if c.sin_responder}
            <span class="snoc-body-sm {c.obligatorio ? 'snoc-error-txt' : 'snoc-tenue'}">
              {c.obligatorio ? 'Sin responder · obligatorio' : 'Sin responder'}
            </span>
          {:else}
            <span class="snoc-body-sm">
              {c.valor === true ? 'Sí' : c.valor === false ? 'No' : c.valor}
              {#if c.fuera_de_la_plantilla}
                <span class="snoc-tenue">(de una plantilla anterior)</span>
              {/if}
            </span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
  {#each form.fotos ?? [] as r (r.requisito_id)}
    <div class="snoc-pila-xs">
      <span class="snoc-body-sm">
        {r.titulo}
        {#if r.obligatorio}<span class="snoc-tenue">· obligatoria</span>{/if}
      </span>
      {#if r.sin_foto && !(r.fotos ?? []).length}
        <span class="snoc-body-sm {r.obligatorio ? 'snoc-error-txt' : 'snoc-tenue'}">
          Sin foto
        </span>
      {/if}
      {#if (r.fotos ?? []).length}
        <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
          {#each r.fotos as f (f.id)}
            {#if f.disponible}
              <a href={`/api/supervisor-noc/evidencias/${f.id}/archivo`} target="_blank"
                 rel="noopener" title="Abrir la foto">
                <img src={`/api/supervisor-noc/evidencias/${f.id}/archivo`}
                     alt={r.titulo}
                     loading="lazy"
                     style="width:96px; height:96px; object-fit:cover; border-radius:6px; border:1px solid var(--snoc-outline-variant);" />
              </a>
            {:else}
              <span class="snoc-body-sm snoc-tenue">Una foto todavía se está subiendo.</span>
            {/if}
          {/each}
        </div>
      {/if}
    </div>
  {/each}
</div>
