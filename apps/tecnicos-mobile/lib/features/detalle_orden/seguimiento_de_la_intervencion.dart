import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';
import 'hoja_de_reporte.dart';

/// La historia de la intervención, leída y nada más.
///
/// ESTA PANTALLA NO DECIDE NADA
/// ----------------------------
/// Cada evento llega del backend con su `etiqueta`, su `severidad` y su
/// `detalle` ya resueltos. Acá no hay un `if (tipo == 'bloqueo_campo')`: lo
/// único que se traduce es **severidad → estilo**, y eso es presentación, que es
/// lo que sí le toca a la aplicación.
///
/// Es la decisión 8 del objetivo, y el motivo de que sea así está medido: si el
/// backend mandara `color` e `icono`, dos frontends tendrían que compartir el
/// mismo diccionario visual, y un cambio de paleta —modo oscuro, contraste—
/// pasaría a ser un cambio de servidor.
///
/// Consecuencia práctica, y es la promesa entera: si mañana aparece un
/// `medicion_extraordinaria` que esta app nunca vio, se dibuja igual.
///
/// NO HAY BOTONES DE ACCIÓN, A PROPÓSITO
/// -------------------------------------
/// La Fase 1 es lectura. Un botón «Registrar avance» que abriera un formulario
/// incapaz de guardar sería peor que no tenerlo: el técnico lo llenaría en la
/// calle y lo perdería. Los botones entran cuando exista la cola de escritura.
class SeguimientoDeLaIntervencion extends StatefulWidget {
  const SeguimientoDeLaIntervencion({
    super.key,
    required this.seguimiento,
    required this.cargando,
    this.actualizado = true,
    this.alReportar,
    this.alResolverBloqueo,
    this.alTomarFoto,
    this.fotosTomadas = const <String, int>{},
    this.alAbrirHoja,
    this.alDescartarBorrador,
    this.mostrarHistoria = true,
    this.mostrarBloqueoAbierto = true,
    this.pendientesDeSubir = 0,
  });

  /// Lo que devolvió el backend, o `null` si **nunca se descargó** en este
  /// teléfono.
  ///
  /// `null` y «sin eventos» son dos cosas distintas y se dicen distinto: una
  /// línea de tiempo vacía se lee como «este trabajo no tiene historia», y lo
  /// que pasa en realidad es «no pude preguntar».
  final Map<String, dynamic>? seguimiento;

  final bool cargando;

  /// `false` cuando se está mostrando el espejo porque la última descarga
  /// falló. Lo que se muestra sigue siendo cierto; lo que no se puede afirmar
  /// es que esté al día.
  final bool actualizado;

  /// Qué hacer con un reporte que el técnico terminó de escribir.
  ///
  /// Se inyecta para que la sección se pueda probar sin base ni red. Si es
  /// `null`, la sección queda en **solo lectura** y no ofrece ningún botón —que
  /// es exactamente lo que hacía la Fase 1.
  final void Function(
    String momento,
    Map<String, dynamic> respuestas, {
    bool requiereNoc,
    bool detener,
  })?
  alReportar;

  /// Qué hacer cuando el técnico dice que el bloqueo se levantó.
  ///
  /// `null` deja la sección sin esa salida. Quien la usa decide si corresponde
  /// ofrecerla; esta sección además la esconde cuando el bloqueo requiere al
  /// NOC, por lo que explica `_bloqueoAbierto`.
  final void Function(String queSeHizo)? alResolverBloqueo;

  /// Qué hacer cuando el técnico pide tomar una foto para un reporte.
  ///
  /// Recibe el momento y el requisito. `null` deja los reportes en solo texto:
  /// esta sección no abre cámaras ni conoce la cola.
  final Future<void> Function(String momento, String requisitoId)? alTomarFoto;

  /// Cuántas fotos lleva cada requisito del momento abierto.
  final Map<String, int> fotosTomadas;

