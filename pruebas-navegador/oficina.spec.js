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
 * `?sala=`, `?piso=` y `?puesto=`, que además es una función real — una
 * oficina sin enlaces no se puede mandar.
 *
 * LA SESIÓN LA PREPARA `sesion.setup.js`. Entrar dentro de cada prueba fue el
 * primer error de esta suite: Playwright le da a cada una un contexto limpio.
 */

/**
 * UN ERROR EN LA PAGINA ROMPE LA PRUEBA, aunque la afirmacion se cumpla.
 *
 * Sin esto, una pagina que revienta al hidratar deja el marcado que pinto el
 * servidor -que puede contener justo lo que la prueba busca- y la prueba pasa
 * con la pantalla muerta. Paso: con `?puesto=` la hidratacion fallaba, la
 * escena se quedaba en «Montando la oficina...» para siempre, y lo unico que
 * se veia era una afirmacion que no encontraba un texto.
 */
test.beforeEach(({ page }, info) => {
  page.on('pageerror', (e) => {
    info.errors.push({ message: `la pagina lanzo un error: ${e.message}`, stack: e.stack });
  });
});

/**
 * ABRIR UNA PANTALLA Y ESPERAR A QUE HIDRATE.
 *
 * `goto` devuelve con el marcado que pintó el servidor, y lo que esta suite
 * afirma vive del lado del cliente: la vista que pide la URL —`?sala=`,
 * `?piso=`, `?puesto=`— la resuelve el navegador. Sin esperar, la aserción
 * corre contra el HTML del servidor, que siempre dice «El edificio».
 *
 * Medido el 31/10/2026: con `goto` a secas, siete pruebas fallaban con
 * «element(s) not found» y la pantalla decía exactamente lo que el servidor
 * había pintado. Con la espera, las mismas siete pasan sin tocar una sola
 * afirmación. En el laboratorio esto tarda porque Vite sirve cientos de
 * módulos sueltos en la primera carga de un contexto nuevo; una compilación de
 * producción no se parece a esto.
 */
async function abrir(page, url) {
  await page.goto(url);
  await page.waitForLoadState('networkidle');
}

/** Lo que la cabecera de la escena publica, una vez montada. */
async function telemetria(page) {
  //  Se espera a que la escena esté montada: mientras monta, la cabecera no
  //  tiene telemetría y leer antes daría cero, que no es «cero objetos».
  await expect(page.getByText('Montando la oficina...')).toHaveCount(0);
  const texto = await page.locator('text=/\\d+ obj/').first().innerText();
  return {
    objetos: Number(texto.match(/(\d+) obj/)?.[1] ?? 0),
    fps: Number(texto.match(/(\d+) fps/)?.[1] ?? 0)
  };
}

test.describe('la oficina carga y se puede recorrer', () => {
  test('el centro de mando v2 dibuja un edificio', async ({ page }) => {
    await abrir(page, '/centro-mando/v2');
    await expect(page.getByRole('heading', { name: 'El edificio' })).toBeVisible();
    //  La estructura sale de la configuración, y el subtítulo dice de dónde.
    await expect(page.locator('text=/departamentos · \\d+ piso/')).toBeVisible();

    const { objetos, fps } = await telemetria(page);
    //  Números y no una captura: una escena con cero objetos no se montó, y a
    //  0 fps no está corriendo. Las dos cosas se ven igual en un lienzo negro.
    expect(objetos).toBeGreaterThan(500);
    expect(fps).toBeGreaterThan(5);
  });

  test('edificio → piso → sala → vuelta', async ({ page }) => {
    await abrir(page, '/centro-mando/v2');
    await page.getByRole('button', { name: /^P\d$/ }).first().click();
    await expect(page.locator('text=/Piso \\d+ · \\d+ sala/')).toBeVisible();

    await page.getByRole('button', { name: 'NOC y Redes', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'NOC y Redes' })).toBeVisible();

    await page.getByRole('button', { name: 'El edificio' }).click();
    await expect(page.getByRole('heading', { name: 'El edificio' })).toBeVisible();
  });

  test('una sala aislada pesa MENOS que el edificio entero', async ({ page }) => {
    //  Lo que esto mata: que seleccionar una sala no filtre nada y se siga
    //  dibujando el edificio entero detrás. A ojo se ve igual.
    await abrir(page, '/centro-mando/v2');
    const todo = await telemetria(page);
    await abrir(page, '/centro-mando/v2?sala=operativo');
    const una = await telemetria(page);
    expect(una.objetos).toBeLessThan(todo.objetos);
  });

  test('un enlace a un piso abre ESE piso', async ({ page }) => {
    await abrir(page, '/centro-mando/v2?piso=3');
    await expect(page.locator('text=/Piso 3 · \\d+ sala/')).toBeVisible();
  });
});

