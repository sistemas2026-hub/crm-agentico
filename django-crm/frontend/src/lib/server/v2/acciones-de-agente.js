/**
 * QUÉ PUEDE HACER HOY CADA AGENTE, PARA LA FICHA DE SU PUESTO.
 *
 * Server-only, mismo puente que el resto: habla con el motor y **el tenant sale
 * del servidor, nunca del cliente**.
 *
 * LO QUE LLEGA NO ES LA LISTA BLANCA DEL ROL, y la diferencia es el punto
 * entero de este archivo. La lista blanca es UNO de los ocho pasos de la
 * frontera de autorización: estar en ella no habilita nada. El motor la cruza
 * con el interruptor de autonomía y el techo vigentes —los dos leídos de la
 * base, sin caché— y devuelve `disponible` con su motivo. Mostrar la lista
 * blanca cruda diría que un agente puede reiniciar una ONU con la empresa
 * detenida, que es exactamente la clase de cosa que esta pantalla no afirma.
 *
 * NO ES UN PERMISO. Nada de esto autoriza: no viaja a ningún ejecutor y nadie
 * decide nada mirándolo. La garantía sigue estando en `frontera.exigir()`.
 *
 * QUÉ DATO SALE AL NAVEGADOR. Nombres de herramienta y su descripción — la
 * misma información que `/agentes` ya le sirve a cualquier usuario de la
 * empresa desde que existe esa pantalla, y que esa pantalla tampoco restringe
 * por cargo. Ningún campo de cliente, ninguna credencial, ningún argumento.
 *
 * NO LANZA. La oficina se dibuja igual sin esto: una pantalla de operación que
 * desaparece cuando falla una consulta es peor que una que admite que le falta
 * un dato. `null` significa «no se pudo leer», y la ficha lo dice con esas
 * palabras en vez de mostrar una lista vacía, que se leería como «no puede
 * hacer nada».
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * @returns {Promise<{autonomia: any, acciones: Record<string, any[]>}|null>}
 */
export async function leerAccionesDeAgentes(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/agentes/acciones?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    const datos = await resp.json();
    if (!datos || typeof datos.acciones !== 'object') return null;
    return { autonomia: datos.autonomia ?? null, acciones: datos.acciones ?? {} };
  } catch {
    return null;
  }
}
