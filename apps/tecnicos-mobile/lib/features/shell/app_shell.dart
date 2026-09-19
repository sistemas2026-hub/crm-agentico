import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_app_header.dart';
import '../../core/widgets/dexter_bottom_nav.dart';
import '../../core/widgets/dexter_sync_strip.dart';
import '../auth/login_screen.dart';
import '../detalle_orden/acciones_orden.dart';
import '../detalle_orden/detalle_orden_screen.dart';
import '../inicio/inicio_screen.dart';
import '../trabajo/seleccion_jornada.dart';
import '../trabajo/trabajo_screen.dart';
import '../trabajo/trabajo_vista.dart';
import 'seccion_en_construccion.dart';

/// Quién está usando la aplicación, tal como se muestra en el encabezado.
class IdentidadTecnico {
  const IdentidadTecnico({required this.nombre, required this.empresa});

  final String nombre;
  final String empresa;

  /// Hasta dos letras para el círculo del perfil.
  String get iniciales {
    final partes = nombre
        .trim()
        .split(RegExp(r'\s+'))
        .where((String p) => p.isNotEmpty)
        .toList();
    if (partes.isEmpty) return '';
    if (partes.length == 1) return partes.first.substring(0, 1).toUpperCase();
    return (partes.first.substring(0, 1) + partes[1].substring(0, 1)).toUpperCase();
  }
}

/// De dónde saca el contenedor lo que muestra.
///
/// Está separado para poder montarlo en una prueba sin base de datos, sin
/// almacenamiento seguro y sin radio: cada cosa entra por acá.
class ShellDependencias {
  const ShellDependencias({
    required this.resumenes,
    required this.resumenInicial,
    required this.sincronizarAhora,
    required this.cargarIdentidad,
    required this.ordenes,
    required this.abrirTrabajo,
    this.conectividad,
    this.cerrarSesion,
  });

  /// El estado de la cola, ya calculado por el servicio real.
  final Stream<SyncSummary> resumenes;
  final SyncSummary? resumenInicial;
  final Future<void> Function() sincronizarAhora;
  final Future<IdentidadTecnico> Function() cargarIdentidad;

  /// Las órdenes de la jornada, compartidas por Inicio y Trabajo. El
  /// contenedor las crea y las cierra; no las interpreta.
  final OrdenesJornada ordenes;

  /// Qué pasa al abrir un trabajo desde cualquiera de las dos pantallas.
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo) abrirTrabajo;

  /// `true` si el teléfono tiene alguna red. Nulo si no se puede saber.
  final Stream<bool>? conectividad;

  final Future<void> Function()? cerrarSesion;

  /// Cableado real: la cola, la sesión y la radio del teléfono.
  factory ShellDependencias.reales() {
    final sincronizacion = SyncQueueService();
    final almacenamiento = SecureStorageService();
    final ordenes = OrdenesJornada.real();
    final acciones = AccionesOrden.reales();

    return ShellDependencias(
      resumenes: sincronizacion.syncSummaryStream,
      resumenInicial: sincronizacion.lastSummary,
      sincronizarAhora: sincronizacion.procesarCola,
      conectividad: _conectividadDelTelefono(),
      cargarIdentidad: () async => IdentidadTecnico(
        nombre: await almacenamiento.getUserName() ?? FieldMockData.tecnicoPorDefecto,
        empresa: await almacenamiento.getOrgName() ?? FieldMockData.empresaPorDefecto,
      ),
      ordenes: ordenes,
      abrirTrabajo: (BuildContext contexto, TrabajoVista trabajo) async {
        await Navigator.of(contexto).push(
          MaterialPageRoute<void>(
            builder: (_) => DetalleOrdenScreen(
              ordenId: trabajo.id,
              ordenes: ordenes,
              acciones: acciones,
              resumenes: sincronizacion.syncSummaryStream,
              resumenInicial: sincronizacion.lastSummary,
            ),
          ),
        );
      },
      cerrarSesion: almacenamiento.clearSession,
    );
  }

  /// Si hay alguna interfaz de red levantada.
  ///
  /// Es una señal real, no un valor de ejemplo, pero dice menos de lo que
  /// parece: que el teléfono tenga wifi no prueba que el servidor conteste.
  /// Por eso el encabezado la combina con el resultado del último envío.
  static Stream<bool> _conectividadDelTelefono() async* {
    final radio = Connectivity();
    try {
      yield _hayRed(await radio.checkConnectivity());
    } catch (_) {
      // Sin respuesta del sistema: se deja en desconocido y sigue el flujo.
    }
    yield* radio.onConnectivityChanged.map(_hayRed);
  }

  static bool _hayRed(List<ConnectivityResult> resultados) =>
      resultados.any((ConnectivityResult r) => r != ConnectivityResult.none);
}

