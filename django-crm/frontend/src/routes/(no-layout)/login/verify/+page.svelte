<script>
  import '../../../../app.css';
  import '$lib/v2/styles/v2.css';
  import imgLogo from '$lib/assets/images/logo.png';

  let { data } = $props();
</script>

<svelte:head>
  <title>Verificando · BottleCRM</title>
  <meta name="referrer" content="no-referrer" />
</svelte:head>

<div class="v2-root v2-auth">
  <div class="v2-auth-box">
    <a href="/" class="v2-auth-brand">
      <img src={imgLogo} alt="" />
      <b>BottleCRM</b>
    </a>

    <div class="v2-auth-card" style="text-align:center">
      {#if data.error}
        <div class="v2-auth-head" style="margin-bottom:16px">
          <h1>Enlace vencido o inválido</h1>
          <p>{data.error}</p>
        </div>
        <a href="/login" class="v2-btn v2-btn-block">Volver a iniciar sesión</a>
      {:else}
        <div
          class="v2-spin"
          style="width:26px;height:26px;margin:4px auto 15px;color:var(--v2-ember)"
        ></div>
        <div class="v2-auth-head" style="margin-bottom:0">
          <h1>Iniciando sesión…</h1>
          <p>Un momento mientras verificamos tu enlace.</p>
        </div>
      {/if}
    </div>
  </div>
</div>
