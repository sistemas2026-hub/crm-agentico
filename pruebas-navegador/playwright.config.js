import { defineConfig, devices } from '@playwright/test';

/**
 * CONTRA EL LABORATORIO, NUNCA CONTRA PRODUCCION.
 *
 * `BASE` lo arma `correr.sh` con la IP de la pasarela del anfitrion y un
 * puerto local; el contenedor donde corre esto no tiene ruta a otra cosa. No
 * es una precaucion de estilo: una suite de navegador que sepa entrar a
 * produccion es una suite que algun dia va a entrar a produccion.
 */
const BASE = process.env.BASE || 'http://host.docker.internal:55600';

export default defineConfig({
  testDir: '.',
  //  En serie y con un solo trabajador: hay pruebas que ESCRIBEN la
  //  organizacion de la empresa, y dos de ellas a la vez se pisarian. El mismo
  //  motivo por el que no se corren dos suites contra el mismo Postgres.
  fullyParallel: false,
  workers: 1,
  //  Un reintento. No para esconder una prueba inestable -- si una falla dos
  //  veces es un defecto -- sino porque el laboratorio arranca Vite en frio y
  //  la primera navegacion puede tardar mas que cualquier plazo razonable.
  retries: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { outputFolder: 'informe', open: 'never' }]],
  outputDir: 'resultados',
  use: {
    baseURL: BASE,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    viewport: { width: 1600, height: 900 }
  },
  projects: [
    //  LA PREPARACION ES UN PROYECTO, no un `globalSetup`: asi su fallo sale
    //  con el nombre de lo que fallo -- «no aparecio la empresa X» -- en vez
    //  de tumbar la corrida entera con un error de arranque.
    { name: 'sesion', testMatch: /sesion\.setup\.js/ },
    {
      name: 'empresa-con',
      testMatch: /oficina\.spec\.js/,
      dependencies: ['sesion'],
      use: { ...devices['Desktop Chrome'], storageState: '.sesiones/con.json' }
    },
    {
      name: 'empresa-sin',
      testMatch: /aislamiento\.spec\.js/,
      dependencies: ['sesion'],
      use: { ...devices['Desktop Chrome'], storageState: '.sesiones/sin.json' }
    }
  ]
});
