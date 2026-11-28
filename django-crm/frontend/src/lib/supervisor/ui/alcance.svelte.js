/**
 * EL ALCANCE DEL SUPERVISOR: nivel de autonomía y freno de mano.
 *
 * Vivía dentro de Pendientes (08/10/2026), en un modal que solo se abría
 * desde allí, y Ajustes mandaba a la persona a buscarlo: «el nivel y el freno
 * se cambian en Pendientes → botón Autonomía». Desde el 21/11/2026 (rediseño
 * aprobado) la misma lógica sirve a las dos pantallas.
 *
 * Habla con `/api/supervisor-noc/autonomia` (GET lee, PUT cambia el nivel,
 * POST mueve el freno). Los mensajes del backend se muestran TAL CUAL: ya
 * dicen cuál de los requisitos falta.
 */
import { invalidateAll } from '$app/navigation';

export class Alcance {
  /** @type {any} */
  estado = $state(null);
  cargando = $state(false);
  guardando = $state(false);
  error = $state('');
  /** @type {number | null} */
  nivelElegido = $state(null);
  motivoNivel = $state('');
  criterios = $state('');
  motivoFreno = $state('');

  /**
   * Si el freno está puesto (el interruptor NO permite actuar). Solo un
   * `false` explícito: un dato que falta no es un freno puesto. Es la misma
   * regla que `tarjetasDeSolo`, para que el botón de la cabecera y el panel
   * no digan cosas distintas (21/11/2026).
   */
  get frenado() {
    return this.estado?.interruptor_permite === false;
  }

  async leer() {
    this.error = '';
    this.cargando = !this.estado;
    try {
      const r = await fetch('/api/supervisor-noc/autonomia');
      const d = await r.json();
      if (!r.ok) {
        this.error = d?.error ?? 'No se pudo leer el alcance.';
      } else {
        this.estado = d;
        this.nivelElegido = d.configurado;
      }
    } catch (/** @type {any} */ e) {
      this.error = `No se pudo leer el alcance: ${e?.message ?? e}`;
    } finally {
      this.cargando = false;
    }
  }

  /** @returns {Promise<boolean>} si se guardó */
  async guardarNivel() {
    this.guardando = true;
    this.error = '';
    try {
      const r = await fetch('/api/supervisor-noc/autonomia', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nivel: this.nivelElegido, motivo: this.motivoNivel, criterios: this.criterios })
      });
      const d = await r.json();
      if (!r.ok) {
        this.error = d?.error ?? 'No se pudo cambiar el nivel.';
        return false;
      }
      this.estado = { ...this.estado, ...d };
      this.motivoNivel = '';
      this.criterios = '';
      await invalidateAll();
      return true;
    } catch (/** @type {any} */ e) {
      this.error = `No se pudo cambiar el nivel: ${e?.message ?? e}`;
      return false;
    } finally {
      this.guardando = false;
    }
  }

  /**
   * @param {boolean} detener
   * @returns {Promise<boolean>} si se movió
   */
  async moverFreno(detener) {
    this.guardando = true;
    this.error = '';
    try {
      const r = await fetch('/api/supervisor-noc/autonomia', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detener, motivo: this.motivoFreno })
      });
      const d = await r.json();
      if (!r.ok) {
        this.error = d?.error ?? 'No se pudo mover el interruptor.';
        return false;
      }
      this.estado = { ...this.estado, ...d };
      this.motivoFreno = '';
      await invalidateAll();
      return true;
    } catch (/** @type {any} */ e) {
      this.error = `No se pudo mover el interruptor: ${e?.message ?? e}`;
      return false;
    } finally {
      this.guardando = false;
    }
  }
}
