/// ACTIVAR LA ONU EN LA RED, DESDE EL PASO DE LA INSTALACIÓN (26/11/2026).
///
/// El usuario: «en el paso 3, instalación, cuando se ponga el serial, cómo se
/// hace para que se active la ONU en SmartOLT enseguida». Decidió: un botón
/// después del serial; la VLAN sale del servidor del contrato; la zona la
/// sugiere el barrio y el técnico la confirma.
///
/// QUÉ SERIAL. El paso tiene dos campos que se leen con la cámara (el serial y
/// el precinto) y la app no los distingue por el nombre. Busca con cada valor
/// escrito, en orden, hasta que la red reconozca uno: son lecturas, no cuesta
/// nada y no adivina.
///
/// Lo peligroso pasa en el servidor y en el motor: solo se autoriza la ONU que
/// la red muestra ESPERANDO, una sola vez, y se confirma leyéndola. Acá se
/// pide, se espera y se dice cómo quedó. Necesita señal.
library;

import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/api_endpoints.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/dexter_bloques.dart';

/// Lo que contestó el servidor. Reemplazable en pruebas.
class ApiDeLaOnu {
  const ApiDeLaOnu();

  static Map<String, dynamic> _cuerpo(dynamic d) =>
      Map<String, dynamic>.from((d is String ? jsonDecode(d) : d) as Map);

  static String _mensaje(Object e) {
    if (e is DioException) {
      final dynamic d = e.response?.data;
      if (d is Map && d['detail'] is String) return d['detail'] as String;
      if (e.response == null) return 'Sin señal. Intenta de nuevo cuando tengas señal.';
      return 'El servidor no respondió bien (${e.response?.statusCode}).';
    }
    return 'Sin señal. Intenta de nuevo cuando tengas señal.';
  }

  /// `{encendido, ultima, onu, error?}` o `{error}`.
  Future<Map<String, dynamic>> estado(String ordenId, {String? serial}) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .get<dynamic>(ApiEndpoints.onuDeLaOrden(ordenId, serial: serial))
          .timeout(const Duration(seconds: 70));
      return _cuerpo(r.data);
    } catch (e) {
      return <String, dynamic>{'error': _mensaje(e)};
    }
  }

  /// `{activacion}` o `{error}`.
  Future<Map<String, dynamic>> activar(String ordenId, String serial, String zona) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .post<dynamic>(ApiEndpoints.activarOnuDeLaOrden(ordenId),
              data: <String, dynamic>{'serial': serial, 'zona': zona})
          .timeout(const Duration(seconds: 30));
      return _cuerpo(r.data);
    } catch (e) {
      return <String, dynamic>{'error': _mensaje(e)};
    }
  }
}

class ActivarOnu extends StatefulWidget {
  const ActivarOnu({
    super.key,
    required this.ordenId,
    required this.seriales,
    this.api = const ApiDeLaOnu(),
    this.cadaCuanto = const Duration(seconds: 5),
    this.vueltas = 40,
    this.esperaEntreBusquedas = const Duration(seconds: 8),
    this.busquedas = 8,
  });

  final String ordenId;

  /// Lo escrito en los campos del paso que se leen con la cámara, en orden.
  final List<String> seriales;
  final ApiDeLaOnu api;

  /// Cada cuánto se pregunta cómo va un pedido, y hasta cuántas veces.
  final Duration cadaCuanto;
  final int vueltas;

  /// LA ONU RECIÉN CONECTADA (26/11/2026). En la primera prueba real la red
  /// no la tenía a las 3:38 p. m. y sí 23 segundos después: el técnico tuvo
  /// que volver a tocar. Si no aparece, se vuelve a buscar sola, cada
  /// [esperaEntreBusquedas], hasta [busquedas] veces (~1 minuto).
  final Duration esperaEntreBusquedas;
  final int busquedas;

  @override
  State<ActivarOnu> createState() => _EstadoActivarOnu();
}

class _EstadoActivarOnu extends State<ActivarOnu> {
  bool _ocupado = false;
  String? _error;
  bool _encendido = true;
  Map<String, dynamic>? _onu;
  String _serial = '';
  String? _zona;
  Map<String, dynamic>? _ultima;
  Timer? _reloj;
  int _vuelta = 0;
  //  En qué búsqueda va (1 = la primera); para decir «sigo buscando».
  int _busqueda = 0;

  @override
  void initState() {
    super.initState();
    _leerUltima();
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }

  Future<void> _leerUltima() async {
    final Map<String, dynamic> d = await widget.api.estado(widget.ordenId);
    if (!mounted || d.containsKey('error')) return;
    setState(() {
      _encendido = d['encendido'] != false;
      _ultima = d['ultima'] is Map ? Map<String, dynamic>.from(d['ultima'] as Map) : null;
    });
    if (_ultima?['en_vuelo'] == true) _seguir();
  }

