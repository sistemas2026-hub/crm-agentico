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
    this.cierreEnFinalizar = false,
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

  /// El reporte de cierre sale del botón «Finalizar», no de acá.
  ///
  /// Decisión del usuario (17/10/2026): «una única acción de cierre». Tener
  /// «Reporte de cierre» al lado de «Finalizar» eran dos procedimientos para
  /// terminar lo mismo. Con esto encendido el botón no se ofrece, y bloquear
  /// —lo que hay que poder hacer siempre— va primero.
  final bool cierreEnFinalizar;

  @override
  State<SeguimientoDeLaIntervencion> createState() =>
      _SeguimientoDeLaIntervencionState();
}

class _SeguimientoDeLaIntervencionState
    extends State<SeguimientoDeLaIntervencion> {
  /// El momento cuya hoja está abierta, o `null` si no hay ninguna.
  String? _abierto;

  /// Las fotos del borrador, para la hoja. La hoja vive en OTRA ruta (sube
  /// desde abajo), así que no se redibuja cuando quien captura actualiza la
  /// cuenta: este aviso es lo que le llega.
  late final ValueNotifier<Map<String, int>> _fotos =
      ValueNotifier<Map<String, int>>(widget.fotosTomadas);

  @override
  void didUpdateWidget(SeguimientoDeLaIntervencion anterior) {
    super.didUpdateWidget(anterior);
    if (!identical(anterior.fotosTomadas, widget.fotosTomadas)) {
      _fotos.value = widget.fotosTomadas;
    }
  }

  // La salida del bloqueo.
  bool _resolviendo = false;
  String? _avisoResolver;
  final TextEditingController _queSeHizo = TextEditingController();

  @override
  void dispose() {
    _queSeHizo.dispose();
    _fotos.dispose();
    super.dispose();
  }

  Map<String, dynamic>? get seguimiento => widget.seguimiento;
  bool get cargando => widget.cargando;
  bool get actualizado => widget.actualizado;

  @override
  Widget build(BuildContext context) {
    return DexterBloque(
      // En la pantalla de ejecución esta tarjeta es para REPORTAR, y se llama
      // así: separada a la vista de «los datos del trabajo» que pide la
      // plantilla, que antes se confundían con el avance.
      titulo: widget.mostrarHistoria
          ? 'Seguimiento de la intervención'
          : 'Reportar',
      icono: widget.mostrarHistoria ? Icons.timeline : Icons.campaign_outlined,
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
          ..._lineaDeTiempo(eventos),
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
    // EN EL ORDEN DEL TRABAJO: inicio, avance, bloqueo (pedido del usuario,
    // 18/10/2026). El bloqueo no va primero —se probó, y rompía la secuencia—
    // sino con su propio tono, para encontrarlo rápido.
    final List<(String, String)> opciones = widget.cierreEnFinalizar
        ? const <(String, String)>[
            ('inicio', 'Registrar inicio'),
            ('avance', 'Registrar avance'),
            ('bloqueo', 'Reportar bloqueo'),
          ]
        : const <(String, String)>[
            ('inicio', 'Registrar inicio'),
            ('avance', 'Registrar avance'),
            ('bloqueo', 'Reportar bloqueo'),
            // «Reporte de cierre» y no «Cerrar intervención»: al lado de
            // «Finalizar orden» los dos sonaban a lo mismo.
            ('cierre', 'Reporte de cierre'),
          ];
    for (final (String momento, String texto) opcion in opciones) {
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
        DexterAccionCompacta(
          texto: _palabraDelMomento(momento),
          descripcion: opcion.$2,
          icono: _icono(momento),
          deAlerta: momento == 'bloqueo',
          alTocar: _abierto != null
              ? null
              : () => _abrirHoja(momento, formularios),
        ),
      );
    }

    return <Widget>[
      if (widget.pendientesDeSubir > 0) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        // «ESTA OT» AL PRINCIPIO, Y NO «ACA».
        //
        // Decía «escritos acá» mientras la cuenta era de TODA la cola del
        // técnico (`contarSeguimientosPendientes` no filtraba por orden): un
        // reporte pendiente de la orden anterior se leía como pendiente de
        // esta. Ahora la cuenta es de esta orden, y el texto lo dice — para
        // que no se pueda confundir con la pastilla del encabezado, que
        // cuenta la cola general y ahora la rotula así.
        Text(
          widget.pendientesDeSubir == 1
              ? 'Esta OT: 1 reporte sin enviar.'
              : 'Esta OT: ${widget.pendientesDeSubir} reportes sin enviar.',
          style: AppTypography.etiquetaChica,
        ),
      ],
      if (botones.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        // EN UNA FILA, ÍCONO Y UNA PALABRA (18/10/2026, pedido del
        // usuario): antes eran botones con frase larga de a dos, y ocupaban
        // dos filas. Todos del mismo ancho.
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (int i = 0; i < botones.length; i++) ...<Widget>[
              if (i > 0) const SizedBox(width: AppSpacing.xs),
              Expanded(child: botones[i]),
            ],
          ],
        ),
      ],
    ];
  }

  /// Abre la hoja del reporte, que SUBE DESDE ABAJO y tapa la pantalla.
  ///
  /// Pedido del usuario (15/10/2026): «¿por qué los botones de avance están
  /// arriba y abajo es donde se pone la información?». La hoja se abría como
  /// otra tarjeta debajo de los botones: fuera de la vista, y con el teclado
  /// abierto más lejos todavía. Y cerrar --o tocar otro botón-- tiraba lo
  /// escrito y las fotos sin preguntar. Ahora:
  ///   - guardar cierra la hoja y lo confirma con un aviso corto;
  ///   - cerrar con algo escrito o una foto sacada PREGUNTA antes de tirarlo;
  ///   - mientras una hoja está abierta, no se puede abrir otra.
  Future<void> _abrirHoja(
    String momento,
    Map<String, dynamic> formularios,
  ) async {
    setState(() => _abierto = momento);
    widget.alAbrirHoja?.call(momento);
    bool pidioNoc = false;

    final bool? guardado = await abrirHojaDeReporte(
      context,
      momento: momento,
      titulo: _tituloDelMomento(momento),
      campos: _camposDe(formularios, momento),
      evidencias: _evidenciasDe(formularios, momento),
      fotos: _fotos,
      alTomarFoto: widget.alTomarFoto == null
          ? null
          : (String requisitoId) => widget.alTomarFoto!(momento, requisitoId),
      alGuardar:
          (
            Map<String, dynamic> respuestas, {
            bool requiereNoc = false,
            bool detener = true,
          }) {
            pidioNoc = requiereNoc;
            widget.alReportar!(
              momento,
              respuestas,
              requiereNoc: requiereNoc,
              detener: detener,
            );
          },
    );

    if (!mounted) return;
    setState(() => _abierto = null);
    if (guardado == true) {
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          // Un bloqueo para el NOC lo dice con todas las letras: guardarlo
          // en el teléfono no es avisarle a nadie (17/10/2026).
          content: Text(
            momento == 'bloqueo' && pidioNoc
                ? 'Bloqueo guardado en el teléfono · el NOC se entera cuando '
                      'suba, al haber señal'
                : '${_nombreDelReporte(momento)} guardado · sube cuando haya '
                      'señal',
          ),
        ),
      );
    } else {
      // Cerrada sin guardar: las fotos sacadas para este reporte no son de
      // ningún otro. La hoja ya preguntó, si había algo que perder.
      widget.alDescartarBorrador?.call(momento);
    }
  }

  /// La palabra del botón compacto.
  static String _palabraDelMomento(String momento) => switch (momento) {
        'inicio' => 'Inicio',
        'avance' => 'Avance',
        'bloqueo' => 'Bloqueo',
        'cierre' => 'Cierre',
        _ => momento,
      };

  static String _nombreDelReporte(String momento) {
    switch (momento) {
      case 'inicio':
        return 'Inicio';
      case 'bloqueo':
        return 'Bloqueo';
      case 'cierre':
        return 'Reporte de cierre';
      default:
        return 'Avance';
    }
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
        return 'Reporte de cierre';
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

  /// La historia como línea de tiempo, agrupada por día y lo más nuevo arriba.
  ///
  /// POR QUÉ (18/10/2026, pedido del usuario): cada evento era una tarjeta
  /// suelta con solo la hora. En una orden de dos días, «14:05» no dice si fue
  /// hoy o ayer, y la historia se leía de lo viejo a lo nuevo cuando lo que el
  /// técnico busca primero es qué pasó último. Ahora cada día tiene su
  /// encabezado con la fecha, cada evento su hora a la izquierda, y una línea
  /// los une en el orden en que ocurrieron.
  List<Widget> _lineaDeTiempo(List<dynamic> crudos) {
    final List<Map<String, dynamic>> eventos = <Map<String, dynamic>>[
      for (final dynamic c in crudos)
        if (c is Map) Map<String, dynamic>.from(c),
    ].reversed.toList();

    final List<Widget> salida = <Widget>[];
    String? diaAnterior;
    for (int i = 0; i < eventos.length; i++) {
      final DateTime? cuando = _fecha(eventos[i]['recibido_en']);
      final String dia = cuando == null ? 'Sin fecha' : _rotuloDelDia(cuando);
      if (dia != diaAnterior) {
        salida.add(Padding(
          padding: EdgeInsets.only(
            top: diaAnterior == null ? 0 : AppSpacing.sm,
            bottom: AppSpacing.xs,
          ),
          child: Text(
            dia.toUpperCase(),
            style: AppTypography.labelCaption.copyWith(color: AppColors.outline),
          ),
        ));
        diaAnterior = dia;
      }
      final bool ultimoDelDia = i == eventos.length - 1 ||
          _rotuloDeEvento(eventos[i + 1]) != dia;
      salida.add(_evento(eventos[i], conLinea: !ultimoDelDia));
    }
    return salida;
  }

  String _rotuloDeEvento(Map<String, dynamic> e) {
    final DateTime? c = _fecha(e['recibido_en']);
    return c == null ? 'Sin fecha' : _rotuloDelDia(c);
  }

  /// «Hoy · 18/10/2026», «Ayer · 17/10/2026», o la fecha sola.
  static String _rotuloDelDia(DateTime cuando, {DateTime? ahora}) {
    final DateTime hoy = ahora ?? DateTime.now();
    final DateTime d = DateTime(cuando.year, cuando.month, cuando.day);
    final int dias = DateTime(hoy.year, hoy.month, hoy.day).difference(d).inDays;
    final String fecha = '${cuando.day.toString().padLeft(2, '0')}/'
        '${cuando.month.toString().padLeft(2, '0')}/${cuando.year}';
    if (dias == 0) return 'Hoy · $fecha';
    if (dias == 1) return 'Ayer · $fecha';
    return fecha;
  }

  Color _colorDeSeveridad(String severidad) => switch (severidad) {
        'problema' => AppColors.error,
        'atencion' => AppColors.precaucion,
        'en_regla' => AppColors.secondary,
        _ => AppColors.outline,
      };

  Widget _evento(Map<String, dynamic> evento, {bool conLinea = false}) {
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

    final Widget contenido = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Wrap(
          spacing: AppSpacing.xs,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            _pastilla(etiqueta, severidad),
            if (quien.isNotEmpty) Text(quien, style: AppTypography.etiquetaChica),
          ],
        ),

        // El detalle de un reporte, leído con el esquema que tenía cuando se
        // capturó. Los títulos vienen de ahí: esta pantalla no sabe qué campos
        // existen ni necesita saberlo.
        for (final dynamic fila in detalle)
          if (fila is Map) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            _dato(
              (fila['titulo'] ?? fila['id'] ?? '').toString(),
              _valorLegible(fila['valor']),
            ),
          ],

        // Los hechos del sistema traen `datos` en vez de `detalle`: el backend
        // expone solo las claves que decidió mostrar.
        for (final String clave in datos.keys)
          if (datos[clave] != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            _dato(_humanizar(clave), _valorLegible(datos[clave])),
          ],

        ..._fotosDelEvento(evento),

        // Las dos horas, cuando difieren. Lo que gobierna el seguimiento es la
        // llegada al servidor; la del teléfono está para reconstruir la
        // historia.
        if (enElTelefono != null && recibido != null) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          Text(
            _demora(enElTelefono, recibido),
            style: AppTypography.etiquetaChica,
          ),
        ],
      ],
    );

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          // La hora, a la izquierda: es lo primero que se busca.
          SizedBox(
            width: 52,
            child: Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                recibido == null ? '—' : _hora(recibido),
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          // El punto y la línea que une con el evento siguiente del mismo día.
          SizedBox(
            width: 20,
            child: Column(
              children: <Widget>[
                const SizedBox(height: 4),
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: _colorDeSeveridad(severidad),
                    shape: BoxShape.circle,
                  ),
                ),
                if (conLinea)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: AppColors.surfaceContainerHigh,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: contenido,
            ),
          ),
        ],
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


