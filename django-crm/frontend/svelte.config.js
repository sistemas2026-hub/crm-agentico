import adapter from '@sveltejs/adapter-node';

const config = {
  vitePlugin: {
    // NO poner en true. Se probo para esquivar el choque entre
    // @tailwindcss/vite 4 y vite-plugin-svelte >=7.1 (ver abajo) y el remedio
    // resulto peor: al pre-empaquetar las librerias Svelte, el runtime de
    // Svelte queda DUPLICADO -- 'svelte_internal_client.js' y compania
    // aparecen en node_modules/.vite/deps y las librerias pasan a usar una
    // copia distinta de la que usa la aplicacion. El estado de los
    // componentes deja de compartirse entre las dos, y navegar por el menu
    // deja la pantalla anterior pegada mientras la URL si cambia, con
    // 'Cannot read properties of undefined' por cada pagina que intenta
    // renderizarse con los datos de otra.
    //
    // El choque con Tailwind (bug tailwindlabs/tailwindcss#20000: el bloque
    // <style> de un componente de node_modules le llega a Tailwind con el
    // <script> pegado adelante, y revienta al parsear el 'import' como CSS)
    // se arregla por el otro camino: fijar vite-plugin-svelte en 7.0.0.
    prebundleSvelteLibraries: false
  },
  kit: {
    adapter: adapter(),

    version: {
      pollInterval: 60000
    },

    experimental: {
      tracing: {
        server: true
      },

      instrumentation: {
        server: true
      }
    }
  }
};

export default config;
