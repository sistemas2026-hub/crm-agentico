/// CÓMO SE CIERRA UNA ORDEN: si lleva contrato, y si la revisa una persona
/// antes de cerrarse.
///
/// Sin Flutter a propósito: lo leen el modelo de la orden ([TrabajoVista]) y
/// las pantallas de ejecución y del contrato, y el modelo no puede depender de
/// una pantalla.
library;

/// Si esta orden es de las que llevan contrato.
///
/// La labor llega del servidor desde la v29 de la base local; las órdenes
/// bajadas antes no la tienen hasta que se vuelvan a leer, y por eso el código
/// de la plantilla sirve de respaldo.
bool llevaContrato(Map<String, dynamic>? orden) {
  if (orden == null) return false;
  if ((orden['labor'] ?? '').toString() == 'instalacion') return true;
  return (orden['tipo_codigo'] ?? '').toString().contains('instalacion');
}

/// Si esta orden, al terminarla, la revisa una PERSONA antes de cerrarse
/// (27/11/2026). El usuario: «el técnico termina y debe haber un botón de
/// mandar a validar, y si confirman que está bien finaliza el trabajo».
///
/// Entonces el botón del final dice «Enviar a validación», y cuando la oficina
/// la aprueba sale «Finalizar trabajo», que entrega y cierra el ticket.
///
/// Lo decide el SERVIDOR (`tipo.valida_una_persona`, desde la v32 de la base
/// local). Antes se adivinaba por el código de la plantilla («contiene
/// instalacion») y en producción la de instalaciones se llama
/// `traslado_servicio`: el técnico nunca vio el botón para entregar y el
/// ticket no se cerró (OT-501). Una orden bajada antes de la v32 no lo trae
/// hasta que se vuelva a leer; mientras, vale [llevaContrato].
bool validaUnaPersona(Map<String, dynamic>? orden) {
  if (orden == null) return false;
  final Object? delServidor = orden['valida_una_persona'];
  if (delServidor is int) return delServidor == 1;
  if (delServidor is bool) return delServidor;
  return llevaContrato(orden);
}