  /// Se llama cuando una hoja se ABRE, con su momento.
  ///
  /// Quien la recibe aprovecha para contar, desde el disco, las fotos que ese
  /// borrador ya tenía. Hace falta porque abrir la cámara puede destruir esta
  /// pantalla: al volver, el conteo en memoria se perdió y la hoja diría que no
  /// hay foto cuando sí la hay.
  final void Function(String momento)? alAbrirHoja;

  /// Se llama cuando una hoja se cierra SIN guardar, con su momento.
  ///
  /// Lo que haya quedado del borrador --fotos sacadas y no mandadas-- es de
  /// quien lo recibe: esta sección no sabe que existe una cola.
  final void Function(String momento)? alDescartarBorrador;

  /// Si se dibuja la HISTORIA (la línea de tiempo).
  ///
  /// EL REPARTO ENTRE LAS DOS PANTALLAS (02/10/2026)
  /// ----------------------------------------------
  /// Esta sección hace dos cosas que ocurren en momentos distintos del trabajo,
  /// y hasta hoy las hacía juntas en la ficha:
  ///
  ///   LEER la historia    — «¿qué pasó en este trabajo?». Se consulta antes de
  ///                         entrar y cuando algo se traba. Vive en la FICHA.
  ///   ESCRIBIR un reporte — «se me cayó un poste». Ocurre con las manos en la
  ///                         caja, o sea en EJECUCIÓN.
  ///
  /// Tenerlas juntas obligaba al técnico a salir de la ejecución, volver atrás y
  /// bajar para reportar un bloqueo. Ahora cada pantalla monta esta misma
  /// sección con su mitad: una sola implementación, dos papeles.
  final bool mostrarHistoria;

  /// Si se dibuja el bloqueo abierto y su salida.
  ///
  /// Va en la FICHA y no en ejecución, y no es una preferencia: con el trabajo
  /// detenido **no hay «Ejecutar el trabajo»** —lo decide la máquina de estados,
  /// y está medido— así que si destrabar viviera allá, un trabajo bloqueado
  /// sería un callejón sin salida. La ficha es la única pantalla alcanzable.
  final bool mostrarBloqueoAbierto;

  /// Cuántos reportes de esta orden esperan subir. Se muestra porque un reporte
  /// guardado y sin subir es un hecho que el técnico tiene que poder ver: si no,
  /// no sabe si el NOC se enteró.
  final int pendientesDeSubir;

  @override
  State<SeguimientoDeLaIntervencion> createState() =>
      _SeguimientoDeLaIntervencionState();
}

