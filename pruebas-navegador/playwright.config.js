import { defineConfig, devices } from '@playwright/test';

/**
 * CONTRA EL LABORATORIO, NUNCA CONTRA PRODUCCION.
 *
 * `BASE` apunta a un puerto de la maquina local y el contenedor donde corre
 * esto no tiene ruta a otra cosa. No es una precaucion de estilo: una suite de
 * navegador que sepa entrar a produccion es una suite que algun dia va a
 * entrar a produccion.
 */
const BASE = process.env.BASE || 'http://host.docker.internal:55600';

export default defineConfig({
  testDir: '.',
  //  En serie y con un solo trabajador: hay pruebas que ESCRIBEN la
  //  organizacion de la empresa, y dos de ellas a la vez se pisarian. El
  //  mismo motivo por el que no se corren dos suites contra el mismo Postgres.
  fullyParallel: false,
  workers: 1,
  //  Un reintento. No para esconder una prueba inestable -- si una falla dos
  //  veces es un defecto -- sino porque el laboratorio arranca Vite en frio y
  //  la primera navegacion puede tardar mas que cualquier plazo razonable.
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { outputFolder: 'informe', open: 'never' }]],
  outputDir: 'resultados',
  use: {
    baseURL: BASE,
    //  La traza solo del reintento: una traza por prueba llena el disco y
    //  nadie la mira cuando todo esta en verde.
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    viewport: { width: 1600, height: 900 }
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
});