/// Contenedor de la aplicación una vez que hay sesión.
///
/// Es un contenedor y nada más: sostiene el encabezado, la franja de
/// sincronización, la sección visible y la barra inferior. Centraliza dos
/// cosas, y solo dos: **el estado de la sincronización** y **las órdenes de la
/// jornada**, para que existan una sola suscripción y una sola carga en vez de
/// una por pantalla. No las interpreta: eso lo hacen Inicio y Trabajo.
class AppShell extends StatefulWidget {
  AppShell({super.key, ShellDependencias? dependencias, this.seccionInicial = SeccionCampo.trabajo})
      : dependencias = dependencias ?? ShellDependencias.reales();

  final ShellDependencias dependencias;
  final SeccionCampo seccionInicial;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  StreamSubscription<SyncSummary>? _suscripcionResumen;
  StreamSubscription<bool>? _suscripcionConexion;

  late SeccionCampo _seccion = widget.seccionInicial;

  /// Las secciones que el técnico ya abrió alguna vez. Una sección se
  /// construye la primera vez que se la visita —así abrir la aplicación no
  /// dispara la carga de las cinco— y desde ahí queda viva, con su scroll y
  /// sus filtros.
  late final Set<SeccionCampo> _visitadas = <SeccionCampo>{widget.seccionInicial};

  SyncSummary? _resumen;
  bool? _hayRed;
  IdentidadTecnico? _identidad;

  /// Cuántos trabajos le siguen tocando al técnico, para el número de la barra
  /// inferior. Se recalcula cuando cambian las órdenes compartidas; el cálculo
  /// es el mismo que usan las dos pantallas.
  int _trabajosActivos = 0;

  @override
  void initState() {
    super.initState();
    _resumen = widget.dependencias.resumenInicial;

    _suscripcionResumen = widget.dependencias.resumenes.listen(
      (SyncSummary resumen) {
        if (mounted) setState(() => _resumen = resumen);
      },
      // Un problema leyendo la cola no puede tumbar la aplicación entera: el
      // técnico tiene que poder seguir trabajando.
      onError: (Object _) {},
    );

    final Stream<bool>? conectividad = widget.dependencias.conectividad;
    if (conectividad != null) {
      _suscripcionConexion = conectividad.listen(
        (bool hayRed) {
          if (mounted) setState(() => _hayRed = hayRed);
        },
        onError: (Object _) {
          if (mounted) setState(() => _hayRed = null);
        },
      );
    }

    widget.dependencias.ordenes.addListener(_alCambiarOrdenes);
    _cargarIdentidad();
  }

  void _alCambiarOrdenes() {
    if (!mounted) return;
    setState(() {
      _trabajosActivos =
          SeleccionJornada.activos(widget.dependencias.ordenes.trabajos).length;
    });
  }

  Future<void> _cargarIdentidad() async {
    final identidad = await widget.dependencias.cargarIdentidad();
    if (mounted) setState(() => _identidad = identidad);
  }

  @override
  void dispose() {
    _suscripcionResumen?.cancel();
    _suscripcionConexion?.cancel();
    widget.dependencias.ordenes.removeListener(_alCambiarOrdenes);
    super.dispose();
  }

  /// Lo máximo que se puede afirmar hoy sobre el enlace.
  ///
  /// No dice "en línea" con solo tener wifi: eso no prueba que el servidor
  /// conteste, y el técnico decide si espera o sigue sin conexión mirando
  /// esto. "En línea" queda para cuando exista una comprobación real contra
  /// el backend.
  EstadoConexion get _estadoConexion {
    if (_hayRed == false) return EstadoConexion.sinRed;
    if (_resumen?.hasConnectionError ?? false) return EstadoConexion.sinServidor;
    if (_hayRed == true) return EstadoConexion.conRed;
    return EstadoConexion.desconocido;
  }

