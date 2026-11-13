import 'de_donde_sale_la_foto.dart';
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';

import '../../demo/field_mock_data.dart';
import '../../core/storage/evidencia_storage_service.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/ubicacion_de_captura.dart';
import '../../core/marca/marca_de_agua_local.dart';
import '../detalle_orden/acciones_orden.dart';
import '../detalle_orden/comprobar_conexion.dart';
import '../detalle_orden/pasos_orden.dart';
import '../detalle_orden/seguimiento_de_la_intervencion.dart';
import '../trabajo/estado_trabajo.dart';
import '../trabajo/trabajo_vista.dart';
import 'campo_del_formulario.dart';
import 'cierre_de_orden.dart';
import 'datos_de_ejecucion.dart';
import 'pasos_del_trabajo.dart';
import 'resumen_para_finalizar.dart';
import 'widgets/consumo_de_material.dart';
import 'widgets/firma_del_cliente.dart';
import 'widgets/foto_con_marca_de_evidencia.dart';
import '../contrato/contrato_screen.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/widgets/contenido_centrado.dart';
import '../../core/widgets/dexter_app_header.dart';
import '../../core/widgets/dexter_bloques.dart';
import '../../core/widgets/dexter_sync_badge.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/offline_saved_banner.dart';
import 'progreso_evidencias.dart';
import 'widgets/bloque_academia.dart';
import 'widgets/formulario_de_campo.dart';
import '../trabajo/widgets/franja_del_servicio.dart';

/// El trabajo, ejecutándose: el formulario de campo y la evidencia.
///
/// El aspecto es el del diseño de Stitch; las preguntas siguen siendo las que
/// manda el backend con la orden (`formulario_campos_json`), y cada respuesta
/// se guarda en SQLite en el momento, sin esperar a tener señal.
class EjecucionScreen extends StatefulWidget {
  final String ordenId;

  /// Enciende lo que el diseño muestra y todavía no existe: la sugerencia de
  /// reemplazo, el medidor por Bluetooth y las cápsulas de Academia.
  final bool mostrarDatosFuturos;

  /// De dónde salen los datos. Nula en la aplicación: se usa la base del
  /// teléfono. En una prueba o una captura se pasa otra, y el dibujo es el
  /// mismo — que es justamente lo que se quiere comparar.
  final FuenteDeEjecucion? fuente;

  /// El estado de la cola, si ya se conoce. Nulo: el chip lo consulta solo.
  final SyncSummary? resumenDeSync;

  const EjecucionScreen({
    super.key,
    required this.ordenId,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
    this.fuente,
    this.resumenDeSync,
    this.acciones,
  });

  /// Medir la señal, el ping y volver a pedir la ficha, para el bloque
  /// «Comprobar conexión» (17/10/2026). Nulo en una prueba que no los usa: el
  /// bloque no se dibuja.
  final AccionesOrden? acciones;

  @override
  State<EjecucionScreen> createState() => _EjecucionScreenState();
}

class _EjecucionScreenState extends State<EjecucionScreen> {
  late final FuenteDeEjecucion _fuente =
      widget.fuente ?? FuenteLocalDeEjecucion();

  /// Las hojas modales —consumo de material, firma— hablan con la base por su
  /// cuenta. No pasan por la fuente porque sólo existen cuando alguien toca un
  /// botón: nunca se abren solas al dibujar, así que no impiden montar la
  /// pantalla en una prueba.
  late final LocalDatabase _baseParaHojas = LocalDatabase();
  final ImagePicker _picker = ImagePicker();

  Map<String, dynamic>? _orden;
  String? _orgId;
  String? _profileId;

  /// Lo que se registro como usado en ESTA orden.
  ///
  /// Se lee de la cola y no de un contador propio: la cola es la que sube, y
  /// un numero aparte se desincronizaria en cuanto algo se reintente.
  List<Map<String, dynamic>> _materialesUsados = <Map<String, dynamic>>[];
  bool _isLoading = true;

  // ------------------------------------------------------------------
  //  EL SEGUIMIENTO, QUE DESDE EL 02/10/2026 SE ESCRIBE ACA
  // ------------------------------------------------------------------
  //  Los botones de reportar vivian en la ficha. El tecnico estaba en esta
  //  pantalla con las manos en la caja, se le caia un poste, y tenia que salir,
  //  volver atras y bajar para reportarlo.
  //
  //  Lo que NO se mueve: la linea de tiempo --se consulta, no se escribe-- y el
  //  bloqueo abierto con su salida. Con el trabajo detenido no hay «Ejecutar el
  //  trabajo», asi que si destrabar viviera aca seria un callejon sin salida.
  Map<String, dynamic>? _seguimiento;
  bool _cargandoSeguimiento = true;
  int _reportesSinSubir = 0;

  /// Cuantas fotos lleva cada requisito de la hoja abierta. Sale del disco, no
  /// de un contador: abrir la camara puede destruir esta pantalla.
  Map<String, int> _fotosDelBorrador = <String, int>{};

  /// La carga terminó y no había nada que mostrar.
  bool _noSePudoCargar = false;
  bool _showSavedIndicator = false;
  Timer? _savedIndicatorTimer;

  /// El botón "Borrador" no guarda nada nuevo —cada respuesta ya se escribió
  /// en SQLite al tocarla—: confirma que lo escrito está a salvo.
  bool _borradorConfirmado = false;

  /// Si ya se intentó finalizar con algo pendiente. Hasta entonces la franja
  /// «Falta» es gris: durante el trabajo siempre falta algo, y pintarlo de rojo
  /// desde el primer minuto hacía que toda la visita pareciera una emergencia.
  bool _intentoFinalizar = false;

  /// En qué paso de la plantilla está el técnico, cuando la plantilla tiene
  /// pasos. Ver `pasosDeEjecucion`.
  int _pasoActual = 0;

  /// Las fotos del borrador para la hoja del cierre, que vive en otra ruta y
  /// no se redibuja sola.
  final ValueNotifier<Map<String, int>> _fotosDeHoja =
      ValueNotifier<Map<String, int>>(<String, int>{});
  Timer? _borradorTimer;

  List<dynamic> _campos = [];
  List<dynamic> _evidenciasRequisitos = [];
  Map<String, dynamic> _valoresFormulario = {};
  List<Map<String, dynamic>> _evidenciasCapturadas = [];

  /// La marca de agua de la empresa, para mostrar sobre cada foto lo que el
  /// servidor le va a estampar (13/11/2026). Arranca apagada y se lee del
  /// teléfono; si hay red, se refresca. Ver `MarcaDeAguaLocal`.
  MarcaDeLaEmpresa _marca = MarcaDeLaEmpresa.apagada;

  final Map<String, TextEditingController> _controllers = {};

  @override
  void initState() {
    super.initState();
    _loadOrdenData();
    _traerSeguimiento();
  }

