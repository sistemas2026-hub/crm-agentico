import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import OrdenDelDia from './OrdenDelDia.svelte';
import RevisionDelCierre from './RevisionDelCierre.svelte';
import { motivosDeLaRevision } from './dia-publicado.js';

/**
 * LO QUE DICE EL SUPERVISOR DEL CIERRE (30/10/2026,
 * SPEC/objetivos/revision-del-cierre.md). Con la forma de
 * `campo/revision_del_cierre.py`: indica, y la persona confirma.
 */
const revision = (extra = {}) => ({
  veredicto: 'se_puede_cerrar',
  texto: 'Se puede cerrar',
  solucion: 'Cambié el conector',
  puntos: [
    { clave: 'checklist', ok: true, texto: 'El checklist está completo: datos y fotos.' },
    { clave: 'servicio', ok: true, texto: 'El técnico afirma que el servicio quedó funcionando.' }
  ],
  evidencias: [{ id: 'foto_ont', titulo: 'Foto de la ONT' }],
  sugeridas: [],
  ...extra
});

//  UNA EVIDENCIA COMO LA MANDA EL BACKEND DESDE EL 06/11/2026: con lo que
//  TENIA que mostrar y con qué ver lo que llegó.
const foto = (extra = {}) => ({
  id: 'foto_ont',
  titulo: 'Foto de la ONT',
  instrucciones: 'El router, con sus luces visibles.',
  obligatoria: true,
  evidencia_id: 'ev-1',
  analisis: '',
  pide_atencion: false,
  muestra_lo_pedido: null,
  ...extra
});

const orden = (extra = {}) => ({
  id: 'o-3', numero: 3, vuelta: 1, estado: 'completada_campo', estado_texto: 'Completada en campo',
  asunto: 'Instalación Tdt', cliente: 'X', tecnicos: [], revision: revision(), ...extra
});

const html = (o) => render(RevisionDelCierre, { props: { orden: o } }).body;

describe('la revisión del cierre en la tarjeta', () => {
  it('dice el veredicto, qué hizo el técnico y cada punto', () => {
    const h = html(orden());
    expect(h).toContain('El Supervisor revisó el cierre:');
    expect(h).toContain('Se puede cerrar');
    expect(h).toContain('Qué hizo: «Cambié el conector»');
    expect(h).toContain('✔');
    expect(h).toContain('El técnico afirma que el servicio quedó funcionando.');
    expect(h).toMatch(/class="rc rc-se_puede_cerrar/);
  });

  it('las dos decisiones, con la orden y su vuelta', () => {
    const h = html(orden({ vuelta: 2 }));
    expect(h).toMatch(/action="\?\/aprobar"/);
    expect(h).toContain('Aprobar y cerrar');
    expect(h).toContain('Devolver al técnico');
    expect(h).toMatch(/name="orden" value="o-3"/);
    expect(h).toMatch(/name="vuelta" value="2"/);
  });

  it('un «no» se marca distinto de un «no se sabe»', () => {
    const h = html(orden({
      revision: revision({
        veredicto: 'no_cerrar', texto: 'No se cierra',
        puntos: [
          { clave: 'servicio', ok: false, texto: 'El técnico dice que el servicio NO quedó funcionando.' },
          { clave: 'material', ok: null, texto: 'No registró material ni confirmó que no usó.' }
        ]
      })
    }));
    expect(h).toMatch(/class="rc rc-no_cerrar/);
    expect(h).toMatch(/class="rc-punto-false[^"]*"><span[^>]*>✖<\/span> El técnico dice que el servicio NO/);
    expect(h).toMatch(/class="rc-punto-null[^"]*"><span[^>]*>\?<\/span> No registró material/);
  });

  it('si el Supervisor la quiso cerrar solo y no pudo, dice cuándo y por qué', () => {
    const h = html(orden({
      revision: revision({ supervisor_no_pudo: { hora: '14:10', detalle: 'NO_AUTORIZADA: B7_REQUERIDO: x' } })
    }));
    expect(h).toContain('El Supervisor la quiso cerrar solo a las 14:10 y el motor no lo dejó: NO_AUTORIZADA: B7_REQUERIDO: x');
    expect(html(orden())).not.toContain('quiso cerrar solo');
  });

  it('si no se sabe si el ISP la cerró, no dice «no lo dejó»', () => {
    const h = html(orden({
      revision: revision({ supervisor_no_pudo: { hora: '15:00', detalle: 'ESTADO_INCIERTO: ReadTimeout' } })
    }));
    expect(h).toContain('no se sabe si el ISP la cerró');
    expect(h).not.toContain('no lo dejó');
  });

  it('sin revisión no dibuja nada', () => {
    expect(html(orden({ revision: null }))).not.toContain('rc-');
  });

  it('en la tarjeta: lo que espera revisión NO se atenúa; lo ya revisado sí', () => {
    const tarjeta = (o) => render(OrdenDelDia, { props: { orden: o, dia: '2026-10-30' } }).body;
    expect(tarjeta(orden())).not.toMatch(/class="od[^"]*od-terminada/);
    expect(tarjeta(orden())).toContain('El Supervisor revisó el cierre:');
    expect(tarjeta(orden({ estado: 'cerrada', revision: null }))).toMatch(/class="od[^"]*od-terminada/);
  });
});

