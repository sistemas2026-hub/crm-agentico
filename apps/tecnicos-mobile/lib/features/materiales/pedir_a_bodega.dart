/// Pedirle material a bodega desde la calle.
///
/// EL PROBLEMA
/// -----------
/// El técnico se queda sin conectores en la tercera instalación y la aplicación
/// no tiene nada que ofrecerle: saca el otro teléfono y escribe al grupo. La
/// pantalla de Materiales le dice lo que tiene, y ahí se corta.
///
/// POR QUÉ UN PEDIDO NO ES UN MOVIMIENTO
/// --------------------------------------
/// Está escrito en el modelo del servidor y ordena todo el inventario: «un
/// movimiento de material ES UN HECHO QUE YA OCURRIÓ en la calle, no una
/// solicitud que el servidor pueda aprobar». Un pedido es lo contrario —todavía
/// no pasó nada, alguien lo tiene que atender, y puede decir que no—. Por eso
/// tiene su propia cola (`cola_pedidos_material`) y no la de movimientos:
/// compartirla le pediría al saldo contar material que nadie entregó.
///
/// SE PIDE SIN SEÑAL
/// -----------------
/// Que es el único momento en que hace falta: el técnico está en el sótano de
/// un edificio. Se encola y sube cuando haya red, con el `id` de la fila como
/// clave de idempotencia — un reenvío es el mismo pedido, no uno nuevo.
///
/// LO QUE NO RESUELVE, Y HAY QUE DECIRLO
/// --------------------------------------
/// Sólo se puede pedir material **que ya está en el kit** (incluso con saldo
/// cero). Pedir algo que nunca tuvo exigiría bajar el catálogo completo de la
/// empresa, que la aplicación hoy no baja. Es un límite declarado, no un olvido.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:uuid/uuid.dart';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/theme/app_theme.dart';
import 'material_en_custodia.dart';


/// Un pedido tal como se ve en la pantalla.
class PedidoEnCola {
  const PedidoEnCola({
    required this.id,
    required this.material,
    required this.cantidad,
    required this.estado,
    this.motivo = '',
    this.errorMensaje = '',
  });

  final String id;
  final String material;
  final String cantidad;

  /// `pendiente`, `enviado` o `fallido`.
  final String estado;
  final String motivo;
  final String errorMensaje;

  /// Qué decirle al técnico sobre este pedido.
  ///
  /// Las tres frases son distintas porque las tres situaciones son distintas, y
  /// una sola («pedido») dejaría a un pedido fallado pareciendo que está en
  /// camino. Eso es peor que no haber pedido: el técnico lo espera.
  String get comoVa => switch (estado) {
        'pendiente' => 'Sube cuando haya señal',
        'enviado' => 'Bodega ya lo recibió',
        'fallido' => 'No se pudo pedir',
        _ => '',
      };

  bool get esProblema => estado == 'fallido';

  static PedidoEnCola desdeLaFila(Map<String, Object?> fila) => PedidoEnCola(
        id: (fila['id'] ?? '').toString(),
        material: (fila['material_nombre'] ?? '').toString(),
        cantidad: (fila['cantidad'] ?? '').toString(),
        estado: (fila['estado'] ?? 'pendiente').toString(),
        motivo: (fila['motivo'] ?? '').toString(),
        errorMensaje: (fila['error_mensaje'] ?? '').toString(),
      );
}

/// Las reglas del pedido, sin pantalla.
///
/// Están acá y no en el widget para poder medirlas: la validación es lo que
/// decide si un pedido se manda, y una regla que sólo se puede probar
/// construyendo un árbol de Flutter termina sin probarse.
class ReglasDelPedido {
  const ReglasDelPedido._();

  /// Qué está mal con esta cantidad, o `null` si está bien.
  ///
  /// Se acepta coma decimal: en Colombia es la que se escribe, y «2,5» es lo
  /// que un técnico teclea para dos metros y medio de bobina. Rechazarlo sería
  /// rechazar la forma correcta de escribirlo.
  static String? queLeFaltaALaCantidad(String crudo) {
    final String texto = crudo.trim();
    if (texto.isEmpty) return 'Decí cuánto necesitás.';
    final double? valor = double.tryParse(texto.replaceAll(',', '.'));
    if (valor == null) return 'Eso no es un número.';
    if (valor <= 0) return 'Tiene que ser más que cero.';
    return null;
  }

