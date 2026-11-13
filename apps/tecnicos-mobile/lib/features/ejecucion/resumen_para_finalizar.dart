/// LO QUE EL TÉCNICO REVISA ANTES DE FINALIZAR (09/11/2026).
///
/// EL PEDIDO
/// ---------
/// El usuario, sobre la app en uso: «ya cuando se llenaron todos los pasos
/// sale el botón de finalizar y adentro un formulario para escribir qué se
/// hizo para resolver otra vez, en texto libre. Para cerrar el caso debería
/// mostrar mejor un resumen de lo realizado, y así el técnico revisa el
/// resumen y corrige o finaliza si está todo bien».
///
/// LO QUE PASABA
/// -------------
/// La misma pregunta aparecía tres veces: el paso «Solución» pedía en texto
/// libre qué se hizo, el botón «Finalizar» abría otro formulario para
/// escribirlo de nuevo, y el checklist de cierre armaba su propia cuenta de
/// fotos y material por separado. Escribir dos veces lo mismo no agrega
/// información: agrega la posibilidad de que las dos versiones no coincidan, y
/// entonces nadie sabe cuál vale.
///
/// POR QUÉ ES LÓGICA PURA
/// ----------------------
/// Porque decidir QUÉ se le muestra a alguien antes de firmar un trabajo es
/// una regla, no un dibujo: si el resumen omite un campo, el técnico aprueba
/// algo que no vio. Acá se prueba sin emulador, sin base y sin red.
///
/// SE ARMA SOBRE [CampoDelFormulario], QUE ES LO QUE LA PANTALLA TIENE
/// -------------------------------------------------------------------
/// La primera versión recibía los mapas crudos del esquema. La pantalla no
/// tiene eso: tiene los campos ya normalizados, con su valor y su unidad
/// adentro. Pasarle mapas hacía que el resumen saliera VACÍO sin fallar --cada
/// campo se descartaba por no ser un `Map`-- y la prueba de pantalla igual
/// pasaba, porque encontraba esos textos en la pantalla de atrás. Lo encontró
/// una mutación.
///
/// LO QUE NO HACE
/// --------------
/// No inventa. Un campo sin responder no aparece --mostrarlo vacío llenaría el
/// resumen de renglones que no dicen nada-- y ninguna línea se calcula: todas
/// salen de lo que la persona escribió.
library;

import 'campo_del_formulario.dart';

/// Un renglón del resumen: lo que se preguntó y lo que se respondió.
class LineaDeResumen {
  const LineaDeResumen({
    required this.id,
    required this.titulo,
    required this.valor,
  });

  /// El id del campo. Sirve para llevar al técnico al campo cuando toca
  /// «Corregir»: sin él habría que buscarlo por su texto.
  final String id;

  final String titulo;
  final String valor;
}

/// Las líneas del resumen, en el orden en que se llenaron los campos.
List<LineaDeResumen> resumenParaFinalizar(List<CampoDelFormulario> campos) {
  final List<LineaDeResumen> salida = <LineaDeResumen>[];

  for (final CampoDelFormulario campo in campos) {
    if (campo.id.isEmpty) continue;
    final String valor = valorLegible(campo);
    if (valor.isEmpty) continue;

    salida.add(LineaDeResumen(
      id: campo.id,
      titulo: campo.titulo.isEmpty ? campo.id : campo.titulo,
      valor: valor,
    ));
  }

  return salida;
}

/// Cómo se lee una respuesta, ya formateada. Vacío cuando no hay respuesta.
///
/// Tres casos que no son obvios:
///
/// - **Booleano**: «Sí» / «No», no `true`. Y el `false` SE MUESTRA: «¿Se
///   reemplazó la ONT? No» es una respuesta, no una ausencia, y es justo la
///   que alguien podría querer corregir antes de firmar.
/// - **«Otro»**: lo que vale es el texto que escribió la persona. Mostrar
///   «Otro» a secas sería ocultar la única parte que agrega información.
/// - **Unidad**: va pegada al número --«-21.19 dBm»--, porque una potencia sin
///   su unidad no se puede revisar.
String valorLegible(CampoDelFormulario campo) {
  final dynamic crudo = campo.valor;

  if (crudo is bool) return crudo ? 'Sí' : 'No';

  final String texto = (crudo ?? '').toString().trim();
  if (texto.isEmpty) return '';

  if (texto == CampoDelFormulario.otro) {
    final String otro = campo.textoOtro.trim();
    //  Sin el texto libre, «Otro» solo no dice nada: se muestra igual para
    //  que el técnico vea que ese campo quedó a medias y pueda corregirlo.
    return otro.isEmpty ? 'Otro (sin detallar)' : otro;
  }

  final String unidad = campo.unidad.trim();
  return unidad.isEmpty ? texto : '$texto $unidad';
}

