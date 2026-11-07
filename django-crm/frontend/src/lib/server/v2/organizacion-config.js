/**
 * LA ORGANIZACIÓN DE LA EMPRESA, LEÍDA Y ESCRITA DESDE EL SERVIDOR.
 *
 * Server-only, mismo puente que el resto de `/settings`: habla con el motor
 * (`PRIVATE_ASISTENTE_URL`) y **el tenant sale del servidor, nunca del
 * cliente**. Que el navegador pudiera elegir de qué empresa es la organización
 * que va a reescribir convertiría esta pantalla en un editor de empresas
 * ajenas.
 *
 * NINGUNA REGLA DE COHERENCIA VIVE ACÁ, y es a propósito. Las once —dos salas
 * con el mismo identificador, un área reclamada por dos departamentos, un
 * agente sentado en dos sitios, un piso que nadie declaró— están en
 * `nucleo/config/schema.py::Organizacion`, y el editor valida el documento
 * completo antes de escribir. Repetirlas en el formulario sería tener dos
 * verdades sobre lo mismo y descubrir el día que se separen cuál manda.
 *
 * Lo que sí hace esta capa es FORMA: que los números sean números y que las
 * listas escritas con comas lleguen como listas. Eso no es una regla de
 * negocio; es traducir un formulario a un documento.
 *
 * `leer` NO LANZA y `guardar` SÍ. Mismo criterio que sus hermanos: el hub de
 * ajustes carga una docena de cosas a la vez y el asistente es otro servicio
 * que puede no estar desplegado —el síntoma sería «no puedo entrar a
 * configuración» en vez de «el asistente no responde»—. Al guardar, en cambio,
 * alguien apretó un botón y tiene que enterarse.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * La organización vigente, el catálogo de salas y los agentes que existen.
 * `null` si no hay asistente o no contesta.
 */
export async function leerOrganizacion(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/organizacion?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Reemplaza la organización entera.
 *
 * Entera y no campo a campo porque un organigrama no se edita así: mover un
 * departamento de piso, renombrarlo y quitarle un espacio son el mismo gesto
 * para quien lo hace, y guardarlos de a uno dejaría estados intermedios
 * inválidos.
 *
 * @throws {Error} con el mensaje del motor, que es el que explica QUÉ regla se
 *   rompió. Traducirlo a «no se pudo guardar» perdería justo lo único útil.
 */
export async function guardarOrganizacion(locals, fetch, organizacion) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('No hay un asistente configurado para esta empresa.');
  const resp = await fetch(`${cfg.baseUrl}/configuracion/organizacion`, {
    method: 'PUT',
    headers: { ...headersMotor(), 'content-type': 'application/json' },
    body: JSON.stringify({ tenant: cfg.tenant, organizacion })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo guardar la organización.');
  return datos;
}

//  La traduccion del formulario vive aparte y se reexporta: quien configura una
//  pantalla no tiene por que saber que esta partida, y la particion existe por
//  el harness de pruebas (ver el encabezado de ese archivo).
export { comasALista, organizacionDelFormulario } from './organizacion-formulario.js';
