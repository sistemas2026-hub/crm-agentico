<script>
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeTime } from '$lib/v2/format.js';
  import { MessagesSquare, TriangleAlert } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let conversaciones = $derived(data.conversaciones ?? []);

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (c) => CANAL_LABEL[c] ?? c;
  const canalTone = (c) => (c === 'whatsapp' ? 'moss' : 'slate');
  const estadoTone = (e) => (e === 'abierta' ? 'clay' : 'slate');

  // Un color por etiqueta, no toda la taxonomia hardcodeada -- si el tenant
  // agrega una categoria nueva en conversaciones.etiquetas, cae en 'ink' en
  // vez de romper.
  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');
</script>

<PageHeader title="Conversaciones">
  {#snippet sub()}
    Todos los chats con clientes finales -- WhatsApp real y el simulador de prueba.
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  {#if data.error}
    <div class="v2-pad">
      <EmptyState title="No se pudo cargar la bandeja" body={data.error}>
        {#snippet icon()}<TriangleAlert size={21} />{/snippet}
      </EmptyState>
    </div>
  {:else if conversaciones.length === 0}
    <EmptyState
      title="Todavía no hay conversaciones"
      body="Acá van a aparecer los chats de WhatsApp con tus clientes. Mientras tanto, probá el Simulador de WhatsApp para ver cómo se vería uno."
    >
      {#snippet icon()}<MessagesSquare size={21} />{/snippet}
    </EmptyState>
  {:else}
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <th>Cliente</th>
            <th>Canal</th>
            <th>Estado</th>
            <th>Etiqueta</th>
            <th>Escalada</th>
            <th>Última actividad</th>
          </tr>
        </thead>
        <tbody>
          {#each conversaciones as c (c.id)}
            <tr>
              <td>
                <a class="v2-row-link" href="/conversaciones/{c.id}">
                  <div class="v2-table-primary">{c.usuario_externo}</div>
                  {#if c.rol_efectivo}
                    <div class="v2-table-secondary">{c.rol_efectivo}</div>
                  {/if}
                </a>
              </td>
              <td data-m="tag"><Pill tone={canalTone(c.canal)}>{canalLabel(c.canal)}</Pill></td>
              <td data-m="tag"><Pill tone={estadoTone(c.estado)}>{c.estado}</Pill></td>
              <td data-m="tag">
                {#if c.etiqueta}
                  <Pill tone={etiquetaTone(c.etiqueta)}>{etiquetaLabel(c.etiqueta)}</Pill>
                {:else}
                  <span class="v2-muted">—</span>
                {/if}
              </td>
              <td data-m="hide">
                {#if c.escalada_a_humano}
                  <span title={c.motivo_escalamiento || 'Escalada a un humano'}>
                    <TriangleAlert size={16} style="color:var(--v2-rust)" />
                  </span>
                {:else}
                  <span class="v2-muted">—</span>
                {/if}
              </td>
              <td class="v2-muted">{relativeTime(c.actualizado_en)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{conversaciones.length}</span>
    </p>
  {/if}
</div>