  @override
  void dispose() {
    _fotosDeHoja.dispose();
    _savedIndicatorTimer?.cancel();
    _borradorTimer?.cancel();
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _triggerSavedBanner() {
    setState(() {
      _showSavedIndicator = true;
    });
    _savedIndicatorTimer?.cancel();
    _savedIndicatorTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _showSavedIndicator = false;
        });
      }
    });
  }

  Future<void> _loadOrdenData() async {
    final DatosDeEjecucion? datos = await _fuente.cargar(widget.ordenId);
    if (datos == null) {
      // No hay sesión, o la orden todavía no bajó al teléfono. Antes esto
      // devolvía en silencio y la pantalla quedaba en blanco para siempre:
      // sin decir qué pasó y sin forma de salir.
      if (mounted) {
        setState(() {
          _isLoading = false;
          _noSePudoCargar = true;
        });
      }
      return;
    }

    _orgId = datos.orgId;
    _profileId = datos.profileId;
    _campos = datos.campos;
    _evidenciasRequisitos = datos.requisitosDeEvidencia;
    _pasosDelProtocolo = datos.pasos;
    _valoresFormulario = Map<String, dynamic>.from(datos.valores);
    _materialesUsados = datos.materialesUsados;
    _evidenciasCapturadas = datos.evidenciasCapturadas;

    // Un controlador por campo, con lo que ya estaba respondido.
    //
    // El id sale del modelo normalizado, no de leer el JSON a mano: era la
    // quinta interpretacion del mismo esquema y la unica que quedaba.
    for (final CampoDelFormulario campo in CampoDelFormulario.normalizar(
      _campos,
      _valoresFormulario,
    )) {
      // `putIfAbsent`: al volver a leer la orden —después de pedir la ficha
      // otra vez— el campo conserva su controlador y lo que se está escribiendo.
      _controllers.putIfAbsent(
        campo.id,
        () => TextEditingController(text: campo.valor?.toString() ?? ''),
      );
    }

    if (mounted) {
      setState(() {
        _orden = datos.orden;
        _isLoading = false;
      });
    }
    unawaited(_cargarMarca(datos.orgId));
  }

  /// Primero lo guardado --para que la vista previa esté aunque no haya
  /// señal-- y después lo que diga el servidor. Nunca lanza.
  Future<void> _cargarMarca(String orgId) async {
    final MarcaDeAguaLocal local = MarcaDeAguaLocal();
    final MarcaDeLaEmpresa guardada = await local.leer(orgId);
    if (mounted) setState(() => _marca = guardada);
    final MarcaDeLaEmpresa fresca = await local.refrescar(orgId);
    if (mounted) setState(() => _marca = fresca);
  }

  Future<void> _onFieldChanged(String clave, dynamic valor) async {
    if (_orgId == null || _profileId == null) return;

    _valoresFormulario[clave] = valor;

    // Persistencia atómica inmediata en SQLite
    await _fuente.guardarCampo(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      clave: clave,
      valor: valor,
    );

    _fuente.refrescarResumen();
    _triggerSavedBanner();
  }

  /// La hoja que ofrece las dos fuentes (09/11/2026).
  ///
  /// El usuario: «deben ser ambos pero en un solo botón». La plantilla ya no
  /// decide SI se puede usar la galería --se puede siempre-- sino cuál se
  /// ofrece primero: para una captura de pantalla, la galería; para el resto,
  /// la cámara. Un toque menos en el caso frecuente de cada requisito.
  ///
  /// Si la hoja se cierra sin elegir, no pasa nada: cerrar no es un error.
  Future<void> _elegirDeDondeSaleLaFoto(
      String requisitoId, Map<String, dynamic>? requisito) async {
    final ImageSource primera = fuenteDeLaEvidencia(requisito);
    final ImageSource segunda = laOtraFuente(primera);

    final ImageSource? elegida = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (BuildContext hoja) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            for (final ImageSource f in <ImageSource>[primera, segunda])
              ListTile(
                leading: Icon(f == ImageSource.camera
                    ? Icons.camera_alt_outlined
                    : Icons.photo_library_outlined),
                title: Text(textoDeLaOpcion(f)),
                onTap: () => Navigator.of(hoja).pop(f),
              ),
          ],
        ),
      ),
    );

    if (elegida == null) return;
    await _tomarFoto(requisitoId, fuente: elegida);
  }

  Future<void> _tomarFoto(String requisitoId,
      {ImageSource fuente = ImageSource.camera}) async {
    if (_orgId == null || _profileId == null) return;

    try {
      final XFile? foto = await _picker.pickImage(
        source: fuente,
        imageQuality: 85,
        maxWidth: 1920,
      );

      if (foto == null) return;

      // El instante en que la persona apreto el obturador -- no el de encolar,
      // que llega despues de copiar el archivo y calcular su sha256.
      final DateTime capturadaEn = DateTime.now();

      // Donde se tomo. Va aca y no antes de abrir la camara porque recien
      // ahora se sabe que hubo foto: pedirle posicion al sistema para una
      // camara que la persona cancela es gastarle bateria por nada.
      //
      // Nunca lanza y nunca tarda mas de su plazo: una evidencia no se pierde
      // ni se demora porque el GPS no fije. Ver `UbicacionDeCaptura`.
      final Map<String, dynamic> metadatos = <String, dynamic>{
        ...await UbicacionDeCaptura.tomar(),
        // DE DÓNDE SALIÓ LA IMAGEN (09/11/2026). Desde que el botón ofrece las
        // dos fuentes, una evidencia puede no haberse tomado en el momento, y
        // quien revisa el cierre no tiene cómo saberlo mirándola.
        //
        // Es la contrapartida de abrir la galería a todos los requisitos:
        // antes esa diferencia se defendía prohibiéndola, y el precio lo
        // pagaba el técnico cuando la cámara no servía para ese requisito.
        // Ahora se defiende diciendo la verdad sobre cada imagen.
        //
        // Va en los metadatos, que ya es un mapa libre que viaja con la
        // evidencia junto con la ubicación de captura.
        'de_galeria': esDeGaleria(fuente),
      };

      final tempFile = File(foto.path);
      // El id se genera ANTES de copiar el archivo porque el archivo se llama
      // como él: si la fila se perdiera, la foto sigue diciendo cual es su
      // evidencia, de quien es y de que orden.
      final evId = const Uuid().v4();
      // Persistir inmediatamente en almacenamiento seguro y durable privado
      final persistentFile =
          await EvidenciaStorageService.persistirArchivoCaptura(
            tempFile,
            nombreOriginal: foto.name,
            orgId: _orgId!,
            profileId: _profileId!,
            ordenId: widget.ordenId,
            evidenciaId: evId,
          );
      final sha = await SyncQueueService.calcularSha256(persistentFile);
      final size = await persistentFile.length();
      final registroKey = const Uuid().v4();
      final confirmacionKey = const Uuid().v4();

      await _fuente.encolarEvidencia(
        id: evId,
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
        requisitoId: requisitoId,
        archivoPath: persistentFile.path,
        sha256: sha,
        tamanoBytes: size,
        mimeType: 'image/jpeg',
        registroIdempotencyKey: registroKey,
        confirmacionIdempotencyKey: confirmacionKey,
        capturadaEn: capturadaEn,
        metadatosCaptura: metadatos,
      );

      _evidenciasCapturadas = await _fuente.evidenciasDe(
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
      );

      _triggerSavedBanner();

      // Disparar sincronización oportunista de fondo
      _fuente.procesarCola();

      if (mounted) setState(() {});
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Error al capturar foto: $e')));
      }
    }
  }

  Future<void> _completarOrden() async {
    if (_orden == null || _orgId == null || _profileId == null) return;

    // El botón le pregunta AL MISMO veredicto que dibuja el checklist.
    //
    // Antes tenía su propia validación: recorría el esquema por su cuenta y
    // sólo miraba si el campo estaba vacío. Con una medición fuera del rango
    // que el esquema declara —un -45 dBm donde se piden entre -30 y -5— el
    // checklist objetaba y el botón dejaba cerrar igual. La orden se firmaba
    // con un número imposible, y eso nadie lo vuelve a mirar.
    //
    // Era la cuarta lectura independiente del mismo esquema. Esta es la que
    // decidía de verdad.
    final CierreDeOrden veredicto = _cierre;
    if (!veredicto.puedeCerrar) {
      setState(() => _intentoFinalizar = true);
      final RequisitoDeCierre primero = veredicto.bloqueantes.first;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: AppTheme.errorRed,
          content: Text(
            primero.detalle.isEmpty
                ? '${primero.titulo}: falta completarlo.'
                : '${primero.titulo}: ${primero.detalle}',
          ),
        ),
      );
      return;
    }

    // 0. EL RESUMEN, ANTES DE NADA (09/11/2026). El usuario: «para cerrar el
    //    caso debería mostrar mejor un resumen de lo realizado, y así el
    //    técnico revisa el resumen y corrige o finaliza si está todo bien».
    //
    //    Va primero --antes de la pregunta del material y antes del formulario
    //    de cierre-- porque es el momento en que todavía se puede corregir sin
    //    deshacer nada. «Corregir» vuelve a la pantalla, donde cada campo está
    //    donde se llenó: si el resumen tuviera sus propios campos editables
    //    habría dos lugares para escribir lo mismo, que es justo el problema
    //    que esto viene a resolver.
    //    Lo que el cierre todavia tiene que preguntar se reparte en tres
    //    (ver `repartirElCierre`): lo que hay que DECLARAR --si el servicio
    //    quedo funcionando-- va dentro del resumen; lo que el resumen ya
    //    responde se llena con el; y si la empresa declaro alguna pregunta
    //    que no es ni una cosa ni la otra, esa se sigue pidiendo en su hoja.
    final Map<String, dynamic>? formularioDeCierre = _formularioDe('cierre');
    final PreguntasDelCierre preguntas = repartirElCierre(
      formularioDeCierre == null
          ? const <CampoDelFormulario>[]
          : CampoDelFormulario.normalizar(
              _listaDe(formularioDeCierre, 'campos'),
              const <String, dynamic>{},
            ),
    );

    final Map<String, dynamic>? delResumen = await _revisarElResumen(preguntas);
    if (delResumen == null) return;
    if (!mounted) return;

    // Todo satisfecho: transicionar localmente a completada_pendiente_sync.
    final revisionBase = _orden!['revision'] as int? ?? 0;

    // 1. SIN MATERIAL REGISTRADO SE PREGUNTA, UNA VEZ (decisión del usuario,
    //    17/10/2026). Sin pantalla nueva y sin bloquear un trabajo que de
    //    verdad no usa material, como cambiar una clave.
    bool sinMaterialConfirmado = false;
    if (_materialesUsados.isEmpty) {
      final String? eleccion = await _confirmarSinMaterial();
      if (!mounted) return;
      if (eleccion == 'registrar') {
        await _abrirConsumoDeMaterial();
        return;
      }
      if (eleccion != 'si') return;
      sinMaterialConfirmado = true;
    }

    // 2. EL REPORTE DE CIERRE SALE DE ACÁ, Y ES UNO POR VUELTA (decisión del
    //    usuario, 17/10/2026: «una única acción de cierre»). El id es fijo por
    //    revisión: un reintento de «Finalizar» no escribe un segundo reporte,
    //    y una orden devuelta —revisión nueva— sí lleva el suyo.
    final String idCierre = 'seg-${widget.ordenId}-cierre-r$revisionBase';
    if (!await _fuente.existeReporte(idCierre)) {
      if (formularioDeCierre != null) {
        //  LA HOJA SOLO SI QUEDA ALGO QUE PREGUNTAR (09/11/2026, el usuario:
        //  «ese ultimo formulario no deberia salir»). Con el minimo del
        //  backend no queda nada: el resumen lo responde entero.
        Map<String, dynamic>? respuestas = delResumen;
        if (!preguntas.alcanzaConElResumen) {
          final Map<String, dynamic>? extra =
              await _pedirCierre(formularioDeCierre);
          if (!mounted) return;
          if (extra == null) return;
          respuestas = <String, dynamic>{...delResumen, ...extra};
        }
        await _encolarPorDefecto(
          widget.ordenId,
          'cierre',
          <String, dynamic>{
            ...respuestas!,
            // Dato de plataforma: viaja aparte de las respuestas (ver la
            // cola). La plantilla no lo declara y el servidor lo rechazaría
            // como respuesta.
            if (sinMaterialConfirmado)
              '__plataforma': <String, dynamic>{'sin_material_confirmado': true},
          },
          idFijo: idCierre,
        );
        if (!mounted) return;
      }
    }
    final idempotencyKey = const Uuid().v4();

    await _fuente.transicionar(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      nuevoEstadoLocal: 'completada_pendiente_sync',
      tipoAccion: 'completar',
      revisionBase: revisionBase,
      idempotencyKey: idempotencyKey,
    );

    // 4. Intentar sincronización en segundo plano
    _fuente.procesarCola();

    if (mounted) {
      await showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          // «¡Trabajo Finalizado con Éxito!» se leía como «la oficina ya lo
          // tiene» aunque estuviera sin señal, y además falta la revisión.
          // Ahora dice las tres cosas que son verdad en ese momento
          // (17/10/2026). El verde se guarda para lo que el servidor aceptó.
          icon: const Icon(
            Icons.task_alt,
            color: AppColors.secondary,
            size: 48,
          ),
          title: const Text('Trabajo terminado en campo'),
          content: const Text(
            'Quedó guardado en este teléfono. Se envía solo cuando haya '
            'señal, y después la oficina lo revisa: todavía puede volver '
            'con observaciones.',
          ),
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                Navigator.of(context).pop();
              },
              child: const Text('ENTENDIDO'),
            ),
          ],
        ),
      );
    }
  }

  /// El formulario de un reporte, de lo que el servidor declaró. Nulo cuando
  /// el seguimiento nunca bajó al teléfono: sin él no se sabe qué pide el
  /// cierre, y se finaliza igual —el trabajo no puede quedar trabado por eso—.
  Map<String, dynamic>? _formularioDe(String momento) {
    final Object? formularios = _seguimiento?['formularios'];
    if (formularios is! Map) return null;
    final Object? f = formularios[momento];
    return f is Map ? Map<String, dynamic>.from(f) : null;
  }

  List<Map<String, dynamic>> _listaDe(Map<String, dynamic> f, String clave) =>
      <Map<String, dynamic>>[
        for (final dynamic x in (f[clave] as List<dynamic>? ?? const <dynamic>[]))
          if (x is Map) Map<String, dynamic>.from(x),
      ];

  /// Muestra lo cargado, pregunta lo único que falta, y finaliza desde ahí
  /// (09/11/2026).
  ///
  /// El usuario, después de ver el resumen andando: «ese último formulario no
  /// debería salir... solo el botón de que el servicio queda funcionando, en
  /// el mismo resumen, y desde ahí sí finaliza».
  ///
  /// Devuelve las respuestas del cierre, o `null` si tocó «Corregir» o cerró
  /// la hoja --las dos cosas significan lo mismo: no finalizar todavía, y nada
  /// se deshace--.
  ///
  /// Las cuentas de fotos, material y firma no se recalculan acá: salen del
  /// mismo checklist que decide si se puede cerrar. Dos cuentas distintas del
  /// mismo hecho terminan contradiciéndose, y entonces el resumen diría una
  /// cosa y el botón haría otra.
  Future<Map<String, dynamic>?> _revisarElResumen(
      PreguntasDelCierre preguntas) async {
    final List<LineaDeResumen> lineas =
        resumenParaFinalizar(_camposNormalizados);

    //  Las declaraciones arrancan sin responder: una que viniera en «sí» por
    //  omisión sería el sistema afirmando algo que nadie afirmó, que es justo
    //  lo que el backend evita marcándolas como declaración.
    final Map<String, bool> declarado = <String, bool>{
      for (final CampoDelFormulario c in preguntas.declaraciones) c.id: false,
    };

    final bool? listo = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (BuildContext hoja) => StatefulBuilder(
        builder: (BuildContext ctx, void Function(void Function()) redibujar) =>
            SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text('Antes de finalizar, revisá',
                    style: AppTypography.tituloChico),
                const SizedBox(height: AppSpacing.sm),
                Flexible(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        //  Sin ningún campo respondido se dice, en vez de
                        //  mostrar un resumen en blanco que parece un error.
                        if (lineas.isEmpty)
                          Text(
                            'Este trabajo no tiene datos cargados para revisar.',
                            style: AppTypography.cuerpoChico,
                          ),
                        for (final LineaDeResumen l in lineas)
                          Padding(
                            padding:
                                const EdgeInsets.only(bottom: AppSpacing.sm),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(l.titulo,
                                    style: AppTypography.etiquetaChica),
                                Text(l.valor, style: AppTypography.cuerpo),
                              ],
                            ),
                          ),
                        //  Lo que no es una respuesta escrita sino una cuenta:
                        //  sale del checklist, que es el que decide si cierra.
                        for (final RequisitoDeCierre r in _cierre.requisitos)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 2),
                            child: Text(
                              r.detalle.isEmpty
                                  ? r.titulo
                                  : '${r.titulo}: ${r.detalle}',
                              style: AppTypography.cuerpoChico,
                            ),
                          ),
                        //  LO ÚNICO QUE TODAVÍA HAY QUE PREGUNTAR. Acá y no en
                        //  otra pantalla: es el pedido del usuario, y además
                        //  es lo que se afirma MIRANDO el resumen de arriba.
                        for (final CampoDelFormulario c
                            in preguntas.declaraciones)
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text(c.titulo, style: AppTypography.cuerpo),
                            value: declarado[c.id] ?? false,
                            onChanged: (bool v) =>
                                redibujar(() => declarado[c.id] = v),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.of(hoja).pop(false),
                        child: const Text('Corregir'),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: FilledButton(
                        onPressed: () => Navigator.of(hoja).pop(true),
                        child: const Text('Está bien, finalizar'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );

    if (listo != true) return null;

    //  Lo declarado, más lo que el resumen ya responde. Ver `cierreDeducido`:
    //  no inventa texto, repite lo que el técnico acaba de aprobar.
    final String delResumen = cierreDeducido(lineas);
    return <String, dynamic>{
      ...declarado,
      for (final CampoDelFormulario c in preguntas.sePuedenDeducir)
        c.id: delResumen,
    };
  }

  Future<Map<String, dynamic>?> _pedirCierre(Map<String, dynamic> formulario) async {
    await _contarFotos('cierre');
    _fotosDeHoja.value = _fotosDelBorrador;
    Map<String, dynamic>? respuestas;
    if (!mounted) return null;
    final bool? guardado = await abrirHojaDeReporte(
      context,
      momento: 'cierre',
      titulo: 'Cierre del trabajo',
      campos: _listaDe(formulario, 'campos'),
      evidencias: _listaDe(formulario, 'evidencias'),
      fotos: _fotosDeHoja,
      alTomarFoto: (String requisitoId) async {
        await _tomarFotoDelReporte('cierre', requisitoId);
        _fotosDeHoja.value = _fotosDelBorrador;
      },
      alGuardar: (Map<String, dynamic> r, {bool requiereNoc = false, bool detener = true}) {
        respuestas = r;
      },
      textoGuardar: 'Guardar y finalizar',
    );
    if (guardado != true) {
      await _descartarBorrador('cierre');
      return null;
    }
    return respuestas;
  }

  /// «No hay materiales registrados en esta orden.» Devuelve `si`,
  /// `registrar` o nulo si se cerró sin elegir.
  Future<String?> _confirmarSinMaterial() {
    return showDialog<String>(
      context: context,
      builder: (BuildContext c) => AlertDialog(
        title: const Text('No hay materiales registrados en esta orden'),
        content: const Text('¿Confirmás que no utilizaste materiales?'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(c).pop('registrar'),
            child: const Text('Volver a registrar'),
          ),
          TextButton(
            onPressed: () => Navigator.of(c).pop('si'),
            child: const Text('Sí, no utilicé materiales'),
          ),
        ],
      ),
    );
  }

  void _confirmarBorrador() {
    // No escribe: solo confirma. Cada respuesta ya se guardó al tocarla.
    _triggerSavedBanner();
    setState(() => _borradorConfirmado = true);
    _borradorTimer?.cancel();
    _borradorTimer = Timer(const Duration(milliseconds: 1500), () {
      if (mounted) setState(() => _borradorConfirmado = false);
    });
  }

  /// Lo registrado en esta orden, de la cola local.
  Future<List<Map<String, dynamic>>> _materialesDeEstaOrden() async {
    if (_orgId == null || _profileId == null) return <Map<String, dynamic>>[];
    final todos = await _fuente.materialesDe(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
    );
    return todos;
  }

  Future<void> _abrirConsumoDeMaterial() async {
    if (_orgId == null || _profileId == null) return;
    final registrado = await ConsumoDeMaterial.abrir(
      context,
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      ordenNumero: _numeroDeLaOrden,
      baseLocal: _baseParaHojas,
    );
    if (registrado != true || !mounted) return;
    final usados = await _materialesDeEstaOrden();
    if (!mounted) return;
    setState(() => _materialesUsados = usados);
  }

  /// El numero de la orden, si se pudo leer. Nunca se inventa uno.
  int? get _numeroDeLaOrden {
    final valor = _orden?['numero'];
    if (valor is int) return valor;
    return int.tryParse(valor?.toString() ?? '');
  }

  /// El paso de materiales.
  ///
  /// Va junto al formulario y las evidencias porque es parte del mismo gesto:
  /// lo que se hizo, con que se hizo y como quedo. Sacarlo a otra pantalla
  /// convertiria "anotar dos conectores" en un viaje de ida y vuelta que nadie
  /// hace con las manos en la caja terminal.

  // ==================================================================
  //  EL SEGUIMIENTO: reportar inicio, avance, bloqueo y cierre
  // ==================================================================
  //
  //  Estos metodos venian de la ficha, donde funcionaban y estaban verificados
  //  contra el backend real. Lo unico que cambia es DONDE viven: el reporte se
  //  escribe con las manos en la caja, no volviendo a la pantalla anterior.
  //
  //  Esta pantalla ya tenia `_orgId`, `_profileId` y la camara, asi que la
  //  mudanza no trajo plomeria nueva.

  /// EL BORRADOR, Y POR QUE SE DERIVA EN VEZ DE SORTEARSE
  /// ----------------------------------------------------
  /// La foto se saca antes de guardar el reporte: en ese momento todavia no hay
  /// fila de `cola_seguimiento` a la cual atarla. Nace con el id del borrador y
  /// al guardar se repunta al reporte real.
  ///
  /// Ese id NO puede ser un UUID guardado en memoria. Abrir la camara en Android
  /// puede destruir esta pantalla; al volver, Flutter la reconstruye con estado
  /// nuevo y el UUID anterior se perdio. La foto quedaria huerfana para siempre.
  /// Medido en el emulador el 02/10/2026.
  String _borradorDe(String momento) => 'borrador-${widget.ordenId}-$momento';

  /// Trae el seguimiento al abrir la orden.
  ///
  /// Se pide ACA y no en la sincronizacion general porque un tecnico puede tener
  /// veinte ordenes asignadas y mira una: traer las veinte gastaria datos y
  /// bateria para dibujar diecinueve historias que nadie va a abrir.
  Future<void> _traerSeguimiento() async {
    try {
      final Map<String, dynamic>? datos = await _seguimientoDelTelefono();
      if (!mounted) return;
      final int sinSubir = await _contarSinSubir();
      if (!mounted) return;
      setState(() {
        _seguimiento = datos;
        _cargandoSeguimiento = false;
        _reportesSinSubir = sinSubir;
      });
    } catch (_) {
      // Que falle no puede dejar la pantalla cargando para siempre: se deja de
      // esperar y la seccion dice lo que sabe.
      if (!mounted) return;
      setState(() {
        _cargandoSeguimiento = false;
      });
    }
  }

  /// El seguimiento, para saber QUE momentos ofrece este tipo de trabajo.
  ///
  /// Esta pantalla no dibuja la historia --eso es de la ficha-- pero necesita
  /// los `formularios`: son los que dicen que campos y que fotos pide cada
  /// momento. Sin eso no habria botones que mostrar.
  ///
  /// Espejo primero, red despues: el mismo orden que en la ficha y por el mismo
  /// motivo. Si se pidiera la red primero, un tecnico sin señal esperaria el
  /// timeout completo mirando una pantalla sin botones, teniendo el dato
  /// guardado en el telefono.
  Future<Map<String, dynamic>?> _seguimientoDelTelefono() =>
      _fuente.seguimiento(widget.ordenId);

  /// Guarda un reporte y lo manda a subir.
  ///
  /// El orden es el que importa en la calle: PRIMERO se guarda en el telefono y
  /// despues se intenta subir. Al reves, un reporte escrito sin señal se perderia
  /// en el error de red -- y el tecnico ya habia hecho el trabajo de escribirlo.
  Future<void> _reportar(
    String momento,
    Map<String, dynamic> respuestas, {
    bool requiereNoc = false,
    bool detener = true,
  }) async {
    await _encolarPorDefecto(
      widget.ordenId,
      momento,
      respuestas,
      requiereNoc: requiereNoc,
      detener: detener,
    );
    // Se vuelve a leer: si subio, el espejo ya trae el evento confirmado por el
    // servidor; si no, al menos se actualiza cuantos esperan.
    await _traerSeguimiento();
  }

  /// Saca una foto para el reporte que se esta escribiendo.
  ///
  /// Reusa el camino que la pantalla de ejecucion usa desde antes: persistir el
  /// archivo en almacenamiento durable, calcular su sha256 y encolarlo. Lo unico
  /// propio es el `reporteLocalId`: el borrador al que pertenece.
  ///
  /// La hora de captura es la del obturador, no la de encolar, y la ubicacion se
  /// pide DESPUES de que haya foto -- pedirsela al sistema para una camara que la
  /// persona cancela es gastarle bateria por nada.
  Future<void> _tomarFotoDelReporte(String momento, String requisitoId) async {
    try {
      final String? orgId = _orgId;
      final String? profileId = _profileId;
      if (orgId == null || profileId == null) {
        return;
      }

      final XFile? foto = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
        maxWidth: 1920,
      );
      if (foto == null) {
        return;
      }

      final DateTime capturadaEn = DateTime.now();
      final Map<String, dynamic> metadatos = await UbicacionDeCaptura.tomar();

      final String evidenciaId = const Uuid().v4();
      final File persistido =
          await EvidenciaStorageService.persistirArchivoCaptura(
            File(foto.path),
            nombreOriginal: foto.name,
            orgId: orgId,
            profileId: profileId,
            ordenId: widget.ordenId,
            evidenciaId: evidenciaId,
          );

      await LocalDatabase().encolarEvidencia(
        id: evidenciaId,
        orgId: orgId,
        profileId: profileId,
        ordenId: widget.ordenId,
        requisitoId: requisitoId,
        archivoPath: persistido.path,
        sha256: await SyncQueueService.calcularSha256(persistido),
        tamanoBytes: await persistido.length(),
        mimeType: 'image/jpeg',
        capturadaEn: capturadaEn,
        metadatosCaptura: metadatos,
        reporteLocalId: _borradorDe(momento),
      );

      await _contarFotos(momento);
    } catch (_) {
      // Que la camara falle no puede tumbar la pantalla: el reporte se tiene que
      // poder guardar igual, que es toda la decision de esta fase.
    }
  }

  /// Relee del disco cuantas fotos lleva la hoja de ese momento.
  Future<void> _contarFotos(String momento) async {
    try {
      final String? orgId = _orgId;
      final String? profileId = _profileId;
      if (orgId == null || profileId == null) return;
      final Map<String, int> cuenta = await LocalDatabase()
          .fotosPorRequisitoDeBorrador(
            borradorId: _borradorDe(momento),
            orgId: orgId,
            profileId: profileId,
          );
      if (!mounted) return;
      setState(() => _fotosDelBorrador = cuenta);
    } catch (_) {
      // Sin cuenta, la hoja dice que no hay fotos. Es lo mismo que decia antes
      // de esta fase y no impide guardar.
    }
  }

  /// Tira las fotos de un borrador que se cerro sin guardar.
  Future<void> _descartarBorrador(String momento) async {
    if (mounted) {
      setState(() => _fotosDelBorrador = <String, int>{});
    }
    try {
      final String? orgId = _orgId;
      final String? profileId = _profileId;
      if (orgId == null || profileId == null) return;
      await LocalDatabase().descartarEvidenciasDeBorrador(
        borradorId: _borradorDe(momento),
        orgId: orgId,
        profileId: profileId,
      );
    } catch (_) {
      // Sin consecuencia visible: lo peor que pasa es que quede una fila que
      // nadie mira.
    }
  }

  Future<void> _encolarPorDefecto(
    String ordenId,
    String momento,
    Map<String, dynamic> respuestas, {
    bool requiereNoc = false,
    bool detener = true,
    String? idFijo,
  }) async {
    final String? orgId = _orgId;
    final String? profileId = _profileId;
    if (orgId == null || profileId == null) {
      return;
    }

    // LAS FOTOS DEL BORRADOR PASAN A SER DE ESTE REPORTE: antes de esto
    // estaban atadas a un id que solo existe en esta pantalla. Lo hace la
    // fuente, junto con encolar, para que no puedan separarse.
    await _fuente.encolarReporte(
      orgId: orgId,
      profileId: profileId,
      ordenId: ordenId,
      momento: momento,
      respuestas: respuestas,
      borradorId: _borradorDe(momento),
      requiereNoc: requiereNoc,
      detener: detener,
      idFijo: idFijo,
    );
    if (mounted) {
      setState(() => _fotosDelBorrador = <String, int>{});
    }

    // Se intenta ahora. Si no hay señal, la cola lo reintenta sola: esto no
    // espera ni bloquea la pantalla.
    _fuente.procesarCola();
  }

  /// El camino real: primero el espejo local --que funciona sin señal-- y
  /// despues un intento de actualizarlo.
  ///
  /// El orden importa. Si se pidiera la red primero, un tecnico sin señal
  /// esperaria el timeout completo mirando una pantalla vacia, teniendo la
  /// historia guardada en el telefono.
  /// Cuantos reportes de ESTA orden esperan subir.
  ///
  /// Se cuenta para poder decirselo al tecnico: un reporte guardado y sin subir
  /// es un hecho que tiene que poder ver, porque si no, no sabe si el NOC se
  /// entero. No es un error ni un aviso: es el estado de su trabajo.
  Future<int> _contarSinSubir() async {
    try {
      final String? orgId = _orgId;
      final String? profileId = _profileId;
      if (orgId == null || profileId == null) {
        return 0;
      }
      // Con `await` y no devolviendo el Future: sin esperarlo, el `catch` de
      // abajo no lo atrapa y un fallo de la base rompe la pantalla en vez de
      // contar cero.
      // CON ordenId: lo que esta pantalla dice es «escritos ACA», y sin
      // acotar devolvia la cola entera del tecnico -- un reporte pendiente de
      // la orden anterior se leia como pendiente de esta.
      return await LocalDatabase().contarSeguimientosPendientes(
        orgId: orgId,
        profileId: profileId,
        ordenId: widget.ordenId,
      );
    } catch (_) {
      return 0;
    }
  }

  Widget _bloqueDeMateriales() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      child: DexterBloque(
        titulo: 'Materiales en esta orden',
        icono: Icons.inventory_2,
        insignia: DexterPastilla.neutra(texto: '${_materialesUsados.length}'),
        separacion: AppSpacing.sm,
        children: <Widget>[
          Text(
            'Se descuenta de tu kit y sube cuando haya señal',
            style: AppTypography.cuerpoChico,
          ),
          if (_materialesUsados.isEmpty)
            Text(
              'Todavía no registraste material en este trabajo.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            )
          else
            for (final m in _materialesUsados)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: <Widget>[
                    Icon(
                      (m['estado'] ?? '') == 'confirmado'
                          ? Icons.cloud_done_outlined
                          : Icons.schedule,
                      size: 16,
                      color: AppColors.onSurfaceVariant,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '${m['material_nombre'] ?? m['material_codigo']} '
                        'x${m['cantidad']}'
                        '${(m['serie'] as String?)?.isNotEmpty == true ? ' · ${m['serie']}' : ''}',
                        style: AppTypography.cuerpo,
                      ),
                    ),
                  ],
                ),
              ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 44,
            child: OutlinedButton.icon(
              onPressed: _abrirConsumoDeMaterial,
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Agregar material'),
            ),
          ),
        ],
      ),
    );
  }

  /// El requisito de firma que declara este tipo de trabajo, si lo declara.
  ///
  /// Se reconoce por su tipo en el esquema, no por su texto: buscar la palabra
  /// "firma" en la descripcion funcionaria hasta que una empresa escriba
  /// "conformidad del abonado" y dejaria de andar sin que nadie lo note.
  Map<String, dynamic>? get _requisitoDeFirma {
    for (final dynamic req in _evidenciasRequisitos) {
      if (req is Map && (req['tipo'] ?? '').toString() == 'firma') {
        return Map<String, dynamic>.from(req);
      }
    }
    return null;
  }

  bool get _exigeFirma => _requisitoDeFirma != null;

  bool get _hayFirma {
    final requisito = _requisitoDeFirma;
    if (requisito == null) return false;
    return _evidenciasCapturadas.any(
      (e) => e['requisito_id'] == requisito['id'],
    );
  }

  bool get _firmaSinSubir {
    final requisito = _requisitoDeFirma;
    if (requisito == null) return false;
    return _evidenciasCapturadas.any(
      (e) =>
          e['requisito_id'] == requisito['id'] &&
          (e['subida_estado'] ?? '') != 'confirmada',
    );
  }

  /// Los campos del formulario, interpretados una sola vez.
  ///
  /// La misma lista que se le pasa al widget del formulario: si el checklist
  /// de cierre leyera el esquema por su cuenta volveriamos a tener dos
  /// lecturas que se desincronizan. Ya paso: el formulario pintaba el
  /// asterisco rojo y el cierre no exigia el campo.
  List<CampoDelFormulario> get _camposNormalizados =>
      CampoDelFormulario.normalizar(
        _campos,
        _valoresFormulario,
        ficha: _fichaDeLaOrden,
      );

  /// Lo que el motor congeló al despachar: el equipo, la hora de captura, el
  /// ticket del ISP. La plantilla dice qué parte mostrar y dónde.
  ///
  /// Se lee por `TrabajoVista` y no parseando el JSON acá: esa clase ya sabe
  /// la forma del contexto, y tenerla en dos lados es como se desincronizan.
  Map<String, dynamic> get _fichaDeLaOrden {
    final Map<String, dynamic>? orden = _orden;
    if (orden == null) return const <String, dynamic>{};
    return TrabajoVista.desdeOrden(orden).contexto;
  }

  /// Lo que impide cerrar por el lado de los datos: obligatorios sin
  /// responder, y tambien valores que no sirven.
  List<String> get _camposObligatoriosSinLlenar => <String>[
    for (final CampoDelFormulario campo in _camposNormalizados)
      if (campo.bloqueaCierre) campo.titulo,
  ];

  /// Las evidencias agrupadas por el paso del protocolo que las pide.
  ///
  /// La decisión vive en `datos_de_ejecucion.dart`, que se prueba sin emulador.
  /// Acá solo se dibuja lo que esa función ya resolvió.
  List<GrupoDeEvidencias> get _gruposDeEvidencia => agruparPorPaso(
        requisitos: _evidenciasRequisitos,
        pasos: _pasosDelProtocolo,
      );

  List<dynamic> _pasosDelProtocolo = <dynamic>[];

  CierreDeOrden get _cierre => CierreDeOrden.evaluar(
    camposObligatoriosSinLlenar: _camposObligatoriosSinLlenar,
    requisitosDeFoto: <dynamic>[
      for (final dynamic r in _evidenciasRequisitos)
        if (!(r is Map && (r['tipo'] ?? '').toString() == 'firma')) r,
    ],
    fotosCapturadas: _evidenciasCapturadas,
    materialesRegistrados: _materialesUsados,
    exigeFirma: _exigeFirma,
    hayFirma: _hayFirma,
    firmaSinSubir: _firmaSinSubir,
    //  LO QUE EL SUPERVISOR PIDIO REHACER (09/11/2026). Sin esto el checklist
    //  daba por buena la foto vieja, dejaba cerrar, y el servidor rechazaba el
    //  cierre con CORRECCION_PENDIENTE: la orden no salia nunca de devuelta y
    //  el cambio quedaba en la cola. Ver `LoDevuelto`.
    devuelto: _loDevuelto,
  );

  /// Que pidio rehacer el supervisor en la vuelta que corre, y cuando.
  LoDevuelto get _loDevuelto {
    final Map<String, dynamic>? orden = _orden;
    if (orden == null) return LoDevuelto.nada;
    final DevolucionDeValidacion? d =
        DevolucionDeValidacion.desdeJson(orden['correccion_json']);
    //  Sin requisitos el resultado es el mismo que `LoDevuelto.nada` --nada
    //  exige foto nueva--, asi que no se distingue: una guarda que no cambia
    //  nada es una guarda que nadie puede probar.
    if (d == null) return LoDevuelto.nada;
    return LoDevuelto(
      requisitos: d.requisitos.toSet(),
      desde: d.devueltaEn,
    );
  }

  Future<void> _abrirFirma() async {
    final requisito = _requisitoDeFirma;
    if (requisito == null || _orgId == null || _profileId == null) return;

    final firmado = await FirmaDelCliente.abrir(
      context,
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      requisitoId: (requisito['id'] ?? '').toString(),
      resumenDelTrabajo: _resumenParaElCliente,
      materialesInstalados: <String>[
        for (final m in _materialesUsados)
          '${m['material_nombre'] ?? m['material_codigo']} x${m['cantidad']}'
              '${(m['serie'] as String?)?.isNotEmpty == true ? ' · serie ${m['serie']}' : ''}',
      ],
      baseLocal: _baseParaHojas,
    );
    if (firmado != true || !mounted) return;

    final evidencias = await _fuente.evidenciasDe(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
    );
    if (!mounted) return;
    setState(() => _evidenciasCapturadas = evidencias);
  }

  /// Lo que el cliente esta aceptando, en una linea.
  String get _resumenParaElCliente {
    final tipo = (_orden?['tipo_nombre'] ?? 'Trabajo').toString();
    final numero = _numeroDeLaOrden;
    return numero == null ? tipo : '$tipo · OT #$numero';
  }

  /// El checklist de cierre.
  ///
  /// Siempre las mismas lineas, en el mismo orden: uno que cambia obliga a
  /// leerlo entero cada vez, y esto se mira parado en una vereda.
  Widget _checklistDeCierre() {
    final cierre = _cierre;
    final int bloquean = cierre.requisitos
        .where((RequisitoDeCierre r) => r.bloquea)
        .length;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      child: DexterBloque(
        titulo: 'Cierre de trabajo',
        icono: Icons.fact_check,
        insignia: bloquean == 0
            ? const DexterPastilla.enRegla(texto: 'Listo para cerrar')
            : DexterPastilla.alerta(
                texto: bloquean == 1 ? 'Falta 1' : 'Faltan $bloquean',
              ),
        separacion: AppSpacing.sm,
        children: <Widget>[
          for (final requisito in cierre.requisitos)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    _iconoDe(requisito.estado),
                    size: 18,
                    color: _colorDe(requisito.estado),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(requisito.titulo, style: AppTypography.cuerpo),
                        if (requisito.detalle.isNotEmpty)
                          Text(
                            requisito.detalle,
                            style: AppTypography.cuerpoChico.copyWith(
                              color: _colorDe(requisito.estado),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          if (_exigeFirma && !_hayFirma) ...<Widget>[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              height: 44,
              child: OutlinedButton.icon(
                onPressed: _abrirFirma,
                icon: const Icon(Icons.draw_outlined, size: 18),
                label: const Text('Tomar la firma del cliente'),
              ),
            ),
          ],
          if (cierre.hayPendienteDeSubir) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Hay trabajo hecho que todavía no llegó al servidor. Sube solo '
              'cuando haya señal; no hace falta esperar acá.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }

  IconData _iconoDe(EstadoDeRequisito estado) => switch (estado) {
    EstadoDeRequisito.completo => Icons.check_circle,
    EstadoDeRequisito.pendiente => Icons.radio_button_unchecked,
    EstadoDeRequisito.opcional => Icons.remove_circle_outline,
    EstadoDeRequisito.sinSubir => Icons.schedule,
    EstadoDeRequisito.conConflicto => Icons.error_outline,
  };

  Color _colorDe(EstadoDeRequisito estado) => switch (estado) {
    EstadoDeRequisito.completo => AppColors.exito,
    EstadoDeRequisito.pendiente => AppColors.error,
    EstadoDeRequisito.opcional => AppColors.onSurfaceVariant,
    EstadoDeRequisito.sinSubir => AppColors.onSurfaceVariant,
    EstadoDeRequisito.conConflicto => AppColors.error,
  };

  @override
  Widget build(BuildContext context) {
    if (_noSePudoCargar) {
      return Scaffold(
        backgroundColor: AppColors.surface,
        appBar: AppBar(title: const Text('Ejecución')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(
                  Icons.cloud_off,
                  size: 40,
                  color: AppColors.onSurfaceVariant,
                ),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'No pudimos abrir este trabajo',
                  style: AppTypography.tituloChico,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'La orden todavía no está en este teléfono. Volvé a la '
                  'lista y sincronizá cuando tengas señal.',
                  style: AppTypography.cuerpo,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.lg),
                // Una salida. Sin esto la unica forma de irse es el gesto de
                // volver del sistema, y en una pantalla en blanco nadie sabe
                // si la aplicacion se colgo.
                FilledButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  child: const Text('Volver'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (_isLoading) {
      // Un fondo quieto, no un indicador que gira. Es la misma decision que
      // ya tomaron Inicio y Materiales: esto lee SQLite y son milisegundos,
      // asi que el spinner solo hace parpadear la pantalla. Ademas una
      // animacion perpetua deja el arbol sin reposo y cuelga cualquier
      // prueba que espere a que las animaciones terminen -- que es
      // exactamente lo que pasaba al intentar probar esta pantalla.
      return const Scaffold(
        backgroundColor: AppColors.surface,
        body: SizedBox.expand(),
      );
    }

    final numero = _orden?['numero'] ?? '---';

    final LecturaDePasos pasoActual = LecturaDePasos.de(
      EstadoTrabajo.desde(_orden?['estado']?.toString()),
    );

    return Scaffold(
      backgroundColor: AppColors.surfaceDim,
      body: ContenidoCentrado(
        child: Column(
          children: [
            // El encabezado de paso del diseño, en lugar de la barra de
            // Material. El titulo sigue siendo "OT #N" y no "Ejecución de
            // orden" como en la maqueta: a 390 px ese texto se cortaba en
            // "Ejecución OT #48..." y se perdia el numero, que es lo unico que
            // identifica el trabajo. El paso, que la maqueta escribe debajo del
            // titulo, ahora se ve aca -- y sale de LecturaDePasos, no del "2 de
            // 5" fijo que Stitch repitio en sus cuatro pantallas.
            DexterStepHeader(
              titulo: 'OT #$numero',
              paso: pasoActual.pasoActual + 1,
              deTotal: PasoOrden.values.length,
              // La chapa del diseño, y no la de la barra de Material: esa
              // está pintada en blanco sobre 15% de blanco, para el azul
              // oscuro que acá ya no existe. Sobre el encabezado claro se
              // leería blanco sobre casi blanco.
              pastilla: DexterSyncBadge(
                estado: SyncPresentacion.estado(widget.resumenDeSync),
                detalle: SyncPresentacion.detalle(widget.resumenDeSync),
              ),
            ),
            OfflineSavedBanner(visible: _showSavedIndicator),
            _paraQuienYEnQuePaso(),
            // LO QUE LE PREGUNTAN AL TÉCNICO, SIN BAJAR (18/10/2026): ticket,
            // serial, IP y la señal de la ficha. Ver `FranjaDelServicio`.
            if (_orden != null)
              FranjaDelServicio(trabajo: TrabajoVista.desdeOrden(_orden!)),
            // EL CONTRATO DEL CLIENTE (13/11/2026): en las instalaciones, el
            // técnico lo crea aquí en vez de llenarlo a mano en WispHub.
            if (llevaContrato(_orden)) _accesoAlContrato(),
            _franjaDelFormulario(),
            // LO QUE FALTA, ARRIBA Y FIJO
            // ---------------------------
            // El checklist de cierre vive al fondo de un scroll largo. Con una
            // mano, en una escalera, llegar hasta ahi para saber que falta es
            // un viaje -- y si no se llega, el tecnico se entera de lo que le
            // falta cuando toca «completar» y el boton no lo deja.
            //
            // NO ES UNA SEGUNDA CUENTA: sale de `_cierre`, el mismo veredicto
            // que decide si se puede cerrar. Una cuenta propia aca seria la
            // forma mas rapida de que la misma pantalla diga dos cosas
            // distintas del mismo trabajo.
            _loQueFalta(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.margen,
                  AppSpacing.lg,
                  AppSpacing.margen,
                  AppSpacing.lg,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // REPORTAR, DONDE OCURRE LO QUE SE REPORTA
                    // ----------------------------------------
                    // Sin la historia y sin el bloqueo abierto: los dos viven en
                    // la ficha. Aca van solo los gestos --inicio, avance,
                    // bloqueo, cierre-- porque es donde el tecnico esta cuando
                    // pasa lo que hay que reportar.
                    SeguimientoDeLaIntervencion(
                      seguimiento: _seguimiento,
                      cargando: _cargandoSeguimiento,
                      mostrarHistoria: false,
                      mostrarBloqueoAbierto: false,
                      pendientesDeSubir: _reportesSinSubir,
                      // El cierre sale de «Finalizar» (17/10/2026).
                      cierreEnFinalizar: true,
                      alTomarFoto: _tomarFotoDelReporte,
                      fotosTomadas: _fotosDelBorrador,
                      alAbrirHoja: _contarFotos,
                      alDescartarBorrador: _descartarBorrador,
                      alReportar:
                          (
                            String momento,
                            Map<String, dynamic> respuestas, {
                            bool requiereNoc = false,
                            bool detener = true,
                          }) {
                            // No se espera: la pantalla no se bloquea mientras el
                            // telefono busca señal.
                            _reportar(
                              momento,
                              respuestas,
                              requiereNoc: requiereNoc,
                              detener: detener,
                            );
                          },
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    // POR PASOS, CUANDO LA PLANTILLA LOS TIENE (17/10/2026).
                    // Cada paso junta su instrucción, sus datos y sus fotos: el
                    // técnico registra lo que está haciendo donde lo está
                    // haciendo. Sin pasos, la pantalla es la de siempre.
                    if (_pasos.isNotEmpty) ...<Widget>[
                      _selectorDePasos(),
                      const SizedBox(height: AppSpacing.sm),
                      _pasoEnCurso(),
                      const SizedBox(height: AppSpacing.lg),
                    ] else ...<Widget>[
                      // LOS DATOS DEL TRABAJO, CON SU NOMBRE. Antes empezaban
                      // sin titulo y se confundian con el avance (pedido del
                      // usuario, 15/10/2026).
                      if (_camposNormalizados.isNotEmpty) ...<Widget>[
                        const EncabezadoDeBloque(
                          titulo: 'Datos del trabajo',
                          icono: Icons.fact_check_outlined,
                        ),
                        const SizedBox(height: AppSpacing.sm),
                      ],
                      FormularioDeCampo(
                        // Una sola lectura del esquema para toda la pantalla:
                        // la misma que usa el checklist de cierre.
                        campos: _camposNormalizados,
                        valores: _valoresFormulario,
                        controladores: _controllers,
                        alCambiar: _onFieldChanged,
                        mostrarDatosFuturos: widget.mostrarDatosFuturos,
                      ),
                      const SizedBox(height: AppSpacing.lg),
                    ],
                    // LOS BLOQUES DEL FINAL, SOLO EN EL ULTIMO PASO
                    // ---------------------------------------------
                    // (09/11/2026) El usuario: «si le dan en 1 diagnostico,
                    // que solo le muestre lo que esta en diagnostico; quitar
                    // la comprobacion de conexion y materiales en esta orden,
                    // esos campos que solo salgan en solucion».
                    //
                    // Antes se dibujaban SIEMPRE debajo del paso, asi que
                    // parado en el paso 1 el tecnico veia su diagnostico y
                    // ademas dos cosas que no le tocan todavia -- y el paso
                    // dejaba de significar algo, porque igual habia que bajar
                    // por todo.
                    //
                    // Cual es «el ultimo» lo decide esElPasoDeCierre, y no
                    // el nombre del paso: ver el porque ahi.
                    if (_vanLosBloquesDelFinal) ...<Widget>[
                      // COMPROBAR CONEXION, SIN SALIR DE LA INTERVENCION.
                      // Antes vivia solo en la ficha.
                      if (_conexion() case final Widget bloque) ...<Widget>[
                        bloque,
                        const SizedBox(height: AppSpacing.lg),
                      ],
                      _bloqueDeMateriales(),
                    ],
                    if (_pasos.isEmpty) _evidencias(),
                    _checklistDeCierre(),
                    if (widget.mostrarDatosFuturos) ...[
                      const SizedBox(height: AppSpacing.lg),
                      const BloqueAcademia(),
                    ],
                  ],
                ),
              ),
            ),
            _barraDeAcciones(),
          ],
        ),
      ),
    );
  }

  /// Los pasos de la plantilla, con lo que se registra en cada uno. Vacío
  /// cuando la plantilla no está organizada por pasos.
  List<PasoDeEjecucion> get _pasos => pasosDeEjecucion(
        campos: _campos,
        requisitos: _evidenciasRequisitos,
        pasos: _pasosDelProtocolo,
      );

  /// Si en el paso donde esta parado el tecnico van los bloques del final:
  /// comprobar la conexion y el material usado. Ver esElPasoDeCierre.
  bool get _vanLosBloquesDelFinal => esElPasoDeCierre(
        indice: _pasoActual,
        total: _pasos.length,
      );

  /// Si a un paso no le falta nada de lo obligatorio.
  bool _pasoCompleto(PasoDeEjecucion paso) {
    final bool faltaDato = CampoDelFormulario.normalizar(
      paso.campos,
      _valoresFormulario,
    ).any((CampoDelFormulario c) => c.bloqueaCierre);
    final bool faltaFoto = requisitosPendientes(
      requisitos: paso.evidencias,
      capturadas: _evidenciasCapturadas,
    ).any((Map<String, dynamic> r) => r['obligatorio'] == true);
    return !faltaDato && !faltaFoto;
  }

  /// La línea de pasos (09/11/2026, el usuario: «hacer que la interfaz sea
  /// más creativa»).
  ///
  /// Antes era una lista vertical: una tarjeta por paso, apiladas, que con
  /// tres pasos se comía media pantalla antes de llegar al primer campo. Y
  /// repetía arriba el título del paso que el contenido ya encabeza.
  ///
  /// Ahora es un renglón: un círculo por paso --con su número, o un ✓ cuando
  /// está completo-- unidos por una línea que se pinta a medida que avanza.
  /// Se ve de un vistazo cuántos faltan y cuáles quedaron a medias, que es lo
  /// que la lista no mostraba sin leerla entera.
  ///
  /// Cada círculo sigue siendo tocable, con su objetivo táctil completo: el
  /// técnico salta al paso que quiera, como antes.
  Widget _selectorDePasos() {
    final List<PasoDeEjecucion> pasos = _pasos;
    final int actual = _pasoActual.clamp(0, pasos.length - 1);

    return Semantics(
      container: true,
      label: 'Paso ${actual + 1} de ${pasos.length}: ${pasos[actual].titulo}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              for (int i = 0; i < pasos.length; i++) ...<Widget>[
                if (i > 0)
                  Expanded(
                    child: Container(
                      height: 3,
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      decoration: BoxDecoration(
                        //  La línea hasta el paso actual va pintada: es el
                        //  camino recorrido, no una decoración.
                        color: i <= actual
                            ? AppColors.primary
                            : AppColors.surfaceContainerHigh,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                _CirculoDePaso(
                  numero: i + 1,
                  estado: estadoDelPaso(
                    indice: i,
                    actual: actual,
                    completo: _pasoCompleto(pasos[i]),
                  ),
                  alTocar: () => setState(() => _pasoActual = i),
                ),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          //  El nombre del paso donde está parado. Los otros no se escriben:
          //  con cuatro pasos los títulos no entran en un renglón, y cortarlos
          //  --«Diagn… Soluc… Otros…»-- no dice nada.
          Text(
            '${actual + 1}. ${pasos[actual].titulo}',
            style: AppTypography.tituloChico,
          ),
          if (pasos[actual].descripcion.isNotEmpty)
            Text(
              pasos[actual].descripcion,
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
        ],
      ),
    );
  }
  Widget _pasoEnCurso() {
    final List<PasoDeEjecucion> pasos = _pasos;
    final int actual = _pasoActual.clamp(0, pasos.length - 1);
    final PasoDeEjecucion paso = pasos[actual];
    final List<CampoDelFormulario> campos = CampoDelFormulario.normalizar(
      paso.campos,
      _valoresFormulario,
    );
    return DexterBloque(
      titulo: paso.titulo,
      icono: Icons.construction,
      insignia: DexterPastilla.neutra(
        texto: 'Paso ${actual + 1} de ${pasos.length}',
      ),
      separacion: AppSpacing.md,
      children: <Widget>[
        if (paso.descripcion.isNotEmpty)
          Text(paso.descripcion, style: AppTypography.cuerpo),
        if (campos.isNotEmpty)
          FormularioDeCampo(
            campos: campos,
            valores: _valoresFormulario,
            controladores: _controllers,
            alCambiar: _onFieldChanged,
            mostrarDatosFuturos: widget.mostrarDatosFuturos,
            conEncabezado: false,
          ),
        for (final dynamic r in paso.evidencias)
          if (r is Map) _buildEvidenciaRequisito(Map<String, dynamic>.from(r)),
        // ACÁ ESTABA «Registrar material usado» (09/11/2026). El usuario,
        // sobre la app en uso: «debajo de las fotos sale registrar material, y
        // más abajo sale material en esta orden; también, igual, para que
        // arriba».
        //
        // Eran dos puertas a la misma hoja --las dos llamaban a
        // `_abrirConsumoDeMaterial`-- y esta era la peor de las dos: un botón
        // suelto que no dice qué llevás registrado, así que para saberlo había
        // que bajar igual hasta el otro bloque. El bloque «Materiales en esta
        // orden» tiene la lista Y su botón «Agregar material»: no se perdió
        // ninguna forma de llegar, se perdió el viaje.
      ],
    );
  }

  /// «Comprobar conexión», o nulo cuando no corresponde: sin acciones de red
  /// —una prueba— o en un trabajo de planta, donde no hay equipo de cliente.
  Widget? _conexion() {
    final AccionesOrden? acciones = widget.acciones;
    final Map<String, dynamic>? orden = _orden;
    if (acciones == null || orden == null) return null;
    final TrabajoVista trabajo = TrabajoVista.desdeOrden(orden);
    if (trabajo.esTrabajoDePlanta) return null;
    return ComprobarConexion(
      ordenId: widget.ordenId,
      trabajo: trabajo,
      acciones: acciones,
      alActualizarFicha: _loadOrdenData,
    );
  }

  /// Cuántos requisitos de foto ya tienen su captura.
  int get _fotosCapturadas => fotosCapturadas(
    requisitos: _evidenciasRequisitos,
    capturadas: _evidenciasCapturadas,
  );

  /// Qué formulario se está respondiendo. La versión del esquema viene con la
  /// orden: si el backend cambia las preguntas, esto cambia con ellas.
  /// Para quién es el trabajo y en qué paso va.
  ///
  /// Esta pantalla es larga y se abre desde una lista: sin esta línea, a los
  /// tres bloques de scroll ya no se sabe de qué orden se trata. El número
  /// solo no alcanza — nadie recuerda a qué cliente corresponde el 4832.
  ///
  /// Los dos datos ya existen: el cliente viene en la orden y el paso lo
  /// calcula `LecturaDePasos`, la misma que dibuja la barra del detalle. No
  /// se agrega ninguna fuente nueva.
  Widget _paraQuienYEnQuePaso() {
    final String cliente = (_orden?['cliente_nombre'] ?? '').toString();
    if (cliente.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      color: AppColors.surfaceContainerLowest,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.margen,
        AppSpacing.sm,
        AppSpacing.margen,
        AppSpacing.sm,
      ),
      child: Row(
        children: <Widget>[
          const Icon(
            Icons.person_outline,
            size: 16,
            color: AppColors.onSurfaceVariant,
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              cliente,
              style: AppTypography.etiquetaGrande.copyWith(
                color: AppColors.onSurface,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          // El paso ya lo dice el encabezado de arriba, con la tipografia
          // del diseño. Estaba dos veces en la misma pantalla.
        ],
      ),
    );
  }

  Widget _franjaDelFormulario() {
    final int version = _orden?['schema_version'] as int? ?? 0;
    final int campos = _campos.length;

    return Container(
      width: double.infinity,
      color: AppColors.surfaceContainerLow,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: 6,
      ),
      child: Row(
        children: [
          const Icon(Icons.save, size: 13, color: AppColors.exitoTexto),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              'Se guarda en este equipo',
              style: AppTypography.etiquetaChica,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          // La version del formulario no se recorta: si se corta por la mitad
          // deja de servir para lo unico que sirve, que es saber contra que
          // esquema se esta trabajando.
          Text(
            version == 0 ? '$campos campos' : 'v$version · $campos campos',
            style: AppTypography.datoChico.copyWith(
              color: AppColors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  /// La evidencia fotográfica que pide el tipo de trabajo. Igual que el
  /// formulario, la lista viene del backend: acá solo se dibuja y se captura.
  Widget _evidencias() {
    return DexterBloque(
      titulo: 'Evidencia Fotográfica',
      icono: Icons.photo_camera,
      insignia: DexterPastilla.neutra(
        texto: '$_fotosCapturadas / ${_evidenciasRequisitos.length}',
      ),
      separacion: AppSpacing.md,
      children: [
        if (_evidenciasRequisitos.isNotEmpty) _progresoDeFotos(),
        if (_evidenciasRequisitos.isEmpty)
          Text(
            'Este tipo de trabajo no exige fotografías.',
            style: AppTypography.cuerpoChico,
          )
        else
          // CADA FOTO DEBAJO DEL PASO QUE LA PIDE.
          //
          // El tecnico trabaja siguiendo el protocolo: «3. Medicion optica con
          // power meter» y «Fotografia de la medicion» son lo mismo, y vivian
          // en dos pantallas sin nada que las relacionara. Ahora la foto se
          // toma DESDE el paso.
          //
          // Cuando la plantilla no declara pasos en sus evidencias --el caso de
          // todas las que existen hoy-- `agruparPorPaso` devuelve un solo grupo
          // sin titulo y esto se dibuja exactamente como antes.
          for (final (int i, GrupoDeEvidencias g) in _gruposDeEvidencia.indexed)
            ...<Widget>[
              if (i > 0) const SizedBox(height: AppSpacing.lg),
              if (g.titulo.isNotEmpty) ...<Widget>[
                Text(
                  g.titulo.toUpperCase(),
                  style: AppTypography.labelCaption
                      .copyWith(color: AppColors.outline, letterSpacing: 0.8),
                ),
                const SizedBox(height: AppSpacing.xs),
              ],
              for (var j = 0; j < g.requisitos.length; j++) ...<Widget>[
                if (j > 0) const SizedBox(height: AppSpacing.md),
                _buildEvidenciaRequisito(
                  Map<String, dynamic>.from(g.requisitos[j] as Map),
                ),
              ],
            ],
        _avisoSinCobertura(),
      ],
    );
  }

  /// Una franja fija con lo que todavia impide cerrar.
  ///
  /// Se esconde sola cuando no falta nada: una franja que dice «todo listo»
  /// permanentemente ocupa el lugar donde el tecnico mira cuando SI falta algo,
  /// y deja de leerse.
  Widget _loQueFalta() {
    final List<RequisitoDeCierre> faltan = _cierre.bloqueantes;
    if (faltan.isEmpty) return const SizedBox.shrink();

    // GRIS MIENTRAS SE TRABAJA, ROJA AL INTENTAR CERRAR (17/10/2026). Sigue
    // fija arriba y con los nombres de lo que falta: lo que cambia es el
    // tono, para que el rojo signifique «esto te impide cerrar ahora».
    final bool rojo = _intentoFinalizar;
    final Color fondo =
        rojo ? AppColors.errorContainer : AppColors.surfaceContainerHigh;
    final Color tinta =
        rojo ? AppColors.onErrorContainer : AppColors.onSurfaceVariant;
    return Container(
      width: double.infinity,
      color: fondo,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(rojo ? Icons.error_outline : Icons.checklist,
              size: 18, color: tinta),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              // Se nombra QUE falta, no cuantos. «Te faltan 2» obliga a bajar
              // igual para saber cuales, que es justo lo que esto evita.
              'Falta: ${faltan.map((RequisitoDeCierre r) => r.titulo).join(' · ')}',
              style: AppTypography.cuerpoChico.copyWith(
                color: tinta,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// La tarjeta de progreso del diseño: el conteo, el porcentaje y la barra
  /// partida en tres tramos.
  ///
  /// La maqueta rotula los tramos "verificadas" y "requerida pendiente".
  /// Verificada no existe en este sistema: una foto está capturada o no, y
  /// quien la revisa es una persona en la oficina, después. Se dice
  /// "capturadas", que es lo que el teléfono sabe.
  Widget _progresoDeFotos() {
    final int total = _evidenciasRequisitos.length;
    final int hechas = _fotosCapturadas;
    final int enviadas = fotosEnviadas(capturadas: _evidenciasCapturadas);
    final int faltan = total - hechas;
    final int obligatoriasPendientes = requisitosPendientes(
      requisitos: _evidenciasRequisitos,
      capturadas: _evidenciasCapturadas,
    ).where((Map<String, dynamic> r) => r['obligatorio'] == true).length;
    final int porcentaje = total == 0 ? 0 : (hechas * 100 / total).round();

    return DexterHundido(
      color: AppColors.surfaceContainer,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              // Flexible y no Text suelto: a 390 px de ancho esta fila
              // desbordaba 28 px. Lo encontro la corrida de capturas, no una
              // prueba -- las capturas dibujan la pantalla al ancho de un
              // telefono de verdad.
              // NO DICE «CARGADAS», Y ES EL PUNTO DE ESTE BLOQUE.
              //
              // Decía «Fotos cargadas: 2/2» mientras la línea de abajo decía
              // «2 capturadas» — dos palabras para dos hechos distintos, y la
              // de arriba era la equivocada. «Cargada» se lee como que el
              // servidor ya la tiene; si el teléfono se rompe esa noche, no la
              // tiene nadie. Lo que esta fila cuenta es lo que hay TOMADO.
              Flexible(
                child: Text(
                  'Fotos',
                  style: AppTypography.labelTelemetry,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.secondary,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  '$hechas / $total',
                  style: AppTypography.labelBadge.copyWith(
                    color: AppColors.onSecondary,
                  ),
                ),
              ),
              const Spacer(),
              // Solo el porcentaje. El diseño escribe "66% Completado", y la
              // palabra no agrega nada al lado de un porcentaje: son 77 px
              // que en un telefono angosto le faltan al resto de la fila.
              Text('$porcentaje%', style: AppTypography.labelCaption),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.circulo),
            child: SizedBox(
              height: 12,
              child: Row(
                children: <Widget>[
                  if (hechas > 0)
                    Expanded(
                      flex: hechas,
                      child: const ColoredBox(
                        color: AppColors.onTertiaryContainer,
                      ),
                    ),
                  if (faltan > 0)
                    Expanded(
                      flex: faltan,
                      child: const ColoredBox(
                        color: AppColors.surfaceContainerHigh,
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          // UNA LINEA POR HECHO, Y NUNCA LAS DOS EN UNA.
          //
          // Estuvieron en un renglon --«0/3 capturadas · 0/3 enviadas»-- y a
          // 360 px ese texto necesita 359 px cuando hay 262: se cortaba 97 px
          // y se perdia el numero de enviadas, que es el que importa. A 390 se
          // perdian 67 px y a 412 otros 45, asi que no era el telefono chico:
          // era el renglon.
          //
          // Partirlo en dos no es una concesion al ancho. Son DOS HECHOS
          // distintos --la foto existe / la empresa la tiene-- y leerlos uno
          // debajo del otro, cada uno con su icono y su color, dice eso mejor
          // que un punto medio entre ambos.
          _unaCuentaDeFotos(
            icono: hechas == total ? Icons.check_circle : Icons.photo_camera,
            texto: '$hechas/$total capturadas',
            color: hechas == total
                ? AppColors.onTertiaryContainer
                : AppColors.outline,
          ),
          const SizedBox(height: 2),
          _unaCuentaDeFotos(
            // El icono sigue a ESTA cuenta, no a la de arriba: un tilde verde
            // al lado de «0/3 enviadas» contradice al texto que tiene pegado,
            // y de los dos el que se mira de reojo es el icono.
            icono: enviadas == hechas && hechas > 0
                ? Icons.cloud_done
                : Icons.cloud_upload_outlined,
            texto: '$enviadas/$total enviadas',
            color: enviadas == hechas && hechas > 0
                ? AppColors.onTertiaryContainer
                : AppColors.outline,
          ),
          // LO QUE FALTA VA EN SU PROPIA FILA.
          //
          // Compartia renglon con las dos cuentas y le robaba el ancho. Son
          // dos informaciones distintas --cuanto hay y que falta-- y cada una
          // necesita su linea para leerse entera en un telefono.
          if (obligatoriasPendientes > 0) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Row(
              children: <Widget>[
                const Icon(Icons.error, size: 14, color: AppColors.error),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    obligatoriasPendientes == 1
                        ? '1 requerida pendiente'
                        : '$obligatoriasPendientes requeridas pendientes',
                    style: AppTypography.labelCaption.copyWith(
                      color: AppColors.error,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// Una de las dos cuentas de fotos: icono, numero y palabra.
  ///
  /// Vive aparte para que las dos se dibujen igual: si una tuviera otro
  /// tamaño o otra separacion, se leerian como cosas de distinta importancia,
  /// y no lo son.
  Widget _unaCuentaDeFotos({
    required IconData icono,
    required String texto,
    required Color color,
  }) {
    return Row(
      children: <Widget>[
        Icon(icono, size: 14, color: color),
        const SizedBox(width: 4),
        Expanded(
          child: Text(
            texto,
            style: AppTypography.labelCaption.copyWith(color: color),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }

  /// El aviso del diseño sobre qué pasa con una foto sin señal.
  ///
  /// La maqueta promete "memoria cifrada interna" y sincronización "al
  /// detectar enlace 4G LTE o red Wi-Fi autorizada". Nada de eso es cierto
  /// acá: la foto se guarda en el almacenamiento de la aplicación, sin
  /// cifrado propio, y la cola reintenta cuando hay red, sea cual sea. Se
  /// dice lo que pasa de verdad -- una promesa de cifrado que no existe es
  /// peor que no decir nada.
  Widget _avisoSinCobertura() {
    return DexterHundido(
      color: AppColors.surfaceContainerHigh,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.cloud_sync, size: 22, color: AppColors.secondary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  'SIN COBERTURA NO SE PIERDE',
                  style: AppTypography.labelBadge,
                ),
                Text(
                  'Las fotos quedan guardadas en el teléfono y se envían '
                  'solas cuando vuelva la señal. No hace falta repetirlas.',
                  style: AppTypography.bodySm.copyWith(
                    color: AppColors.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// La barra fija del diseño: el borrador a la izquierda, el cierre a la
  /// derecha. El diseño dice "Registrar Materiales"; ese módulo todavía no
  /// existe, así que el botón hace lo que la aplicación sí sabe hacer: cerrar
  /// la orden con lo registrado.
  bool get _hayPasoAnterior => _pasos.isNotEmpty && _pasoActual > 0;
  bool get _hayPasoSiguiente =>
      _pasos.isNotEmpty && _pasoActual < _pasos.length - 1;

  Widget _barraDeAcciones() {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        boxShadow: AppTheme.sombraNivel2,
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.margen,
            vertical: AppSpacing.md,
          ),
          // A 360 px ESTA FILA DESBORDABA 67 PIXELES, Y A 412 OTROS 15.
          //
          // El boton de borrador tomaba su ancho natural y «Finalizar orden»
          // se quedaba con lo que sobraba: 175 px para un contenido de 242.
          // O sea que el boton que CIERRA la orden aparecia cortado en el
          // telefono mas comun de una cuadrilla, y con la letra en 1.3 --lo
          // primero que sube quien trabaja al sol-- peor.
          //
          // No lo detectaba ninguna prueba porque la guarda de ancho real no
          // cubria esta pantalla: cubria inicio, la lista, la ficha, bodega,
          // materiales y visitas. Ahora la cubre.
          //
          // Los dos ceden, y el secundario cede PRIMERO (flex 1 contra 2):
          // su texto es «Borrador»/«Guardado» y lo respalda un icono, asi que
          // es el que se puede perder. El principal no.
          child: Row(
            children: [
              Flexible(
                child: Material(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brTarjeta,
                child: InkWell(
                  borderRadius: AppRadius.brTarjeta,
                  onTap: _hayPasoAnterior
                      ? () => setState(() => _pasoActual--)
                      : _confirmarBorrador,
                  child: Container(
                    height: AppSpacing.objetivoTactilAmplio,
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                    ),
                    alignment: Alignment.center,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _hayPasoAnterior
                              ? Icons.arrow_back
                              : (_borradorConfirmado ? Icons.check : Icons.save),
                          size: 18,
                          color: AppColors.onSurface,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Flexible(
                          child: Text(
                            _hayPasoAnterior
                                ? 'Anterior'
                                : (_borradorConfirmado ? 'Guardado' : 'Borrador'),
                            style: AppTypography.etiqueta.copyWith(
                              color: AppColors.onSurface,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                flex: 2,
                child: Material(
                  color: AppColors.primary,
                  borderRadius: AppRadius.brTarjeta,
                  child: InkWell(
                    borderRadius: AppRadius.brTarjeta,
                    onTap: _hayPasoSiguiente
                        ? () => setState(() => _pasoActual++)
                        : _completarOrden,
                    child: Container(
                      height: AppSpacing.objetivoTactilAmplio,
                      alignment: Alignment.center,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // «FINALIZAR» Y NO «FINALIZAR ORDEN». El objeto se
                          // entiende por donde esta parado el tecnico --dentro
                          // de la orden, en su barra de abajo-- y la palabra
                          // de mas era justo la que no entraba. Cortarla a
                          // «Finalizar ord...» habria sido peor que sacarla.
                          Flexible(
                            child: Text(
                              _hayPasoSiguiente ? 'Siguiente paso' : 'Finalizar',
                              style: AppTypography.etiquetaGrande.copyWith(
                                color: AppColors.onPrimary,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          const Icon(
                            Icons.arrow_forward,
                            size: 20,
                            color: AppColors.onPrimary,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _accesoAlContrato() {
    final String titulo = 'OT #${_orden?['numero'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.fromLTRB(AppSpacing.md, AppSpacing.xs, AppSpacing.md, 0),
      child: Material(
        color: AppColors.infoFondo,
        borderRadius: AppRadius.brTarjeta,
        child: InkWell(
          borderRadius: AppRadius.brTarjeta,
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => ContratoScreen(ordenId: widget.ordenId, titulo: titulo),
          )),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(children: <Widget>[
              const Icon(Icons.assignment_outlined, color: AppColors.azulAccion),
              const SizedBox(width: 10),
              Expanded(
                child: Text('Contrato del cliente: créalo aquí con la firma',
                    style: AppTypography.etiqueta.copyWith(color: AppColors.azulAccion)),
              ),
              const Icon(Icons.chevron_right, color: AppColors.azulAccion),
            ]),
          ),
        ),
      ),
    );
  }

  Widget _buildEvidenciaRequisito(Map<String, dynamic> req) {
    final reqId = req['id'] as String;
    final descripcion =
        (req['descripcion'] ?? req['titulo'] ?? reqId) as String;
    final obligatorio = req['obligatorio'] == true;
    final instrucciones = req['instrucciones'] as String?;
    //  Lo dice la plantilla; ausente, es cámara. Ver `_deDondeSale`.
    final esCaptura = esUnaCaptura(req);

    final evidencia = _evidenciasCapturadas.firstWhere(
      (e) => e['requisito_id'] == reqId,
      orElse: () => {},
    );
    final hasFoto = evidencia.isNotEmpty && evidencia['archivo_path'] != null;
    final filePath = hasFoto ? evidencia['archivo_path'] as String : null;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: !hasFoto && obligatorio
            ? Border.all(
                color: AppColors.onErrorContainer.withValues(alpha: 0.4),
              )
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: hasFoto
                      ? AppColors.exitoFondo
                      : AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Icon(
                  hasFoto ? Icons.check_circle : Icons.camera_alt_outlined,
                  size: 18,
                  color: hasFoto ? AppColors.exito : AppColors.secondary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  '$descripcion${obligatorio ? ' *' : ''}',
                  style: AppTypography.etiqueta.copyWith(
                    color: AppColors.onSurface,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: hasFoto
                      ? AppColors.exitoFondo
                      : (obligatorio
                            ? AppColors.errorContainer
                            : AppColors.surfaceContainer),
                  borderRadius: AppRadius.brChico,
                ),
                child: Text(
                  hasFoto ? 'CAPTURADA' : 'PENDIENTE',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: hasFoto
                        ? AppColors.exitoTexto
                        : (obligatorio
                              ? AppColors.onErrorContainer
                              : AppColors.onSurfaceVariant),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          if (instrucciones != null && instrucciones.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(instrucciones, style: AppTypography.etiquetaChica),
          ],
          const SizedBox(height: AppSpacing.sm),
          if (hasFoto && filePath != null) ...[
            //  LA FOTO ENTERA, CON LA MARCA QUE VA A LLEVAR (13/11/2026). Era
            //  `BoxFit.cover` en 140 px, y el recorte escondía justo el borde
            //  donde va la banda. Tocarla la abre en grande.
            MiniaturaConMarca(
              archivo: File(filePath),
              marca: _marca,
              datos: datosDeLaFila(_marca, evidencia, esCaptura: esCaptura),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          SizedBox(
            height: AppSpacing.objetivoTactil,
            child: OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.primary,
                side: const BorderSide(color: AppColors.outlineVariant),
                shape: const RoundedRectangleBorder(
                  borderRadius: AppRadius.brTarjeta,
                ),
              ),
              //  UN SOLO BOTÓN PARA LAS DOS (09/11/2026, el usuario: «en test
              //  de velocidad solo sale para elegir captura, deben ser ambos
              //  pero en un solo botón»). El botón ya no nombra una fuente:
              //  abre la elección, y por eso dice «agregar».
              icon: Icon(
                hasFoto ? Icons.replay : Icons.add_a_photo_outlined,
                size: 18,
              ),
              label: Text(textoDelBoton(
                  yaHayFoto: hasFoto, esCaptura: esCaptura)),
              onPressed: () => _elegirDeDondeSaleLaFoto(reqId, req),
            ),
          ),
        ],
      ),
    );
  }
}

/// Un paso en la línea de arriba de la ejecución (09/11/2026).
///
/// Mide 40 px --el objetivo táctil del diseño-- aunque el círculo dibujado sea
/// de 28: el técnico lo toca con guante, en una escalera, y un blanco de 28 px
/// se falla.
class _CirculoDePaso extends StatelessWidget {
  const _CirculoDePaso({
    required this.numero,
    required this.estado,
    required this.alTocar,
  });

  final int numero;
  final EstadoDelPaso estado;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final bool enCurso = estado == EstadoDelPaso.enCurso;
    final bool hecho = estado == EstadoDelPaso.hecho;

    final Color fondo = enCurso
        ? AppColors.primary
        : (hecho ? AppColors.secondaryContainer : AppColors.surfaceContainerLowest);
    final Color tinta = enCurso
        ? AppColors.onPrimary
        : (hecho ? AppColors.onSecondary : AppColors.outline);

    return Semantics(
      button: true,
      selected: enCurso,
      label: hecho ? 'Paso $numero, completo' : 'Paso $numero',
      excludeSemantics: true,
      child: InkResponse(
        onTap: alTocar,
        radius: 24,
        child: SizedBox(
          width: AppSpacing.objetivoTactil,
          height: AppSpacing.objetivoTactil,
          child: Center(
            child: Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: fondo,
                shape: BoxShape.circle,
                border: Border.all(
                  color: enCurso
                      ? AppColors.primary
                      : (hecho ? AppColors.secondary : AppColors.outlineVariant),
                  width: 1.5,
                ),
              ),
              child: Center(
                child: hecho
                    ? Icon(Icons.check, size: 16, color: tinta)
                    : Text(
                        '$numero',
                        style: AppTypography.etiquetaGrande.copyWith(
                          color: tinta,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