test.describe('la ficha de un puesto', () => {
  test('un puesto OCUPADO dice quién es y qué puede hacer', async ({ page }) => {
    await abrir(page, '/centro-mando/v2?sala=operativo&puesto=operativo:principal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Agente IA ejecutable')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Qué puede hacer' })).toBeVisible();
  });

  test('un puesto LIBRE lo dice, y no se disfraza', async ({ page }) => {
    //  «Sin agente asignado» es un dato, no un hueco que haya que rellenar.
    //  Se usa Auditoría porque nace sin nadie: es un departamento real de un
    //  proveedor de internet que ningún agente representa, y era justo el caso
    //  que la estructura deducida de los agentes no podía dibujar.
    await abrir(page, '/centro-mando/v2?sala=auditoria&puesto=auditoria:principal');
    await expect(page.getByText('Puesto libre')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Qué puede hacer' })).toHaveCount(0);
  });

  test('un puesto inventado NO abre una ficha inventada', async ({ page }) => {
    await abrir(page, '/centro-mando/v2?sala=operativo&puesto=operativo:no-existe');
    //  Primero que la pantalla ESTÉ: sin esto, la ausencia de la ficha la
    //  cumpliría también una página de error, y la prueba pasaría por el
    //  motivo equivocado.
    await expect(page.getByRole('heading', { name: 'NOC y Redes' })).toBeVisible();
    await expect(page.getByText('Agente IA ejecutable')).toHaveCount(0);
  });

  test('una sala que no existe cae al edificio en vez de romperse', async ({ page }) => {
    //  Un enlace puede ser viejo. Un edificio es una respuesta honesta; una
    //  pantalla en blanco no.
    await abrir(page, '/centro-mando/v2?sala=departamento-que-no-existe');
    await expect(page.getByRole('heading', { name: 'El edificio' })).toBeVisible();
  });
});

test.describe('la empresa con asistente ve la suya', () => {
  test('el constructor carga con la estructura real', async ({ page }) => {
    //  La otra mitad del aislamiento: sin esta, «no se ve nada» pasaría por
    //  aislamiento cuando podría ser que no se ve nada en ningún lado.
    await abrir(page, '/settings/organizacion');
    await expect(page.getByRole('heading', { name: 'Pisos' })).toBeVisible();
    await expect(page.locator('input[name="dep:0:id"]')).toBeVisible();
  });

  test('cada puesto de la sala elegida tiene su selector', async ({ page }) => {
    await abrir(page, '/settings/organizacion');
    const sillas = page.locator('select[name^="dep:0:ocupa_"]');
    await expect(sillas.first()).toBeVisible();
    expect(await sillas.count()).toBeGreaterThan(1);
  });
});

test.describe('editar la organización no pierde lo que no se editó', () => {
  test('guardar sin cambiar nada conserva TODAS las ocupaciones', async ({ page }) => {
    //  EL DEFECTO QUE ESTO MATA, medido el 31/10/2026: al guardar, Atención al
    //  Cliente perdió a su segundo agente y el pie de la oficina pasó de «6 de
    //  37 puestos ocupados» a «5 de 40». Sin error, sin aviso, y sólo visible
    //  contando. Por eso la afirmación es un NÚMERO.
    await abrir(page, '/centro-mando/v2');
    const antes = await page.locator('footer').innerText();
    const ocupadosAntes = Number(antes.match(/(\d+) de \d+ puestos/)?.[1] ?? -1);
    expect(ocupadosAntes).toBeGreaterThan(0);

    await abrir(page, '/settings/organizacion');
    await page.getByRole('button', { name: 'Guardar organización' }).click();
    await expect(page.getByText('Organización guardada.')).toBeVisible();

    await abrir(page, '/centro-mando/v2');
    const despues = await page.locator('footer').innerText();
    expect(Number(despues.match(/(\d+) de \d+ puestos/)?.[1] ?? -1)).toBe(ocupadosAntes);
  });

  test('cambiar el tamaño de una sala cambia sus sillas y no toca las demás', async ({ page }) => {
    await abrir(page, '/settings/organizacion');
    const sillas = (i) => page.locator(`select[name^="dep:${i}:ocupa_"]`);
    const plantilla = page.locator('select[name="dep:0:plantilla"]');
    const original = await plantilla.inputValue();
    const antes = await sillas(0).count();
    const antesOtra = await sillas(1).count();

    //  A la variante de tres puestos más: el nombre de la plantilla dice
    //  cuántos trae, así que la cuenta es comprobable.
    await plantilla.selectOption(`${original}_${antes + 3}`);
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
    await abrir(page, '/settings/organizacion');
    await page.locator('.proponer').first().click();
    await expect(page.locator('[data-prueba^="propuesta-"]').first()).toBeVisible();
    await expect(page.getByText('Organización guardada.')).toHaveCount(0);
  });
});
