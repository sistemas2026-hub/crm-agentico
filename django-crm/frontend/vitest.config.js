import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import path from 'node:path';

/**
 * THE CEILING OF THIS HARNESS
 *
 * This is a bare Vite config, not the app's own `vite.config.js`, so none of
 * SvelteKit's virtual modules exist here by default. Two aliases are wired in
 * below because `$lib/server/v2/leads.js:26` and `$lib/api-helpers.js:8` both
 * import `$env/dynamic/public` at module scope: it is a Vite virtual module
 * generated at build/dev time, not a real file, so a plain `node`/vitest run
 * cannot resolve it without a stand-in. `$lib` is aliased because
 * `path.resolve('./src/lib')` is the only way to reach it outside SvelteKit's
 * own resolution.
 *
 * That is as far as this config goes. It resolves `$lib` and
 * `$env/dynamic/public` and nothing else: `$app/forms`, `$app/navigation`,
 * `$env/static/*`, and `$env/dynamic/private` are all still unresolvable
 * here, and there is no Svelte plugin, so `.svelte` files cannot be compiled
 * at all. `include: ['src/**\/*.test.js']` will happily pick up a test placed
 * anywhere under `src/`, including next to a route module or a component, but
 * importing either from a test run through this config fails with an opaque
 * "Failed to resolve import" rather than a clear "not supported here".
 *
 * This harness therefore covers server modules only (`$lib/server/v2/*.js`
 * and similar, functions over `apiRequest` with no SvelteKit runtime
 * dependency). Testing a route module (`+page.server.js`, which pulls in
 * `$app/forms` via its actions) or a `.svelte` component means moving
 * `test: {}` into the app's own `vite.config.js`, where the `sveltekit()`
 * plugin already provides `$lib`, `$app/*`, `$env/*` and Svelte compilation
 * for free. That is a real tradeoff, not a strict improvement: it also pulls
 * `sentrySvelteKit()` and `tailwindcss()` into every test run, which this
 * standalone config exists specifically to avoid.
 *
 * EL TECHO SUBIO UN ESCALON EL 22/09/2026, Y POR UN FALLO CONCRETO.
 * Al fundir dos bandas del compositor en una, la rama nueva quedo ANTES que
 * la de la IA y se llevo puesto el boton «Intervenir»: con la IA atendiendo y
 * la ventana de WhatsApp cerrada, no habia forma de tomar el control. Ningun
 * test se puso rojo, porque ninguno podia -- las guardas del compositor son
 * greps sobre el archivo, y un grep no sabe que rama gana.
 *
 * Asi que se agrega `svelte()` A SECAS, no `sveltekit()`. Es lo que el parrafo
 * de arriba contemplaba sin llegar a hacer, y en su version barata: compila
 * `.svelte` y nada mas. NO trae `$app/*` ni `$env/static/*`, NO trae
 * `sentrySvelteKit()` ni `tailwindcss()`, y por lo tanto no le cuesta nada a
 * las corridas que no tocan componentes.
 *
 * LO QUE ESTO HABILITA, Y LO QUE NO: un componente cuyos imports sean solo
 * `$lib`, paquetes de node y `svelte/*` se puede renderizar con
 * `render()` de 'svelte/server' y AFIRMAR SOBRE LO QUE DIBUJA. Uno que
 * importe `$app/forms` --CasePanel, por ejemplo-- sigue sin poder: le haria
 * falta un stub, y ese es el proximo escalon, no este.
 *
 * `path.resolve('./src/lib')` below resolves against `process.cwd()`, not
 * against this file's location, so `pnpm test` (and `vitest` directly) must
 * be run from `frontend/`. Running it from the repo root or from `src/`
 * silently resolves `$lib` to the wrong place.
 */
export default defineConfig({
  plugins: [svelte()],
  test: {
    // Node alcanza incluso para los componentes: se renderizan con `render()`
    // de 'svelte/server', que devuelve HTML sin tocar el DOM. Un jsdom serviria
    // para probar clics; para afirmar QUE DIBUJA cada combinacion de props no
    // hace falta, y cuesta arranque en cada corrida.
    //
    // SE INTENTO, Y NO ARRANCA AQUI (07/10/2026). Se instalo jsdom 30.1.2 y se
    // escribio un archivo con `// @vitest-environment jsdom`. El worker de
    // vitest 4.1.10 muere con "Timeout waiting for worker to respond" a los
    // 60 s, SIEMPRE: con pool forks, con threads, con --no-isolate, y tambien
    // con una sonda trivial de tres lineas que no importa Svelte. O sea que no
    // es el componente ni la prueba: es el entorno --contenedor efimero sobre
    // un volumen de Windows, donde una corrida normal ya gasta 720 s solo en
    // transformar--. Se revirtio la dependencia en vez de dejar una prueba que
    // no corre: una prueba que no corre es peor que ninguna, porque enseña a
    // ignorar el rojo.
    //
    // Lo que queda sin cubrir, y hay que decirlo en vez de fingir: pulsar un
    // puesto, pasar por encima y arrastrar la camara. Por ese hueco se
    // escaparon dos defectos reales --`setPointerCapture` robandose el click,
    // y un `{@const}` suelto que no compilaba--. Hoy se verifica a mano con
    // navegador contra un banco. Cerrarlo de verdad pide correr las pruebas
    // FUERA del volumen montado, o un Playwright en CI; las dos cosas son otro
    // trabajo, no un ajuste de esta linea.
    environment: 'node',
    include: ['src/**/*.test.js']
  },
  resolve: {
    alias: {
      $lib: path.resolve('./src/lib'),
      '$env/dynamic/public': path.resolve('./test/stubs/env-dynamic-public.js')
    }
  }
});