  Future<void> _abrirPerfil() async {
    final salir = await showModalBottomSheet<bool>(
      context: context,
      builder: (BuildContext hoja) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            ListTile(
              leading: const Icon(Icons.person_outline),
              title: Text(_identidad?.nombre ?? FieldMockData.tecnicoPorDefecto),
              subtitle: Text(_identidad?.empresa ?? FieldMockData.empresaPorDefecto),
            ),
            const Divider(),
            ListTile(
              leading: const Icon(Icons.logout, color: AppColors.error),
              title: Text(
                'Cerrar sesión',
                style: AppTypography.cuerpoGrande.copyWith(color: AppColors.error),
              ),
              onTap: () => Navigator.of(hoja).pop(true),
            ),
          ],
        ),
      ),
    );

    if (salir != true || !mounted) return;

    await widget.dependencias.cerrarSesion?.call();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const LoginScreen()),
    );
  }

  /// Qué se muestra en cada sección. Se llama solo para las ya visitadas.
  Widget _contenidoDe(SeccionCampo seccion) => switch (seccion) {
        SeccionCampo.inicio => InicioScreen(
            ordenes: widget.dependencias.ordenes,
            abrirTrabajo: widget.dependencias.abrirTrabajo,
            nombreTecnico: _identidad?.nombre ?? FieldMockData.tecnicoPorDefecto,
            resumenSincronizacion: _resumen,
            onVerTodos: () => setState(() {
              _seccion = SeccionCampo.trabajo;
              _visitadas.add(SeccionCampo.trabajo);
            }),
          ),
        SeccionCampo.trabajo => TrabajoScreen(
            ordenes: widget.dependencias.ordenes,
            abrirTrabajo: widget.dependencias.abrirTrabajo,
          ),
        SeccionCampo.materiales => const SeccionEnConstruccion(
            titulo: 'Mi kit y custodia',
            descripcion: 'Acá vas a ver el material que tenés a cargo, lo que '
                'consumiste y el cierre de la jornada.',
            icono: Icons.inventory_2_outlined,
          ),
        SeccionCampo.academia => const SeccionEnConstruccion(
            titulo: 'Academia',
            descripcion: 'Acá van a estar las guías y los videos cortos para '
                'resolver en sitio.',
            icono: Icons.school_outlined,
          ),
        SeccionCampo.mas => const SeccionEnConstruccion(
            titulo: 'Más',
            descripcion:
                'Ajustes, ayuda y todo lo que no entra en las otras secciones.',
            icono: Icons.grid_view_outlined,
          ),
      };

  @override
  Widget build(BuildContext context) {
    final estadoSync = SyncPresentacion.estado(_resumen);

    return Scaffold(
      body: Column(
        children: <Widget>[
          DexterAppHeader(
            empresa: _identidad?.empresa ?? FieldMockData.empresaPorDefecto,
            iniciales: _identidad?.iniciales,
            conexion: _estadoConexion,
            // Dato de ejemplo: todavía no hay notificaciones de verdad.
            notificacionesSinLeer: FieldMockData.notificacionesSinLeer,
            onPerfil: _abrirPerfil,
          ),
          DexterSyncStrip(
            estado: estadoSync,
            frase: SyncPresentacion.fraseFranja(_resumen),
            onSincronizar: SyncPresentacion.puedeSincronizarAhora(_resumen)
                ? widget.dependencias.sincronizarAhora
                : null,
          ),
          Expanded(
            // IndexedStack mantiene viva cada sección ya abierta: volver a
            // Trabajo conserva el scroll, los filtros y lo cargado. Las que
            // nunca se visitaron ni siquiera se construyen.
            child: IndexedStack(
              index: SeccionCampo.values.indexOf(_seccion),
              children: <Widget>[
                for (final SeccionCampo seccion in SeccionCampo.values)
                  _visitadas.contains(seccion)
                      ? _contenidoDe(seccion)
                      : const SizedBox.shrink(),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: DexterBottomNav(
        seleccionada: _seccion,
        indicadores: <SeccionCampo, int>{
          if (_trabajosActivos > 0) SeccionCampo.trabajo: _trabajosActivos,
        },
        onSeleccion: (SeccionCampo seccion) => setState(() {
          _seccion = seccion;
          _visitadas.add(seccion);
        }),
      ),
    );
  }
}