  /// La cantidad como viaja al servidor: con punto decimal y sin ceros de
  /// relleno. «2,5» sale «2.5»; «20» sale «20», no «20.0».
  static String cantidadParaElServidor(String crudo) {
    final String texto = crudo.trim().replaceAll(',', '.');
    if (!texto.contains('.')) return texto;
    final String recortado = texto.replaceAll(RegExp(r'0+$'), '');
    return recortado.endsWith('.')
        ? recortado.substring(0, recortado.length - 1)
        : recortado;
  }
}

/// Encola un pedido. Devuelve `false` si no se pudo ni guardar.
///
/// Se guarda ANTES de intentar subirlo, como todo lo demás: un pedido que se
/// escribió y no subió se reintenta solo; uno que se intentó subir y no se
/// guardó se perdió sin que nadie se enterara.
Future<bool> encolarPedidoDeMaterial({
  required MaterialEnCustodia material,
  required String cantidad,
  String motivo = '',
  String? ordenId,
  LocalDatabase? baseLocal,
  SecureStorageLectura? almacenamiento,
  String? idFijo,
}) async {
  if (material.codigo.isEmpty) return false;
  if (ReglasDelPedido.queLeFaltaALaCantidad(cantidad) != null) return false;

  final LocalDatabase db = baseLocal ?? LocalDatabase();
  final SecureStorageLectura storage = almacenamiento ?? SecureStorageService();

  String? orgId;
  String? profileId;
  try {
    orgId = await storage.getOrgId();
    profileId = await storage.getProfileId();
  } catch (_) {
    return false;
  }
  if (orgId == null || orgId.isEmpty || profileId == null || profileId.isEmpty) {
    return false;
  }

  try {
    await db.encolarPedidoDeMaterial(
      orgId: orgId,
      profileId: profileId,
      id: idFijo ?? const Uuid().v4(),
      materialId: material.codigo,
      materialNombre: material.nombre,
      cantidad: ReglasDelPedido.cantidadParaElServidor(cantidad),
      motivo: motivo.trim(),
      ordenId: ordenId,
    );
    return true;
  } catch (_) {
    return false;
  }
}

/// Los pedidos de esta persona, lo más nuevo primero.
Future<List<PedidoEnCola>> leerPedidosDeMaterial({
  LocalDatabase? baseLocal,
  SecureStorageLectura? almacenamiento,
}) async {
  final LocalDatabase db = baseLocal ?? LocalDatabase();
  final SecureStorageLectura storage = almacenamiento ?? SecureStorageService();
  try {
    final String? orgId = await storage.getOrgId();
    final String? profileId = await storage.getProfileId();
    if (orgId == null || orgId.isEmpty) return const <PedidoEnCola>[];
    if (profileId == null || profileId.isEmpty) return const <PedidoEnCola>[];
    final List<Map<String, dynamic>> filas = await db.leerPedidosDeMaterial(
      orgId: orgId,
      profileId: profileId,
    );
    return <PedidoEnCola>[
      for (final Map<String, dynamic> f in filas) PedidoEnCola.desdeLaFila(f),
    ];
  } catch (_) {
    // Sin identidad o sin base no hay pedidos que mostrar. Vacío y no una
    // excepción: una pantalla que no puede leer tiene que decir que no hay
    // nada, no quedarse girando.
    return const <PedidoEnCola>[];
  }
}

/// La hoja para pedir: qué material, cuánto, y por qué.
///
/// EN UNA HOJA Y NO EN UNA PANTALLA porque se pide en medio de otra cosa —con
/// el cliente esperando— y volver atrás no puede costar perder dónde estaba.
class HojaDePedido extends StatefulWidget {
  const HojaDePedido({
    super.key,
    required this.materiales,
    this.preseleccionado,
    this.ordenId,
    this.alPedir,
  });

  final List<MaterialEnCustodia> materiales;

  /// El material desde el que se abrió la hoja, si se abrió desde su tarjeta.
  final MaterialEnCustodia? preseleccionado;

  /// Para qué orden es, si es por una en particular.
  final String? ordenId;

  /// Se inyecta en las pruebas. En la aplicación encola de verdad.
  final Future<bool> Function({
    required MaterialEnCustodia material,
    required String cantidad,
    String motivo,
    String? ordenId,
  })? alPedir;

  @override
  State<HojaDePedido> createState() => _HojaDePedidoState();
}

