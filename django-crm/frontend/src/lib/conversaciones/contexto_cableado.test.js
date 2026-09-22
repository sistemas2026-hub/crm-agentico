/**
 * Los paneles de contexto (fase 1.5).
 *
 * Dos cosas que ninguna otra guarda ve:
 *
 * 1. D28 — el dueño del ticket del CRM NO es quien atiende la conversación.
 *    El panel mostraba el primero rotulado sólo como «Asignado a», y era fácil
 *    leerlo como si dijera quién está atendiendo. Ahora lo dice cuando no
 *    coinciden; el riesgo nuevo es que lo diga cuando SÍ coinciden, o cuando
 *    falta uno de los dos, y entonces el aviso se vuelve ruido que nadie lee.
 *
 * 2. Los cuatro tokens semánticos (ember/clay/rust/moss) que 1.1 dejó sin
 *    remapear a propósito, para resolverlos «en la fase de su pantalla,
 *    consumidor por consumidor». Ésta es esa fase para los paneles de
 *    contexto: si vuelve a aparecer uno, es que alguien agregó un consumidor
 *    sin decidir su significado.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const dir = fileURLToPath(new URL('./context/', import.meta.url));
const leer = (f) => readFileSync(dir + f, 'utf-8');
const paneles = readdirSync(dir).filter((f) => f.endsWith('.svelte'));
const caso = leer('CasePanel.svelte');

describe('D28: los dos dueños no se confunden', () => {
  it('el aviso exige que los DOS nombres consten', () => {
    // Sin el dueño de Dexter no hay nada que contrastar, y avisar seria
    // afirmar una diferencia que no se midio.
    expect(caso).toMatch(/!!nombreCrm && !!asignadaDexter/);
  });

  it('y que sean distintos, comparando sin espacios de sobra', () => {
    expect(caso).toMatch(/nombreCrm !== asignadaDexter\.trim\(\)/);
  });

  it('el aviso solo se dibuja bajo esa condición', () => {
    expect(caso).toMatch(/\{#if duenosDistintos\}[\s\S]{0,600}aviso-duenos/);
  });

  it('el rótulo del CRM dice de quién es el ticket, no quién atiende', () => {
    expect(caso).toMatch(/Dueño del ticket/);
    expect(caso).toMatch(/A cargo en Dexter/);
    // El rotulo viejo, ambiguo, no vuelve.
    expect(caso).not.toMatch(/>Asignado a</);
  });

  it('la aclaración de autoridad va SIEMPRE, no dentro del if del aviso', () => {
    // Éste es el caso homónimo: dos nombres iguales no prueban que sean la
    // misma persona -- el CRM y Dexter no comparten identidad de usuario.
    // Sin esta línea, dos "Juan Pérez" se leerían como "está bien asignado".
    // En el MARKUP: la clase sola no alcanza, porque una regla huérfana en el
    // <style> la dejaría "presente" con el párrafo ya borrado.
    const markup = caso.slice(caso.indexOf('</script>'), caso.indexOf('<style>'));
    expect(markup).toMatch(/class="nota-autoridad"/);
    const bloqueSiDistintos = caso.slice(
      caso.indexOf('{#if duenosDistintos}'),
      caso.indexOf('{/if}', caso.indexOf('{#if duenosDistintos}'))
    );
    expect(bloqueSiDistintos).not.toMatch(/nota-autoridad/);
  });

  it('y dice cuál de los dos sistemas manda', () => {
    expect(caso).toMatch(/asignación del CRM es informativa/i);
    expect(caso).toMatch(/lo\s+determina Dexter/);
  });

  it('nunca afirma que los dueños sean la misma persona', () => {
    // Sobre el TEXTO VISIBLE, no sobre el archivo: los comentarios del código
    // dicen justamente lo contrario (que no se puede afirmar), y buscarlos ahí
    // haría fallar la prueba por explicar bien la regla.
    const visible = caso
      .slice(caso.indexOf('</script>'), caso.indexOf('<style>'))
      .replace(/<!--[\s\S]*?-->/g, '');
    for (const frase of [
      /misma persona/i, /coinciden/i, /sincronizad/i,
      /correctamente asignad/i, /mismo (dueño|responsable)/i
    ]) {
      expect(visible).not.toMatch(frase);
    }
  });

  it('no inventa un id compartido para comparar', () => {
    // Comparar por id exigiria una reconciliacion CRM/Dexter que no existe.
    // D28 sigue abierto: la pantalla lo dice, no lo resuelve.
    expect(caso).not.toMatch(/ownerActual\??\.id\s*===|assigned_to\s*===/);
  });

  it('el dueño durable llega resuelto de la página, no se deduce acá', () => {
    // Si el panel lo dedujera (legado vs gobernada), esa regla viviria en dos
    // lugares y podria decir algo distinto que el encabezado.
    expect(caso).not.toMatch(/asignada_a_nombre|tomada_por|relevo_version/);
  });
});

describe('no se inventan campos', () => {
  it('el ticket operativo sólo se muestra si la conversación tiene uno', () => {
    expect(caso).toMatch(/\{#if conversacion\.ticket_operativo\}/);
  });

  it('no aparecen área ni prioridad del ticket operativo', () => {
    // Stitch los muestra; Dexter no los tiene. Un campo inventado en un panel
    // de contexto se lee como un dato del cliente.
    expect(caso).not.toMatch(/Prioridad|Área operativa/);
  });
});

describe('los cuatro semánticos quedaron resueltos en esta pantalla', () => {
  it.each(paneles)('%s no usa ember/clay/rust/moss sin decidir', (f) => {
    expect(leer(f)).not.toMatch(/var\(--v2-(ember|clay|rust|moss)/);
  });

  it('y se resolvieron a los tokens de la Bandeja, no a colores sueltos', () => {
    const trace = leer('TracePanel.svelte');
    expect(trace).toMatch(/var\(--bandeja-ok\)/);       // ejecución normal
    expect(trace).toMatch(/var\(--bandeja-aviso\)/);    // bloqueo: no es un fallo
    expect(trace).toMatch(/var\(--bandeja-error\)/);    // error real del sistema
    expect(trace).not.toMatch(/#[0-9a-f]{6}/i);
  });
});

describe('los paneles comparten sus piezas, no las copian', () => {
  // Hasta el cierre de la Fase 1 cada panel tenía su propia copia de estas
  // cuatro reglas. Tres eran idénticas; `.mono` NO -- y el mismo tipo de dato
  // se veía distinto en tres paneles apilados en la misma columna. Con el CSS
  // scopeado de Svelte eso no lo ve ninguna herramienta: hay que mirar los
  // tres juntos.
  const COMPARTIDAS = ['bloque-titulo', 'dato', 'mono', 'nota-fuente'];

  it.each(paneles)('%s no redefine las utilidades de panel', (f) => {
    const estilo = leer(f).split('<style>')[1] ?? '';
    for (const c of COMPARTIDAS) {
      expect(estilo).not.toContain(`\n  .${c} {`);
    }
  });

  it('y las usan con el prefijo propio, que no colisiona con el CRM', () => {
    // `.dato` y `.mono` ya existen en componentes del CRM fuera de la mesa.
    const usados = paneles.map(leer).join('\n');
    expect(usados).toMatch(/class="panel-titulo/);
    expect(usados).toMatch(/panel-mono/);
  });

  it('las utilidades viven en bandeja.css, scopeadas a la mesa', () => {
    const css = readFileSync(
      fileURLToPath(new URL('./estilos/bandeja.css', import.meta.url)), 'utf-8');
    for (const c of ['panel-titulo', 'panel-dato', 'panel-mono', 'panel-nota']) {
      expect(css).toContain(`.bandeja .${c} {`);
    }
  });

  it('y `panel-mono` lleva las dos propiedades que estaban repartidas', () => {
    const css = readFileSync(
      fileURLToPath(new URL('./estilos/bandeja.css', import.meta.url)), 'utf-8');
    const regla = css.slice(css.indexOf('.bandeja .panel-mono'));
    expect(regla.slice(0, 220)).toMatch(/tabular-nums/);
    expect(regla.slice(0, 220)).toMatch(/overflow-wrap: anywhere/);
  });
});

describe('la actividad no se queda vieja', () => {
  const pagina = readFileSync(
    fileURLToPath(new URL('../../routes/(app)/conversaciones/[id]/+page.svelte', import.meta.url)),
    'utf-8'
  );
  const server = readFileSync(
    fileURLToPath(new URL('../../routes/(app)/conversaciones/[id]/+page.server.js', import.meta.url)),
    'utf-8'
  );

  it('el load declara un identificador PROPIO, no el del sondeo del layout', () => {
    // 'app:conversaciones' lo invalida el reloj del layout cada pocos segundos
    // para refrescar la lista. Colgar este load de ahí recargaría el hilo
    // entero, las herramientas y el ticket del CRM en cada vuelta.
    expect(server).toMatch(/depends\('app:relevo'\)/);
    expect(server).not.toMatch(/depends\('app:conversaciones'\)/);
  });

  it('refrescar lee de nuevo del motor y no arma el evento en la pantalla', () => {
    const fn = pagina.slice(pagina.indexOf('async function refrescarRelevo'));
    expect(fn.slice(0, 500)).toMatch(/await invalidate\('app:relevo'\)/);
    expect(fn.slice(0, 500)).toMatch(/relevo = data\.relevo/);
    // Nada de empujar una línea inventada mientras llega la de verdad.
    expect(fn.slice(0, 500)).not.toMatch(/relevo\.push|\.unshift/);
  });

  it('toda transición que deja evento lo refresca', () => {
    // tomar · reasignar · intervenir · cerrar · enviar T6 · reintentar T6
    const veces = (pagina.match(/await refrescarRelevo\(\)/g) ?? []).length;
    expect(veces).toBeGreaterThanOrEqual(6);
  });

  it('y lo hace DESPUÉS de que la petición respondió, nunca antes', () => {
    // Si se refrescara al lanzarla, el panel mostraría un movimiento que
    // todavía puede no haber ocurrido. Es un registro de auditoría.
    for (const bloque of pagina.split('await refrescarRelevo()').slice(0, -1)) {
      expect(bloque).toMatch(/await fetch\([\s\S]*$/);
    }
  });

  it('sin sondeo ni temporizadores propios', () => {
    const fn = pagina.slice(
      pagina.indexOf('async function refrescarRelevo'),
      pagina.indexOf('async function refrescarRelevo') + 700
    );
    expect(fn).not.toMatch(/setInterval|setTimeout/);
  });

  it('un T6 que NO volvió a la IA también refresca', () => {
    // 'devolucion_fallida' es un evento, y es justo el que alguien va a
    // querer ver: refrescar sólo en el éxito escondería el movimiento.
    expect(pagina).toMatch(/if \(devolviendo\) await refrescarRelevo\(\)/);
    expect(pagina).toMatch(/if \(m\.devolver === true\) await refrescarRelevo\(\)/);
  });
});

describe('el panel del cliente no inventa la ficha', () => {
  const cli = leer('CustomerPanel.svelte');
  const visible = cli
    .slice(cli.indexOf('</script>'), cli.indexOf('<style>'))
    .replace(/<!--[\s\S]*?-->/g, '');
  // La nota que explica qué NO está nombra esos mismos campos; buscarlos ahí
  // haría fallar la prueba por decir bien la verdad.
  const campos = visible.replace(/<p class="panel-nota">[\s\S]*?<\/p>/, '');

  it('no muestra los campos que la referencia marca como MOCK', () => {
    // Dirección, plan, velocidades, saldo y facturas viven en el ISP y Dexter
    // no los guarda (PRD RNF-01). Un campo inventado en un panel de contexto
    // se lee como un dato del cliente.
    for (const campo of [/direcci[oó]n/i, /localidad/i, /\bplan\b/i, /saldo/i,
                         /factura/i, /\bpago\b/i, /Mbps/i]) {
      expect(campos).not.toMatch(campo);
    }
  });

  it('dice por qué no están, en vez de dejar secciones vacías', () => {
    expect(visible).toMatch(/viven en el sistema del ISP y no se traen/i);
  });

  it('no consulta nada en vivo: es presentación', () => {
    expect(cli).not.toMatch(/fetch\(|onMount|\$effect/);
  });

  it('la verificación se deriva de id_cliente, que es lo que la prueba', () => {
    // Los campos técnicos sólo se escriben al verificar, y verificar exige
    // id_cliente. No hay bandera aparte que inventar.
    expect(cli).toMatch(/verificado = \$derived\(!!conversacion\?\.id_cliente\)/);
  });

  it('sin verificar se avisa que nada está confirmado, y en ámbar', () => {
    expect(visible).toMatch(/nada de lo de abajo está confirmado/i);
    expect(cli).toMatch(/\.v-no \{[\s\S]{0,200}--bandeja-aviso/);
    expect(cli).not.toMatch(/\.v-no \{[\s\S]{0,200}--bandeja-error/);
  });

  it('un campo de equipo que el tenant agregue se muestra igual', () => {
    // El motor ya lo manda (filtra por CAMPOS_PERSISTIBLES); esconderlo acá
    // perdería un dato que alguien fue a buscar.
    expect(cli).toMatch(/ROTULO_EQUIPO\[clave\] \?\? clave\.replaceAll/);
  });
});

describe('el panel de red no ejecuta ni inventa', () => {
  const red = leer('NetworkPanel.svelte');
  const visible = red
    .slice(red.indexOf('</script>'), red.indexOf('<style>'))
    .replace(/<!--[\s\S]*?-->/g, '');
  const campos = visible.replace(/<p class="panel-nota">[\s\S]*?<\/p>/, '');

  /* ESTAS CUATRO GUARDAS CAMBIARON EL 21/09/2026, Y HAY QUE DECIR POR QUÉ.
     Decían: el panel no tiene botones, no consulta nada, no muestra `dBm` y
     explica que la telemetría no se ve acá. Protegían una decisión real --no
     convertir la Bandeja en una segunda fuente de verdad, ni abrir una segunda
     puerta a una acción que corta el servicio.
     La decisión de producto se invirtió: el estado del enlace SÍ se lee en
     vivo desde la pantalla. Lo que no cambió es el motivo por el que la guarda
     existía, así que no se borran: se reescriben sobre lo que ahora hay que
     sostener. Una guarda que se elimina porque se puso roja deja de proteger
     sin que nadie lo decida. */

  it('reiniciar no se dispara de un solo clic', () => {
    /* El reinicio entró el 21/09/2026 y esta guarda cambió con él -- saltó
       justo cuando apareció, que es para lo que estaba puesta.
       Lo que ahora protege: que el botón NO llame al endpoint. Tiene que
       abrir la confirmación, y la confirmación exige un motivo. Un botón que
       ejecutara directo dejaría a un cliente sin servicio por un clic mal
       puesto en una columna de 304px. */
    const [, trasElBoton = ''] = red.split(/onclick=\{\(\) => \{ pidiendoReinicio = true/);
    expect(red).toMatch(/pidiendoReinicio = true/);
    expect(trasElBoton.slice(0, 200)).not.toMatch(/fetch\(/);
    // Y sin motivo el botón de confirmar está deshabilitado.
    expect(red).toMatch(/disabled=\{reiniciando \|\| !motivoReinicio\.trim\(\)\}/);
    // La función tampoco sale sin motivo, aunque alguien altere el `disabled`.
    expect(red).toMatch(/if \(reiniciando \|\| !motivo/);
  });

  it('no afirma que el equipo reinició: sólo que se pidió', () => {
    /* 'ACCION_CONFIRMADA' significa que el equipo reinició y volvió, y eso
       lo dice la comprobación posterior, no la respuesta del ISP. Decir
       "reiniciado" cuando sólo se aceptó la orden es afirmar un efecto que
       todavía no se midió. */
    const prosa = visible.replace(/\s+/g, ' ');
    expect(prosa).toMatch(/Reinicio pedido/i);
    expect(prosa).not.toMatch(/equipo reiniciado con éxito|se reinició correctamente/i);
  });

  it('no consulta en bucle: el proveedor lo pide expresamente', () => {
    // ~10 s por consulta y la skill `smartolt-api` pide no usarla en polling.
    // Un `setInterval` acá sería exactamente eso.
    expect(red).not.toMatch(/setInterval/);
  });

  it('ninguna medición se muestra sin la hora en que se leyó', () => {
    // Un valor óptico sin su hora es una afirmación sobre el presente que
    // puede tener cinco minutos, y con eso se decide si mandar un técnico.
    expect(visible).toMatch(/leido_en|leído|Leído/);
  });

  it('no muestra campos sin fuente conocida', () => {
    /* LA LISTA SE ACORTÓ EL 22/09/2026, Y NO POR CAPRICHO.
       `PON` y `CTO` estaban acá porque se había concluido que ningún sistema
       conectado los exponía. Era falso: `get_onu_details/{sn}` de SmartOLT
       devuelve `olt_id`, `olt_name`, `board`, `port`, `onu`, `zone_name` y
       `odb_name` --la caja, o sea el CTO-- y está verificado en vivo
       (14/08/2026, skill `smartolt-api`). Se conectó, y salieron de la lista.

       Los que quedan siguen sin fuente: ningún endpoint de los sistemas
       conectados los devuelve. El día que alguno lo haga, esta prueba se
       pone roja y ahí se decide -- que es para lo que está. */
    for (const campo of [/\bMAC\b/, /firmware/i, /temperatura/i,
                         /voltaje/i, /bias/i, /dispositivos conectados/i]) {
      expect(campos).not.toMatch(campo);
    }
  });

  it('la topología no arrastra el nombre del cliente', () => {
    /* `get_onu_details` devuelve `name`: el nombre completo del cliente en el
       registro de la ONU (marcado 🔴 en la skill). El endpoint lo descarta
       con una lista blanca; acá se comprueba que la pantalla tampoco lo pida
       por su cuenta. */
    expect(red).not.toMatch(/topologia\??\.name\b|detalle\??\.name\b/);
  });

  it('distingue «no se hizo nada» de «no se pudo consultar»', () => {
    expect(visible).toMatch(/No se ejecutó ninguna acción sobre el equipo/i);
  });

  it('dice que la medición no se guarda y cuándo se consulta sola', () => {
    /* Sobre el texto con los espacios normalizados, no sobre el archivo: la
       frase está repartida en dos renglones del marcado y buscarla tal cual
       la ponía roja por dónde cae el salto de línea, que no es lo que esta
       prueba quiere proteger. */
    const prosa = visible.replace(/\s+/g, ' ');
    expect(prosa).toMatch(/no se guardan acá/i);
    expect(prosa).toMatch(/en manos de una persona/i);
  });
});

describe('el proceso sigue contando lo que cuenta el motor', () => {
  it('la pantalla no recalcula bloqueos ni errores', () => {
    // El backend los cuenta porque distinguir un bloqueo de un fallo depende
    // de una columna de la base. La pantalla dibuja tres numeros.
    const trace = leer('TracePanel.svelte');
    expect(trace).toMatch(/diagnostico\?\.(bloqueadas|errores)/);
    expect(trace).not.toMatch(/filter\([^)]*es_bloqueo/);
  });
});