/// Abre la hoja de un reporte desde abajo. Devuelve `true` si se guardó.
///
/// Es la misma para los reportes de la sección «Reportar» y para el cierre que
/// sale de «Finalizar» (17/10/2026): una sola forma de escribir un reporte,
/// con la misma pregunta antes de descartar.
Future<bool?> abrirHojaDeReporte(
  BuildContext context, {
  required String momento,
  required String titulo,
  required List<Map<String, dynamic>> campos,
  required List<Map<String, dynamic>> evidencias,
  required ValueNotifier<Map<String, int>> fotos,
  required Future<void> Function(String requisitoId)? alTomarFoto,
  required void Function(
    Map<String, dynamic> respuestas, {
    bool requiereNoc,
    bool detener,
  })
  alGuardar,
  String textoGuardar = 'Guardar el reporte',
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    // Ni arrastrar ni tocar afuera la cierran: los dos la cerraban sin pasar
    // por la pregunta, y un roce no puede costar un reporte escrito en la
    // calle. Se cierra con la ✕ o con «atrás», y los dos preguntan.
    enableDrag: false,
    isDismissible: false,
    backgroundColor: AppColors.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.hoja)),
    ),
    builder: (BuildContext hoja) => _HojaDelReporte(
      momento: momento,
      titulo: titulo,
      campos: campos,
      evidencias: evidencias,
      fotos: fotos,
      alTomarFoto: alTomarFoto,
      alGuardar: alGuardar,
      textoGuardar: textoGuardar,
    ),
  );
}

