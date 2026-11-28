/**
 * ============================================================================
 *  CÓMO QUEDÓ CADA FOTO  --  17/11/2026
 * ============================================================================
 * Lo que estas guardas afirman es el EFECTO sobre la línea que el supervisor
 * lee: qué dice, y sobre todo CUÁNDO NO DICE NADA.
 *
 * El riesgo entero de este cambio está en el `null`. Resumir ocho renglones
 * en una línea es fácil; lo difícil es no convertir una ausencia de revisión
 * en un visto bueno. El componente ya tenía esa guarda («sin análisis no
 * inventa un visto bueno») y acá se mide en la función que ahora decide.
 * ============================================================================
 */
import { describe, it, expect } from 'vitest';
import { comoQuedoLaFoto } from './estado-de-la-foto.js';

/** Una evidencia como la manda el backend. */
const foto = (extra = {}) => ({
  evidencia_id: 'ev-1',
  instrucciones: 'El router, con sus luces visibles.',
  analisis: '',
  pide_atencion: false,
  muestra_lo_pedido: null,
  ...extra
});

describe('comoQuedoLaFoto', () => {
  it('sin análisis NO dice nada: ni ✓ ni ⚠', () => {
    //  LA GUARDA QUE ORDENA TODO LO DEMÁS. La visión puede estar apagada
    //  para esa empresa. Un ✓ acá sería la pantalla afirmando una revisión
    //  que no pasó, y los otros campos vienen en su valor por defecto
    //  --`false`, `null`-- justamente porque nadie los escribió.
    expect(comoQuedoLaFoto(foto({ analisis: '' })).ok).toBe(null);
    expect(comoQuedoLaFoto(foto({ analisis: '' })).texto).toBe('');
  });

  it('la foto mirada y sin problemas dice «sin observaciones», no «está bien»', () => {
    //  El modelo no afirma que la foto sirva: afirma que no vio nada que
    //  llame la atención. Misma distinción que `inspeccion_visual.py`
    //  (31/10/2026): la IA puede pedir atención, nunca aprobar.
    const q = comoQuedoLaFoto(foto({
      analisis: 'Se ve el router con sus luces.', muestra_lo_pedido: true
    }));

    expect(q.ok).toBe(true);
    expect(q.texto).toBe('Sin observaciones.');
    expect(q.texto).not.toMatch(/bien|correcta|aprob/i);
  });

  it('la que no llegó lo dice, aunque no haya nada más', () => {
    const q = comoQuedoLaFoto(foto({ evidencia_id: null, analisis: '' }));

    expect(q.ok).toBe(false);
    expect(q.texto).toBe('No llegó.');
  });

  it('«no es lo que se pidió» gana sobre «pide una mirada»', () => {
    //  Son dos problemas con dos arreglos distintos: uno se arregla sacando
    //  otra foto, el otro volviendo a la casa. En una línea sola va el más
    //  específico, y el detalle sigue teniendo los dos.
    const q = comoQuedoLaFoto(foto({
      analisis: 'Se ve un televisor encendido.',
      muestra_lo_pedido: false, pide_atencion: true
    }));

    expect(q.texto).toBe('No es lo que se pidió.');
  });

  it('la que pide una mirada lo dice', () => {
    const q = comoQuedoLaFoto(foto({
      analisis: 'Se ve un cable suelto detrás del equipo.',
      muestra_lo_pedido: true, pide_atencion: true
    }));

    expect(q.ok).toBe(false);
    expect(q.texto).toBe('Pide una mirada.');
  });

  it('«no se sabe» con instrucciones se dice, y NO como «no es lo que se pidió»', () => {
    //  `null` es «no se puede determinar» --borrosa, oscura, un primer
    //  plano--, y tratarlo como `false` marcaría como foto equivocada una
    //  que quizás está bien.
    const q = comoQuedoLaFoto(foto({
      analisis: 'La imagen está muy oscura.', muestra_lo_pedido: null
    }));

    expect(q.ok).toBe(false);
    expect(q.texto).toContain('No se pudo determinar');
    expect(q.texto).not.toContain('No es lo que se pidió');
  });

  it('«no se sabe» SIN instrucciones no marca nada: no se le pidió nada', () => {
    //  Sin instrucciones el modelo no escribe la línea `MUESTRA:` (regla 12
    //  de `nucleo/canales/vision.py`), así que ese `null` no es una duda
    //  sobre la foto: es que nadie declaró qué tenía que mostrar. Marcarlo
    //  pondría un interrogante permanente en toda plantilla que no las
    //  tenga, y un interrogante permanente se aprende a ignorar.
    const q = comoQuedoLaFoto(foto({
      analisis: 'Se ve un equipo sobre una mesa.',
      muestra_lo_pedido: null, instrucciones: ''
    }));

    expect(q.ok).toBe(true);
    expect(q.texto).toBe('Sin observaciones.');
  });
});
