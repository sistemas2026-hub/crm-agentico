import { test, expect } from '@playwright/test';

/**
 * EL AISLAMIENTO ENTRE DOS EMPRESAS, MEDIDO DESDE EL NAVEGADOR.
 *
 * Estas pruebas corren con la sesión de la empresa que **no tiene asistente**.
 * Es un caso real y no inventado: en este laboratorio conviven dos
 * organizaciones y sólo una está atada a un tenant del motor.
 *
 * LO QUE VIGILAN es que la pantalla falle **cerrada**. El motor contesta 404 a
 * `/tenant-de-organizacion/<id>` de una empresa sin tenant, y lo que no puede
 * pasar es que la pantalla caiga a la estructura de la empresa de al lado: eso
 * sería exactamente la fuga que el aislamiento por organización existe para
 * impedir. Una pantalla vacía que lo dice es la respuesta correcta.
 *
 * La otra mitad —que la empresa que SÍ tiene asistente vea la suya— vive en
 * `oficina.spec.js`. Sin las dos, «no se ve nada» pasaría por aislamiento
 * cuando podría ser que no se ve nada en ningún lado.
 */

/** Igual que en `oficina.spec.js`: lo que se afirma lo resuelve el cliente. */
async function abrir(page, url) {
  await page.goto(url);
  await page.waitForLoadState('networkidle');
}

test('el constructor de una empresa SIN asistente falla cerrado y lo explica', async ({ page }) => {
  await abrir(page, '/settings/organizacion');
  await expect(page.getByText(/No se pudo leer la organización/)).toBeVisible();
  //  Y NO muestra la estructura de nadie: ni un piso, ni un departamento.
  await expect(page.locator('input[name="dep:0:id"]')).toHaveCount(0);
});

test('y su oficina no inventa un edificio', async ({ page }) => {
  await abrir(page, '/centro-mando/v2');
  //  Y lo dice con lo que de verdad pasa. Hasta el 31/10/2026 la pantalla
  //  contestaba «falta PRIVATE_ASISTENTE_URL o la empresa de la sesión»: le
  //  nombraba a quien mira una variable de entorno que no puede tocar, y
  //  culpaba al despliegue de un hecho del producto.
  await expect(
    page.getByText(/Esta empresa todavía no tiene un asistente configurado/)
  ).toBeVisible();
  await expect(page.getByText(/PRIVATE_ASISTENTE_URL/)).toHaveCount(0);
  //  Sin estructura: ni un departamento inventado.
  await expect(page.getByText(/0 departamentos/)).toBeVisible();
});

test('no se cuela el nombre de ningún departamento de la otra empresa', async ({ page }) => {
  //  La afirmación que de verdad mide la fuga. Las dos anteriores dicen que
  //  esta empresa no ve nada; ésta dice que lo que no ve es, en concreto, lo
  //  de la empresa de al lado.
  await abrir(page, '/centro-mando/v2');
  for (const ajeno of ['NOC y Redes', 'Finanzas y Cartera', 'Recursos Humanos']) {
    await expect(page.getByText(ajeno, { exact: true })).toHaveCount(0);
  }
});
