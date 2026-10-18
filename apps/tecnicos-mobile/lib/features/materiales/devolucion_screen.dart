import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_typography.dart';
import '../../core/widgets/contenido_centrado.dart';
import 'estado_de_jornada.dart';
import 'widgets/confirmar_cierre.dart';
import 'widgets/motivo_de_diferencia.dart';

/// «2 unidades», «1 unidad», «35,5 m».
String cantidadConUnidad(double cantidad, String unidad) {
  final texto = MaterialDeJornada.numero(cantidad);
  if (cantidad == 1 && unidad == 'unidades') return '1 unidad';
  return '$texto $unidad';
}

/// Devolver lo que sobró y cerrar la jornada.
///
/// NINGÚN NÚMERO DE ESTA PANTALLA SE CALCULA ACÁ
/// ---------------------------------------------
/// Lo esperado, lo devuelto y las diferencias los calcula el dominio, que es
/// el mismo que después firma el acta. La pantalla los muestra y encola lo que
/// el técnico hace. Si hiciera su propia cuenta, el día que las dos difieran
/// nadie sabría cuál creer — y una de las dos estaría en un papel firmado.
///
/// Lo único que el teléfono suma por su cuenta es lo que todavía no subió,
/// para que el técnico no vea un saldo de hace dos horas.
///
/// DEVOLVER NO CORRIGE: AGREGA
/// ---------------------------
/// Una devolución es un movimiento nuevo, igual que un consumo. No edita ni
/// anula lo anterior. Por eso acá no hay ningún botón que modifique un
/// registro viejo: lo que pasó, pasó.
class DevolucionScreen extends StatefulWidget {
  const DevolucionScreen({
    super.key,
    this.baseLocal,
    this.estado,
    this.almacenamiento,
    this.sincronizar,
  });

  final LocalDatabase? baseLocal;

  /// Se inyecta en pruebas; en la aplicación se lee de la base.
  final EstadoDeJornada? estado;

  /// Quién es el dueño de estos datos. Se inyecta en pruebas.
  final SecureStorageLectura? almacenamiento;

  /// Cómo se empuja la cola al cerrar. Nulo en pruebas de dibujo.
  final Future<void> Function()? sincronizar;

  @override
  State<DevolucionScreen> createState() => _DevolucionScreenState();
}

class _DevolucionScreenState extends State<DevolucionScreen> {
  late final LocalDatabase _db = widget.baseLocal ?? LocalDatabase();
  StreamSubscription<LocalDatabaseChangeEvent>? _suscripcion;
  EstadoDeJornada? _estado;
  bool _cargando = true;
  bool _cerrando = false;
  late final SecureStorageLectura _almacenamiento =
      widget.almacenamiento ?? SecureStorageService();

  @override
  void dispose() {
    _suscripcion?.cancel();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _cargar();
    // La suscripcion se guarda para poder cancelarla en dispose.
    //
    // Sin eso queda viva despues de que la pantalla se fue: es una fuga en el
    // telefono, y en una prueba deja al arbol con un oyente pendiente que
    // impide que el test termine.
    _suscripcion = LocalDatabase.onDataChanged.listen((evento) {
      if (!mounted) return;
      if (evento.tabla == 'local_jornada' ||
          evento.tabla == 'cola_movimientos_material') {
        _cargar();
      }
    });
  }

  Future<void> _cargar() async {
    if (widget.estado != null) {
      setState(() {
        _estado = widget.estado;
        _cargando = false;
      });
      return;
    }
    final estado = await EstadoDeJornada.leer(baseLocal: _db);
    if (!mounted) return;
    setState(() {
      _estado = estado;
      _cargando = false;
    });
  }

  Future<void> _devolver(MaterialDeJornada material) async {
    final orgId = await _almacenamiento.getOrgId();
    final profileId = await _almacenamiento.getProfileId();
    if (orgId == null || profileId == null) return;

    await _db.encolarMovimientoMaterial(
      id: const Uuid().v4(),
      orgId: orgId,
      profileId: profileId,
      materialCodigo: material.codigo,
      materialNombre: material.nombre,
      tipo: 'devolucion',
      cantidad: material.porDevolver.toString(),
      serie: material.serie ?? '',
    );
    await _cargar();
  }

