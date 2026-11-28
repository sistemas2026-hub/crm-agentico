/**
 * Cómo se dicen los niveles de respuesta en Plantillas (24/10/2026). Fuera
 * del componente para poder probarlo: «quién lo decidió» es lo que hace que
 * una persona confíe en lo que puso el Supervisor, y se rompe sin que la
 * pantalla se vea rota.
 */

/** @param {number} dias */
export function textoDelPlazo(dias) {
  const n = Number(dias);
  if (n === 0) return 'mismo día';
  return n === 1 ? '1 día' : `${n} días`;
}

/**
 * Quién decidió el nivel de un asunto, y por qué.
 *
 * @param {{ por?: string | null, nivel?: string | null, motivo?: string,
 *           decidido_por?: string, decidido_en?: string | null }} a
 * @param {(iso: string) => string} [fecha]
 */
export function quienLoDecidio(a, fecha) {
  //  Un asunto de una plantilla que todavía nadie ubicó (sin el Supervisor
  //  ubicándolos, lo pone una persona).
  if (!a?.por) return 'Sin nivel todavía';
  if (a?.por === 'persona') {
    const quien = (a.decidido_por || '').trim() || 'Una persona';
    const cuando = a.decidido_en && fecha ? `, ${fecha(a.decidido_en)}` : '';
    return `${quien}${cuando} · el Supervisor no lo vuelve a tocar`;
  }
  const motivo = (a?.motivo || '').trim();
  return motivo ? `Supervisor · ${motivo}` : 'Supervisor';
}
