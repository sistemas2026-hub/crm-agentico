import { test, expect } from '@playwright/test';

/**
 * LA OFICINA VIRTUAL, EN UN NAVEGADOR DE VERDAD.
 *
 * QUÉ VIGILA ESTA SUITE Y NINGUNA OTRA
 * El camino completo: `pantalla → load del servidor → API del motor → base`.
 * `vitest` prueba módulos y componentes sueltos, y los dos defectos más caros
 * del 29/09/2026 vivían justamente en los saltos que ninguna de esas pruebas
 * atraviesa — `requiere_noc` viajaba bien desde el backend y la capa servidor
 * lo dejaba caer, con su prueba de backend en verde.
 *
 * CÓMO AFIRMA, Y POR QUÉ ASÍ
 * Sobre lo que la pantalla DICE, nunca sobre píxeles. El lienzo es un bitmap:
 * una prueba de píxeles se rompe cada vez que alguien mueve una planta dos
 * celdas y no se rompe cuando el defecto importa. De la escena sólo se afirma
 * lo que la propia cabecera publica —objetos y fotogramas—, que es un número y
 * se puede comparar.
 *
 * LOS PUESTOS SE ABREN POR ENLACE Y NO A CLICS EN EL LIENZO. Adivinar en qué
 * píxel cayó un escritorio depende de la cámara, del zoom y del tamaño de la
 * ventana: una prueba así falla por lo que no importa. La pantalla acepta
 * `?sala=` y `?puesto=`, que además es una función real — una oficina sin
 * enlaces no se puede mandar.
 */

const USUARIO = process.env.USUARIO || 'admin@localhost';
const CLAVE = process.env.CLAVE || 'lab12345';
const ORG_CON = process.env.ORG_CON || 'MicroPyramid';
const ORG_SIN = process.env.ORG_SIN || 'Plumeline Media';

/** Entrar y quedarse en la organización pedida. */
async function entrar(page, organizacion) {
  await page.goto('/login');
  //  Ya hay sesión: el formulario no aparece y no hay nada que hacer.
  if (await page.getByLabel('Correo electrónico').count()) {
    await page.getByLabel('Correo electrónico').fill(USUARIO);
    await page.getByLabel('Contraseña').fill(CLAVE);
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  }
  await elegirOrganizacion(page, organizacion);
}

/** Elegir empresa, venga la pantalla de elección o no. */
async function elegirOrganizacion(page, organizacion) {
  if (!page.url().includes('/org')) await page.goto('/org');
  const boton = page.getByRole('button', { name: new RegExp(organizacion) });
  if (await boton.count()) await boton.first().click();
  await expect(page.locator('body')).toBeVisible();
}

/** Lo que la cabecera de la escena publica: objetos y fotogramas. */
async function telemetria(page) {
  const texto = await page.locator('text=/\\d+ obj/').first().innerText();
  return {
    objetos: Number(texto.match(/(\d+) obj/)?.[1] ?? 0),
    fps: Number(texto.match(/(\d+) fps/)?.[1] ?? 0)
  };
}