class _HojaDePedidoState extends State<HojaDePedido> {
  late MaterialEnCustodia? _elegido;
  final TextEditingController _cantidad = TextEditingController();
  final TextEditingController _motivo = TextEditingController();
  String? _problema;
  bool _mandando = false;

  @override
  void initState() {
    super.initState();
    _elegido = widget.preseleccionado ??
        (widget.materiales.isEmpty ? null : widget.materiales.first);
  }

  @override
  void dispose() {
    _cantidad.dispose();
    _motivo.dispose();
    super.dispose();
  }

  Future<void> _pedir() async {
    final MaterialEnCustodia? material = _elegido;
    if (material == null) return;
    final String? falta =
        ReglasDelPedido.queLeFaltaALaCantidad(_cantidad.text);
    if (falta != null) {
      setState(() => _problema = falta);
      return;
    }

    setState(() {
      _problema = null;
      _mandando = true;
    });

    final bool quedo = widget.alPedir != null
        ? await widget.alPedir!(
            material: material,
            cantidad: _cantidad.text,
            motivo: _motivo.text,
            ordenId: widget.ordenId,
          )
        : await encolarPedidoDeMaterial(
            material: material,
            cantidad: _cantidad.text,
            motivo: _motivo.text,
            ordenId: widget.ordenId,
          );

    if (!mounted) return;
    if (!quedo) {
      // NO se cierra la hoja. Cerrarla diciendo «listo» cuando nada se guardó
      // es la peor salida posible: el técnico sigue su día creyendo que el
      // material viene.
      setState(() {
        _mandando = false;
        _problema = 'No se pudo guardar el pedido. Volvé a intentar.';
      });
      return;
    }
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.md,
        right: AppSpacing.md,
        top: AppSpacing.md,
        bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.md,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.local_shipping, color: AppColors.primary),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Pedir a bodega',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          const Text(
            'Queda guardado y sube cuando haya señal.',
            style: TextStyle(fontSize: 12, color: AppColors.textoSecundario),
          ),
          const SizedBox(height: AppSpacing.md),
          if (widget.materiales.isEmpty)
            const Text(
              'Todavía no hay kit cargado, así que no hay de qué pedir.',
              style: TextStyle(color: AppColors.textoSecundario),
            )
          else
            DropdownButtonFormField<MaterialEnCustodia>(
              initialValue: _elegido,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Material',
                border: OutlineInputBorder(),
              ),
              items: <DropdownMenuItem<MaterialEnCustodia>>[
                for (final MaterialEnCustodia m in widget.materiales)
                  DropdownMenuItem<MaterialEnCustodia>(
                    value: m,
                    child: Text(
                      // El saldo va en la misma línea: lo primero que uno
                      // quiere saber al pedir es cuánto le queda.
                      '${m.nombre} · quedan ${m.disponibles} ${m.unidad}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (MaterialEnCustodia? m) =>
                  setState(() => _elegido = m),
            ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            controller: _cantidad,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: <TextInputFormatter>[
              FilteringTextInputFormatter.allow(RegExp(r'[0-9,.]')),
            ],
            decoration: InputDecoration(
              labelText: 'Cuánto necesitás',
              border: const OutlineInputBorder(),
              errorText: _problema,
              suffixText: _elegido?.unidad,
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            controller: _motivo,
            maxLength: 120,
            decoration: const InputDecoration(
              // Opcional, y dicho: parado en una escalera, escribir un motivo
              // es lo primero que se saltea. Exigirlo haría que el pedido no se
              // haga, que es el único resultado malo acá.
              labelText: 'Para qué (opcional)',
              border: OutlineInputBorder(),
              counterText: '',
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          FilledButton.icon(
            onPressed: _mandando || widget.materiales.isEmpty ? null : _pedir,
            icon: _mandando
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.send),
            label: Text(_mandando ? 'Guardando…' : 'Pedir'),
          ),
        ],
      ),
    );
  }
}

/// Abre la hoja. Devuelve `true` si el pedido quedó encolado.
Future<bool> abrirHojaDePedido(
  BuildContext context, {
  required List<MaterialEnCustodia> materiales,
  MaterialEnCustodia? preseleccionado,
  String? ordenId,
}) async {
  final bool? quedo = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (BuildContext c) => HojaDePedido(
      materiales: materiales,
      preseleccionado: preseleccionado,
      ordenId: ordenId,
    ),
  );
  return quedo ?? false;
}
