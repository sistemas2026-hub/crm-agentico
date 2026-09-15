import { env } from '$env/dynamic/private';

/**
 * El header que nucleo/canales/api.py::_exigir_token_de_servicio exige
 * quando `MOTOR_SERVICE_TOKEN` esta configurado en el motor. Sin la
 * variable puesta ACA (`PRIVATE_MOTOR_SERVICE_TOKEN`), no se manda nada --
 * mismo criterio permisivo-por-defecto que el propio motor: no romper un
 * entorno que todavia no cargo la variable en los dos lados.
 *
 * Uso: fetch(url, { headers: headersMotor({ 'Content-Type': 'application/json' }) })
 * @param {Record<string, string>} extra
 * @returns {Record<string, string>}
 */
export function headersMotor(extra = {}) {
  const token = env.PRIVATE_MOTOR_SERVICE_TOKEN;
  return token ? { ...extra, 'X-Servicio-Token': token } : extra;
}
