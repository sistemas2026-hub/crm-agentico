import { sentrySvelteKit } from '@sentry/sveltekit';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    // Dentro de Docker, el codigo entra por un bind mount desde el host. En
    // Windows y macOS los eventos de archivo del host NO cruzan al contenedor
    // Linux, asi que el watcher de Vite nunca se entera de un cambio: sigue
    // sirviendo el modulo compilado viejo. No falla, no avisa -- se edita un
    // archivo, se recarga el navegador y no pasa nada, o peor, SSR y cliente
    // quedan en versiones distintas y sale 'hydration_mismatch'. Se pierde
    // media hora buscando el bug en el codigo que se acaba de escribir.
    //
    // El arreglo habitual -- sondear los archivos en vez de esperar eventos --
    // SE PROBO ACA Y NO SIRVE, con node_modules excluido y todo: el sondeo
    // sobre el bind mount de Windows deja el proceso ocupado a ~25% de CPU
    // constante y le come el turno al servidor. Medido: '/login' dejo de
    // responder por completo (4 minutos sin devolver un byte); apagando el
    // sondeo, la misma ruta devolvio 200 y el CPU cayo a 0%.
    //
    // Asi que en Docker NO hay recarga en caliente: despues de editar un
    // archivo del frontend hay que reiniciar el contenedor
    // ('docker compose restart frontend'). Es lento pero funciona, que es mas
    // de lo que se puede decir del sondeo. Queda detras de una variable por si
    // alguien quiere volver a intentarlo en otra maquina -- apagada por
    // defecto, y sabiendo lo de arriba antes de encenderla.
    server: env.VITE_USE_POLLING
      ? {
          watch: {
            usePolling: true,
            interval: 1000,
            ignored: ['**/node_modules/**', '**/.svelte-kit/**', '**/.git/**']
          }
        }
      : {},
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