test.describe('entrar y elegir empresa', () => {
  test('la cuenta del laboratorio entra', async ({ page }) => {
    await page.goto('/login');
    if (await page.getByLabel('Correo electrónico').count()) {
      await page.getByLabel('Correo electrónico').fill(USUARIO);
      await page.getByLabel('Contraseña').fill(CLAVE);
      await page.getByRole('button', { name: 'Iniciar sesión' }).click();
    }
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('con dos empresas, hay que ELEGIR una', async ({ page }) => {
    //  No es un detalle de la demo: quedarse en la empresa equivocada es lo
    //  que hacía que `/settings/organizacion` dijera «no se pudo leer la
    //  organización». La pantalla falla cerrada, que es correcto, pero quien
    //  la mira tiene que poder llegar a la empresa que sí tiene asistente.
    await page.goto('/org');
    await expect(page.getByRole('button', { name: new RegExp(ORG_CON) })).toBeVisible();
    await expect(page.getByRole('button', { name: new RegExp(ORG_SIN) })).toBeVisible();
  });
});

test.describe('la oficina carga y se puede recorrer', () => {
  test.beforeEach(async ({ page }) => { await entrar(page, ORG_CON); });

  test('el centro de mando v2 dibuja un edificio', async ({ page }) => {
    await page.goto('/centro-mando/v2');
    await expect(page.getByRole('heading', { name: 'El edificio' })).toBeVisible();
    //  La estructura sale de la configuración: el subtítulo dice de dónde.
    await expect(page.locator('text=/departamentos · \\d+ piso/')).toBeVisible();
    const { objetos, fps } = await telemetria(page);
    //  Números y no una captura: una escena con cero objetos es una escena
    //  que no se montó, y a 0 fps no está corriendo. Las dos cosas se ven
    //  igual en un lienzo negro.
    expect(objetos).toBeGreaterThan(500);
    expect(fps).toBeGreaterThan(20);
  });

  test('edificio → piso → sala → vuelta', async ({ page }) => {
    await page.goto('/centro-mando/v2');
    await page.getByRole('button', { name: /^P\d$/ }).first().click();
    await expect(page.locator('text=/Piso \\d+ · \\d+ sala/')).toBeVisible();

    await page.getByRole('button', { name: 'NOC y Redes' }).click();
    await expect(page.getByRole('heading', { name: 'NOC y Redes' })).toBeVisible();

    await page.getByRole('button', { name: 'El edificio' }).click();
    await expect(page.getByRole('heading', { name: 'El edificio' })).toBeVisible();
  });

  test('una sala aislada pesa MENOS que el edificio entero', async ({ page }) => {
    //  Lo que esto mata: que seleccionar una sala no filtre nada y se siga
    //  dibujando el edificio entero detrás. A ojo se ve igual.
    await page.goto('/centro-mando/v2');
    const todo = await telemetria(page);
    await page.goto('/centro-mando/v2?sala=operativo');
    const una = await telemetria(page);
    expect(una.objetos).toBeLessThan(todo.objetos);
  });
});

test.describe('la ficha de un puesto', () => {
  test.beforeEach(async ({ page }) => { await entrar(page, ORG_CON); });

  test('un puesto OCUPADO dice quién es y qué puede hacer', async ({ page }) => {
    await page.goto('/centro-mando/v2?sala=operativo&puesto=operativo:principal');
    await expect(page.getByText('Agente IA ejecutable')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Qué puede hacer' })).toBeVisible();
  });

  test('un puesto LIBRE lo dice, y no se disfraza', async ({ page }) => {
    //  «Sin agente asignado» es un dato, no un hueco que haya que rellenar.
    await page.goto('/centro-mando/v2?sala=operativo&puesto=operativo:p1');
    await expect(page.getByText('Puesto libre')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Qué puede hacer' })).toHaveCount(0);
  });

  test('un puesto inventado NO abre una ficha inventada', async ({ page }) => {
    await page.goto('/centro-mando/v2?sala=operativo&puesto=operativo:no-existe');
    await expect(page.getByText('Agente IA ejecutable')).toHaveCount(0);
  });

  test('una sala que no existe cae al edificio en vez de romperse', async ({ page }) => {
    //  Un enlace puede ser viejo. Un edificio es una respuesta honesta; una
    //  pantalla en blanco no.
    await page.goto('/centro-mando/v2?sala=departamento-que-no-existe');
    await expect(page.getByRole('heading', { name: 'El edificio' })).toBeVisible();
  });
});

test.describe('lo que la pantalla dice cuando NO sabe', () => {
  test('una empresa SIN asistente falla cerrada y lo explica', async ({ page }) => {
    //  El aislamiento medido desde el navegador: esta organización no tiene
    //  tenant, el motor devuelve 404 y la pantalla NO cae a la estructura de
    //  otra empresa. Servir la organización de al lado sería exactamente la
    //  fuga que el aislamiento existe para impedir.
    await entrar(page, ORG_SIN);
    await page.goto('/settings/organizacion');
    await expect(page.getByText(/No se pudo leer la organización/)).toBeVisible();
  });

  test('y la oficina de esa empresa no inventa un edificio', async ({ page }) => {
    await entrar(page, ORG_SIN);
    await page.goto('/centro-mando/v2');
    await expect(
      page.getByText(/No se pudo leer la estructura de la empresa/)
    ).toBeVisible();
  });

  test('la empresa CON asistente sigue viendo la suya', async ({ page }) => {
    //  La otra mitad del aislamiento. Sin esta, «no se ve nada» pasaría por
    //  aislamiento cuando podría ser que no se ve nada en ningún lado.
    await entrar(page, ORG_CON);
    await page.goto('/settings/organizacion');
    await expect(page.getByRole('heading', { name: 'Pisos' })).toBeVisible();
    await expect(page.locator('input[name="dep:0:id"]')).toBeVisible();
  });
});

test.describe('editar la organización no pierde lo que no se editó', () => {
  test.beforeEach(async ({ page }) => { await entrar(page, ORG_CON); });

  test('guardar sin cambiar nada conserva TODAS las ocupaciones', async ({ page }) => {
    //  EL DEFECTO QUE ESTO MATA, medido el 31/10/2026: al guardar, Atención al
    //  Cliente perdió a su segundo agente y el pie de la oficina pasó de «6 de
    //  37 puestos ocupados» a «5 de 40». Sin error, sin aviso, y sólo visible
    //  contando. Por eso la afirmación es un NÚMERO.
    await page.goto('/centro-mando/v2');
    const antes = await page.locator('footer').innerText();
    const ocupadosAntes = Number(antes.match(/(\d+) de \d+ puestos/)?.[1] ?? -1);
    expect(ocupadosAntes).toBeGreaterThan(0);

    await page.goto('/settings/organizacion');
    await page.getByRole('button', { name: 'Guardar organización' }).click();
    await expect(page.getByText('Organización guardada.')).toBeVisible();

    await page.goto('/centro-mando/v2');
    const despues = await page.locator('footer').innerText();
    const ocupadosDespues = Number(despues.match(/(\d+) de \d+ puestos/)?.[1] ?? -1);
    expect(ocupadosDespues).toBe(ocupadosAntes);
  });

  test('cambiar el tamaño de una sala cambia sus sillas y no toca las demás', async ({ page }) => {
    await page.goto('/settings/organizacion');
    const sillas = (i) => page.locator(`select[name^="dep:${i}:ocupa_"]`);
    const plantilla = page.locator('select[name="dep:0:plantilla"]');
    const original = await plantilla.inputValue();
    const antesOtra = await sillas(1).count();
    const antes = await sillas(0).count();

    //  A la variante de tres puestos más: el nombre de la plantilla dice
    //  cuántos trae, así que la cuenta es comprobable.
    const mayor = `${original}_${antes + 3}`;
    await plantilla.selectOption(mayor);
    await expect(sillas(0)).toHaveCount(antes + 3);
    expect(await sillas(1).count()).toBe(antesOtra);

    //  Y se deja como estaba: esta suite no puede dejar el laboratorio
    //  distinto de como lo encontró, o la siguiente prueba mide otra cosa.
    await plantilla.selectOption(original);
    await expect(sillas(0)).toHaveCount(antes);
  });

  test('«sugerir ocupantes» propone y NO guarda', async ({ page }) => {
    //  La diferencia entre proponer y decidir, medida: después de pulsar, el
    //  formulario cambió y la configuración no.
    await page.goto('/settings/organizacion');
    await page.locator('.proponer').first().click();
    await expect(page.locator('[data-prueba^="propuesta-"]').first()).toBeVisible();
    //  Nada se guardó: no hay mensaje de guardado.
    await expect(page.getByText('Organización guardada.')).toHaveCount(0);
  });
});
