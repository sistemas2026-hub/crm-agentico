import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/storage/evidencia_storage_service.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/ubicacion_de_captura.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../demo/field_mock_data.dart';
import 'seguimiento_de_la_intervencion.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_app_header.dart';
import '../../core/widgets/dexter_bloques.dart';
import '../../core/widgets/dexter_card.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../../core/widgets/contenido_centrado.dart';
import '../../core/widgets/dexter_sync_badge.dart';
import '../ejecucion/ejecucion_screen.dart';
import '../trabajo/estado_trabajo.dart';
import '../trabajo/trabajo_vista.dart';
import 'acciones_orden.dart';
import 'diagnostico_de_campo.dart';
import 'materiales_de_esta_orden.dart';
import 'pasos_orden.dart';

/// La orden, abierta.
///
/// Sirve para entender qué hay que hacer y para avanzar el estado. El
/// formulario y las fotos siguen viviendo en la pantalla de ejecución.
///
/// No carga órdenes por su cuenta: lee la que le toca de [OrdenesJornada], la
/// misma lista que muestran Inicio y Trabajo, y la refresca después de cada
/// transición para que las tres queden iguales.
/// Los valores de ejemplo de un trabajo.
///
/// Se piden acá y no dentro de `TrabajoVista`: un modelo que trae adentro un
/// dato inventado se lo entrega a cualquiera que lo lea —`trabajo.futuro.zona`
/// devolvía siempre algo, hubiera zona o no— y arrastraba al núcleo a depender
/// de la demostración a través de `ordenes_jornada.dart`.
TrabajoFuturoMock _ejemploDe(TrabajoVista trabajo) =>
    FieldMockData.trabajoFuturo(trabajo.id);

/// El rango aceptable de señal óptica, como se le escribe al técnico.
///
/// UNA SOLA VEZ EN TODA LA APLICACIÓN
/// ----------------------------------
/// Estaba en dos lugares con dos pares distintos: la tarjeta real decía
/// "-8 y -25" y la de ejemplo "-18.0 a -25.0". Sumadas a las dos que traían
/// las plantillas, eran CUATRO rangos para la misma señal, y un técnico que
/// medía -12 dBm leía "aceptable" en una pantalla y "fuera del umbral" en
/// otra de la misma orden.
///
/// El número manda desde la configuración del tenant
/// (`veredictos.onu_signal_1490`), que es quien calcula el veredicto. Esto es
/// el texto que lo acompaña, y todavía es un literal: el día que los umbrales
/// viajen en el contexto de la orden, sale de ahí y esta constante se va.
/// Mientras tanto, que haya uno solo.
const String textoDelRangoOptico = 'Aceptable entre -8 y -25 dBm (G-GO-04)';

class DetalleOrdenScreen extends StatefulWidget {
  const DetalleOrdenScreen({
    super.key,
    required this.ordenId,
    required this.ordenes,
    required this.acciones,
    this.resumenes,
    this.resumenInicial,
    this.abrirEjecucion,
    this.cargarSeguimiento,
    this.encolarReporte,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final String ordenId;
  final OrdenesJornada ordenes;
  final AccionesOrden acciones;

  /// Estado de la cola. Esta pantalla vive fuera del contenedor, así que se
  /// suscribe por su cuenta y se da de baja al cerrarse.
  final Stream<SyncSummary>? resumenes;
  final SyncSummary? resumenInicial;

  /// Qué hacer al tocar "Ejecutar el trabajo". Por defecto, la pantalla de
  /// ejecución que ya existe.
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo)?
  abrirEjecucion;

  /// De donde sale el seguimiento de esta orden.
  ///
  /// Se inyecta --como `abrirEjecucion`-- para que la pantalla se pueda probar
  /// sin base ni red. El valor por defecto lee el espejo local y, si hay señal,
  /// lo actualiza.
  ///
  /// Devuelve `(seguimiento, actualizado)`: `null` significa que NUNCA se
  /// descargo en este telefono, que no es lo mismo que no tener reportes.
  final Future<(Map<String, dynamic>?, bool)> Function(String ordenId)?
  cargarSeguimiento;

  /// Donde va un reporte que el tecnico acaba de escribir.
  ///
  /// Se inyecta como el resto. El valor por defecto lo encola en el telefono y
  /// pide una sincronizacion: si hay señal sube ahora, y si no espera. El tecnico
  /// no tiene que saber cual de las dos pasó para seguir trabajando.
  final Future<void> Function(
    String ordenId,
    String momento,
    Map<String, dynamic> respuestas, {
    bool requiereNoc,
    bool detener,
  })?
  encolarReporte;

  final bool mostrarDatosFuturos;

  @override
  State<DetalleOrdenScreen> createState() => _DetalleOrdenScreenState();
}

/// En cuantas tandas se piden los paquetes del ping, y de que tamaño.
///
/// **El mínimo que WispHub acepta es 3**, medido el 25/09/2026: pedir 1 o 2
/// devuelve HTTP 400. Por eso los paquetes no se pueden pedir de a uno para
/// irlos mostrando -- la tanda más chica es de tres.
///
/// Y no se pide una sola de diez: esa tarda ~18 s con el técnico mirando una
/// rueda girar sin saber si el primero volvió. En tandas, los primeros caen a
/// los ~5 s. Se pagan tres llamadas en vez de una; a cambio se ve el ping
/// pasar, que es para lo que se pide.
///
/// Tiene que sumar lo mismo que TANDAS en campo/services/telemetria.py.
const List<int> _tandasDelPing = <int>[3, 3, 4];

/// Cada cuánto se descubre el paquete siguiente de una tanda que ya llegó.
/// Es cadencia de pantalla y nada más: los tiempos que se leen son los que
/// midió cada paquete.
const Duration _pausaEntrePaquetes = Duration(milliseconds: 260);
const int _paquetesDelPing = 10;

class _DetalleOrdenScreenState extends State<DetalleOrdenScreen> {
  StreamSubscription<SyncSummary>? _suscripcionResumen;
  SyncSummary? _resumen;
  bool _trabajando = false;
  bool _pingEnCurso = false;
  ResultadoPing? _ping;

  // El seguimiento de la intervencion. `null` mientras no se sepa; la pantalla
  // distingue "cargando" de "nunca se descargo", porque son dos cosas distintas
  // y la segunda hay que decirla.
  Map<String, dynamic>? _seguimiento;
  bool _cargandoSeguimiento = true;
  bool _seguimientoActualizado = true;
  int _reportesSinSubir = 0;

  /// EL BORRADOR, Y POR QUE SE DERIVA EN VEZ DE SORTEARSE
  /// ----------------------------------------------------
  /// La foto se saca antes de guardar el reporte: en ese momento todavia no hay
  /// fila de `cola_seguimiento` a la cual atarla. Nace con el id del borrador y
  /// al guardar se repunta al reporte real.
  ///
  /// Ese id NO puede ser un UUID guardado en memoria. Abrir la camara en Android
  /// puede destruir esta pantalla; al volver, Flutter la reconstruye con estado
  /// nuevo y el UUID anterior se perdio. La foto quedaria huerfana para siempre:
  /// no sube --no tiene evento-- y no se descarta --nadie recuerda su id--.
  /// Medido en el emulador el 02/10/2026, con la foto en la cola y la hoja
  /// diciendo «todavia no hay foto».
  ///
  /// Derivarlo de la orden y el momento lo hace reproducible: despues de
  /// cualquier reconstruccion se vuelve a calcular igual, y la foto reaparece.
  String _borradorDe(String momento) => 'borrador-${widget.ordenId}-$momento';

  /// Cuantas fotos lleva cada requisito de la hoja abierta. Sale del disco, no
  /// de un contador: ver arriba.
  Map<String, int> _fotosDelBorrador = <String, int>{};

  final ImagePicker _camara = ImagePicker();

  // El material de esta orden. Otro espejo: `null` es "no se sabe" y no "no se
  // uso nada".
  Map<String, dynamic>? _materiales;
  bool _cargandoMateriales = true;

  @override
  void initState() {
    super.initState();
    _resumen = widget.resumenInicial;
    widget.ordenes.addListener(_alCambiar);
    // Normalmente se llega desde Inicio o Trabajo, con la lista ya cargada.
    // Pero si alguien abre esta pantalla antes —o la lista se vacia— hay que
    // pedirla: sin esto, la pantalla diria que la orden no existe.
    widget.ordenes.asegurarCargado();
    _suscripcionResumen = widget.resumenes?.listen((SyncSummary resumen) {
      if (mounted) setState(() => _resumen = resumen);
    }, onError: (Object _) {});
    _traerSeguimiento();
    _traerMateriales();
  }

  /// Trae el material de esta orden. Mismo criterio que el seguimiento: espejo
  /// primero, red despues, y si falla no se toca lo que habia.
  Future<void> _traerMateriales() async {
    try {
      final SecureStorageService almacen = SecureStorageService();
      final String? orgId = await almacen.getOrgId();
      if (orgId == null) {
        if (mounted) setState(() => _cargandoMateriales = false);
        return;
      }
      final LocalDatabase base = LocalDatabase();
      final Map<String, dynamic>? local = await base.leerMaterialesDeOrden(
        ordenId: widget.ordenId,
        orgId: orgId,
      );
      final bool actualizo = await SyncQueueService()
          .descargarMaterialesDeOrden(ordenId: widget.ordenId, orgId: orgId);
      final Map<String, dynamic>? fresco = actualizo
          ? await base.leerMaterialesDeOrden(
              ordenId: widget.ordenId,
              orgId: orgId,
            )
          : null;
      if (!mounted) return;
      setState(() {
        _materiales = fresco ?? local;
        _cargandoMateriales = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _cargandoMateriales = false);
    }
  }

  /// Trae el seguimiento al abrir la orden.
  ///
  /// Se pide ACA y no en la sincronizacion general porque un tecnico puede tener
  /// veinte ordenes asignadas y mira una: traer las veinte gastaria datos y
  /// bateria para dibujar diecinueve historias que nadie va a abrir.
  Future<void> _traerSeguimiento() async {
    final cargar = widget.cargarSeguimiento ?? _seguimientoPorDefecto;
    try {
      final (Map<String, dynamic>? datos, bool actualizado) = await cargar(
        widget.ordenId,
      );
      if (!mounted) return;
      final int sinSubir = await _contarSinSubir();
      if (!mounted) return;
      setState(() {
        _seguimiento = datos;
        _seguimientoActualizado = actualizado;
        _cargandoSeguimiento = false;
        _reportesSinSubir = sinSubir;
      });
    } catch (_) {
      // Que falle no puede dejar la pantalla cargando para siempre: se deja de
      // esperar y la seccion dice lo que sabe.
      if (!mounted) return;
      setState(() {
        _cargandoSeguimiento = false;
        _seguimientoActualizado = false;
      });
    }
  }

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
    final encolar = widget.encolarReporte ?? _encolarPorDefecto;
    await encolar(
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
      final SecureStorageService almacen = SecureStorageService();
      final String? orgId = await almacen.getOrgId();
      final String? profileId = await almacen.getProfileId();
      if (orgId == null || profileId == null) {
        return;
      }

      final XFile? foto = await _camara.pickImage(
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
      final SecureStorageService almacen = SecureStorageService();
      final String? orgId = await almacen.getOrgId();
      final String? profileId = await almacen.getProfileId();
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
      final SecureStorageService almacen = SecureStorageService();
      final String? orgId = await almacen.getOrgId();
      final String? profileId = await almacen.getProfileId();
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
  }) async {
    final SecureStorageService almacen = SecureStorageService();
    final String? orgId = await almacen.getOrgId();
    final String? profileId = await almacen.getProfileId();
    if (orgId == null || profileId == null) {
      return;
    }

    final String reporteId = await LocalDatabase().encolarSeguimiento(
      ordenId: ordenId,
      orgId: orgId,
      profileId: profileId,
      momento: momento,
      respuestas: respuestas,
      requiereNoc: requiereNoc,
      detener: detener,
    );

    // LAS FOTOS DEL BORRADOR PASAN A SER DE ESTE REPORTE
    // --------------------------------------------------
    // Antes de esta linea las fotos estaban atadas a un id que solo existe en
    // esta pantalla; despues, al reporte que acaba de encolarse. Es lo que
    // permite que la sincronizacion las encuentre cuando el servidor devuelva el
    // id del evento. El borrador se renueva para la hoja siguiente.
    await LocalDatabase().reasignarEvidenciasDeBorrador(
      borradorId: _borradorDe(momento),
      reporteLocalId: reporteId,
      orgId: orgId,
      profileId: profileId,
    );
    if (mounted) {
      setState(() => _fotosDelBorrador = <String, int>{});
    }

    // Se intenta ahora. Si no hay señal, la cola lo reintenta sola: esto no
    // espera ni bloquea la pantalla.
    await SyncQueueService().procesarCola();
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
      final SecureStorageService almacen = SecureStorageService();
      final String? orgId = await almacen.getOrgId();
      final String? profileId = await almacen.getProfileId();
      if (orgId == null || profileId == null) {
        return 0;
      }
      // Con `await` y no devolviendo el Future: sin esperarlo, el `catch` de
      // abajo no lo atrapa y un fallo de la base rompe la pantalla en vez de
      // contar cero.
      return await LocalDatabase().contarSeguimientosPendientes(
        orgId: orgId,
        profileId: profileId,
      );
    } catch (_) {
      return 0;
    }
  }

