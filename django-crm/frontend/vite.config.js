import { sentrySvelteKit } from '@sentry/sveltekit';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [
      sentrySvelteKit({
        org: 'micropyramid-fa',
        project: 'bottlecrm-app',
        sourceMapsUploadOptions: {
          authToken: env.SENTRY_AUTH_TOKEN
        },
        autoUploadSourceMaps: !!env.PUBLIC_SENTRY_DSN
      }),
      tailwindcss(),
      sveltekit()
    ]
    // NOTA: se probo 'server.watch.usePolling' aca (sondear el filesystem
    // en vez del watcher nativo, workaround tipico para bind mounts de
    // Docker Desktop) para una recarga fantasma vista en vivo -- pero
    // sondear cada 300ms sobre todo /app (incluido el volumen de
    // node_modules) dejo al servidor de Vite sin responder del todo
    // (confirmado: curl a :5173 sin respuesta, CPU sostenida ~54%). Revertido
    // -- la cura fue peor que la enfermedad. Si hace falta retomarlo, acotar
    // 'ignored' a node_modules/.svelte-kit/.git primero.
  };
});
