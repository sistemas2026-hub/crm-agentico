/// Si alguien dio por bueno el trabajo.
///
/// Es una **máquina distinta** de [EstadoTrabajo], no un campo más de aquella.
/// Responden preguntas que no son la misma:
///
/// - `estado` (operativo) dice **dónde está** el trabajo;
/// - `estado_validacion` dice **si alguien lo revisó** y qué decidió.
///
/// Una orden puede estar completada en campo y devuelta para corregir a la vez,
/// y las dos cosas son ciertas. Por eso este valor **nunca** mueve el estado
/// operativo, no encola una mutación y no cambia el paso que muestra el
/// detalle: aprobar es un juicio sobre el trabajo, no un movimiento del
/// trabajo. Así lo dice también el backend (`campo/services/transiciones.py`,
/// donde `aprobar()` deliberadamente no toca `estado_operativo`).
///
/// Los seis valores salen de `OrdenTrabajo.ESTADOS_VALIDACION`. Cualquier otra
/// cosa cae en [desconocido] en vez de hacerse pasar por uno de estos: si el
/// backend agrega un séptimo, la aplicación lo ignora sin romperse.
enum EstadoValidacion {
  sinEvaluar,
  pendiente,

  /// Declarado en el backend y sin uso: nadie lo escribe todavía.
  aprobable,
  requiereCorreccion,
  requiereRevision,
  aprobado,

  /// No llegó, o llegó algo que esta versión no conoce.
  desconocido;

  static EstadoValidacion desde(String? valor) => switch (valor) {
        'sin_evaluar' => EstadoValidacion.sinEvaluar,
        'pendiente' => EstadoValidacion.pendiente,
        'aprobable' => EstadoValidacion.aprobable,
        'requiere_correccion' => EstadoValidacion.requiereCorreccion,
        'requiere_revision' => EstadoValidacion.requiereRevision,
        'aprobado' => EstadoValidacion.aprobado,
        _ => EstadoValidacion.desconocido,
      };

  /// Cómo se llamaría en pantalla. Todavía no se muestra en ningún lado: esta
  /// fase solo conserva el dato de punta a punta.
  String get etiqueta => switch (this) {
        EstadoValidacion.sinEvaluar => 'Sin evaluar',
        EstadoValidacion.pendiente => 'Pendiente de validación',
        EstadoValidacion.aprobable => 'Aprobable',
        EstadoValidacion.requiereCorreccion => 'Requiere corrección',
        EstadoValidacion.requiereRevision => 'Requiere revisión humana',
        EstadoValidacion.aprobado => 'Aprobado',
        EstadoValidacion.desconocido => 'Sin información',
      };
}