/// LO QUE EL CIERRE TODAVÍA TIENE QUE PREGUNTAR (09/11/2026).
///
/// El usuario, después de ver el resumen andando: «ese último formulario no
/// debería salir... solo el botón de que el servicio queda funcionando, en el
/// mismo resumen, y desde ahí sí finaliza».
///
/// El formulario de cierre que pide el backend cuando el tipo de trabajo no
/// declara el suyo (`campo/services/seguimiento_campo.py`, MINIMO) trae dos
/// cosas que no son iguales:
///
/// - «Qué se hizo para resolverlo», en texto. Es lo que el técnico YA cargó
///   durante la ejecución y lo que el resumen muestra: volver a pedirlo es
///   escribir dos veces lo mismo, y si las dos versiones no coinciden nadie
///   sabe cuál vale.
/// - «¿El servicio quedó funcionando?», que NO está en ningún otro lado. Es
///   una declaración: el backend la marca así a propósito --«esto lo AFIRMA
///   una persona; el sistema no puede saberlo y no va a decir que lo sabe»--.
///
/// Así que una se responde con lo ya cargado y la otra se pregunta. Las dos en
/// la misma hoja del resumen, que es lo que pidió el usuario.
///
/// LO QUE PASA SI LA EMPRESA DECLARA SU PROPIO CIERRE. Sus preguntas de texto
/// no se pueden deducir de nada --nadie las respondió antes--, así que esas se
/// siguen preguntando en su hoja. La regla de abajo separa justamente eso: lo
/// que hay que declarar, lo que se puede deducir, y lo que no entra en ninguna
/// de las dos.
class PreguntasDelCierre {
  const PreguntasDelCierre({
    required this.declaraciones,
    required this.sePuedenDeducir,
    required this.hayQuePreguntarAparte,
  });

  /// Booleanos: se dibujan como interruptores dentro del resumen.
  final List<CampoDelFormulario> declaraciones;

  /// Campos de texto que el resumen ya responde. Se llenan con él.
  final List<CampoDelFormulario> sePuedenDeducir;

  /// Lo que no es ni una cosa ni la otra. Si queda alguno, la hoja de cierre
  /// se abre igual: preferible una pantalla de más que una pregunta de la
  /// empresa que nadie contestó.
  final List<CampoDelFormulario> hayQuePreguntarAparte;

  bool get alcanzaConElResumen => hayQuePreguntarAparte.isEmpty;
}

/// Reparte los campos del formulario de cierre en esos tres grupos.
///
/// Recibe el modelo ya normalizado y no los mapas del esquema: leer `tipo` a
/// mano acá sería otra lectura independiente del mismo esquema, que es lo que
/// `arquitectura_esquema_test` evita --y la que decide de verdad es la del
/// normalizador--.
PreguntasDelCierre repartirElCierre(List<CampoDelFormulario> campos) {
  final List<CampoDelFormulario> declaraciones = <CampoDelFormulario>[];
  final List<CampoDelFormulario> deducibles = <CampoDelFormulario>[];
  final List<CampoDelFormulario> aparte = <CampoDelFormulario>[];

  for (final CampoDelFormulario campo in campos) {
    if (campo.id.isEmpty) continue;

    if (campo.esBooleano) {
      declaraciones.add(campo);
    } else if (campo.esTextoLibre) {
      deducibles.add(campo);
    } else {
      //  Un número, una fecha, una selección: nadie los respondió antes y no
      //  se pueden inventar.
      aparte.add(campo);
    }
  }

  return PreguntasDelCierre(
    declaraciones: declaraciones,
    sePuedenDeducir: deducibles,
    hayQuePreguntarAparte: aparte,
  );
}

/// Con qué se responde un campo de texto del cierre: el resumen, escrito de
/// corrido.
///
/// No inventa nada --cada renglón es una respuesta del técnico, con el título
/// de su pregunta-- y es lo que él acaba de aprobar en pantalla. Así el
/// reporte que le llega al Supervisor dice exactamente lo mismo que el técnico
/// revisó, que es lo que un segundo campo de texto no podía garantizar.
String cierreDeducido(List<LineaDeResumen> lineas) =>
    lineas.map((LineaDeResumen l) => '${l.titulo}: ${l.valor}').join('. ');