describe('el porqué de una devolución, ya escrito', () => {
  it('lo que no está bien o no se sabe, una línea por punto', () => {
    expect(motivosDeLaRevision({
      puntos: [
        { ok: true, texto: 'bien' },
        { ok: false, texto: 'Falta la foto de la ONT.' },
        { ok: null, texto: 'No registró material.' }
      ]
    })).toBe('Falta la foto de la ONT.\nNo registró material.');
    expect(motivosDeLaRevision(null)).toBe('');
  });
});


/**
 * COMPARAR LO PEDIDO CON LO QUE LLEGO  --  06/11/2026
 *
 * El usuario: «el supervisor debe revisar si las fotos coinciden con lo
 * pedido; si piden foto del router y manda el TV no debe pasar, y si pide la
 * potencia y no manda la potencia no debería pasar».
 *
 * EL HUECO ERA DE INFORMACION, NO DE PODER. «Devolver al técnico» ya existía;
 * lo que no había era con qué decidir: la pantalla decía «El checklist está
 * completo: datos y fotos» --que es contar fotos, no mirarlas-- y los títulos
 * aparecían recién dentro del formulario de devolver, sin la imagen y sin lo
 * que cada una tenía que mostrar.
 */
describe('las fotos, para poder compararlas', () => {
  const html = (evidencias) =>
    render(RevisionDelCierre, {
      props: { orden: orden({ revision: revision({ evidencias }) }) }
    }).body;

  it('dice QUE TENIA QUE MOSTRAR cada foto', () => {
    //  La mitad de la comparación que faltaba.
    const b = html([foto()]);

    expect(b).toContain('El router, con sus luces visibles.');
    expect(b).toContain('Foto de la ONT');
  });

  it('y MUESTRA la que llegó, con enlace para verla grande', () => {
    //  La otra mitad. Una miniatura de 72px no alcanza para juzgar una
    //  lectura de medidor: tiene que poder abrirse.
    const b = html([foto()]);

    expect(b).toContain('/api/supervisor-noc/evidencias/ev-1/archivo');
    expect(b).toMatch(/<img[^>]+ev-1/);
  });

  it('LA QUE FALTA sale igual, y se nota que falta', () => {
    //  EL SEGUNDO CASO DEL USUARIO: «si pide la potencia y no manda la
    //  potencia». Si desapareciera, se verían menos filas sin notar cuál.
    const b = html([foto({ evidencia_id: null })]);

    expect(b).toContain('Foto de la ONT');
    expect(b).toContain('No llegó');
    //  Y no se dibuja una imagen rota apuntando a nada.
    expect(b).not.toMatch(/<img[^>]+evidencias\/null/);
  });

  it('lo que la IA vio se LEE, y se marca cuando pide una mirada', () => {
    //  EL PRIMER CASO DEL USUARIO: «si piden foto del router y manda el TV».
    const b = html([
      foto({ analisis: 'Se ve un televisor encendido, no un router.',
             pide_atencion: true })
    ]);

    expect(b).toContain('Se ve un televisor encendido, no un router.');
    expect(b).toContain('⚠');
    //  Y lo pedido sigue al lado: es lo que permite ver que NO coincide.
    expect(b).toContain('El router, con sus luces visibles.');
  });

  it('«NO es lo que se pidió» se dice APARTE del resto del análisis', () => {
    //  Son dos cosas distintas y mezclarlas le quita a cada una lo suyo:
    //  «se ve un cable suelto» dice que el TRABAJO tiene un problema; «hay un
    //  televisor donde pedían el router» dice que la FOTO está mal. Una se
    //  arregla volviendo a la casa, la otra sacando otra foto.
    const b = html([
      foto({ muestra_lo_pedido: false,
             analisis: 'Se ve un televisor encendido.', pide_atencion: true })
    ]);

    expect(b).toContain('No es lo que se pidió');
  });

  it('«no se sabe» NO se muestra como si no correspondiera', () => {
    //  `null` es "no se puede determinar" --borrosa, oscura, un primer
    //  plano--, y tratarlo como `false` marcaría en rojo fotos que quizás
    //  están bien. El texto del análisis ya dice qué pasó.
    const b = html([
      foto({ muestra_lo_pedido: null, analisis: 'La imagen está muy oscura.' })
    ]);

    expect(b).not.toContain('No es lo que se pidió');
  });

  it('una foto que SÍ corresponde no lleva ninguna marca roja', () => {
    const b = html([
      foto({ muestra_lo_pedido: true, analisis: 'Se ve el router con sus luces.' })
    ]);

    expect(b).not.toContain('No es lo que se pidió');
  });

  it('sin análisis no inventa un visto bueno', () => {
    //  La visión puede estar apagada. Silencio NO es aprobación: la pantalla
    //  no puede mostrar un «lo revisó la IA» que no pasó.
    const b = html([foto({ analisis: '', pide_atencion: false })]);

    expect(b).not.toContain('⚠');
  });

  it('con una plantilla vieja --sin estos datos-- no dibuja la sección vacía', () => {
    //  Compatibilidad: las evidencias de antes son `{id, titulo}` a secas.
    //  Mostrar una lista de fotos sin fotos ni instrucciones sería ruido.
    const b = html([{ id: 'foto_ont', titulo: 'Foto de la ONT' }]);

    expect(b).not.toContain('Las fotos que se pidieron');
  });

  it('la sección NO reemplaza los botones: quien decide sigue decidiendo', () => {
    //  Esto informa; no aprueba ni rechaza nada por su cuenta.
    const b = html([foto()]);

    expect(b).toContain('Aprobar y cerrar');
    expect(b).toContain('Devolver al técnico');
  });
});