class _SeguimientoDeLaIntervencionState
    extends State<SeguimientoDeLaIntervencion> {
  /// El momento cuya hoja está abierta, o `null` si no hay ninguna.
  String? _abierto;

  // La salida del bloqueo.
  bool _resolviendo = false;
  String? _avisoResolver;
  final TextEditingController _queSeHizo = TextEditingController();

  @override
  void dispose() {
    _queSeHizo.dispose();
    super.dispose();
  }

  Map<String, dynamic>? get seguimiento => widget.seguimiento;
  bool get cargando => widget.cargando;
  bool get actualizado => widget.actualizado;

  @override
  Widget build(BuildContext context) {
    return DexterBloque(
      titulo: 'Seguimiento de la intervención',
      icono: Icons.timeline,
      children: _cuerpo(),
    );
  }

  List<Widget> _cuerpo() {
    if (cargando && seguimiento == null) {
      return <Widget>[
        Text(
          'Buscando la historia de este trabajo…',
          style: AppTypography.cuerpoChico,
        ),
      ];
    }

    // NUNCA se descargó. Se dice así, en vez de dibujar una historia vacía.
    if (seguimiento == null) {
      return <Widget>[
        Text(
          'El seguimiento todavía no está disponible en este dispositivo.',
          style: AppTypography.cuerpo,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Se descarga al abrir la orden con señal. Que no esté acá no quiere '
          'decir que el trabajo no tenga reportes.',
          style: AppTypography.cuerpoChico,
        ),
      ];
    }

    final List<dynamic> eventos =
        (seguimiento!['eventos'] as List<dynamic>?) ?? const <dynamic>[];

    return <Widget>[
      ..._resumen(),
      if (!actualizado) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          'No se pudo actualizar ahora: esto es lo último que se supo.',
          style: AppTypography.cuerpoChico,
        ),
      ],
      ..._bloqueoAbierto(),
      ..._acciones(),
      if (widget.mostrarHistoria) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        if (eventos.isEmpty)
          Text(
            'Todavía no hay reportes de campo en esta orden.',
            style: AppTypography.cuerpoChico,
          )
        else
          for (final dynamic crudo in eventos)
            if (crudo is Map) _evento(Map<String, dynamic>.from(crudo)),
      ],
    ];
  }

  /// Las fotos de un reporte, y la que se pedía y no está.
  ///
  /// POR QUE SE DIBUJAN LAS DOS LISTAS
  /// --------------------------------
  /// El backend manda `evidencias` --las que llegaron-- y `evidencias_declaradas`
  /// --las que ese reporte pedía, congeladas en su snapshot--. Sin la segunda, un
  /// bloqueo sin foto y un bloqueo al que nunca se le pidió una se leen igual, y
  /// quien revisa no puede saber si falta algo o si nunca hizo falta.
  ///
  /// No se muestra la imagen todavía: la URL de lectura es firmada y dura poco,
  /// así que pedirla para cada fila de una bitácora entera sería emitir enlaces
  /// que vencen mientras la pantalla está abierta. Acá se dice qué hay; abrirla
  /// es un paso aparte.
  List<Widget> _fotosDelEvento(Map<String, dynamic> evento) {
    final List<dynamic> tiene =
        (evento['evidencias'] as List<dynamic>?) ?? const <dynamic>[];
    final List<dynamic> pedidas =
        (evento['evidencias_declaradas'] as List<dynamic>?) ?? const <dynamic>[];
    if (tiene.isEmpty && pedidas.isEmpty) {
      return const <Widget>[];
    }

    final Set<String> llegaron = <String>{
      for (final dynamic f in tiene)
        if (f is Map) (f['requisito_id'] ?? '').toString(),
    };
    final List<dynamic> faltan = <dynamic>[
      for (final dynamic p in pedidas)
        if (p is Map && !llegaron.contains((p['id'] ?? '').toString())) p,
    ];

    // El título lo declara el tipo de trabajo; el servidor manda el `id`. Sin
    // este cruce la bitácora diría «foto_del_obstaculo», que es cómo se llama el
    // campo y no cómo se le dice a una persona.
    final Map<String, String> titulos = <String, String>{
      for (final dynamic p in pedidas)
        if (p is Map)
          (p['id'] ?? '').toString(): (p['titulo'] ?? p['id'] ?? '').toString(),
    };

    return <Widget>[
      const SizedBox(height: AppSpacing.xs),
      for (final dynamic f in tiene)
        if (f is Map) _unaFoto(Map<String, dynamic>.from(f), titulos),
      for (final dynamic p in faltan)
        if (p is Map)
          Text(
            'Falta la foto: ${(p['titulo'] ?? p['id'] ?? '').toString()}',
            style: AppTypography.etiquetaChica,
          ),
    ];
  }

  Widget _unaFoto(Map<String, dynamic> foto, Map<String, String> titulos) {
    // `disponible` lo decide el servidor: que exista la fila no es que el
    // archivo haya llegado. Decir "foto" sobre algo que todavía está subiendo
    // haría creer que el NOC ya puede verla.
    final bool disponible = foto['disponible'] == true;
    final String requisito = (foto['requisito_id'] ?? '').toString();
    // Si el reporte no declaraba esa foto --pasa con un evento viejo, cuyo
    // snapshot es el de entonces-- se muestra el id. Es feo y es honesto: el
    // título de hoy no es el que se le mostró a quien la sacó.
    final String titulo = titulos[requisito] ?? (requisito.isEmpty
        ? 'Foto'
        : requisito);

    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        children: <Widget>[
          Icon(
            disponible ? Icons.photo_outlined : Icons.cloud_upload_outlined,
            size: 14,
            color: AppColors.onSurfaceVariant,
          ),
          const SizedBox(width: 4),
          Expanded(
            child: Text(
              disponible ? titulo : '$titulo · subiendo',
              style: AppTypography.etiquetaChica,
            ),
          ),
        ],
      ),
    );
  }

  /// El bloqueo vivo, si hay, y la salida cuando le toca al técnico.
  ///
  /// QUIÉN PUEDE RESOLVER, Y POR QUÉ NO ES UNA CUESTIÓN DE PERMISOS
  /// -------------------------------------------------------------
  /// El backend deja que el técnico asignado resuelva: eso está medido. Pero la
  /// pregunta que importa no es si **puede**, es si **sabe qué se hizo** — y
  /// `que_se_hizo` es obligatorio del otro lado.
  ///
  /// Si el bloqueo requiere al NOC y coordinación gestionó un permiso municipal,
  /// el técnico no sabe qué gestionaron: escribiría «ya puedo entrar», que no es
  /// qué se hizo, y ese campo quedaría inservible para la pregunta que existe
  /// para responder («¿por qué este trabajo tardó tres días?»).
  ///
  /// Si NO requiere NOC —esperando al cliente, falta un material que el técnico
  /// fue a buscar— el que sabe es él.
  ///
  /// Así que la frontera la marca `requiere_noc`, que ya existe, en vez de
  /// inventar un permiso nuevo.
  List<Widget> _bloqueoAbierto() {
    // En EJECUCIÓN no va: el bloqueo abierto y su salida viven en la ficha,
    // que es la única pantalla alcanzable con el trabajo detenido.
    if (!widget.mostrarBloqueoAbierto) {
      return const <Widget>[];
    }
    final Map<String, dynamic>? bloqueo = _mapa(
      seguimiento!['bloqueo_abierto'],
    );
    if (bloqueo == null) {
      return const <Widget>[];
    }

    final bool requiereNoc = bloqueo['requiere_noc'] == true;
    final bool detuvo = bloqueo['detuvo_el_trabajo'] == true;
    final int? minutos = bloqueo['minutos_detenido'] as int?;
    final String necesita = (bloqueo['necesita'] ?? '').toString();
    final String motivo = (bloqueo['motivo'] ?? '').toString();
    final bool puedeResolver = !requiereNoc && widget.alResolverBloqueo != null;

    return <Widget>[
      const SizedBox(height: AppSpacing.sm),
      Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          borderRadius: AppRadius.brTarjeta,
          boxShadow: AppTheme.sombraNivel1,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: <Widget>[
                DexterPastilla.critica(
                  texto: detuvo ? 'Trabajo detenido' : 'Bloqueo reportado',
                ),
                if (requiereNoc) DexterPastilla.alerta(texto: 'Requiere NOC'),
              ],
            ),
            if (motivo.isNotEmpty) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(motivo, style: AppTypography.cuerpo),
            ],
            if (necesita.isNotEmpty) ...<Widget>[
              const SizedBox(height: 2),
              Text('Hace falta: $necesita', style: AppTypography.etiquetaChica),
            ],
            if (detuvo && minutos != null) ...<Widget>[
              const SizedBox(height: 2),
              Text(
                'Detenido hace $minutos min',
                style: AppTypography.etiquetaChica,
              ),
            ],
            if (!detuvo) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(
                'El estado del trabajo no cambió: el bloqueo quedó anotado y se '
                'puede seguir.',
                style: AppTypography.etiquetaChica,
              ),
            ],

            // La salida. O la explicación de por qué no está acá.
            const SizedBox(height: AppSpacing.xs),
            if (puedeResolver)
              DexterAccionRapida(
                texto: _resolviendo ? 'Escribiendo…' : 'Ya se puede seguir',
                icono: Icons.play_circle_outline,
                alTocar: () => setState(() => _resolviendo = !_resolviendo),
              )
            else if (requiereNoc)
              Text(
                'Lo destraba quien hizo la gestión: el NOC o coordinación. '
                'Cuando lo resuelvan, acá va a decir que podés seguir.',
                style: AppTypography.etiquetaChica,
              ),

            if (_resolviendo && puedeResolver) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              TextField(
                controller: _queSeHizo,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Qué se hizo para poder seguir',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_avisoResolver != null) ...<Widget>[
                const SizedBox(height: 4),
                Text(
                  _avisoResolver!,
                  style: AppTypography.cuerpoChico.copyWith(
                    color: AppColors.error,
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.xs),
              DexterAccionDominante(
                texto: 'Destrabar el trabajo',
                icono: Icons.lock_open,
                alTocar: () {
                  final String texto = _queSeHizo.text.trim();
                  if (texto.isEmpty) {
                    // El backend lo exige, y con razon: un bloqueo resuelto sin
                    // decir que se hizo no explica nada despues.
                    setState(
                      () => _avisoResolver =
                          'Decí qué se hizo para poder seguir.',
                    );
                    return;
                  }
                  widget.alResolverBloqueo!(texto);
                  setState(() {
                    _resolviendo = false;
                    _avisoResolver = null;
                    _queSeHizo.clear();
                  });
                },
              ),
            ],
          ],
        ),
      ),
    ];
  }

  /// Los botones, y la hoja del que esté abierto.
  ///
  /// SOLO SE OFRECE LO QUE LA MÁQUINA PERMITE
  /// ----------------------------------------
  /// La lista no sale de lo que sea cómodo mostrar: sale de `formularios`, que es
  /// lo que el backend declaró para este tipo de trabajo, y de
  /// `momentos_registrados`, que dice qué ya ocurrió. Un INICIO no se ofrece dos
  /// veces porque el servidor lo rechazaría, y un botón que lleva a un rechazo es
  /// peor que no tenerlo: el técnico escribe el reporte en la calle y lo pierde.
  ///
  /// Si no hay a quién entregar el reporte (`alReportar == null`), no hay
  /// botones. Así la sección sigue sirviendo como pantalla de lectura.
  List<Widget> _acciones() {
    if (widget.alReportar == null) {
      return const <Widget>[];
    }

    final Map<String, dynamic> formularios =
        _mapa(seguimiento!['formularios']) ?? <String, dynamic>{};
    final List<dynamic> yaOcurrio =
        (seguimiento!['momentos_registrados'] as List<dynamic>?) ??
        const <dynamic>[];
    final bool huboInicio = yaOcurrio.contains('inicio_campo');

    final List<Widget> botones = <Widget>[];
    for (final (String momento, String texto) opcion in <(String, String)>[
      ('inicio', 'Registrar inicio'),
      ('avance', 'Registrar avance'),
      ('bloqueo', 'Reportar bloqueo'),
      ('cierre', 'Cerrar intervención'),
    ]) {
      final String momento = opcion.$1;
      // El tipo de trabajo tiene que declarar ese momento.
      if (!formularios.containsKey(momento)) {
        continue;
      }
      // El INICIO solo antes del primer INICIO.
      if (momento == 'inicio' && huboInicio) {
        continue;
      }
      botones.add(
        DexterAccionRapida(
          texto: opcion.$2,
          icono: _icono(momento),
          alTocar: () =>
              setState(() {
                // Cerrar o cambiar de momento descarta lo del anterior: la foto
                // se sacó para el reporte que se estaba escribiendo, no para el
                // siguiente.
                final String? previo = _abierto;
                if (previo != null && previo != momento) {
                  widget.alDescartarBorrador?.call(previo);
                }
                if (previo == momento) {
                  widget.alDescartarBorrador?.call(momento);
                  _abierto = null;
                } else {
                  _abierto = momento;
                  widget.alAbrirHoja?.call(momento);
                }
              }),
        ),
      );
    }

    return <Widget>[
      if (widget.pendientesDeSubir > 0) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          widget.pendientesDeSubir == 1
              ? '1 reporte escrito acá todavía no subió.'
              : '${widget.pendientesDeSubir} reportes escritos acá todavía no '
                    'subieron.',
          style: AppTypography.etiquetaChica,
        ),
      ],
      if (botones.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.xs,
          runSpacing: AppSpacing.xs,
          children: botones,
        ),
      ],
      if (_abierto != null) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        HojaDeReporte(
          // La clave por momento NO es decorativa: sin ella, Flutter reusa el
          // mismo estado al cambiar de hoja y los campos se arrastran. Medido en
          // el emulador el 02/10/2026: se escribió un BLOQUEO, se tocó «Cerrar
          // intervención» sin guardar, y el motivo del bloqueo apareció dentro
          // de «¿Qué se hizo para resolverlo?» — listo para mandarse como si
          // fuera la respuesta a otra pregunta. Los dos formularios declaran un
          // campo con el mismo id, así que para el framework eran el mismo.
          key: ValueKey<String>(_abierto!),
          momento: _abierto!,
          titulo: _tituloDelMomento(_abierto!),
          campos: _camposDe(formularios, _abierto!),
          evidencias: _evidenciasDe(formularios, _abierto!),
          alTomarFoto: widget.alTomarFoto == null
              ? null
              : (String requisitoId) async {
                  await widget.alTomarFoto!(_abierto!, requisitoId);
                  if (mounted) setState(() {});
                },
          fotosTomadas: widget.fotosTomadas,
          alGuardar:
              (
                Map<String, dynamic> respuestas, {
                bool requiereNoc = false,
                bool detener = true,
              }) {
                widget.alReportar!(
                  _abierto!,
                  respuestas,
                  requiereNoc: requiereNoc,
                  detener: detener,
                );
                setState(() => _abierto = null);
              },
        ),
      ],
    ];
  }

  /// Los campos crudos que el backend declaró para ese momento.
  ///
  /// Se pasan TAL CUAL a la hoja, que los interpreta con el mismo lector que el
  /// resto de la aplicación. Acá no se mira qué campos son.
  List<Map<String, dynamic>> _camposDe(
    Map<String, dynamic> formularios,
    String momento,
  ) => _listaDe(formularios, momento, 'campos');

  /// Las fotos que el tipo de trabajo pide en ese momento.
  ///
  /// Sale del MISMO formulario que los campos y por el mismo camino: la app no
  /// sabe qué foto pide esta empresa hasta preguntar, igual que no sabe qué
  /// campos pide. Una lista vacía es lo normal.
  List<Map<String, dynamic>> _evidenciasDe(
    Map<String, dynamic> formularios,
    String momento,
  ) => _listaDe(formularios, momento, 'evidencias');

  List<Map<String, dynamic>> _listaDe(
    Map<String, dynamic> formularios,
    String momento,
    String clave,
  ) {
    final Map<String, dynamic>? form = _mapa(formularios[momento]);
    final List<dynamic> crudos =
        (form?[clave] as List<dynamic>?) ?? const <dynamic>[];
    return <Map<String, dynamic>>[
      for (final dynamic c in crudos)
        if (c is Map) Map<String, dynamic>.from(c),
    ];
  }

  static String _tituloDelMomento(String momento) {
    switch (momento) {
      case 'inicio':
        return 'Registrar el inicio';
      case 'bloqueo':
        return 'Reportar un bloqueo';
      case 'cierre':
        return 'Cerrar la intervención';
      default:
        return 'Registrar un avance';
    }
  }

  static IconData _icono(String momento) {
    switch (momento) {
      case 'inicio':
        return Icons.play_arrow;
      case 'bloqueo':
        return Icons.pause_circle_outline;
      case 'cierre':
        return Icons.check_circle_outline;
      default:
        return Icons.add_comment_outlined;
    }
  }

  /// El último reporte y la salud, los dos tal como los nombró el backend.
  List<Widget> _resumen() {
    final Map<String, dynamic>? ultimo = _mapa(seguimiento!['ultimo_reporte']);
    final Map<String, dynamic>? salud = _mapa(seguimiento!['salud']);
    final int? sincronizado = seguimiento!['sincronizado_en'] as int?;

    return <Widget>[
      Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xs,
        children: <Widget>[
          // La etiqueta de la salud viene del servidor porque el TEXTO es el
          // veredicto: «sin sincronización reciente» no es lo mismo que «no
          // reportó». Acá solo se elige cómo se ve.
          if (salud != null && (salud['etiqueta'] ?? '').toString().isNotEmpty)
            _pastilla(
              (salud['etiqueta']).toString(),
              _severidadDeSalud((salud['tipo'] ?? '').toString()),
            ),
          if (ultimo != null)
            DexterPastilla.neutra(texto: _textoDelUltimo(ultimo)),
        ],
      ),
      if (sincronizado != null) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Última sincronización: ${_hora(DateTime.fromMillisecondsSinceEpoch(sincronizado))}',
          style: AppTypography.etiquetaChica,
        ),
      ],
    ];
  }

  Widget _evento(Map<String, dynamic> evento) {
    final String etiqueta = (evento['etiqueta'] ?? evento['tipo'] ?? '—')
        .toString();
    final String severidad = (evento['severidad'] ?? 'info').toString();
    final String quien = (evento['quien'] ?? '').toString();
    final DateTime? recibido = _fecha(evento['recibido_en']);
    final DateTime? enElTelefono = _fecha(evento['capturado_en_dispositivo']);
    final List<dynamic> detalle =
        (evento['detalle'] as List<dynamic>?) ?? const <dynamic>[];
    final Map<String, dynamic> datos =
        _mapa(evento['datos']) ?? <String, dynamic>{};

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          borderRadius: AppRadius.brTarjeta,
          boxShadow: AppTheme.sombraNivel1,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                _pastilla(etiqueta, severidad),
                const Spacer(),
                if (recibido != null)
                  Text(_hora(recibido), style: AppTypography.etiquetaChica),
              ],
            ),
            if (quien.isNotEmpty) ...<Widget>[
              const SizedBox(height: 2),
              Text(quien, style: AppTypography.etiquetaChica),
            ],

            // El detalle de un reporte, leído con el esquema que tenía cuando se
            // capturó. Los títulos vienen de ahí: esta pantalla no sabe qué
            // campos existen ni necesita saberlo.
            for (final dynamic fila in detalle)
              if (fila is Map) ...<Widget>[
                const SizedBox(height: AppSpacing.xs),
                _dato(
                  (fila['titulo'] ?? fila['id'] ?? '').toString(),
                  _valorLegible(fila['valor']),
                ),
              ],

            // Los hechos del sistema traen `datos` en vez de `detalle`: el
            // backend expone solo las claves que decidió mostrar.
            for (final String clave in datos.keys)
              if (datos[clave] != null) ...<Widget>[
                const SizedBox(height: AppSpacing.xs),
                _dato(_humanizar(clave), _valorLegible(datos[clave])),
              ],

            ..._fotosDelEvento(evento),

            // Las dos horas, cuando difieren. Es la decisión del objetivo hecha
            // visible: lo que gobierna el seguimiento es la llegada al
            // servidor, y la del teléfono está para reconstruir la historia.
            if (enElTelefono != null && recibido != null) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(
                _demora(enElTelefono, recibido),
                style: AppTypography.etiquetaChica,
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// Una fila «título: valor», con la tipografía del diseño.
  ///
  /// El título lo pone el esquema del tipo de trabajo, no esta pantalla: por eso
  /// se dibuja tal como llegó, sin traducirlo ni acortarlo.
  Widget _dato(String titulo, String valor) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          flex: 2,
          child: Text(titulo, style: AppTypography.etiquetaChica),
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(flex: 3, child: Text(valor, style: AppTypography.cuerpoChico)),
      ],
    );
  }

  // --- Lo único que esta pantalla traduce ---------------------------------

  /// Severidad → estilo. El único mapeo que vive en la aplicación.
  Widget _pastilla(String texto, String severidad) {
    switch (severidad) {
      case 'problema':
        return DexterPastilla.critica(texto: texto);
      case 'atencion':
        return DexterPastilla.alerta(texto: texto);
      case 'en_regla':
        return DexterPastilla.enRegla(texto: texto);
      default:
        // Una severidad que esta versión no conoce se dibuja neutra en vez de
        // romperse. Degradar es parte del contrato: el backend puede agregar
        // valores sin esperar a que se publique la app.
        return DexterPastilla.neutra(texto: texto);
    }
  }

  /// La salud del seguimiento usa los nombres de su propio servicio.
  String _severidadDeSalud(String tipo) {
    switch (tipo) {
      case 'vencido':
        return 'problema';
      case 'pausado_noc':
      case 'sin_contacto_reciente':
        return 'atencion';
      case 'al_dia':
        return 'en_regla';
      default:
        return 'info';
    }
  }

  String _textoDelUltimo(Map<String, dynamic> ultimo) {
    final String etiqueta = (ultimo['etiqueta'] ?? '').toString();
    final Object? minutos = ultimo['minutos_desde_que_lo_recibimos'];
    if (minutos is int) {
      return '$etiqueta · hace $minutos min';
    }
    return etiqueta.isEmpty ? 'Sin reportes' : etiqueta;
  }

  String _demora(DateTime enElTelefono, DateTime recibido) {
    final int minutos = recibido.difference(enElTelefono).inMinutes;
    if (minutos < 2) {
      return 'Escrito y recibido a la misma hora';
    }
    final String cuanto = minutos >= 60
        ? '${minutos ~/ 60} h ${minutos % 60} min'
        : '$minutos min';
    return 'Escrito en el teléfono a las ${_hora(enElTelefono)} · '
        'demora de sincronización: $cuanto';
  }

  // --- Ayudas de formato --------------------------------------------------

  static Map<String, dynamic>? _mapa(Object? valor) =>
      valor is Map ? Map<String, dynamic>.from(valor) : null;

  static DateTime? _fecha(Object? valor) {
    if (valor is! String || valor.isEmpty) {
      return null;
    }
    return DateTime.tryParse(valor)?.toLocal();
  }

  static String _hora(DateTime cuando) {
    final String hh = cuando.hour.toString().padLeft(2, '0');
    final String mm = cuando.minute.toString().padLeft(2, '0');
    return '$hh:$mm';
  }

  static String _valorLegible(Object? valor) {
    if (valor == null) {
      return '—';
    }
    if (valor is bool) {
      return valor ? 'Sí' : 'No';
    }
    return valor.toString();
  }

  /// `que_se_hizo` → `Que se hizo`. Para las claves de los hechos del sistema,
  /// que no traen título propio.
  static String _humanizar(String clave) {
    final String conEspacios = clave.replaceAll('_', ' ');
    if (conEspacios.isEmpty) {
      return clave;
    }
    return conEspacios[0].toUpperCase() + conEspacios.substring(1);
  }
}