/// La hoja del reporte, como ruta propia que sube desde abajo.
///
/// Sabe una sola cosa además de dibujar el formulario: si cerrarla tiraría
/// algo. Con algo escrito o una foto sacada, pregunta; sin nada, se cierra.
class _HojaDelReporte extends StatefulWidget {
  const _HojaDelReporte({
    required this.momento,
    required this.titulo,
    required this.campos,
    required this.evidencias,
    required this.fotos,
    required this.alTomarFoto,
    required this.alGuardar,
    this.textoGuardar = 'Guardar el reporte',
  });

  final String textoGuardar;
  final String momento;
  final String titulo;
  final List<Map<String, dynamic>> campos;
  final List<Map<String, dynamic>> evidencias;
  final ValueNotifier<Map<String, int>> fotos;
  final Future<void> Function(String requisitoId)? alTomarFoto;
  final void Function(
    Map<String, dynamic> respuestas, {
    bool requiereNoc,
    bool detener,
  })
  alGuardar;

  @override
  State<_HojaDelReporte> createState() => _HojaDelReporteState();
}

class _HojaDelReporteState extends State<_HojaDelReporte> {
  bool _hayAlgoEscrito = false;

  bool get _hayAlgoQuePerder =>
      _hayAlgoEscrito || widget.fotos.value.values.any((int n) => n > 0);

