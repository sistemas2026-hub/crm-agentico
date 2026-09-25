import * as Sentry from '@sentry/sveltekit';
import { env } from '$env/dynamic/public';
import {
  ERRORES_IGNORADOS,
  OPCIONES_REPLAY,
  limpiarEvento,
  limpiarLog,
  limpiarMiga,
  limpiarTransaccion
} from '$lib/observabilidad/privacidad.js';
import { esChunkViejo, recargarUnaVez, vigilarChunksViejos } from '$lib/observabilidad/recarga.js';

// Sin DSN no hay proveedor: hoy produccion corre asi. Cuando se configure uno,
// TODO lo que salga pasa por $lib/observabilidad/privacidad.js -- ver
// OBSERVABILIDAD_Y_PRIVACIDAD.md en la raiz del repo para el contrato.
const dsn = env.PUBLIC_SENTRY_DSN || '';

Sentry.init({
  dsn,
  enabled: !!dsn,
  // Nunca datos personales por defecto (IP, cabeceras, cookies, usuario).
  sendDefaultPii: false,
  tracesSampleRate: 1.0,
  enableLogs: true,
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,
  // El replay graba la forma de la pantalla, no el texto: todo enmascarado,
  // entradas enmascaradas, medios bloqueados, y las areas con datos de
  // clientes (bandeja, paneles, instalaciones, solicitud) bloqueadas enteras.
  integrations: [Sentry.replayIntegration(OPCIONES_REPLAY)],
  // Ruido de extensiones del navegador, no de Dexter.
  ignoreErrors: ERRORES_IGNORADOS,
  // Cada cosa que sale, limpia. Si limpiar falla, no sale.
  beforeSend: limpiarEvento,
  beforeBreadcrumb: limpiarMiga,
  beforeSendTransaction: limpiarTransaccion,
  beforeSendLog: limpiarLog
});

// Una pestaña abierta antes de un deploy pide chunks que ya no existen. Ver
// $lib/observabilidad/recarga.js: se recarga UNA vez, no en bucle.
vigilarChunksViejos();

const reportarASentry = Sentry.handleErrorWithSentry();

/**
 * El tercer camino por donde llega un chunk viejo: el error de una navegacion
 * de SvelteKit. Se recarga y se le devuelve al operador un aviso en vez de la
 * pantalla de error -- si la recarga sale, el mensaje no llega a verse.
 *
 * Todo lo demas sigue yendo a Sentry como antes.
 */
export function handleError(entrada) {
  if (esChunkViejo(entrada?.error) && recargarUnaVez()) {
    return { message: 'Actualizando a la versión nueva…' };
  }
  return reportarASentry(entrada);
}
