<script>
  import { goto } from '$app/navigation';
  import { Button } from '$lib/components/ui/button/index.js';
  import { ArrowLeft, Home, Compass, Users, FileText, Ticket, BarChart3 } from '@lucide/svelte';

  /**
   * @typedef {Object} Props
   * @property {number} [status]   HTTP status code
   * @property {string} [message]  Error message from the server (optional)
   * @property {boolean} [showQuickLinks]  Show the "Try one of these" panel (default true for 404)
   */

  /** @type {Props} */
  let { status = 404, message = '', showQuickLinks } = $props();

  let isNotFound = $derived(status === 404);
  let showLinks = $derived(showQuickLinks ?? isNotFound);

  let title = $derived.by(() => {
    if (isNotFound) return 'Página no encontrada';
    if (status === 403) return 'No tenés acceso a esta página';
    if (status === 401) return 'Por favor iniciá sesión para continuar';
    if (status >= 500) return 'Algo salió mal';
    return 'No se pudo abrir esta página';
  });

  let description = $derived.by(() => {
    if (message) return message;
    if (isNotFound) return 'La página que buscás no existe o puede haberse movido.';
    if (status === 403) return 'Tu cuenta no tiene permiso para ver este recurso.';
    if (status === 401) return 'Tu sesión puede haber vencido. Iniciá sesión de nuevo para continuar.';
    if (status >= 500)
      return 'Ocurrió un error inesperado de nuestro lado. Ya nos enteramos. Por favor intentá de nuevo en un momento.';
    return 'Por favor revisá la URL o intentá volver a donde estabas.';
  });

  const quickLinks = [
    { href: '/', label: 'Panel', icon: BarChart3 },
    { href: '/leads', label: 'Prospectos', icon: Users },
    { href: '/contacts', label: 'Contactos', icon: Users },
    { href: '/tickets', label: 'Tickets', icon: Ticket },
    { href: '/tasks', label: 'Tareas', icon: FileText }
  ];

  function goBack() {
    if (typeof history !== 'undefined' && history.length > 1) history.back();
    else goto('/');
  }
</script>

<div class="flex min-h-[80vh] w-full items-center justify-center px-6 py-16">
  <div class="w-full max-w-xl text-center">
    <!-- Stylized status code -->
    <div class="relative mb-6 flex items-center justify-center">
      <div
        class="bg-primary/10 absolute inset-0 mx-auto h-32 w-32 rounded-full blur-3xl"
        aria-hidden="true"
      ></div>
      <div class="relative">
        <span
          class="text-primary block text-[7rem] leading-none font-bold tracking-tighter md:text-[9rem]"
          style="font-feature-settings: 'tnum';"
        >
          {status}
        </span>
      </div>
    </div>

    <!-- Headline + supporting copy -->
    <h1 class="text-foreground mb-3 text-2xl font-semibold tracking-tight md:text-3xl">
      {title}
    </h1>
    <p class="text-muted-foreground mx-auto mb-8 max-w-md text-base leading-relaxed">
      {description}
    </p>

    <!-- Primary actions -->
    <div class="flex flex-col items-center justify-center gap-3 sm:flex-row">
      <Button onclick={() => goto('/')} class="gap-2">
        <Home class="h-4 w-4" />
        Ir al panel
      </Button>
      <Button variant="outline" onclick={goBack} class="gap-2">
        <ArrowLeft class="h-4 w-4" />
        Volver
      </Button>
    </div>

    <!-- Quick links (404 only by default) -->
    {#if showLinks}
      <div class="mt-12">
        <div class="mb-4 flex items-center justify-center gap-2">
          <Compass class="text-muted-foreground h-4 w-4" />
          <span class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Probá alguno de estos
          </span>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-2">
          {#each quickLinks as link (link.href)}
            <a
              href={link.href}
              class="border-border/60 bg-background hover:border-primary/40 hover:bg-accent hover:text-foreground text-muted-foreground inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors"
            >
              <link.icon class="h-3.5 w-3.5" />
              {link.label}
            </a>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</div>