  Future<void> _intentarCerrar() async {
    if (!_hayAlgoQuePerder) {
      Navigator.of(context).pop(false);
      return;
    }
    final bool? descartar = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogo) => AlertDialog(
        title: const Text('¿Descartar este reporte?'),
        content: const Text(
          'Se pierde lo que escribiste y las fotos que sacaste para él.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogo).pop(false),
            child: const Text('Seguir escribiendo'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogo).pop(true),
            child: const Text('Descartar'),
          ),
        ],
      ),
    );
    if (descartar == true && mounted) {
      Navigator.of(context).pop(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // Casi toda la pantalla, y por encima del teclado: sin el `viewInsets`, el
    // teclado tapaba justo el botón de guardar.
    final MediaQueryData medidas = MediaQuery.of(context);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (bool yaSalio, Object? _) {
        if (!yaSalio) _intentarCerrar();
      },
      child: Padding(
        padding: EdgeInsets.only(bottom: medidas.viewInsets.bottom),
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: medidas.size.height * 0.92),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.margen,
                  AppSpacing.md,
                  AppSpacing.xs,
                  0,
                ),
                child: Row(
                  children: <Widget>[
                    const Icon(Icons.edit_note, color: AppColors.secondary),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        widget.titulo,
                        style: AppTypography.cuerpoGrande,
                      ),
                    ),
                    IconButton(
                      tooltip: 'Cerrar',
                      icon: const Icon(Icons.close),
                      onPressed: _intentarCerrar,
                    ),
                  ],
                ),
              ),
              Flexible(
                child: ValueListenableBuilder<Map<String, int>>(
                  valueListenable: widget.fotos,
                  builder: (_, Map<String, int> fotos, _) => HojaDeReporte(
                    momento: widget.momento,
                    titulo: widget.titulo,
                    campos: widget.campos,
                    evidencias: widget.evidencias,
                    alTomarFoto: widget.alTomarFoto,
                    fotosTomadas: fotos,
                    enHojaModal: true,
                    textoDelBoton: widget.textoGuardar,
                    alCambiarContenido: (bool hay) => _hayAlgoEscrito = hay,
                    alGuardar:
                        (
                          Map<String, dynamic> respuestas, {
                          bool requiereNoc = false,
                          bool detener = true,
                        }) {
                          widget.alGuardar(
                            respuestas,
                            requiereNoc: requiereNoc,
                            detener: detener,
                          );
                          Navigator.of(context).pop(true);
                        },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