  Future<void> _buscar() async {
    final List<String> candidatos =
        widget.seriales.map((String s) => s.trim()).where((String s) => s.isNotEmpty).toList();
    if (candidatos.isEmpty) {
      setState(() => _error = 'Primero escribe o escanea el serial de la ONU.');
      return;
    }
    setState(() {
      _ocupado = true;
      _error = null;
      _onu = null;
      _busqueda = 1;
    });
    Map<String, dynamic>? primera;
    for (int vez = 1; vez <= widget.busquedas; vez++) {
      if (vez > 1) {
        //  No apareció: la red puede tardar unos segundos en verla.
        setState(() => _busqueda = vez);
        await Future<void>.delayed(widget.esperaEntreBusquedas);
        if (!mounted) return;
      }
      primera = null;
      for (final String s in candidatos) {
        final Map<String, dynamic> d = await widget.api.estado(widget.ordenId, serial: s);
        if (!mounted) return;
        if (d['onu'] is! Map) {
          //  Un error que no es de este serial (sin contrato, sin señal) se
          //  dice y se para: con el otro valor, o esperando, pasaría lo mismo.
          setState(() {
            _ocupado = false;
            _busqueda = 0;
            _error = (d['error'] ?? 'No se pudo buscar la ONU.').toString();
            _encendido = d['encendido'] != false;
          });
          return;
        }
        final Map<String, dynamic> onu = Map<String, dynamic>.from(d['onu'] as Map);
        primera ??= <String, dynamic>{...onu, 'serial': s};
        _encendido = d['encendido'] != false;
        if (onu['estado'] == 'esperando' || onu['estado'] == 'ya_estaba') {
          primera = <String, dynamic>{...onu, 'serial': s};
          break;
        }
      }
      //  Solo «no espera» se vuelve a buscar: lo demás ya es una respuesta.
      if (primera?['estado'] != 'no_espera') break;
    }
    setState(() {
      _ocupado = false;
      _busqueda = 0;
      _onu = primera;
      _serial = (primera?['serial'] ?? '').toString();
      final String sugerida = (primera?['zona_sugerida'] ?? '').toString();
      _zona = sugerida.isEmpty ? null : sugerida;
    });
  }

  Future<void> _activar() async {
    final String? zona = _zona;
    if (zona == null) {
      setState(() => _error = 'Elige la zona de la ONU.');
      return;
    }
    setState(() {
      _ocupado = true;
      _error = null;
    });
    final Map<String, dynamic> d = await widget.api.activar(widget.ordenId, _serial, zona);
    if (!mounted) return;
    setState(() {
      _ocupado = false;
      if (d['activacion'] is Map) {
        _ultima = Map<String, dynamic>.from(d['activacion'] as Map);
        _onu = null;
      } else {
        _error = (d['error'] ?? 'No se pudo pedir.').toString();
      }
    });
    if (_ultima?['en_vuelo'] == true) _seguir();
  }

  /// Pregunta cómo va hasta que deja de estar en vuelo.
  void _seguir() {
    _reloj?.cancel();
    _vuelta = 0;
    _reloj = Timer.periodic(widget.cadaCuanto, (Timer t) async {
      _vuelta++;
      final Map<String, dynamic> d = await widget.api.estado(widget.ordenId);
      if (!mounted) return t.cancel();
      if (d['ultima'] is Map) {
        setState(() => _ultima = Map<String, dynamic>.from(d['ultima'] as Map));
      }
      if (_ultima?['en_vuelo'] != true || _vuelta >= widget.vueltas) t.cancel();
    });
  }

  @override
  Widget build(BuildContext context) {
    final Map<String, dynamic>? ultima = _ultima;
    final Map<String, dynamic>? onu = _onu;
    final bool enVuelo = ultima?['en_vuelo'] == true;
    return DexterBloque(
      titulo: 'Activar la ONU',
      icono: Icons.settings_input_antenna,
      insignia: _insignia(ultima),
      separacion: AppSpacing.sm,
      children: <Widget>[
        if (!_encendido)
          _Nota(texto: 'Tu empresa todavía no encendió «Activar ONU» desde la app.',
              alerta: true),
        if (ultima != null) _Resultado(ultima: ultima),
        if (onu != null) ..._encontrada(onu),
        if (_error != null) _Nota(texto: _error!, alerta: true),
        if (_ocupado && _busqueda > 1)
          _Nota(
            texto: 'Todavía no aparece. Si la acabas de conectar, la red tarda unos '
                'segundos en verla: sigo buscando ($_busqueda de ${widget.busquedas}).',
          ),
        if (onu == null && !enVuelo)
          SizedBox(
            height: AppSpacing.objetivoTactil,
            child: OutlinedButton.icon(
              onPressed: _ocupado ? null : _buscar,
              icon: _ocupado
                  ? const SizedBox(width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.search),
              label: Text(ultima == null ? 'Buscar la ONU en la red' : 'Volver a buscar'),
            ),
          ),
      ],
    );
  }

  Widget? _insignia(Map<String, dynamic>? ultima) {
    switch (ultima?['estado']) {
      case 'activada':
      case 'ya_estaba':
        return const DexterPastilla.enRegla(texto: 'Activada');
      case 'pedida':
      case 'en_curso':
        return const DexterPastilla.neutra(texto: 'Activando');
      case null:
        return null;
      default:
        return const DexterPastilla.alerta(texto: 'Revisar');
    }
  }