  Future<(Map<String, dynamic>?, bool)> _seguimientoPorDefecto(
    String ordenId,
  ) async {
    final String? orgId = await SecureStorageService().getOrgId();
    if (orgId == null) return (null, false);

    final LocalDatabase base = LocalDatabase();
    final Map<String, dynamic>? local = await base.leerSeguimiento(
      ordenId: ordenId,
      orgId: orgId,
    );

    final bool actualizo = await SyncQueueService().descargarSeguimientoDeOrden(
      ordenId: ordenId,
      orgId: orgId,
    );
    if (!actualizo) {
      // Se queda con lo que habia. Si nunca hubo nada, `local` es null y la
      // seccion lo dice.
      return (local, false);
    }
    final Map<String, dynamic>? fresco = await base.leerSeguimiento(
      ordenId: ordenId,
      orgId: orgId,
    );
    return (fresco ?? local, true);
  }

  @override
  void dispose() {
    widget.ordenes.removeListener(_alCambiar);
    _suscripcionResumen?.cancel();
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  TrabajoVista? get _trabajo {
    for (final TrabajoVista t in widget.ordenes.trabajos) {
      if (t.id == widget.ordenId) return t;
    }
    return null;
  }

  Future<void> _ejecutarAccion(TrabajoVista trabajo, AccionOrden accion) async {
    if (_trabajando) return;

    if (accion.abreEjecucion) {
      final abrir = widget.abrirEjecucion ?? _abrirEjecucionPorDefecto;
      await abrir(context, trabajo);
      await widget.ordenes.recargar();
      return;
    }

    setState(() => _trabajando = true);
    try {
      await widget.acciones.transicionar(
        ordenId: trabajo.id,
        nuevoEstadoLocal: accion.nuevoEstadoLocal!,
        tipoAccion: accion.tipoAccion!,
        revisionBase: trabajo.revision,
      );
      // La lista compartida se relee: Inicio y Trabajo ven el estado nuevo.
      await widget.ordenes.recargar();
    } finally {
      if (mounted) setState(() => _trabajando = false);
    }
  }

  Future<void> _abrirEjecucionPorDefecto(
    BuildContext contexto,
    TrabajoVista trabajo,
  ) async {
    await Navigator.of(contexto).push(
      MaterialPageRoute<void>(
        builder: (_) => EjecucionScreen(ordenId: trabajo.id),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final trabajo = _trabajo;

    if (trabajo == null && widget.ordenes.cargando) {
      return Scaffold(
        appBar: AppBar(title: const Text('Detalle Orden')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (trabajo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Detalle Orden')),
        body: const Center(
          child: DexterEmptyState(
            icono: Icons.search_off,
            titulo: 'No encontramos esta orden',
            mensaje: 'Puede haber sido reasignada. Volvé y actualizá la lista.',
            esAdvertencia: true,
          ),
        ),
      );
    }

    final lectura = LecturaDePasos.de(trabajo.estado);
    final acciones = AccionesDisponibles.para(trabajo.estado);

    return Scaffold(
      backgroundColor: AppColors.surfaceDim,
      body: ContenidoCentrado(
        child: Column(
          children: <Widget>[
            // El encabezado claro del diseño, en lugar de la barra azul oscura
            // de Material. El titulo sigue siendo "OT #N" y no "Detalle Orden":
            // a 390 px, con la chapa de la cola al lado, el titulo largo se
            // cortaba en "Detalle Orden #..." y se perdia justamente el numero,
            // que es lo que identifica el trabajo.
            DexterStepHeader(
              titulo: trabajo.numero == null
                  ? 'Detalle Orden'
                  : 'OT #${trabajo.numero}',
              paso: lectura.pasoActual + 1,
              deTotal: PasoOrden.values.length,
              pastilla: DexterSyncBadge(
                estado: SyncPresentacion.estado(_resumen),
                detalle: SyncPresentacion.detalle(_resumen),
                onTap: widget.acciones.sincronizar,
              ),
            ),
            if (widget.mostrarDatosFuturos) _franjaDeEnlace(),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.margen,
                  AppSpacing.md,
                  AppSpacing.margen,
                  AppSpacing.xl,
                ),
                children: <Widget>[
                  if (trabajo.requiereActualizacion)
                    _avisoActualizacion(trabajo),
                  _cabeceraConPasos(trabajo, lectura),
                  if (lectura.avisoExcepcion != null) ...<Widget>[
                    const SizedBox(height: AppSpacing.md),
                    _avisoExcepcion(trabajo, lectura),
                  ],
                  if (trabajo.estado ==
                      EstadoTrabajo.completadaSinEnviar) ...<Widget>[
                    const SizedBox(height: AppSpacing.md),
                    _avisoSinEnviar(),
                  ],
                  if (trabajo.correccion != null) ...<Widget>[
                    const SizedBox(height: AppSpacing.md),
                    _loQueHayQueRehacer(trabajo, trabajo.correccion!),
                  ],
                  const SizedBox(height: AppSpacing.md),
                  _accionesRapidas(trabajo),
                  // LA FICHA SE LEE POR MOMENTOS, NO POR CATEGORIAS
                  // ----------------------------------------------
                  // Antes esto era una pila de doce tarjetas con el mismo fondo,
                  // el mismo borde y la misma separacion: todas se leian como
                  // pares, y al bajar parecia una sola seccion larga. Nada
                  // distinguia lo que se CONSULTA de lo que se HACE.
                  //
                  // Los tres rotulos nombran el momento del trabajo --llegar,
                  // entender, ejecutar-- y no la categoria del dato: «para
                  // llegar» le dice al tecnico CUANDO mirar esto; «informacion
                  // del cliente» no le dice nada que no sepa.
                  //
                  // Un grupo sin tarjetas no se dibuja: varias son
                  // condicionales.
                  const SizedBox(height: AppSpacing.lg),
                  GrupoDeFicha(
                    titulo: 'Para llegar',
                    children: <Widget?>[
                      _datosDelCliente(trabajo),
                      // Lo que la orden SI trae. Antes vivia detras de la
                      // bandera de demostracion junto a los datos de ejemplo,
                      // asi que en produccion se ocultaba tambien lo verdadero:
                      // el ticket de origen, la franja prometida y los
                      // requisitos de seguridad llegan del backend y nadie los
                      // veia.
                      _datosDeLaOrden(trabajo),
                    ],
                  ),

                  const SizedBox(height: AppSpacing.lg),
                  GrupoDeFicha(
                    titulo: 'Para entender la falla',
                    children: <Widget?>[
                      _datosTecnicos(trabajo),
                      // La telemetria se ve cuando la orden trae una lectura del
                      // equipo, aunque no haya modo demostracion: la señal
                      // optica es un dato REAL desde que el motor la consulta al
                      // armar la ficha.
                      //
                      // Cuando no hay lectura la tarjeta tambien se muestra,
                      // porque decir POR QUE no la hay --falta el serial, el
                      // serial no esta en la OLT-- es informacion, y callarla
                      // manda a buscar una falla de red donde no la hay.
                      if (trabajo.contextoDisponible ||
                          widget.mostrarDatosFuturos)
                        _telemetria(trabajo),
                      if (trabajo.hayEvaluacionDexter)
                        _loQueDexterAveriguo(trabajo),
                      if (trabajo.diagnosticoPrevio.isNotEmpty ||
                          widget.mostrarDatosFuturos)
                        _triage(trabajo),
                    ],
                  ),

                  const SizedBox(height: AppSpacing.lg),
                  GrupoDeFicha(
                    titulo: 'Para ejecutar',
                    children: <Widget?>[
                      // El protocolo se ve cuando la plantilla lo trae, aunque
                      // no haya modo demostracion: es un dato real del tipo de
                      // trabajo.
                      if (trabajo.pasosDelProcedimiento.isNotEmpty ||
                          widget.mostrarDatosFuturos)
                        _protocoloDeAtencion(trabajo),
                      // El seguimiento se muestra SIEMPRE, no detras de
                      // `mostrarDatosFuturos`: es la historia real de la
                      // intervencion, leida del servidor o del espejo del
                      // telefono.
                      SeguimientoDeLaIntervencion(
                        seguimiento: _seguimiento,
                        cargando: _cargandoSeguimiento,
                        actualizado: _seguimientoActualizado,
                        pendientesDeSubir: _reportesSinSubir,
                        alTomarFoto: _tomarFotoDelReporte,
                        fotosTomadas: _fotosDelBorrador,
                        alAbrirHoja: _contarFotos,
                        alDescartarBorrador: _descartarBorrador,
                        // La resolucion viaja por la MISMA cola que los
                        // reportes: es otra cosa que el tecnico escribio en la
                        // calle y tiene que subir. El momento `resolver` le dice al
                        // procesador a que ruta va.
                        alResolverBloqueo: (String queSeHizo) {
                          _reportar('resolver', <String, dynamic>{
                            'que_se_hizo': queSeHizo,
                            'resuelto_por_rol': 'tecnico',
                          });
                        },
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
                      // El material REAL de esta orden, del libro de
                      // movimientos.
                      // En LECTURA a proposito: anotar vive en la pantalla de
                      // ejecucion, que ya tiene su «Agregar material». Ver el
                      // encabezado de `MaterialesDeEstaOrden`.
                      MaterialesDeEstaOrden(
                        materiales: _materiales,
                        cargando: _cargandoMateriales,
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // La barra fija del diseño: la acción principal no se pierde abajo
            // del scroll, que en esta pantalla es largo.
            Container(
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerLowest,
                boxShadow: AppTheme.sombraNivel2,
              ),
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.margen,
                    AppSpacing.md,
                    AppSpacing.margen,
                    AppSpacing.md,
                  ),
                  child: _acciones(trabajo, acciones),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// CAMPO-DATA-035 y CAMPO-DATA-036 · La franja del diseño: qué enlace habla
  /// con el servidor y cuándo fue el último envío bueno.
  ///
  /// La marca de tiempo todavía no existe —la cola no la guarda—, así que la
  /// franja entera vive en la demostración: un "hace 1 min" falso en la calle
  /// haría creer que lo registrado ya viajó.
  Widget _franjaDeEnlace() {
    return Container(
      width: double.infinity,
      color: AppColors.inverseSurface,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: 6,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: AppColors.exitoFuerte,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          // Flexibles: a 390 px los cuatro textos no entran en una fila, y un
          // Row rigido no se acomoda, desborda. El techo de ancho de la
          // aplicacion destapo esto, que antes se escondia porque las pruebas
          // renderizaban a mil pixeles.
          Flexible(
            child: Text(
              FieldMockData.enlaceDexter,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.inverseOnSurface,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          const Icon(Icons.check, size: 12, color: AppColors.exitoFuerte),
          const SizedBox(width: 2),
          Flexible(
            child: Text(
              'En dispositivo',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.exitoFuerte,
              ),
            ),
          ),
          const Spacer(),
          const Icon(Icons.cloud_done, size: 14, color: AppColors.surfaceDim),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              'Sync: ${FieldMockData.ultimaSincronizacion}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.surfaceDim,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// La tarjeta de estado del diseño: prioridad, número, estado en vivo, qué
  /// hay que hacer y en qué condición está lo guardado en el teléfono.
  ///
  /// Es el primer bloque de la pantalla "Detalle de Orden" de Stitch, con los
  /// datos reales de la orden en lugar de los de la maqueta.
  Widget _cabeceraConPasos(TrabajoVista trabajo, LecturaDePasos lectura) {
    return DexterBloque(
      separacion: AppSpacing.sm,
      children: <Widget>[
        Row(
          children: <Widget>[
            // CAMPO-DATA-002 · El SLA todavía no llega del backend.
            if (widget.mostrarDatosFuturos) ...<Widget>[
              DexterPastilla.alerta(
                texto: 'SLA ${_ejemploDe(trabajo).slaRestante}h',
              ),
              const SizedBox(width: AppSpacing.xs),
            ],
            Flexible(
              child: Text(
                trabajo.numero == null ? 'Orden' : '#OT-${trabajo.numero}',
                style: AppTypography.labelTelemetry.copyWith(
                  color: AppColors.primary,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const Spacer(),
            DexterPastillaConPunto(
              texto: trabajo.estado.etiqueta,
              colorDelPunto: trabajo.estado.enMarcha
                  ? AppColors.onTertiaryContainer
                  : AppColors.outline,
            ),
          ],
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(trabajo.tipoNombre, style: AppTypography.headlineMd),
            // CAMPO-DATA-037 · Qué hay que hacer, en una línea.
            if (widget.mostrarDatosFuturos)
              Text(
                FieldMockData.resumenDelTrabajo,
                style: AppTypography.cuerpoChico,
              ),
            Text(trabajo.clienteNombre, style: AppTypography.cuerpoChico),
          ],
        ),
        _loQueHayEnElTelefono(),
        _BarraDePasos(lectura: lectura),
      ],
    );
  }

  /// La línea del diseño sobre el caché local, dicha con lo que la cola sabe.
  ///
  /// La maqueta afirma siempre "CACHE LOCAL SINCRONIZADO". Acá eso se dice
  /// solo cuando es cierto: con cambios esperando en la cola, afirmarlo sería
  /// justo lo contrario de lo que pasa, y el técnico decide si se va del sitio
  /// mirando esta línea.
  Widget _loQueHayEnElTelefono() {
    final int pendientes = _resumen?.totalPendientes ?? 0;
    final bool sincronizado = pendientes == 0;

    return DexterHundido(
      child: Row(
        children: <Widget>[
          Icon(
            sincronizado ? Icons.cloud_done : Icons.cloud_upload_outlined,
            size: 20,
            color: sincronizado
                ? AppColors.secondary
                : AppColors.onSurfaceVariant,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  sincronizado
                      ? 'CACHE LOCAL SINCRONIZADO'
                      : 'HAY CAMBIOS SIN ENVIAR',
                  style: AppTypography.labelBadge,
                ),
                Text(
                  sincronizado
                      ? 'Datos listos para validar y cerrar sin cobertura'
                      : 'Guardado en el teléfono; viaja solo cuando haya señal',
                  style: AppTypography.labelCaption,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Las acciones rápidas, con la rejilla del diseño.
  ///
  /// El diseño las pone de a DOS por fila y de 56 px de alto; la versión
  /// anterior metía las cuatro en una sola fila, y a 390 px de ancho cada
  /// objetivo quedaba en unos 85 px con el rótulo recortado. Van en dos filas
  /// de dos: se conservan las cuatro y cada una entra en el pulgar con
  /// guantes.
  ///
  /// LLAMAR Y RUTA ESTÁN APAGADOS, Y SE VE
  /// -------------------------------------
  /// Los dos necesitan abrir OTRA aplicación del teléfono, y esta no tiene
  /// todavía la dependencia para hacerlo (`url_launcher` no está en
  /// `pubspec.yaml`, verificado). Hasta hace unas versiones se pintaban
  /// encendidos cuando el cliente tenía teléfono, y al tocarlos no pasaba
  /// nada: exactamente lo que el comentario de este mismo método decía que no
  /// había que hacer. Ahora se ven apagados, que es la verdad.
  ///
  /// El día que se agregue el lanzador, es pasarles su `alTocar` y nada más.
  ///
  /// POR QUÉ SE QUITÓ WHATSAPP (02/10/2026)
  /// --------------------------------------
  /// Decisión del usuario: los técnicos no se comunican por ahí. Y hay un
  /// motivo que la sostiene más allá del hábito: en este producto WhatsApp es
  /// **el canal del asistente con el cliente**, y queda registrado. Un técnico
  /// escribiéndole desde su aplicación personal abre una conversación paralela
  /// que el sistema no ve — lo acordado ahí no existe para el NOC ni para la
  /// bitácora del trabajo. El botón no sumaba un canal: restaba trazabilidad.
  ///
  /// POR QUÉ SE QUITÓ TAMBIÉN «GUÍA FTTH» (02/10/2026)
  /// --------------------------------------------------
  /// Prometía el procedimiento del trabajo y abría una MAQUETA: pasos
  /// inventados de `FieldMockData`, iguales para cualquier orden, y solo en modo
  /// demostración. Mientras tanto el protocolo REAL —el que declara el tipo de
  /// trabajo— ya tiene su propia tarjeta en «Para ejecutar», con sus pasos y su
  /// cuenta.
  ///
  /// Dos cosas con el mismo nombre y distinto contenido en la misma pantalla no
  /// es redundancia: es una que miente. Y la que mentía era ésta.
  ///
  /// Quedan dos, que es exactamente la rejilla del diseño: una fila de a dos.
  Widget _accionesRapidas(TrabajoVista trabajo) {
    return Column(
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: DexterAccionRapida(
                icono: Icons.phone_in_talk,
                texto: 'Llamar Cliente',
                // Sin lanzador de aplicaciones: ver el comentario de arriba.
                alTocar: null,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: DexterAccionRapida(
                icono: Icons.directions,
                texto: 'Ruta GPS',
                alTocar: null,
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Qué pidió rehacer el supervisor.
  ///
  /// No es un dato de ejemplo: lo manda el backend en `correccion`. Hasta el
  /// 22/09/2026 esa lista vivía solo en la bitácora del servidor, así que una
  /// orden devuelta llegaba sin decir qué corregir y se averiguaba por
  /// teléfono.
  Widget _loQueHayQueRehacer(TrabajoVista trabajo, DevolucionDeValidacion c) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.errorContainer,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(
          color: AppColors.onErrorContainer.withValues(alpha: 0.35),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.assignment_return,
                size: 18,
                color: AppColors.onErrorContainer,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Te devolvieron este trabajo',
                  style: AppTypography.etiquetaGrande.copyWith(
                    color: AppColors.onErrorContainer,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                'Vuelta ${c.vuelta}',
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onErrorContainer,
                ),
              ),
            ],
          ),
          if (c.observacion.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              '“${c.observacion}”',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onErrorContainer,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
          if (c.requisitos.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              c.requisitos.length == 1
                  ? 'Hay que volver a tomar esta evidencia:'
                  : 'Hay que volver a tomar estas evidencias:',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onErrorContainer,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            for (final String requisito in c.requisitos)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(
                      Icons.photo_camera,
                      size: 13,
                      color: AppColors.onErrorContainer,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        // El título de la plantilla, que es como el técnico
                        // conoce esa foto. Si el requisito ya no existe en la
                        // plantilla se muestra su identificador: es feo, pero
                        // es cierto, y callarlo dejaría la lista incompleta.
                        trabajo.titulosDeEvidencia[requisito] ?? requisito,
                        style: AppTypography.cuerpoChico.copyWith(
                          color: AppColors.onErrorContainer,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          if (c.devueltaEn != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Devuelta el ${_fechaCorta(c.devueltaEn!)}',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onErrorContainer,
              ),
            ),
          ],
        ],
      ),
    );
  }

  static String _fechaCorta(DateTime fecha) {
    final String dia = fecha.day.toString().padLeft(2, '0');
    final String mes = fecha.month.toString().padLeft(2, '0');
    final String hora = fecha.hour.toString().padLeft(2, '0');
    final String minuto = fecha.minute.toString().padLeft(2, '0');
    return '$dia/$mes a las $hora:$minuto';
  }

  /// CAMPO-DATA-025 · Qué material tiene asignado este trabajo.

  /// CAMPO-DATA-049 · El protocolo del tipo de trabajo.
  ///
  /// Va aparte de la barra de estados a propósito: la barra dice dónde está la
  /// orden de verdad —lo que el técnico marcó y el backend aceptó—, y esto es
  /// el procedimiento que todavía nadie guarda.
  Widget _protocoloDeAtencion(TrabajoVista trabajo) {
    // Los pasos reales vienen con la plantilla del tipo de trabajo (el backend
    // los entrega en `tipo.pasos` desde el 22/09/2026). Solo se cae al ejemplo
    // cuando la orden todavía no los trajo.
    final bool reales = trabajo.pasosDelProcedimiento.isNotEmpty;
    final List<String> pasos = reales
        ? trabajo.pasosDelProcedimiento
        : FieldMockData.protocoloAtencion;
    final int pasoActual = reales ? 0 : FieldMockData.protocoloPasoActual;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
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
              const Icon(Icons.checklist, size: 16, color: AppColors.secondary),
              const SizedBox(width: 6),
              Text(
                'Protocolo de Atención',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  reales
                      ? '${pasos.length} pasos'
                      : 'Paso $pasoActual de ${pasos.length}',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          for (int i = 0; i < pasos.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    i < pasoActual - 1
                        ? Icons.check_circle
                        : (i == pasoActual - 1
                              ? Icons.radio_button_checked
                              : Icons.radio_button_unchecked),
                    size: 14,
                    color: i < pasoActual - 1
                        ? AppColors.exito
                        : (i == pasoActual - 1
                              ? AppColors.primary
                              : AppColors.outlineVariant),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      '${i + 1}. ${pasos[i]}',
                      style: AppTypography.etiquetaChica.copyWith(
                        color: i == pasoActual - 1
                            ? AppColors.onSurface
                            : AppColors.onSurfaceVariant,
                        fontWeight: i == pasoActual - 1
                            ? FontWeight.w700
                            : FontWeight.w400,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _avisoActualizacion(TrabajoVista trabajo) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: DexterCard(
        colorAcento: AppColors.error,
        child: Row(
          children: <Widget>[
            const Icon(Icons.system_update, size: 18, color: AppColors.error),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                trabajo.versionEsquemaConocida
                    ? 'Esta orden necesita una versión más nueva de la '
                          'aplicación. Actualizala antes de trabajarla.'
                    : 'Todavía no sabemos qué versión de la aplicación necesita '
                          'esta orden: falta que baje su detalle.',
                style: AppTypography.cuerpo.copyWith(color: AppColors.error),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Lo que hay que saber antes de tocar la puerta.
  ///
  /// QUÉ ENTRA Y QUÉ NO
  /// ------------------
  /// El criterio no es "mostrar todo lo que el backend manda", sino: ¿esto
  /// cambia algo de lo que la persona va a hacer en los próximos minutos?
  ///
  /// Entra:
  ///
  /// - **De qué ticket salió.** El cliente abre la puerta diciendo "ya llamé
  ///   tres veces". Saber el ticket evita volver a preguntar lo que ya está
  ///   contestado, y es lo que permite buscar el historial.
  /// - **La franja prometida.** Es el compromiso que alguien le dio a una
  ///   persona que está esperando; llegar fuera de ella no es lo mismo que
  ///   llegar tarde a una hora estimada.
  /// - **Los requisitos de seguridad.** "Trabajo en altura" decide si el
  ///   trabajo se puede hacer hoy, con lo que hay en la camioneta. Va primero
  ///   y en rojo por eso, no por énfasis.
  ///
  /// No entra:
  ///
  /// - **La prioridad.** Sirve para decidir a cuál ir, y eso ya pasó: quien
  ///   está leyendo esta pantalla ya llegó. Vive en Inicio, que es donde
  ///   ordena.
  /// - **La zona.** Ya está dicha en la dirección; repetirla ocupa una línea
  ///   y no cambia ninguna decisión.
  ///
  /// Cada línea aparece sólo si el servidor la mandó. Una orden vieja, creada
  /// antes de que existieran estos campos, muestra menos y no inventa nada.
  /// `null` cuando la orden no trae ventana, origen, requisitos ni ticket.
  ///
  /// Misma razón que [_datosTecnicos]: una tarjeta que se dibuja vacía sigue
  /// contando como tarjeta para el grupo que la contiene.
  Widget? _datosDeLaOrden(TrabajoVista trabajo) {
    final String ventana = trabajo.ventanaTexto;
    final String origen = trabajo.origen?.etiqueta ?? '';
    final List<String> seguridad = trabajo.requisitosSeguridad;

    // El ticket del ISP cuenta para decidir si la tarjeta existe. Sin esto,
    // una orden que SOLO trae el número de ticket --que es el caso normal de
    // un caso importado-- escondía la tarjeta entera y el número no se veía
    // en ningún lado.
    if (ventana.isEmpty &&
        origen.isEmpty &&
        seguridad.isEmpty &&
        trabajo.numeroTicket.isEmpty) {
      return null;
    }

    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.assignment_outlined,
                size: 16,
                color: AppColors.secondary,
              ),
              const SizedBox(width: 6),
              Text(
                'El trabajo',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
            ],
          ),
          if (seguridad.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            for (final String requisito in seguridad)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: AppSpacing.xs),
                padding: const EdgeInsets.all(AppSpacing.sm),
                decoration: const BoxDecoration(
                  color: AppColors.errorContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(
                      Icons.health_and_safety_outlined,
                      size: 16,
                      color: AppColors.onErrorContainer,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        requisito,
                        style: AppTypography.cuerpoChico.copyWith(
                          color: AppColors.onErrorContainer,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          if (ventana.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.schedule,
              etiqueta: 'Franja prometida al cliente',
              valor: ventana,
            ),
          ],
          // EL TICKET DEL ISP, NO EL UUID DEL CASO. Acá decía
          // «Viene de · Case · 293f1eb8-958d-4ada-96af-731b2797e08c», que no
          // le sirve a nadie: la oficina y el técnico hablan de «el 93426».
          // El número entra a la ficha desde el 25/09/2026.
          if (trabajo.numeroTicket.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.confirmation_number_outlined,
              // La etiqueta va antes del número y en mayúsculas: es un
              // identificador, y quien lo busca lo busca por esa palabra.
              etiqueta: 'TICKET:',
              // El estado es el de ALLÁ, y puede no coincidir con el del CRM:
              // alguien pudo cerrarlo del otro lado.
              // El proveedor va en el valor y no en la etiqueta: el número
              // es lo que se lee primero, y de qué sistema es importa después.
              valor: <String>[
                '#${trabajo.numeroTicket}',
                if (trabajo.estadoTicketIsp.isNotEmpty) trabajo.estadoTicketIsp,
                if (trabajo.proveedorTicket.isNotEmpty) trabajo.proveedorTicket,
              ].join(' · '),
            ),
            if (trabajo.abiertoPorTicket.isNotEmpty)
              // Quién lo abrió cambia la conversación: no es lo mismo que lo
              // haya pedido el cliente a que lo haya abierto la oficina. Si el
              // cliente no sabe de qué le hablan, esto lo explica.
              _lineaDeDato(
                icono: Icons.person_outline,
                etiqueta: 'Lo abrió',
                valor: trabajo.abiertoPorTicket,
              ),
          ] else if (origen.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.alt_route,
              etiqueta: 'Viene de',
              valor: origen,
            ),
          ],
        ],
      ),
    );
  }

  /// Lo que el técnico necesita del equipo y de la red.
  ///
  /// Sale del contexto que el despacho congeló al crear la orden: la caja
  /// donde va a conectar y el serial del equipo del cliente. Sin esos dos
  /// datos, la primera media hora en el sitio se va en buscarlos.
  ///
  /// La potencia óptica todavía no está: la mide SmartOLT y ese puente no
  /// existe. Cuando exista va acá, con su hora al lado, porque una lectura
  /// vieja es peor que ninguna.
  /// `null` cuando no hay ni CTO ni serial.
  ///
  /// Devolver `SizedBox.shrink()` parecia equivalente y no lo es: para el
  /// grupo que la contiene era una tarjeta mas, asi que el rotulo «PARA
  /// ENTENDER LA FALLA» se dibujaba sobre la nada. Ausente se dice con `null`.
  Widget? _datosTecnicos(TrabajoVista trabajo) {
    final String cto = trabajo.contexto['cto']?.toString() ?? '';
    final String serial = trabajo.serialOnu;
    if (cto.isEmpty && serial.isEmpty) return null;

    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.hub_outlined,
                size: 16,
                color: AppColors.secondary,
              ),
              const SizedBox(width: 6),
              Text(
                'Datos técnicos',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
            ],
          ),
          if (cto.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.settings_input_component,
              etiqueta: 'Caja de distribución',
              valor: cto,
              monoespaciada: true,
            ),
          ],
          if (serial.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _lineaDeDato(
              icono: Icons.qr_code_2,
              etiqueta: 'Serial del equipo del cliente',
              valor: serial,
              monoespaciada: true,
            ),
          ],
        ],
      ),
    );
  }

  /// Una línea de dato: qué es, y el valor.
  ///
  /// Los identificadores van en monoespaciada porque se leen carácter por
  /// carácter y se comparan contra una etiqueta pegada en un equipo: ahí la
  /// diferencia entre O y 0 importa.
  Widget _lineaDeDato({
    required IconData icono,
    required String etiqueta,
    required String valor,
    bool monoespaciada = false,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(icono, size: 16, color: AppColors.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(etiqueta, style: AppTypography.etiquetaChica),
              Text(
                valor,
                style: monoespaciada
                    ? AppTypography.datoChico.copyWith(
                        color: AppColors.onSurface,
                      )
                    : AppTypography.cuerpo.copyWith(
                        color: AppColors.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _datosDelCliente(TrabajoVista trabajo) {
    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.person_pin_circle,
                size: 16,
                color: AppColors.secondary,
              ),
              const SizedBox(width: 6),
              Text(
                'Cliente & Ubicación',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
            ],
          ),
          // Solo si la orden trae direccion. Sin la guarda quedaba el alfiler
          // solo, sobre un renglon en blanco: se ve como algo que no cargo,
          // no como algo que la orden no tiene.
          if (trabajo.direccion.trim().isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Icon(
                  Icons.location_on_outlined,
                  size: 16,
                  color: AppColors.azulAccion,
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(trabajo.direccion, style: AppTypography.cuerpo),
                ),
              ],
            ),
          ],
          if (trabajo.telefono.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: <Widget>[
                const Icon(
                  Icons.phone_outlined,
                  size: 16,
                  color: AppColors.exito,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(trabajo.telefono, style: AppTypography.etiquetaGrande),
              ],
            ),
          ],
          // Cómo se entra al inmueble: torre, piso, apartamento. Lo carga el
          // despacho y evita la vuelta al portero.
          if (trabajo.detalleAcceso.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Padding(
              padding: const EdgeInsets.only(left: 24),
              child: Text(
                trabajo.detalleAcceso,
                style: AppTypography.etiquetaChica,
              ),
            ),
          ],
          // El número con el que el cliente se identifica cuando llama a
          // soporte: es el que va a citar si algo queda pendiente.
          if (trabajo.idAbonado.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: <Widget>[
                const Icon(
                  Icons.badge_outlined,
                  size: 16,
                  color: AppColors.onSurfaceVariant,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(trabajo.idAbonado, style: AppTypography.datoChico),
              ],
            ),
          ],
          const SizedBox(height: AppSpacing.sm),
          _ubicacion(trabajo),
          // El plan se muestra cuando la orden lo trae, no cuando hay
          // demostración: define contra qué velocidad se prueba el servicio
          // antes de dar el trabajo por bueno.
          if (trabajo.planContratado.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            _planContratado(),
          ],
          if (trabajo.familia != FamiliaTrabajo.otro) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              '${trabajo.familia.etiqueta} · ${trabajo.tipoCodigo}',
              style: AppTypography.etiquetaChica,
            ),
          ],
        ],
      ),
    );
  }

  /// El recuadro de ubicación del diseño.
  ///
  /// No hay proveedor de mapas ni permiso para abrir otra aplicación, pero las
  /// coordenadas de la orden **sí** son reales (`cliente.lat/lng`): se dibuja
  /// la retícula con el punto donde queda y se muestran los grados. Sin
  /// coordenadas se dice que faltan, en vez de pintar un mapa de adorno que
  /// haría creer que la ubicación está confirmada.
  Widget _ubicacion(TrabajoVista trabajo) {
    final bool ubicado = trabajo.latitud != null && trabajo.longitud != null;

    return SizedBox(
      height: 96,
      child: ClipRRect(
        borderRadius: AppRadius.brTarjeta,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            const ColoredBox(color: AppColors.surfaceContainerHigh),
            const CustomPaint(painter: _Reticula()),
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: AppColors.surface.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                  boxShadow: AppTheme.sombraNivel1,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(
                      ubicado ? Icons.pin_drop : Icons.location_off,
                      size: 16,
                      color: ubicado ? AppColors.error : AppColors.outline,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      ubicado
                          ? '${trabajo.latitud!.toStringAsFixed(5)}, '
                                '${trabajo.longitud!.toStringAsFixed(5)}'
                          : 'Sin coordenadas en la orden',
                      style: ubicado
                          ? AppTypography.datoChico.copyWith(
                              color: AppColors.onSurface,
                            )
                          : AppTypography.etiquetaChica,
                    ),
                  ],
                ),
              ),
            ),
            if (widget.mostrarDatosFuturos)
              Positioned(
                left: AppSpacing.sm,
                top: AppSpacing.sm,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 2,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceContainerLowest,
                    borderRadius: AppRadius.brChico,
                  ),
                  // CAMPO-DATA-003 · La zona, que la orden todavía no trae.
                  child: Text(
                    'Zona ${trabajo.zona.isEmpty ? _ejemploDe(trabajo).zona : trabajo.zona}',
                    style: AppTypography.etiquetaChica,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// El plan del cliente. Viene en `contexto`, que el despacho congela al
  /// crear la orden; si no vino, se cae al ejemplo (CAMPO-DATA-023).
  /// El plan, tal como vino. Vacío si la orden no lo trae: el bloque
  /// entonces no se dibuja, en vez de anunciar una velocidad de ejemplo que
  /// alguien usaría para decidir si el servicio quedó bien.
  String get _plan => _trabajo?.planContratado ?? '';

  /// CAMPO-DATA-023 · Qué tiene contratado el cliente.
  /// Qué tiene contratado el cliente, tal como vino en la orden.
  ///
  /// Sin el chip "+ Dexter TV" que estaba escrito a mano: nada dice que este
  /// cliente tenga televisión. Se veía sólo en demostración y pasó a verse
  /// siempre al mostrar el plan real, que es como los datos de ejemplo se
  /// escapan a producción.
  Widget _planContratado() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.router, size: 18, color: AppColors.secondary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Plan Activo', style: AppTypography.etiquetaChica),
                Text(
                  _plan,
                  style: AppTypography.cuerpoChico.copyWith(
                    color: AppColors.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// CAMPO-DATA-001, 011 y 012: telemetría de red. Ningún sistema la entrega
  /// para campo todavía; se ve solo en modo demostración.
  static String _hhmm(DateTime f) =>
      '${f.hour.toString().padLeft(2, '0')}:${f.minute.toString().padLeft(2, '0')}';

  /// La potencia óptica, con la forma del panel de SmartOLT y los colores de
  /// la aplicación: dos tarjetas, la que RECIBE la ONT y la que recibe la OLT.
  ///
  /// **Dato real desde el 24/09/2026.** Antes acá se dibujaba
  /// `FieldMockData.potenciaRxPrevia` (-28.9 dBm) con la etiqueta roja
  /// «ATENUACIÓN ALTA» **siempre**, sin mirar la bandera de demostración. Con
  /// la orden 1849 en la mano, la lectura real era -21.19 dBm y el veredicto
  /// `aceptable`: la pantalla le decía al técnico que la señal estaba mal
  /// cuando estaba bien, y lo mandaba a buscar una atenuación que no existía.
  ///
  /// **Los umbrales son los del motor, no los del panel del proveedor.** El
  /// panel de SmartOLT rotula `crit -30 · warn -28`; acá manda G-GO-04, que
  /// declara aceptable entre -8 y -25 dBm. Dibujar la regla del proveedor al
  /// lado de un veredicto calculado con otra haría que la barra y la etiqueta
  /// se contradigan en los casos de borde, que son justo los que importan.
  /// El veredicto **no se recalcula acá**: llega resuelto
  /// (`onu_signal_1490_veredicto`) y la pantalla lo muestra.
  Widget _potenciaOptica(TrabajoVista trabajo) {
    if (!trabajo.hayLecturaDeEquipo) {
      // El ejemplo solo aparece donde NO hay lectura real, y solo con la
      // demostración encendida. Esa es toda la diferencia con lo que había
      // antes: el valor de ejemplo ya no puede taparle la señal a nadie.
      return widget.mostrarDatosFuturos
          ? _potenciaDeEjemplo()
          : _sinLecturaDeEquipo(trabajo);
    }

    final bool aceptable = trabajo.veredictoSenal == 'aceptable';

    return Column(
      children: <Widget>[
        // MISMA ALTURA LAS DOS. Sin esto quedan desparejas, porque solo la de
        // bajada lleva etiqueta de veredicto: la de subida no tiene, y poner
        // una seria inventarla. 'IntrinsicHeight' mide la más alta y
        // 'stretch' iguala la otra, en vez de reservar un hueco del tamaño de
        // una etiqueta que puede no existir.
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Expanded(
                child: _MedidaOptica(
                  titulo: 'Rx ONU',
                  // La DIRECCION, que es lo que decide como leer el numero:
                  // esta es la de bajada (1490 nm), lo que llega a la casa.
                  detalle: 'OLT → CLIENTE',
                  valor: trabajo.potenciaOptica,
                  // El veredicto del motor es sobre 1490: es la de bajada, la
                  // única que habla de lo que llega a la casa.
                  etiqueta: trabajo.veredictoSenal,
                  buena: aceptable,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _MedidaOptica(
                  titulo: 'Rx OLT',
                  // La de subida (1310 nm): lo que la central recibe.
                  detalle: 'CLIENTE → OLT',
                  valor: trabajo.potenciaOpticaSubida,
                  // Sin etiqueta: el motor no emite veredicto para la de
                  // subida, y ponerle uno acá sería inventarlo.
                  etiqueta: '',
                  buena: aceptable,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          textoDelRangoOptico,
          style: AppTypography.etiquetaChica.copyWith(color: AppColors.outline),
        ),
      ],
    );
  }

  /// Un ping en vivo, que es lo único que la ficha congelada no puede
  /// contestar: el técnico movió un conector y necesita saber si el equipo
  /// responde AHORA.
  ///
  /// **Diez paquetes, listados uno por uno.** Un promedio esconde lo que le
  /// interesa a quien está parado en la casa —si el enlace es intermitente o
  /// está caído parejo—, y con tres muestras esa diferencia no se dibuja:
  /// está medido que el mismo equipo sano devuelve 1, 2 y 3 de 3 en corridas
  /// seguidas, así que una racha corta no se distingue de un patrón.
  ///
  /// **No dictamina.** Se enseña el conteo crudo y cada intento; quien decide
  /// qué significa es la persona que está ahí.
  Widget _probarConexion() {
    final bool disponible = widget.acciones.probarConexion != null;
    final ResultadoPing? r = _ping;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.network_ping,
                size: 18,
                color: AppColors.secondary,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(child: Text('Ping', style: AppTypography.cuerpoChico)),
              if (_pingEnCurso) ...<Widget>[
                Text(
                  _ping == null
                      ? '$_paquetesDelPing paquetes…'
                      : '${_ping!.paquetes.length} de $_paquetesDelPing…',
                  style: AppTypography.etiquetaChica,
                ),
                const SizedBox(width: AppSpacing.sm),
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ] else ...<Widget>[
                TextButton(
                  onPressed: disponible ? _lanzarPing : null,
                  child: Text(r == null ? 'Ping' : 'Repetir'),
                ),
                // Cerrar el resultado. No es cosmética: la lista ocupa media
                // pantalla y debajo está el botón con el que el técnico
                // avanza la orden.
                if (r != null)
                  IconButton(
                    onPressed: () => setState(() => _ping = null),
                    icon: const Icon(Icons.close, size: 18),
                    tooltip: 'Cerrar el resultado',
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ],
          ),
          if (r != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            if (r.medido) ...<Widget>[
              Text(
                'Respondieron ${r.respondieron}',
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              // La tabla del panel del proveedor: número, quién contestó y
              // cuánto tardó. Se conserva esa forma porque es la que la
              // operación ya sabe leer.
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: 4,
                ),
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainerHigh,
                  borderRadius: AppRadius.brChico,
                ),
                child: Row(
                  children: <Widget>[
                    SizedBox(
                      width: 24,
                      child: Text(
                        '#',
                        style: AppTypography.etiquetaChica.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        'Host',
                        style: AppTypography.etiquetaChica.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    SizedBox(
                      width: 78,
                      child: Text(
                        'Tiempo',
                        textAlign: TextAlign.right,
                        style: AppTypography.etiquetaChica.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              for (final PaqueteDePing p in r.paquetes)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    // La fila alterna, como la tabla del proveedor. Un
                    // paquete perdido se pinta entero: es lo que hay que ver
                    // de un vistazo.
                    color: p.respondio
                        ? (p.n.isEven
                              ? AppColors.surfaceContainerLowest
                              : Colors.transparent)
                        : AppColors.errorContainer,
                  ),
                  child: Row(
                    children: <Widget>[
                      SizedBox(
                        width: 24,
                        child: Text(
                          '${p.n}',
                          style: AppTypography.etiquetaChica,
                        ),
                      ),
                      Expanded(
                        child: Text(
                          p.host.isEmpty ? '—' : p.host,
                          style: AppTypography.datoChico.copyWith(
                            color: p.respondio
                                ? AppColors.onSurfaceVariant
                                : AppColors.onErrorContainer,
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 78,
                        child: Text(
                          p.respondio
                              ? (p.rtt.isEmpty ? 'volvió' : p.rtt)
                              : 'sin respuesta',
                          textAlign: TextAlign.right,
                          style: AppTypography.datoChico.copyWith(
                            color: p.respondio
                                ? AppColors.exitoTexto
                                : AppColors.onErrorContainer,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ] else
              Text(
                // Cada motivo se arregla distinto, así que cada uno dice lo
                // suyo. «No se pudo medir» jamás se dibuja como «no
                // respondió»: esa confusión manda a revisar una roseta sana.
                switch (r.motivo) {
                  'sin_conexion' =>
                    'Sin conexión: esta prueba necesita señal y no se encola. '
                        'Se puede repetir cuando haya.',
                  'ping_no_habilitado' =>
                    'La prueba no está habilitada para esta empresa todavía.',
                  'motor_no_responde' => 'No se pudo preguntar. No dice nada del equipo del cliente.',
                  _ => 'No se pudo medir.',
                },
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
          ],
        ],
      ),
    );
  }

  /// Pide las tandas en orden y va agregando cada una apenas llega, para que
  /// los paquetes se vean caer en vez de aparecer los diez al final.
  ///
  /// Si una tanda falla, se corta ahí y se muestra el motivo **conservando lo
  /// que ya volvió**: cinco paquetes medidos y una explicación valen más que
  /// una pantalla en blanco.
  /// Qué dice lo medido, en una frase, y qué tramo conviene mirar primero.
  ///
  /// Junta el ping, la potencia y el estado de la ONU. **No agrega ningún
  /// dato**: solo combina los que ya están en esta tarjeta. Las reglas viven
  /// en `diagnostico_de_campo.dart`, con sus pruebas.
  ///
  /// No dictamina: dice dónde empezar, que es una decisión de orden de
  /// trabajo. Y si no hay con qué, no aparece.
  Widget _queDiceLoMedido(TrabajoVista trabajo) {
    final DiagnosticoDeCampo d = DiagnosticoDeCampo.de(
      veredicto: trabajo.veredictoSenal,
      estadoOnu: trabajo.estadoOnu,
      ping: _ping,
    );
    if (!d.hayAlgoQueDecir) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: d.malo ? AppColors.errorContainer : AppColors.exitoFondo,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(
              d.malo ? Icons.troubleshoot : Icons.check_circle_outline,
              size: 18,
              color: d.malo ? AppColors.onErrorContainer : AppColors.exitoTexto,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'QUÉ DICE LO MEDIDO',
                    style: AppTypography.etiquetaChica.copyWith(
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                      color: d.malo
                          ? AppColors.onErrorContainer
                          : AppColors.exitoTexto,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    d.texto,
                    style: AppTypography.cuerpoChico.copyWith(
                      color: d.malo
                          ? AppColors.onErrorContainer
                          : AppColors.exitoTexto,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _lanzarPing() async {
    final Future<ResultadoPing> Function(String, int)? probar =
        widget.acciones.probarConexion;
    if (probar == null || _pingEnCurso) return;

    setState(() {
      _pingEnCurso = true;
      // El resultado anterior se borra al arrancar: dejarlo en pantalla
      // mientras corre el siguiente invita a leer el viejo como el nuevo.
      _ping = null;
    });

    final List<PaqueteDePing> acumulados = <PaqueteDePing>[];
    for (final int tanda in _tandasDelPing) {
      final ResultadoPing r = await probar(widget.ordenId, tanda);
      if (!mounted) return;

      if (!r.medido) {
        setState(() {
          _pingEnCurso = false;
          // Lo que ya se midió no se tira: se muestra con el motivo al lado.
          _ping = acumulados.isEmpty
              ? r
              : ResultadoPing(
                  medido: true,
                  respondieron: _conteo(acumulados),
                  paquetes: List<PaqueteDePing>.of(acumulados),
                  motivo: r.motivo,
                );
        });
        return;
      }

      // DE A UNO, aunque hayan llegado de a tres.
      //
      // WispHub no acepta pedir menos de 3 por llamada (medido: 1 y 2 dan
      // 400), así que los tres vuelven juntos. Mostrarlos juntos hace que la
      // lista salte de 3 en 3; mostrarlos de a uno deja ver el ping pasar,
      // que es para lo que se pide.
      //
      // La cadencia es DE LA PANTALLA, no del dato: los tiempos que se leen
      // son los que midió cada paquete, no el momento en que aparecieron.
      // Por eso no se escribe ninguna hora al lado.
      //
      // Y se renumeran de corrido: cada tanda vuelve empezando en 1, y una
      // lista que dijera 1,2,3,1,2,3 sería ilegible.
      for (final PaqueteDePing p in r.paquetes) {
        acumulados.add(
          PaqueteDePing(
            n: acumulados.length + 1,
            respondio: p.respondio,
            rtt: p.rtt,
            perdida: p.perdida,
            host: p.host,
          ),
        );
        if (!mounted) return;
        setState(() {
          _ping = ResultadoPing(
            medido: true,
            respondieron: _conteo(acumulados),
            paquetes: List<PaqueteDePing>.of(acumulados),
          );
        });
        await Future<void>.delayed(_pausaEntrePaquetes);
      }
    }

    if (mounted) setState(() => _pingEnCurso = false);
  }

  /// «X de Y» con lo que se lleva medido. Se cuenta acá y no se reenvía el
  /// texto de una tanda: cada una dice «3 de 3», y pegar el de la última haría
  /// que diez paquetes con dos perdidos se anuncien como «4 de 4».
  static String _conteo(List<PaqueteDePing> ps) =>
      '${ps.where((PaqueteDePing p) => p.respondio).length} de ${ps.length}';

  /// CAMPO-DATA-001 · La potencia de ejemplo, para ver el producto completo
  /// cuando la orden todavía no trae lectura. Es el bloque que estaba acá
  /// antes, intacto: lo único que cambió es **cuándo** se dibuja.
  Widget _potenciaDeEjemplo() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.errorContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Row(
        children: <Widget>[
          const Icon(
            Icons.warning,
            size: 18,
            color: AppColors.onErrorContainer,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        'Potencia RX ONT Actual',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.etiquetaChica.copyWith(
                          color: AppColors.onErrorContainer,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 5,
                        vertical: 1,
                      ),
                      decoration: const BoxDecoration(
                        color: AppColors.error,
                        borderRadius: AppRadius.brChico,
                      ),
                      child: Text(
                        'ATENUACIÓN ALTA',
                        style: AppTypography.etiquetaChica.copyWith(
                          fontSize: 9,
                          color: AppColors.onError,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                Text(
                  textoDelRangoOptico,
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onErrorContainer,
                  ),
                ),
              ],
            ),
          ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: <Widget>[
              Text(
                FieldMockData.potenciaRxPrevia.toStringAsFixed(1),
                style: AppTypography.medicion.copyWith(color: AppColors.error),
              ),
              const SizedBox(width: 2),
              Text(
                'dBm',
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.onErrorContainer,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Por qué no hay lectura, que no es lo mismo que una tarjeta vacía.
  ///
  /// Una tarjeta en blanco manda a buscar una falla de red donde lo único que
  /// pasa es que falta cargar un serial — y eso le ocurre a 1.299 de 4.163
  /// clientes activos, medido. Cada motivo se arregla distinto, así que cada
  /// uno dice lo suyo.
  Widget _sinLecturaDeEquipo(TrabajoVista trabajo) {
    final (IconData icono, String texto) = switch (trabajo.sinEquipo) {
      SinEquipo.serialNoCargado => (
        Icons.link_off,
        'Este cliente no tiene el equipo cargado en el sistema, así que no '
            'hay señal que consultar. No es una falla de red.',
      ),
      SinEquipo.serialDesactualizado => (
        Icons.sync_problem,
        'El serial que figura no existe en la OLT. Suele pasar cuando se le '
            'cambió el equipo al cliente y se actualizó un solo sistema.',
      ),
      _ => (
        Icons.cloud_off,
        'La señal del equipo no se alcanzó a leer. Se vuelve a intentar al '
            'refrescar la ficha.',
      ),
    };

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(icono, size: 18, color: AppColors.outline),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              texto,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _telemetria(TrabajoVista trabajo) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
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
              Container(
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: const Icon(
                  Icons.router,
                  size: 18,
                  color: AppColors.secondary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Telemetría SmartOLT',
                      style: AppTypography.cuerpoGrande,
                    ),
                    Text('Vía Dexter API', style: AppTypography.etiquetaChica),
                  ],
                ),
              ),
              // La lectura está CONGELADA, no en vivo. Acá decía "Live" con un
              // punto verde sobre datos capturados horas antes. El backend ya
              // dejó escrito por qué importa: "al congelarse, una medición deja
              // de ser una medición -- pasa a ser un registro de lo que se veía
              // en un momento". Un técnico parado en la casa que lee "Live" no
              // tiene forma de saber que está viendo el pasado.
              if (trabajo.fichaCapturadaEn != null)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 3,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceContainerHigh,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      const Icon(
                        Icons.history,
                        size: 11,
                        color: AppColors.outline,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        'Medido ${_hhmm(trabajo.fichaCapturadaEn!)}',
                        style: AppTypography.etiquetaChica,
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          // El serial va SOLO en su fila: doce caracteres no entran en media
          // pantalla sin partirse, y es la única llave con la que se llega a
          // SmartOLT -- si se corta, no sirve para buscar nada.
          _CajaDato(
            titulo: 'ONT SERIAL',
            valor: trabajo.serialOnu.isNotEmpty
                ? trabajo.serialOnu
                : (widget.mostrarDatosFuturos ? FieldMockData.serialOnt : '—'),
            detalle: trabajo.estadoOnu.isNotEmpty
                ? 'Equipo ${trabajo.estadoOnu}'
                : 'Sin lectura',
          ),
          const SizedBox(height: AppSpacing.sm),
          // CAMPO-DATA-011, ya no es de ejemplo: el puerto PON y la caja
          // entran a la ficha desde el 25/09/2026 (api.py::_estado_equipo,
          // con lista blanca -- esa respuesta trae el nombre del cliente).
          //
          // DOS TARJETAS Y NO UNA. Estaban juntas bajo «PUERTO PON / CAJA» y
          // se leía mal: el valor grande era el puerto y la caja quedaba
          // debajo como si fuera su detalle. Son dos datos distintos, de dos
          // cosas distintas de la red, y cada uno puede faltar por su cuenta.
          Row(
            children: <Widget>[
              Expanded(
                child: _CajaDato(
                  titulo: 'PUERTO PON',
                  valor: trabajo.puertoPon.isNotEmpty
                      ? trabajo.puertoPon
                      : (widget.mostrarDatosFuturos
                            ? FieldMockData.puertoPon
                            : '—'),
                  // 'board/port'. El número de ONU va aparte: es su posición
                  // DENTRO del puerto, no parte del identificador.
                  detalle: trabajo.puertoPon.isNotEmpty
                      ? 'tarjeta / puerto'
                      : 'Dato no disponible',
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              // La CAJA puede venir vacía y es normal, no un fallo: medido, el
              // cliente de la orden 1849 no la tiene cargada en SmartOLT. Se
              // dice, en vez de dibujar una que no existe.
              Expanded(
                child: _CajaDato(
                  titulo: 'CAJA / CTO',
                  valor: trabajo.cajaDeDistribucion.isNotEmpty
                      ? trabajo.cajaDeDistribucion
                      : '—',
                  detalle: trabajo.cajaDeDistribucion.isNotEmpty
                      ? 'caja de distribución'
                      : 'Sin caja cargada',
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          _potenciaOptica(trabajo),
          const SizedBox(height: AppSpacing.sm),
          // La planta, con lo que la ficha capturó de verdad. Cada fila
          // aparece solo si su dato llegó: una etiqueta con un guion al lado
          // ocupa el mismo lugar y no informa nada.
          for (final (String titulo, String valor) in <(String, String)>[
            ('OLT', trabajo.oltDelEquipo),
            // El número de ONU va acá y no pegado al puerto: es su posición
            // DENTRO del PON, no parte del identificador del puerto.
            ('ONU en el puerto', trabajo.indiceOnu),
            ('Zona de red', trabajo.zonaDeRed),
            ('Equipo', trabajo.modeloDelEquipo),
            ('Distancia a la OLT', trabajo.distanciaOlt),
          ])
            if (valor.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(titulo, style: AppTypography.etiquetaChica),
                    ),
                    Text(
                      valor,
                      style: AppTypography.datoChico.copyWith(
                        color: AppColors.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
          const SizedBox(height: AppSpacing.sm),
          _probarConexion(),
          _queDiceLoMedido(trabajo),
          const SizedBox(height: AppSpacing.sm),
          // CAMPO-DATA-012 y -030 · El historico de 48 horas no llega de
          // ningun lado: la ficha congela UNA lectura, no una serie. Dibujar
          // una curva de ejemplo al lado de una potencia REAL la haria pasar
          // por el historico de este cliente.
          if (widget.mostrarDatosFuturos) ...<Widget>[
            // CAMPO-DATA-012
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerLow,
                borderRadius: AppRadius.brCampo,
              ),
              child: Row(
                children: <Widget>[
                  Text('Histórico 48h', style: AppTypography.etiquetaChica),
                  const SizedBox(width: AppSpacing.sm),
                  // CAMPO-DATA-030 · La serie de las últimas 48 horas.
                  const Expanded(
                    child: SizedBox(
                      height: 28,
                      child: CustomPaint(
                        painter: _CurvaRx(FieldMockData.historicoRx48h),
                        size: Size.infinite,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  const Icon(
                    Icons.trending_down,
                    size: 16,
                    color: AppColors.error,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${FieldMockData.deltaPotencia48h} dBm',
                    style: AppTypography.etiqueta.copyWith(
                      color: AppColors.error,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            // CAMPO-DATA-048 · La matriz completa del diseño: de qué OLT cuelga,
            // por qué puerto, a qué distancia y con cuánta potencia sale.
            for (final (String titulo, String valor) in <(String, String)>[
              ('OLT & Puerto', FieldMockData.oltYPuerto),
              ('CTO Distribución', FieldMockData.terminal),
              ('Distancia Splitter', FieldMockData.distanciaSplitter),
              ('Potencia TX OLT', FieldMockData.potenciaTxOlt),
            ])
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(titulo, style: AppTypography.etiquetaChica),
                    ),
                    Text(
                      valor,
                      style: AppTypography.datoChico.copyWith(
                        color: AppColors.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
          ],
          // Aca decia 'Fuente: SmartOLT via Dexter API - lectura congelada
          // al despachar'. Se quito el 25/09/2026: la cabecera ya dice
          // 'Medido HH:mm', que es la misma advertencia en dos palabras y
          // en el lugar donde se mira el numero. Repetirla abajo la volvia
          // letra chica que nadie lee.
        ],
      ),
    );
  }

  /// Lo que el asistente ya averiguó, antes de que existiera esta orden.
  ///
  /// **Es trabajo hecho que se estaba tirando.** Dexter habla con el cliente
  /// por WhatsApp: verifica identidad, mide el equipo, descarta causas y deja
  /// escrito qué falta averiguar. Todo eso vivía en su base y no salía de ahí,
  /// así que el técnico llegaba a la casa a preguntar lo que el cliente ya
  /// había contestado.
  ///
  /// El «siguiente paso» va arriba y destacado: no es una etiqueta, es la
  /// instrucción concreta con la que conviene tocar el timbre.
  ///
  /// El resumen viaja **sin el documento del cliente** (lo redacta el modelo y
  /// trae la cédula cuando la verificó). Ver `_sin_documentos` en el backend.
  Widget _loQueDexterAveriguo(TrabajoVista trabajo) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
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
              const Icon(
                Icons.auto_awesome,
                size: 18,
                color: AppColors.primary,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Lo que el asistente ya averiguó',
                  style: AppTypography.cuerpoGrande,
                ),
              ),
              if (trabajo.motivoEscaladaDexter.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 3,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceContainerHigh,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Text(
                    trabajo.motivoEscaladaDexter.replaceAll('_', ' '),
                    style: AppTypography.etiquetaChica,
                  ),
                ),
            ],
          ),
          if (trabajo.siguientePasoDexter.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brCampo,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'QUÉ FALTA AVERIGUAR',
                    style: AppTypography.etiquetaChica.copyWith(
                      fontWeight: FontWeight.w700,
                      color: AppColors.primary,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    trabajo.siguientePasoDexter,
                    style: AppTypography.cuerpoChico,
                  ),
                ],
              ),
            ),
          ],
          if (trabajo.resumenDexter.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              trabajo.resumenDexter,
              style: AppTypography.datoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
          ],
          if (trabajo.casoDexter.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Clasificado como ${trabajo.casoDexter.replaceAll('_', ' ')}',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.outline,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// El triage del diseño. La cita del cliente es **real** —es el diagnóstico
  /// que manda el backend—; la lista de comprobaciones y la causa sugerida son
  /// de ejemplo (CAMPO-DATA-024) hasta que exista un diagnóstico estructurado.
  Widget _triage(TrabajoVista trabajo) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
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
              Container(
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: const Icon(
                  Icons.smart_toy,
                  size: 18,
                  color: AppColors.primary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Triage Inteligente Dexter',
                      style: AppTypography.cuerpoGrande,
                    ),
                    Text(
                      widget.mostrarDatosFuturos
                          ? 'Análisis correlacionado en tiempo real'
                          : 'Lo que trae la orden',
                      style: AppTypography.etiquetaChica,
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (trabajo.diagnosticoPrevio.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerLow,
                borderRadius: AppRadius.brCampo,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Icon(
                    Icons.record_voice_over,
                    size: 16,
                    color: AppColors.onSurfaceVariant,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      trabajo.diagnosticoPrevio,
                      style: AppTypography.cuerpo.copyWith(
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (widget.mostrarDatosFuturos) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            const _FilaChequeo(
              icono: Icons.verified,
              texto: 'Facturación y perfil de cliente',
              estado: 'AL DÍA',
              color: AppColors.exito,
            ),
            const _FilaChequeo(
              icono: Icons.cell_tower,
              texto: 'Puerto OLT PON 0/1/4',
              estado: 'NORMAL',
              color: AppColors.exito,
            ),
            const _FilaChequeo(
              icono: Icons.error_outline,
              texto: 'Atenuación acumulada',
              estado: 'DEGRADADO',
              color: AppColors.error,
            ),
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerHigh,
                borderRadius: AppRadius.brCampo,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Icon(
                    Icons.lightbulb,
                    size: 16,
                    color: AppColors.primary,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'CAUSA SUGERIDA',
                          style: AppTypography.etiquetaChica.copyWith(
                            color: AppColors.primary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        Text(
                          'Conector SC/APC sucio, fisura interna o radio de '
                          'curvatura estrangulado en acometida.',
                          style: AppTypography.cuerpoChico,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _avisoExcepcion(TrabajoVista trabajo, LecturaDePasos lectura) {
    final esCancelada = trabajo.estado == EstadoTrabajo.cancelada;
    return DexterCard(
      colorFondo: esCancelada
          ? AppColors.inactivoFondo
          : AppColors.precaucionFondo,
      colorBorde: esCancelada ? AppColors.bordeFuerte : AppColors.precaucion,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            esCancelada ? Icons.block : Icons.assignment_return_outlined,
            size: 18,
            color: esCancelada ? AppColors.inactivo : AppColors.precaucion,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(lectura.avisoExcepcion!, style: AppTypography.cuerpo),
          ),
        ],
      ),
    );
  }

  /// Terminada en el teléfono, sin confirmar el servidor. La diferencia
  /// importa: hasta que la cola no la envíe, para la empresa ese trabajo no
  /// está hecho.
  Widget _avisoSinEnviar() {
    return DexterCard(
      colorFondo: AppColors.precaucionFondo,
      colorBorde: AppColors.precaucion,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.cloud_upload_outlined,
                size: 18,
                color: AppColors.precaucion,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Completado en campo · pendiente de enviar',
                  style: AppTypography.cuerpoGrande,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Lo que hiciste está guardado en el teléfono. Se envía solo cuando '
            'haya señal; no hace falta repetirlo.',
            style: AppTypography.cuerpoChico,
          ),
        ],
      ),
    );
  }

  Widget _acciones(TrabajoVista trabajo, AccionesDisponibles acciones) {
    if (trabajo.requiereActualizacion) {
      return const ElevatedButton(
        onPressed: null,
        child: Text('Actualizá la aplicación para trabajar esta orden'),
      );
    }

    if (acciones.primaria == null) {
      return Text(
        _sinAccionesPorque(trabajo.estado),
        style: AppTypography.cuerpoChico,
        textAlign: TextAlign.center,
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ElevatedButton(
          onPressed: _trabajando
              ? null
              : () => _ejecutarAccion(trabajo, acciones.primaria!),
          child: _trabajando
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(acciones.primaria!.etiqueta),
        ),
        for (final AccionOrden secundaria in acciones.secundarias) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          OutlinedButton(
            onPressed: _trabajando
                ? null
                : () => _ejecutarAccion(trabajo, secundaria),
            child: Text(secundaria.etiqueta),
          ),
        ],
      ],
    );
  }

  String _sinAccionesPorque(EstadoTrabajo estado) => switch (estado) {
    EstadoTrabajo.completadaSinEnviar =>
      'Ya está hecho. Falta que se envíe al servidor.',
    EstadoTrabajo.completadaCampo =>
      'Trabajo entregado. Queda esperar la revisión del supervisor.',
    EstadoTrabajo.cerrada => 'Este trabajo está cerrado.',
    EstadoTrabajo.cancelada => 'Este trabajo fue cancelado.',
    _ => 'No hay ninguna acción disponible para este estado.',
  };
}

/// La línea de pasos del diseño, alimentada por [LecturaDePasos].
class _BarraDePasos extends StatelessWidget {
  const _BarraDePasos({required this.lectura});

  final LecturaDePasos lectura;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: lectura.pasoActual < 0
          ? 'Sin avance'
          : 'Paso ${lectura.pasoActual + 1} de ${PasoOrden.values.length}: '
                '${PasoOrden.values[lectura.pasoActual].etiqueta}',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          // El rótulo del paso vive en el encabezado, que es donde lo pone
          // el diseño. Acá quedaba dos veces en la misma pantalla.
          if (lectura.pasoActual < 0) ...<Widget>[
            Text(
              'SIN AVANCE',
              style: AppTypography.labelBadge.copyWith(
                color: AppColors.outline,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
          ],
          Row(
            children: <Widget>[
              for (int i = 0; i < PasoOrden.values.length; i++) ...<Widget>[
                if (i > 0) const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Container(
                    height: 4,
                    decoration: BoxDecoration(
                      color: _colorDelPaso(i),
                      borderRadius: AppRadius.brChico,
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              for (int i = 0; i < PasoOrden.values.length; i++) ...<Widget>[
                if (i > 0) const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Column(
                    children: <Widget>[
                      if (i < lectura.pasoActual)
                        const Icon(
                          Icons.check,
                          size: 11,
                          color: AppColors.exito,
                        ),
                      Text(
                        PasoOrden.values[i].etiqueta,
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.etiquetaChica.copyWith(
                          fontSize: 10,
                          height: 1.1,
                          color: i == lectura.pasoActual
                              ? AppColors.primary
                              : AppColors.onSurfaceVariant,
                          fontWeight: i == lectura.pasoActual
                              ? FontWeight.w700
                              : FontWeight.w400,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Color _colorDelPaso(int indice) {
    if (lectura.pasoActual < 0) return AppColors.borde;
    if (indice > lectura.pasoActual) return AppColors.borde;
    // El paso donde está parada una orden devuelta se pinta en ámbar: llegó
    // hasta ahí, pero no por el camino normal.
    if (indice == lectura.pasoActual && lectura.excepcion) {
      return AppColors.precaucion;
    }
    return AppColors.azulMarino;
  }
}

/// Una casilla de dato técnico, como las del diseño.
class _CajaDato extends StatelessWidget {
  const _CajaDato({
    required this.titulo,
    required this.valor,
    required this.detalle,
  });

  final String titulo;
  final String valor;
  final String detalle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(titulo, style: AppTypography.etiquetaChica),
          const SizedBox(height: 2),
          Text(
            valor,
            style: AppTypography.etiquetaGrande.copyWith(
              color: AppColors.onSurface,
              fontWeight: FontWeight.w700,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          Text(
            detalle,
            style: AppTypography.etiquetaChica,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

/// Una línea de la lista de comprobaciones del triage.
class _FilaChequeo extends StatelessWidget {
  const _FilaChequeo({
    required this.icono,
    required this.texto,
    required this.estado,
    required this.color,
  });

  final IconData icono;
  final String texto;
  final String estado;
  final Color color;

  /// La fila degradada se pinta entera: es la que hay que mirar primero.
  bool get _esAlerta => color == AppColors.error;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.xs),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: _esAlerta
            ? AppColors.errorContainer
            : AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 16, color: color),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              texto,
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurface,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Text(
            estado,
            style: AppTypography.etiquetaChica.copyWith(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

/// CAMPO-DATA-030 · La curva de potencia de las últimas 48 horas.
///
/// Dibuja la serie tal cual llega, sin suavizar ni recortar: si alguna vez
/// llegan lecturas reales, lo que se ve es lo que midió la OLT.
class _CurvaRx extends CustomPainter {
  const _CurvaRx(this.serie);

  final List<double> serie;

  @override
  void paint(Canvas lienzo, Size medida) {
    if (serie.length < 2) return;

    final double minimo = serie.reduce((double a, double b) => a < b ? a : b);
    final double maximo = serie.reduce((double a, double b) => a > b ? a : b);
    final double rango = (maximo - minimo).abs() < 0.01 ? 1 : maximo - minimo;

    final Path camino = Path();
    for (int i = 0; i < serie.length; i++) {
      final double x = medida.width * i / (serie.length - 1);
      final double y = medida.height * (1 - (serie[i] - minimo) / rango);
      if (i == 0) {
        camino.moveTo(x, y);
      } else {
        camino.lineTo(x, y);
      }
    }

    lienzo.drawPath(
      camino,
      Paint()
        ..color = AppColors.error
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5
        ..strokeCap = StrokeCap.round,
    );

    // El último punto, que es la lectura de ahora.
    lienzo.drawCircle(
      Offset(medida.width, medida.height * (1 - (serie.last - minimo) / rango)),
      2.5,
      Paint()..color = AppColors.error,
    );
  }

  @override
  bool shouldRepaint(_CurvaRx anterior) => anterior.serie != serie;
}

/// Una acción rápida del detalle. Cuando no hay con qué —sin teléfono, sin
/// coordenadas— se ve apagada en vez de fallar al tocarla.

/// La retícula del recuadro de ubicación. No es un mapa: es el fondo sobre el
/// que se leen las coordenadas, para que nadie lo confunda con una calle.
class _Reticula extends CustomPainter {
  const _Reticula();

  @override
  void paint(Canvas lienzo, Size medida) {
    final Paint linea = Paint()
      ..color = AppColors.surfaceContainerLowest.withValues(alpha: 0.6)
      ..strokeWidth = 1;

    for (double x = 0; x < medida.width; x += 24) {
      lienzo.drawLine(Offset(x, 0), Offset(x, medida.height), linea);
    }
    for (double y = 0; y < medida.height; y += 24) {
      lienzo.drawLine(Offset(0, y), Offset(medida.width, y), linea);
    }
  }

  @override
  bool shouldRepaint(_Reticula anterior) => false;
}

/// Una medida óptica con la forma del panel de SmartOLT —valor grande,
/// etiqueta de estado y una barra con la zona buena— y los colores de esta
/// aplicación.
///
/// La barra usa los umbrales de **G-GO-04**, no los del panel del proveedor
/// (`crit -30 · warn -28`). Mezclarlos haría que la barra contradiga al
/// veredicto en los casos de borde, que son los únicos en los que alguien
/// mira la barra.
class _MedidaOptica extends StatelessWidget {
  const _MedidaOptica({
    required this.titulo,
    required this.detalle,
    required this.valor,
    required this.etiqueta,
    required this.buena,
  });

  final String titulo;
  final String detalle;

  /// Como lo manda SmartOLT: '-21.19 dBm'.
  final String valor;

  /// El veredicto del motor, o vacío si no emitió ninguno para esta medida.
  final String etiqueta;
  final bool buena;

  /// Los bordes de la zona aceptable, en dBm. Son los de G-GO-04, y no los
  /// de la maqueta.
  ///
  /// LA MAQUETA TRAE OTROS, Y NO SE COPIARON
  /// ---------------------------------------
  /// El diseño de Stitch escribe "Umbral óptimo: -18 a -24 dBm". Ese par no
  /// sale de ningún lado del sistema: el rango acordado es -8 a -25, y el
  /// veredicto lo calcula el motor, no esta pantalla. Copiar el de la maqueta
  /// habría puesto en el teléfono del técnico una regla distinta de la que
  /// usa el asistente para decidir, que es la peor clase de diferencia:
  /// invisible hasta que dos personas discuten mirando la misma señal.
  static const double _min = -25.0;
  static const double _max = -8.0;

  /// Hasta dónde se dibuja la barra. No empieza en el umbral: una barra que
  /// arranca justo donde termina lo aceptable no deja ver CUÁNTO se pasó.
  ///
  /// Va de la más fuerte a la más débil, izquierda a derecha, como en el
  /// diseño (que rotula "Alto" a la izquierda y "Corte" a la derecha).
  static const double _masFuerte = -4.0;
  static const double _masDebil = -32.0;

  /// Las ocho celdas del diseño (`grid-cols-8`).
  static const int _celdas = 8;

  double? get _numero {
    final String limpio = valor.replaceAll(RegExp(r'[^0-9.\-]'), '');
    return double.tryParse(limpio);
  }

  /// En qué celda cae una lectura. Fuera de la barra se queda en el borde:
  /// decir «está fuera» es la información; cuánto más allá no cambia lo que
  /// hace el técnico.
  static int celdaDe(double dbm) {
    const double ancho = (_masFuerte - _masDebil) / _celdas;
    final int i = ((_masFuerte - dbm) / ancho).floor();
    return i.clamp(0, _celdas - 1);
  }

  /// El color de cada celda.
  ///
  /// La barra no decide nada: pinta en verde las celdas cuyo centro cae
  /// dentro del rango acordado, deja en gris las de afuera, y marca con el
  /// color del VEREDICTO —que viene del motor— la celda donde cayó la
  /// lectura. Si el veredicto y la posición no coincidieran, manda el
  /// veredicto: es quien tiene la regla.
  static List<Color> coloresDe(double? dbm, {required bool buena}) {
    const double ancho = (_masFuerte - _masDebil) / _celdas;
    final List<Color> colores = <Color>[];
    for (int i = 0; i < _celdas; i++) {
      final double centro = _masFuerte - ancho * (i + 0.5);
      final bool enRango = centro <= _max && centro >= _min;
      colores.add(
        enRango
            ? AppColors.onTertiaryContainer
            : AppColors.surfaceContainerHigh,
      );
    }
    if (dbm != null) {
      colores[celdaDe(dbm)] = buena
          ? AppColors.tertiaryFixedDim
          : AppColors.error;
    }
    return colores;
  }

  @override
  Widget build(BuildContext context) {
    final double? dbm = _numero;
    final bool hay = dbm != null;
    final Color acento = buena
        ? AppColors.onTertiaryContainer
        : AppColors.error;

    return DexterHundido(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            titulo.toUpperCase(),
            style: AppTypography.labelCaption.copyWith(
              color: AppColors.outline,
            ),
          ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: <Widget>[
              Text(
                hay ? dbm.toStringAsFixed(2) : '—',
                style: AppTypography.medicion.copyWith(color: acento),
              ),
              const SizedBox(width: 2),
              Text(
                'dBm',
                style: AppTypography.labelTelemetry.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ],
          ),
          if (etiqueta.isNotEmpty) ...<Widget>[
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerLeft,
              child: buena
                  ? DexterPastilla.enRegla(texto: etiqueta.replaceAll('_', ' '))
                  : DexterPastilla.critica(
                      texto: etiqueta.replaceAll('_', ' '),
                    ),
            ),
          ],
          if (hay) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            // Sin los rotulos de los extremos: el rango completo ya se
            // escribe una sola vez debajo de las dos tarjetas ("Aceptable
            // entre -8 y -25 dBm"), y repetirlo en letra chica bajo cada
            // barra era ruido sobre la lectura, que es lo que hay que mirar.
            // Sigue estando para el lector de pantalla, que no tiene esa
            // linea a la vista.
            DexterBarraSegmentada(
              celdas: coloresDe(dbm, buena: buena),
              descripcionAccesible:
                  '$titulo, $detalle: ${dbm.toStringAsFixed(2)} dBm. '
                  'Aceptable entre ${_max.toStringAsFixed(0)} y '
                  '${_min.toStringAsFixed(0)} dBm.',
            ),
          ],
          const SizedBox(height: 4),
          Text(detalle, style: AppTypography.labelCaption),
        ],
      ),
    );
  }
}
