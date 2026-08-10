<script>
  import '../../../app.css';
  import '$lib/v2/styles/v2.css';
  import { enhance } from '$app/forms';

  import imgGoogle from '$lib/assets/images/google.svg';
  import imgLogo from '$lib/assets/images/logo.png';
  import { Mail, Check } from '@lucide/svelte';

  let { data = {} } = $props();

  let isLoading = $state(false);
  let email = $state('');
  let magicLinkSent = $state(false);
  let isSendingLink = $state(false);
  let magicLinkError = $state('');

  let passwordEmail = $state('');
  let password = $state('');
  let isSigningIn = $state(false);
  let passwordError = $state('');

  function handleGoogleLogin() {
    isLoading = true;
  }

  function handlePasswordLogin() {
    isSigningIn = true;
    passwordError = '';
    return async ({ result, update }) => {
      isSigningIn = false;
      if (result?.type === 'failure') {
        passwordError = result.data?.error || 'Correo o contraseña incorrectos.';
      } else {
        // 'success' here is the server redirecting to /org; 'redirect' if
        // SvelteKit already followed it. Either way there is nothing local
        // left to update -- but call it anyway for the case that isn't.
        await update();
      }
    };
  }

  function handleMagicLink() {
    isSendingLink = true;
    magicLinkError = '';
    return async ({ result }) => {
      isSendingLink = false;
      if (result?.type === 'success') {
        magicLinkSent = true;
      } else if (result?.type === 'failure') {
        magicLinkError = result.data?.error || 'Algo salió mal. Probá de nuevo.';
      } else if (!result) {
        magicLinkError = 'Algo salió mal. Probá de nuevo.';
      }
    };
  }
</script>

<svelte:head>
  <title>Iniciar sesión · BottleCRM</title>
  <meta
    name="description"
    content="Iniciá sesión en BottleCRM para gestionar tus contactos, negociaciones y hacer crecer tu negocio."
  />
</svelte:head>

<div class="v2-root v2-auth">
  <div class="v2-auth-box">
    <a href="/" class="v2-auth-brand">
      <img src={imgLogo} alt="" />
      <b>BottleCRM</b>
    </a>

    <div class="v2-auth-card">
      <div class="v2-auth-head">
        <h1>Iniciar sesión</h1>
        <p>Bienvenido de nuevo. Elegí cómo querés continuar.</p>
      </div>

      <!-- Primary path. Google's mark keeps a white tile so it stays legible on
           Ember; the whole button is the one Ember action on this screen. -->
      <a
        href={data['google_url']}
        onclick={handleGoogleLogin}
        class="v2-btn v2-btn-primary v2-btn-block"
        style:pointer-events={isLoading ? 'none' : null}
        style:opacity={isLoading ? '0.85' : null}
      >
        {#if isLoading}
          <span class="v2-spin"></span>
          <span>Redirigiendo…</span>
        {:else}
          <img src={imgGoogle} alt="" class="v2-auth-gicon" />
          <span>Continuar con Google</span>
        {/if}
      </a>

      <div class="v2-auth-divider">o</div>

      <form
        method="POST"
        action="?/password"
        use:enhance={handlePasswordLogin}
        style="display:flex;flex-direction:column;gap:9px"
      >
        <label for="password-email" class="v2-sr-only">Correo electrónico</label>
        <input
          id="password-email"
          type="email"
          name="email"
          class="v2-input"
          placeholder="vos@empresa.com"
          required
          bind:value={passwordEmail}
          disabled={isSigningIn}
        />
        <label for="password" class="v2-sr-only">Contraseña</label>
        <input
          id="password"
          type="password"
          name="password"
          class="v2-input"
          placeholder="Contraseña"
          required
          bind:value={password}
          disabled={isSigningIn}
        />
        <button type="submit" class="v2-btn v2-btn-primary v2-btn-block" disabled={isSigningIn}>
          {#if isSigningIn}
            <span class="v2-spin"></span>
            <span>Iniciando sesión…</span>
          {:else}
            <span>Iniciar sesión</span>
          {/if}
        </button>
        {#if passwordError}
          <div class="v2-auth-note v2-auth-note-bad">
            <span>{passwordError}</span>
          </div>
        {/if}
      </form>

      <div class="v2-auth-divider">o</div>

      {#if magicLinkSent}
        <div class="v2-auth-note v2-auth-note-ok">
          <Check />
          <div>
            <b>Revisá tu correo.</b>
            <div style="font-weight:400;margin-top:2px">
              Te enviamos un enlace de acceso. Vence en 10 minutos.
            </div>
          </div>
        </div>
      {:else}
        <form
          method="POST"
          action="?/magicLink"
          use:enhance={handleMagicLink}
          style="display:flex;flex-direction:column;gap:9px"
        >
          <label for="email" class="v2-sr-only">Correo electrónico</label>
          <input
            id="email"
            type="email"
            name="email"
            class="v2-input"
            placeholder="vos@empresa.com"
            required
            bind:value={email}
            disabled={isSendingLink}
          />
          <button type="submit" class="v2-btn v2-btn-block" disabled={isSendingLink}>
            {#if isSendingLink}
              <span class="v2-spin"></span>
              <span>Enviando…</span>
            {:else}
              <Mail size={15} />
              <span>Continuar con correo</span>
            {/if}
          </button>
        </form>
        {#if magicLinkError}
          <div class="v2-auth-note v2-auth-note-bad" style="margin-top:11px">
            <span>{magicLinkError}</span>
          </div>
        {/if}
      {/if}
    </div>

    <p class="v2-sub" style="text-align:center;margin:14px 0 0">
      ¿Primera vez? Ingresá tu correo arriba para empezar.
    </p>

    <div class="v2-auth-foot">
      <a href="https://bottlecrm.io/privacy-policy">Privacidad</a>
      <span class="v2-auth-dot"></span>
      <a href="https://bottlecrm.io/terms">Términos</a>
      <span class="v2-auth-dot"></span>
      <a href="https://github.com/django-crm/Django-CRM" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</div>