  Future<void> _explicar(MaterialDeJornada material) async {
    final orgId = await _almacenamiento.getOrgId();
    final profileId = await _almacenamiento.getProfileId();
    if (orgId == null || profileId == null || !mounted) return;

    final explicado = await MotivoDeDiferencia.abrir(
      context,
      orgId: orgId,
      profileId: profileId,
      material: material,
      baseLocal: _db,
    );
    if (explicado == true) await _cargar();
  }

  /// Toma el cierre de la jornada.
  ///
  /// Lo que se guarda es la INTENCION: el tecnico afirma que termino, y eso
  /// ocurre en la calle, no cuando el telefono encuentra red. El servidor es
  /// quien despues valida y congela el acta; hasta entonces la pantalla dice
  /// "pendiente de sincronizacion" y no "cerrada", porque no seria cierto.
  Future<void> _cerrarJornada() async {
    final estado = _estado;
    if (estado == null || !estado.puedeCerrar || _cerrando) return;

    final confirmado = await ConfirmarCierre.abrir(context, estado);
    if (confirmado != true || !mounted) return;

    setState(() => _cerrando = true);

    final orgId = await _almacenamiento.getOrgId();
    final profileId = await _almacenamiento.getProfileId();
    if (orgId == null || profileId == null) {
      if (mounted) setState(() => _cerrando = false);
      return;
    }

    // Una sola clave por cierre: dos toques del boton, o un reintento de la
    // cola, no pueden producir dos actas.
    await _db.marcarCierreLocal(
      orgId: orgId,
      profileId: profileId,
      clave: 'cierre-$orgId-$profileId-${DateTime.now().toIso8601String()}',
    );

    // Se intenta subir ya; si no hay senal, la cola lo lleva despues.
    try {
      await widget.sincronizar?.call();
    } catch (_) {
      // Sin red el cierre queda tomado igual: eso es lo que se le prometio.
    }

    if (!mounted) return;
    setState(() => _cerrando = false);
    await _cargar();
  }

  @override
  Widget build(BuildContext context) {
    // La pantalla trae su propio Scaffold.
    //
    // Sin un Material arriba, cada Text se dibuja con el subrayado amarillo
    // de Flutter y la pantalla entera se ve rota. No se habia notado porque
    // nadie podia llegar hasta aca: el boton que debia abrirla era un
    // Container sin accion.
    return Scaffold(
      backgroundColor: AppColors.surfaceDim,
      appBar: AppBar(title: const Text('Cierre de jornada')),
      body: ContenidoCentrado(child: _contenido(context)),
    );
  }

