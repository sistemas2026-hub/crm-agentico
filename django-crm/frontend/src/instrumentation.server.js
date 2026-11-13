import * as Sentry from '@sentry/sveltekit';
import { env } from '$env/dynamic/public';
import {
  ERRORES_IGNORADOS,
  limpiarEvento,
  limpiarLog,
  limpiarMiga,
  limpiarTransaccion
} from '$lib/observabilidad/privacidad.js';

// Mismo contrato que el cliente (hooks.client.js): sin DSN no sale nada; con
// DSN, nada sale sin pasar por $lib/observabilidad/privacidad.js. El servidor
// ve ademas las peticiones que proxea al motor -- cuerpos con texto de
// clientes -- y las cookies con el JWT: por eso sendDefaultPii es false y el
// `request` del evento se reduce a metodo y ruta sin query.
const dsn = env.PUBLIC_SENTRY_DSN || '';

Sentry.init({
  dsn,
  enabled: !!dsn,
  sendDefaultPii: false,
  tracesSampleRate: 1.0,
  enableLogs: true,
  ignoreErrors: ERRORES_IGNORADOS,
  beforeSend: limpiarEvento,
  beforeBreadcrumb: limpiarMiga,
  beforeSendTransaction: limpiarTransaccion,
  beforeSendLog: limpiarLog
});
