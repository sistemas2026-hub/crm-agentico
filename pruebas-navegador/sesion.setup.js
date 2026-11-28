import { test as setup, expect } from '@playwright/test';
import fs from 'node:fs';

/**
 * ENTRAR UNA VEZ Y GUARDAR LA SESIÓN, en vez de entrar en cada prueba.
 *
 * No es una optimización. La primera versión de esta suite entraba dentro de
 * cada prueba y **trece de quince fallaban**: Playwright le da a cada prueba un
 * contexto limpio, así que la sesión que abría una no existía para la
 * siguiente, y el síntoma era «no encuentro el botón» en sitios donde el botón
 * está — porque lo que había delante era la pantalla de entrar.
 *
 * Son DOS sesiones y no una, por lo que esta suite tiene que poder afirmar:
 *
 *   `empresa-con`   la que SÍ tiene asistente. Casi todo pasa por acá.
 *   `empresa-sin`   la que NO. Sirve para una sola cosa, y es la importante:
 *                   que la pantalla falle CERRADA en vez de servirle la
 *                   organización de la empresa de al lado.
 *
 * Sin la segunda, «no se ve nada» pasaría por aislamiento cuando podría ser
 * que no se ve nada en ningún lado.
 */

const USUARIO = process.env.USUARIO || 'admin@localhost';
const CLAVE = process.env.CLAVE || 'lab12345';

async function entrarYElegir(page, organizacion, destino) {
  await page.goto('/login');

  //  La pantalla de entrar sólo aparece si no hay sesión. Con una sesión viva
  //  —el contenedor reutiliza el navegador entre los dos setups— el formulario
  //  no está, y buscarlo colgaría la preparación entera.
  if (await page.getByLabel('Correo electrónico').count()) {
    await page.getByLabel('Correo electrónico').fill(USUARIO);
    await page.getByLabel('Contraseña').fill(CLAVE);
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  }

  //  Con dos empresas el CRM pregunta cuál abrir. Es exactamente donde se
  //  quedó atascada la sesión de un operador el 31/10/2026: la empresa
  //  equivocada hace que `/settings/organizacion` diga «no se pudo leer la
  //  organización», que es correcto y no se parece al problema.
  await page.goto('/org');
  //  SE ESPERA A QUE LA PAGINA SE ASIENTE ANTES DE PULSAR. El formulario de
  //  elegir empresa usa `use:enhance`, y pulsarlo antes de que el navegador
  //  haya hidratado la pagina manda un POST nativo que no termina de
  //  resolverse como la aplicacion espera: la pantalla se queda donde estaba,
  //  sin error visible, y el sintoma aparece trece pruebas despues.
  await page.waitForLoadState('networkidle');

  //  DIAGNOSTICO TEMPORAL: que contesta el POST de elegir empresa.
  const respuestas = [];
  page.on('framenavigated', (f) => { if (f === page.mainFrame()) respuestas.push(`-> ${f.url()}`); });
  page.on('response', async (r) => {
    if (!r.url().includes('selectOrg')) return;
    let cuerpo = '';
    try { cuerpo = (await r.text()).slice(0, 400); } catch { cuerpo = '(sin cuerpo)'; }
    respuestas.push(`${r.status()} ${r.url()} :: ${cuerpo}`);
  });

  const boton = page.getByRole('button', { name: new RegExp(organizacion) });
  await expect(boton.first(), `no apareció la empresa «${organizacion}»`).toBeVisible();
  await boton.first().click();

  //  Elegir empresa emite tokens nuevos con el contexto de esa organización.
  //  Hasta que la navegación termina, las cookies guardadas serían las de
  //  antes y la sesión volvería a pedir elegir.
  try {
    await page.waitForURL((u) => !u.pathname.startsWith('/org'), { timeout: 15_000 });
  } catch {
    //  Si se quedó, que el fallo diga lo que la pantalla dice, en vez de un
    //  «timeout» que no señala a nada.
    const texto = (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 200);
    const galletas = (await page.context().cookies()).map((c) => `${c.name}=${String(c.value).slice(0, 12)}…`);
    throw new Error(
      `elegir «${organizacion}» no llevó a ninguna parte.
       respuestas: ${JSON.stringify(respuestas, null, 2)}
       cookies: ${galletas.join(', ')}
       pantalla: ${texto}`
    );
  }

  //  QUE LA ELECCION TOMO EFECTO SE COMPRUEBA CONTRA ALGO QUE NO SE CUMPLE
  //  SOLO. La primera version buscaba el nombre de la empresa en cualquier
  //  parte de `/`, y eso lo cumple tambien la pantalla de elegir -ahi estan
  //  los dos nombres-. Resultado: la preparacion daba verde con la sesion sin
  //  empresa, y trece pruebas fallaban despues diciendo «no encuentro el
  //  edificio».
  //
  //  Asi que son DOS condiciones juntas: estar fuera de `/org` -la unica
  //  pantalla donde conviven los dos nombres- y ver el de esta empresa. En la
  //  aplicacion solo lo pinta la barra lateral, con la empresa ya resuelta.
  await page.goto('/');
  await expect(page, 'la sesion se quedo en la pantalla de elegir').not.toHaveURL(/\/org/);
  await expect(
    page.getByText(organizacion).first(),
    `la sesion no quedo en «${organizacion}»`
  ).toBeVisible();

  await page.context().storageState({ path: destino });
}

setup('sesión en la empresa CON asistente', async ({ page }) => {
  fs.mkdirSync('.sesiones', { recursive: true });
  await entrarYElegir(page, process.env.ORG_CON || 'MicroPyramid',
                      '.sesiones/con.json');
});

setup('sesión en la empresa SIN asistente', async ({ page }) => {
  fs.mkdirSync('.sesiones', { recursive: true });
  await entrarYElegir(page, process.env.ORG_SIN || 'Plumeline Media',
                      '.sesiones/sin.json');
});