  List<Widget> _encontrada(Map<String, dynamic> onu) {
    final String estado = (onu['estado'] ?? '').toString();
    if (estado == 'ya_estaba') {
      return const <Widget>[_Nota(texto: 'Esta ONU ya está activada en la red.')];
    }
    if (estado != 'esperando') {
      return <Widget>[
        _Nota(
          texto: estado == 'no_espera'
              ? 'La ONU no aparece esperando autorización después de buscarla un '
                  'minuto. Revisa que esté conectada y con luz, y que el serial esté '
                  'bien escrito.'
              : 'No se pudo saber cómo está la ONU. Intenta de nuevo.',
          alerta: true,
        ),
        SizedBox(
          height: AppSpacing.objetivoTactil,
          child: OutlinedButton.icon(
            onPressed: _ocupado ? null : _buscar,
            icon: const Icon(Icons.refresh),
            label: const Text('Volver a buscar'),
          ),
        ),
      ];
    }
    final List<String> zonas = <String>[
      for (final dynamic z in (onu['zonas'] as List? ?? const <dynamic>[])) z.toString(),
    ];
    final dynamic vlan = onu['vlan'];
    return <Widget>[
      DexterBaldosaConIcono(
        icono: Icons.lan_outlined,
        rotulo: 'Esperando en la red',
        valor: 'OLT ${onu['olt']} · placa ${onu['placa']} · puerto ${onu['puerto']}',
      ),
      DropdownButtonFormField<String>(
        initialValue: zonas.contains(_zona) ? _zona : null,
        isExpanded: true,
        hint: const Text('Elige la zona'),
        decoration: InputDecoration(
          labelText: 'Zona',
          helperText: (onu['zona_sugerida'] ?? '').toString().isEmpty
              ? 'No se pudo sugerir por el barrio: elígela.'
              : 'Sugerida por el barrio del contrato.',
        ),
        items: <DropdownMenuItem<String>>[
          for (final String z in zonas) DropdownMenuItem<String>(value: z, child: Text(z)),
        ],
        onChanged: (String? v) => setState(() => _zona = v),
      ),
      _Nota(
        texto: vlan == null
            ? 'Falta la VLAN del servidor ${onu['servidor'] ?? ''} en Programación.'
            : 'VLAN $vlan, la del servidor ${onu['servidor'] ?? ''}.',
        alerta: vlan == null,
      ),
      SizedBox(
        height: AppSpacing.objetivoTactilAmplio,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.azulAccion,
            shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
          ),
          onPressed: (_ocupado || vlan == null || !_encendido || _zona == null) ? null : _activar,
          icon: _ocupado
              ? const SizedBox(width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Icon(Icons.power_settings_new),
          label: const Text('Activar ONU'),
        ),
      ),
    ];
  }
}

/// Cómo quedó el último pedido.
class _Resultado extends StatelessWidget {
  const _Resultado({required this.ultima});
  final Map<String, dynamic> ultima;

  @override
  Widget build(BuildContext context) {
    final String estado = (ultima['estado'] ?? '').toString();
    final String lugar = (ultima['olt'] ?? '').toString().isEmpty
        ? ''
        : ' (OLT ${ultima['olt']} · placa ${ultima['placa']} · puerto ${ultima['puerto']})';
    final String texto = switch (estado) {
      'activada' => 'ONU activada en la red$lugar.',
      'ya_estaba' => 'La ONU ya estaba activada en la red.',
      'pedida' || 'en_curso' => 'Activando la ONU… puede tardar hasta un minuto.',
      'no_espera' => 'La ONU no aparecía esperando autorización: revisa que esté conectada '
          'y el serial, y vuelve a buscar.',
      'fallida' => 'La red rechazó la activación. Avisa a la oficina.',
      'por_revisar' => (ultima['detalle'] ?? 'Que la oficina la revise.').toString(),
      _ => 'No salió: ${(ultima['detalle'] ?? '').toString()}',
    };
    final bool bien = estado == 'activada' || estado == 'ya_estaba';
    final bool esperando = estado == 'pedida' || estado == 'en_curso';
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
      if (esperando)
        const Padding(
          padding: EdgeInsets.only(top: 2),
          child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        )
      else
        Icon(bien ? Icons.check_circle : Icons.error_outline,
            size: 20, color: bien ? AppColors.exito : AppColors.precaucion),
      const SizedBox(width: AppSpacing.sm),
      Expanded(child: Text(texto, style: AppTypography.cuerpo)),
    ]);
  }
}

class _Nota extends StatelessWidget {
  const _Nota({required this.texto, this.alerta = false});
  final String texto;
  final bool alerta;

  @override
  Widget build(BuildContext context) => Text(
        texto,
        style: AppTypography.cuerpoChico.copyWith(
            color: alerta ? AppColors.precaucion : AppColors.onSurfaceVariant),
      );
}
