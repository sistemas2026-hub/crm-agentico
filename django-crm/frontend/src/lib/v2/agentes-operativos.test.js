import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { AGENTES_OPERATIVOS } from './agentes-operativos.js';

/**
 * EL SUPERVISOR NOC IA NO APARECÍA, Y NO ERA UN FALLO.
 *
 * `/agentes` lista lo que devuelve el motor, y el motor solo conoce sus roles
 * conversacionales. El Supervisor vive en el CRM, no habla con nadie y no
 * tiene prompt: no había forma de que la pantalla lo viera.
 *
 * Estas pruebas afirman las tres cosas que hacen que la tarjeta esté bien
 * puesta, y las tres se pueden romper sin que nada más avise:
 *
 *   1. que lleve a un tablero que EXISTE;
 *   2. que NO declare métricas — un número escrito aquí envejece solo;
 *   3. que la tarjeta esté FUERA del bloque que depende del motor, o un fallo
 *      del motor borraría de la pantalla un agente que está vivo.
 */

const PANTALLA = new URL('../../routes/(app)/agentes/+page.svelte', import.meta.url);
const fuente = () => readFileSync(PANTALLA, 'utf8');

describe('la ficha del agente operativo', () => {
  it('trae al Supervisor NOC IA con su rótulo de familia', () => {
    const s = AGENTES_OPERATIVOS.find((a) => a.clave === 'supervisor-noc');

    expect(s).toBeDefined();
    expect(s.nombre).toBe('Supervisor NOC IA');
    expect(s.rotulo).toBe('Agente operativo · Supervisión técnica');
  });

  it('lleva al tablero que ya existe', () => {
    const s = AGENTES_OPERATIVOS[0];
    expect(s.href).toBe('/supervisor-noc');
  });

  it('dice lo que el Supervisor NO hace, que es la mitad de lo que hay que saber', () => {
    const d = AGENTES_OPERATIVOS[0].descripcion.toLowerCase();
    expect(d).toMatch(/no conversa/);
    expect(d).toMatch(/no ejecuta/);
  });

  it('NO declara ninguna métrica', () => {
    //  Cuántas propuestas tiene pendientes cambia cada minuto. Un número aquí
    //  sería una segunda verdad que envejece sola; el tablero lo muestra con
    //  su fuente.
    for (const a of AGENTES_OPERATIVOS) {
      for (const valor of Object.values(a)) {
        expect(String(valor)).not.toMatch(/\b\d+\s*(propuestas?|hallazgos?|señales?|habilidades?)\b/i);
      }
      expect(a).not.toHaveProperty('metricas');
      expect(a).not.toHaveProperty('pendientes');
    }
  });
});

describe('la tarjeta en la pantalla', () => {
  it('se pinta ANTES del bloque que depende del motor', () => {
    //  Si estuviera dentro del `{#if data.error}`, un fallo del motor borraría
    //  de la pantalla un agente que vive en el CRM y está perfectamente vivo.
    const t = fuente();
    const tarjeta = t.indexOf('AGENTES_OPERATIVOS as operativo');
    const bloqueDelMotor = t.indexOf('{#if data.error}');

    expect(tarjeta).toBeGreaterThan(-1);
    expect(bloqueDelMotor).toBeGreaterThan(-1);
    expect(tarjeta).toBeLessThan(bloqueDelMotor);
  });

  it('usa la ficha y no repite los textos a mano', () => {
    const t = fuente();
    expect(t).toMatch(/AGENTES_OPERATIVOS/);
    //  El nombre no está escrito en el marcado: sale de la ficha, así que
    //  cambiarlo en un solo sitio cambia la pantalla.
    expect(t).not.toMatch(/>Supervisor NOC IA</);
  });

  it('cada clase que usa la tarjeta está definida en la pantalla', () => {
    //  El CSS no avisa de una clase que no existe: el elemento simplemente no
    //  toma el estilo. Misma guarda que clases-snoc.test.js.
    const t = fuente();
    for (const clase of ['tarjeta-operativa', 'pill-operativo', 'enlace-tablero',
                         'seccion-operativos', 'titulo-familia', 'nota-familia']) {
      expect(t, `falta .${clase} en el <style>`).toMatch(new RegExp(`\\.${clase}[\\s,{:]`));
    }
  });

  it('no registra al Supervisor como rol del tenant', () => {
    //  Declararlo rol lo metería en el enrutador de derivación del motor, y
    //  alguien podría acabar derivándole un cliente.
    //
    //  Se mira el OBJETO, no el texto del archivo: la primera versión de esta
    //  prueba buscaba las palabras en el fuente y se caía por el comentario
    //  que explica justamente por qué no se hace.
    for (const a of AGENTES_OPERATIVOS) {
      for (const campoDeRol of ['puede_consultar', 'campos_permitidos', 'exige_verificacion',
                                'orientado_a', 'motivos_escalada', 'herramientas']) {
        expect(a, `${a.clave} no debe declarar ${campoDeRol}`).not.toHaveProperty(campoDeRol);
      }
    }
  });
});