  Widget _contenido(BuildContext context) {
    if (_cargando) return const ColoredBox(color: AppColors.surface);

    final estado = _estado ?? const EstadoDeJornada.vacio();
    if (!estado.hayJornada) {
      return const ColoredBox(
        color: AppColors.surface,
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Text(
              'Todavía no hay una jornada que cerrar. Aparece cuando tengas '
              'material entregado y haya señal para sincronizar.',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    }

    return ColoredBox(
      color: AppColors.surface,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: <Widget>[
          _resumen(estado),
          const SizedBox(height: 16),
          Text('Material a devolver', style: AppTypography.tituloChico),
          const SizedBox(height: 8),
          for (final material in estado.materiales) _fila(material),
          if (estado.transferencias.isNotEmpty) ...<Widget>[
            const SizedBox(height: 16),
            _transferencias(estado),
          ],
          const SizedBox(height: 16),
          _cierre(estado),
        ],
      ),
    );
  }

  Widget _resumen(EstadoDeJornada estado) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLow,
          borderRadius: AppRadius.brTarjeta,
          border: Border.all(color: AppColors.outlineVariant),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Kit de hoy', style: AppTypography.tituloChico),
            const SizedBox(height: 10),
            // POR UNIDAD (18/10/2026): «Recibido 362» sumaba 42 conectores
            // con 320 metros de cable. Con un servidor viejo, que no manda
            // la separación, queda el total de antes.
            if (estado.porUnidad.isEmpty) ...<Widget>[
              _renglon('Recibido', estado.recibido),
              _renglon('Consumido', estado.consumido),
              _renglon('A devolver', estado.aDevolver),
              _renglon('Devuelto', estado.devuelto),
            ] else ...<Widget>[
              _renglon('Recibido',
                  _porUnidad(estado, (TotalPorUnidad u) => u.recibido)),
              _renglon('Consumido',
                  _porUnidad(estado, (TotalPorUnidad u) => u.consumido)),
              _renglon('A devolver',
                  _porUnidad(estado, (TotalPorUnidad u) => u.aDevolver)),
              _renglon('Devuelto',
                  _porUnidad(estado, (TotalPorUnidad u) => u.devuelto)),
            ],
            _renglon(
              'Diferencias',
              estado.diferencias.toString(),
              resaltado: estado.diferencias > 0,
            ),
            const Divider(height: 20),
            Row(
              children: <Widget>[
                Icon(
                  estado.sinSubir == 0 ? Icons.cloud_done_outlined : Icons.upload,
                  size: 16,
                  color: AppColors.onSurfaceVariant,
                ),
                const SizedBox(width: 8),
                Text(
                  estado.sinSubir == 0
                      ? 'Todo enviado'
                      : '${estado.sinSubir} pendiente(s) de sincronizar',
                  style: AppTypography.cuerpoChico.copyWith(
                    color: AppColors.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ],
        ),
      );

  /// «42 unidades · 320 m». Una unidad sola, si de esa no hay nada, no se
  /// escribe en cero: se omite. Todo en cero dice «0».
  static String _porUnidad(
      EstadoDeJornada estado, double Function(TotalPorUnidad) cuanto) {
    final partes = <String>[
      for (final u in estado.porUnidad)
        if (cuanto(u) != 0) cantidadConUnidad(cuanto(u), u.unidad),
    ];
    return partes.isEmpty ? '0' : partes.join(' · ');
  }

  Widget _renglon(String etiqueta, String valor, {bool resaltado = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(etiqueta, style: AppTypography.cuerpo),
            const SizedBox(width: 12),
            Flexible(
              child: Text(
                valor,
                textAlign: TextAlign.end,
                style: AppTypography.dato.copyWith(
                  color: resaltado ? AppColors.error : AppColors.onSurface,
                ),
              ),
            ),
          ],
        ),
      );

  Widget _fila(MaterialDeJornada material) {
    final cuadra = material.diferencia == 0;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(
          color: cuadra ? AppColors.outlineVariant : AppColors.error,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(material.nombre, style: AppTypography.cuerpoGrande),
          // Un equipo con número nunca se muestra solo como cantidad: lo que
          // hay que ubicar es ESE aparato, no "una unidad".
          if (material.serie != null)
            Text('Serie ${material.serie}',
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                )),
          const SizedBox(height: 6),
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Esperado ${material.esperado} · Devuelto ${material.devuelto}',
                  style: AppTypography.cuerpoChico,
                ),
              ),
              if (cuadra)
                Row(children: <Widget>[
                  const Icon(Icons.check_circle, size: 16, color: AppColors.exito),
                  const SizedBox(width: 4),
                  Text('Correcto',
                      style: AppTypography.cuerpoChico
                          .copyWith(color: AppColors.exito)),
                ])
              else
                Row(children: <Widget>[
                  const Icon(Icons.warning_amber_rounded,
                      size: 16, color: AppColors.error),
                  const SizedBox(width: 4),
                  Text('Diferencia',
                      style: AppTypography.cuerpoChico
                          .copyWith(color: AppColors.error)),
                ]),
            ],
          ),
          ..._dondeVaLoDevuelto(material),
          if (material.porDevolver > 0) ...<Widget>[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              height: 40,
              child: OutlinedButton(
                onPressed: () => _devolver(material),
                // Antes decía «Devolver 2.0 unidades».
                child: Text('Devolver ${cantidadConUnidad(
                    material.porDevolver, material.unidad)}'),
              ),
            ),
            const SizedBox(height: 6),
            // Lo que no vuelve tiene que poder explicarse. Sin este camino, la
            // unica salida de una diferencia seria devolver material que no se
            // tiene, y eso es justamente lo que hace que un inventario mienta.
            SizedBox(
              width: double.infinity,
              height: 40,
              child: TextButton(
                onPressed: () => _explicar(material),
                child: const Text('No lo tengo: explicar por qué'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Lo devuelto, en sus tres momentos: anotado en el teléfono, enviado al
  /// servidor, recibido por bodega. Solo aparece lo que tiene cantidad.
  List<Widget> _dondeVaLoDevuelto(MaterialDeJornada material) {
    String de(double cuanto) => cantidadConUnidad(cuanto, material.unidad);
    final momentos = <Widget>[
      if (material.anotado > 0)
        _momento(Icons.schedule, '${de(material.anotado)} sin enviar',
            AppColors.onSurfaceVariant),
      // Sin el dato de bodega (servidor viejo) se dice solo que se envió:
      // no se puede afirmar ni que llegó ni que falta.
      if (material.recibidoEnBodega == null && material.enviado > 0)
        _momento(Icons.cloud_done_outlined, '${de(material.enviado)} enviado',
            AppColors.onSurfaceVariant),
      if (material.enviadoSinRecibir > 0)
        _momento(
            Icons.local_shipping_outlined,
            '${de(material.enviadoSinRecibir)} enviado · falta que bodega '
            'lo reciba',
            AppColors.onSurfaceVariant),
      if ((material.recibidoEnBodega ?? 0) > 0)
        _momento(Icons.inventory_2_outlined,
            '${de(material.recibidoEnBodega!)} recibido por bodega',
            AppColors.exito),
    ];
    if (momentos.isEmpty) return const <Widget>[];
    return <Widget>[const SizedBox(height: 6), ...momentos];
  }

  /// Un renglón chico con su ícono. No es una pastilla a propósito: la
  /// pastilla corta en una línea, y «falta que bodega lo reciba» quedaba en
  /// puntos suspensivos en un teléfono.
  Widget _momento(IconData icono, String texto, Color color) => Padding(
        padding: const EdgeInsets.only(top: 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(icono, size: 16, color: color),
            const SizedBox(width: 6),
            Expanded(
              child: Text(texto,
                  style: AppTypography.cuerpoChico.copyWith(color: color)),
            ),
          ],
        ),
      );

  Widget _transferencias(EstadoDeJornada estado) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainer,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Entregado a otro técnico', style: AppTypography.etiquetaGrande),
            const SizedBox(height: 4),
            // Explica un saldo que no baja: hasta que el otro acepte, el
            // material sigue siendo de quien lo entregó.
            Text(
              'Sigue contando como tuyo hasta que lo acepten.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            for (final t in estado.transferencias)
              Text('· ${t.material} x${t.cantidad} → ${t.recibe} '
                  '(pendiente de aceptación)',
                  style: AppTypography.cuerpoChico),
          ],
        ),
      );

  Widget _cierre(EstadoDeJornada estado) {
    // Tomado en el telefono pero todavia sin confirmar del servidor. Se dice
    // exactamente eso: afirmar "cerrada" seria afirmar algo que no paso.
    if (estado.cierreTomado && !estado.cerrada) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainer,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Row(children: <Widget>[
          const Icon(Icons.schedule, color: AppColors.onSurfaceVariant),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Cierre pendiente de sincronización. Tu jornada quedó cerrada '
              'en el teléfono; termina de registrarse cuando haya señal.',
              style: AppTypography.cuerpo,
            ),
          ),
        ]),
      );
    }

    if (estado.cerrada) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.exitoFondo,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Row(children: <Widget>[
          const Icon(Icons.check_circle, color: AppColors.exitoFuerte),
          const SizedBox(width: 10),
          Expanded(
            child: Text('Jornada cerrada. El acta quedó firmada con estos '
                'números.',
                style: AppTypography.cuerpo
                    .copyWith(color: AppColors.exitoTexto)),
          ),
        ]),
      );
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(color: AppColors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Cerrar la jornada', style: AppTypography.tituloChico),
          const SizedBox(height: 8),
          if (estado.motivos.isEmpty)
            Text(
              'Todo cuadra. Podés cerrar cuando entregues el material en '
              'bodega.',
              style: AppTypography.cuerpoChico,
            )
          else ...<Widget>[
            // Lo que falta, en frases. Un código de error no le dice a nadie
            // qué tiene que hacer para poder irse a su casa.
            Text('Falta resolver esto:', style: AppTypography.cuerpoChico),
            const SizedBox(height: 6),
            for (final motivo in estado.motivos)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(Icons.error_outline,
                        size: 16, color: AppColors.error),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(motivo,
                          style: AppTypography.cuerpoChico
                              .copyWith(color: AppColors.error)),
                    ),
                  ],
                ),
              ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton(
              // La señal NO entra en esta decisión: lo que bloquea es que la
              // jornada se contradiga, no que el teléfono no tenga red.
              onPressed:
                  estado.puedeCerrar && !_cerrando ? _cerrarJornada : null,
              child: _cerrando
                  ? const SizedBox(
                      width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Cerrar jornada'),
            ),
          ),
          if (estado.sinSubir > 0)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Hay ${estado.sinSubir} registro(s) que todavía no subieron. '
                'Suben solos; no hace falta esperar.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
