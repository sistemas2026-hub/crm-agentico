/// EL CONTRATO DEL CLIENTE, CREADO DESDE LA APP (13/11/2026).
///
/// Decisión del usuario: el técnico crea el contrato aquí y deja de llenarlo a
/// mano en WispHub. Los datos del cliente ya vienen de la solicitud que llenó;
/// el técnico los revisa con el documento delante, elige el servidor y el
/// cliente firma. El servidor arma el PDF (`campo/contrato.py`).
///
/// EXIGE SEÑAL, Y NO SE ENCOLA. Todo lo demás de esta app funciona sin red y
/// sube después. Esto no: es el primer paso del alta de un cliente, y un alta
/// que sale sola horas después, sin que nadie mire, puede crear un cliente
/// dos veces. Sin red la pantalla lo dice y el botón espera.
///
/// El alta en WispHub todavía no sale de aquí: el contrato queda «firmado» y la
/// pantalla lo dice. Ver SPEC/objetivos/agente-de-campo-para-instalaciones.md.
///
/// A NOMBRE DE OTRA PERSONA (26/11/2026). El usuario: «cuando el técnico llegue
/// y el contrato se hace a nombre de otra persona, pero los otros datos siguen
/// igual: solo cambiarían el nombre, el apellido y la cédula». Es un modo
/// explícito, no un nombre cambiado a mano: la persona nueva acepta ahí mismo
/// el tratamiento de sus datos, porque las autorizaciones de la solicitud las
/// aceptó otra. Lo que puede elegir y aceptar lo manda el servidor
/// (`otro_titular`); un servidor viejo no lo manda y el botón no sale.
///
/// EL CLIENTE FIRMA EL CONTRATO DEL PROVEEDOR (26/11/2026). Decisión del
/// usuario: el cliente firma SOLO el contrato de WispHub. Con la empresa en
/// ese modo (`firma_en_el_proveedor`), aquí no hay firma: el técnico confirma
/// los datos —antes tienen que estar subidas la cédula y el recibo, lo exige el
/// servidor—, se crea la instalación y Dexter guarda el contrato de WispHub.
/// Listo, «Firmar en WispHub» abre el enlace en el navegador del teléfono (el
/// enlace entra al portal del cliente sin clave: no se guarda, se pide cada
/// vez) y «Ya firmó: comprobar» lo lee en WispHub.
library;

import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';
import '../../core/storage/ubicacion_de_captura.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';
import '../detalle_orden/mapa_del_cliente.dart';
import '../ejecucion/widgets/firma_del_cliente.dart';
import 'elegir_ubicacion.dart';

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

/// Las coordenadas como se muestran: «lat, lng», o vacío si no hay.
///
/// Llegan como número o como texto según de dónde salieron (el ticket, la
/// solicitud, el teléfono); las dos formas se muestran igual.
String textoDeCoordenadas(dynamic gps) {
  if (gps is! Map) return '';
  final dynamic lat = gps['lat'];
  final dynamic lng = gps['lng'];
  if (lat == null || lng == null) return '';
  String uno(dynamic v) => v is num ? v.toStringAsFixed(6) : v.toString().trim();
  final String a = uno(lat);
  final String b = uno(lng);
  return a.isEmpty || b.isEmpty ? '' : '$a, $b';
}

/// Lo que el servidor contestó, traducido a lo que la pantalla necesita.
@immutable
class RespuestaDelServidor {
  const RespuestaDelServidor({this.cuerpo, this.error});
  final Map<String, dynamic>? cuerpo;
  final String? error;
}

/// Las dos llamadas. Reemplazable en pruebas.
class ApiDelContrato {
  const ApiDelContrato();

  static String _mensaje(Object e) {
    if (e is DioException) {
      final dynamic d = e.response?.data;
      if (d is Map && d['detail'] is String) return d['detail'] as String;
      if (e.response == null) {
        return 'Sin señal: el contrato no se creó. Toca otra vez cuando tengas señal.';
      }
      return 'El servidor no respondió bien (${e.response?.statusCode}). Intenta de nuevo.';
    }
    if (e is TimeoutException) {
      return 'Sin señal: el contrato no se creó. Toca otra vez cuando tengas señal.';
    }
    return 'No se pudo completar. Intenta de nuevo.';
  }

  Future<RespuestaDelServidor> leer(String ordenId) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .get<dynamic>(ApiEndpoints.contratoDeLaOrden(ordenId))
          .timeout(const Duration(seconds: 15));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return RespuestaDelServidor(cuerpo: Map<String, dynamic>.from(d as Map));
    } catch (e) {
      return RespuestaDelServidor(error: _mensaje(e));
    }
  }

  /// Las IP que se le pueden ofrecer en esa zona.
  ///
  /// NO devuelve error: una lista vacia con su motivo es una respuesta
  /// legitima --el servidor contesta 200 y explica por que no hay-- y el
  /// tecnico tiene que poder seguir firmando sin esto. El contrato no depende
  /// de la IP.
  Future<Map<String, dynamic>> ipsLibres(String ordenId, int idZona) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .get<dynamic>(ApiEndpoints.ipsLibresDeLaOrden(ordenId, idZona))
          .timeout(const Duration(seconds: 15));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return Map<String, dynamic>.from(d as Map);
    } catch (e) {
      return <String, dynamic>{
        'libres': const <dynamic>[],
        'motivo': 'No se pudieron consultar las direcciones disponibles.',
      };
    }
  }

  Future<RespuestaDelServidor> firmar(String ordenId, Map<String, dynamic> cuerpo) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .post<dynamic>(ApiEndpoints.contratoDeLaOrden(ordenId), data: cuerpo)
          .timeout(const Duration(seconds: 40));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return RespuestaDelServidor(cuerpo: Map<String, dynamic>.from(d as Map));
    } catch (e) {
      return RespuestaDelServidor(error: _mensaje(e));
    }
  }

  static String _mensajeDeFirma(Object e) {
    if (e is DioException) {
      final dynamic d = e.response?.data;
      if (d is Map && d['detail'] is String) return d['detail'] as String;
      if (e.response == null) return 'Sin señal. Toca otra vez cuando tengas señal.';
      return 'El servidor no respondió bien (${e.response?.statusCode}). Intenta de nuevo.';
    }
    if (e is TimeoutException) return 'Sin señal. Toca otra vez cuando tengas señal.';
    return 'No se pudo completar. Intenta de nuevo.';
  }

  /// El enlace para que el cliente firme en el proveedor (26/11/2026). Se pide
  /// cada vez y NO se guarda: entra al portal del cliente sin clave.
  Future<({String? enlace, String? error})> enlaceDeFirma(String ordenId) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .post<dynamic>(ApiEndpoints.enlaceDeFirma(ordenId), data: <String, dynamic>{})
          .timeout(const Duration(seconds: 70));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      final String enlace = d is Map ? (d['enlace'] ?? '').toString() : '';
      if (!enlace.startsWith('http://') && !enlace.startsWith('https://')) {
        return (enlace: null, error: 'El servidor no dio un enlace. Intenta de nuevo.');
      }
      return (enlace: enlace, error: null);
    } catch (e) {
      return (enlace: null, error: _mensajeDeFirma(e));
    }
  }

  /// Lee en el proveedor si el cliente ya firmó. Devuelve el contrato.
  Future<RespuestaDelServidor> comprobarFirma(String ordenId) async {
    try {
      final Response<dynamic> r = await ApiClient()
          .post<dynamic>(ApiEndpoints.comprobarFirma(ordenId), data: <String, dynamic>{})
          .timeout(const Duration(seconds: 70));
      final dynamic d = r.data is String ? jsonDecode(r.data as String) : r.data;
      return RespuestaDelServidor(cuerpo: Map<String, dynamic>.from(d as Map));
    } catch (e) {
      return RespuestaDelServidor(error: _mensajeDeFirma(e));
    }
  }

  /// Abre el enlace en el navegador del teléfono, fuera de la app.
  Future<bool> abrir(String enlace) async {
    try {
      return await launchUrl(Uri.parse(enlace), mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }
}

/// Cada cuánto y cuántas veces se vuelve a leer el contrato mientras se crea
/// la instalación o se prepara el contrato del proveedor (26/11/2026).
/// Público para que las pruebas lo acorten.
class ContratoScreenRelectura {
  static Duration intervalo = const Duration(seconds: 8);
  static const int maximas = 40;
}

class ContratoScreen extends StatefulWidget {
  const ContratoScreen({
    super.key,
    required this.ordenId,
    required this.titulo,
    this.api = const ApiDelContrato(),
  });

  final String ordenId;
  final String titulo;
  final ApiDelContrato api;

  @override
  State<ContratoScreen> createState() => _EstadoContrato();
}

/// Los campos del cliente, en el orden en que se muestran.
const List<List<String>> _camposDelCliente = <List<String>>[
  <String>['nombre', 'Nombre'],
  <String>['apellido', 'Apellido'],
  <String>['numero_documento', 'Documento'],
  <String>['telefono', 'Teléfono'],
  <String>['correo', 'Correo'],
  <String>['direccion', 'Dirección'],
  <String>['barrio', 'Barrio'],
];

/// Lo que cambia cuando el contrato va a nombre de otra persona. Lo demás
/// (teléfono, correo, dirección, barrio) sigue siendo el de la solicitud.
const List<String> _datosDelTitular = <String>['nombre', 'apellido', 'numero_documento'];

/// Dos números de documento son el mismo si coinciden letras y dígitos: con
/// puntos o espacios es la misma cédula. La misma regla que el servidor.
bool mismoDocumento(String a, String b) {
  String limpio(String x) => x.replaceAll(RegExp(r'[^0-9A-Za-z]'), '').toUpperCase();
  return limpio(a) == limpio(b);
}

class _EstadoContrato extends State<ContratoScreen> {
  bool _cargando = true;
  String? _errorDeCarga;
  Map<String, dynamic>? _contrato;
  Map<String, dynamic>? _borrador;
  List<Map<String, dynamic>> _servidores = <Map<String, dynamic>>[];
  //  LOS PLANES DE LA EMPRESA, cada uno con sus servidores y el del corte
  //  (26/11/2026). Vacia cuando el servidor no los manda: entonces el plan se
  //  escribe, como antes.
  List<Map<String, dynamic>> _planes = <Map<String, dynamic>>[];
  int? _idZona;
  //  LA IP LA ASIGNA EL SISTEMA AL FIRMAR (el usuario, 26/11/2026: «sería
  //  mejor si el sistema le indica la IP al contrato sin que tenga que elegir
  //  el técnico»). La app ya no pide la lista ni manda una: la elige el
  //  servidor (`contrato._ip_automatica`) y sale en el contrato firmado.
  //
  //  LAS COORDENADAS DE LA CASA. Llegan del ticket; el técnico las puede
  //  corregir en el mapa o con el GPS (el usuario, 26/11/2026: «que permita
  //  editar, y si sale un mapa para que seleccione la ubicación correcta»).
  //  Solo viajan si las corrigió: si no, mandan las del ticket.
  ({double lat, double lng})? _coordenadas;
  bool _coordenadasCorregidas = false;
  bool _enviando = false;
  String? _errorDeEnvio;
  final TrazoDeFirma _trazo = TrazoDeFirma();
  //  EL CLIENTE FIRMA EN EL PROVEEDOR (26/11/2026): sin firma aquí; después de
  //  confirmar, el recuadro de WispHub. Se vuelve a leer solo mientras espera.
  bool _firmaEnElProveedor = false;
  bool _pidiendoEnlace = false;
  bool _comprobando = false;
  String? _avisoDeFirma;
  Timer? _releer;
  int _relecturas = 0;
  final Map<String, TextEditingController> _campos = <String, TextEditingController>{};
  final TextEditingController _plan = TextEditingController();
  String _tipoDocumento = 'CC';
  //  A NOMBRE DE OTRA PERSONA: qué tipos de documento y qué autorizaciones
  //  ofrece el servidor (nulo: un servidor viejo, sin el botón), si está
  //  puesto, lo que había de la solicitud para volver, el tipo elegido y lo
  //  que la persona nueva aceptó.
  Map<String, dynamic>? _paraOtroTitular;
  bool _otraPersona = false;
  final Map<String, String> _deLaSolicitud = <String, String>{};
  String _tipoDelOtro = '';
  final Map<String, bool> _aceptadas = <String, bool>{};

  @override
  void initState() {
    super.initState();
    _trazo.addListener(_redibujar);
    _cargar();
  }

  void _redibujar() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _releer?.cancel();
    _trazo.removeListener(_redibujar);
    _trazo.dispose();
    for (final TextEditingController c in _campos.values) {
      c.dispose();
    }
    _plan.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _errorDeCarga = null;
    });
    final RespuestaDelServidor r = await widget.api.leer(widget.ordenId);
    if (!mounted) return;
    if (r.error != null) {
      setState(() {
        _cargando = false;
        _errorDeCarga = r.error;
      });
      return;
    }
    final Map<String, dynamic> d = r.cuerpo!;
    setState(() {
      _cargando = false;
      _contrato = d['contrato'] is Map ? Map<String, dynamic>.from(d['contrato'] as Map) : null;
      _borrador = d['borrador'] is Map ? Map<String, dynamic>.from(d['borrador'] as Map) : null;
      _firmaEnElProveedor = d['firma_en_el_proveedor'] == true;
      _servidores = <Map<String, dynamic>>[
        for (final dynamic s in (d['servidores'] as List? ?? const <dynamic>[]))
          if (s is Map) Map<String, dynamic>.from(s),
      ];
      //  EL DEL CORTE DEL TICKET, YA MARCADO; los demás del plan, a la mano
      //  para cambiarlo (el usuario, 26/11/2026: «en la parte de corte no
      //  deja escoger»).
      final dynamic sugerido = _borrador?['servidor_sugerido'];
      if (_servidores.length == 1) {
        _idZona = _servidores.first['id_zona'] as int?;
      } else if (_servidores.any((Map<String, dynamic> s) => s['id_zona'] == sugerido)) {
        _idZona = sugerido as int;
      }
      _coordenadas = _punto(_borrador?['gps']);
      _paraOtroTitular = d['otro_titular'] is Map
          ? Map<String, dynamic>.from(d['otro_titular'] as Map)
          : null;
      //  Un nombre, una vez: el menú exige valores únicos y se cae con dos
      //  planes que se llamen igual.
      final Set<String> vistos = <String>{};
      _planes = <Map<String, dynamic>>[
        for (final dynamic p in (d['planes'] as List? ?? const <dynamic>[]))
          if (p is Map &&
              (p['nombre'] ?? '').toString().isNotEmpty &&
              vistos.add(p['nombre'].toString()))
            Map<String, dynamic>.from(p),
      ];
      final Map<String, dynamic> cliente =
          Map<String, dynamic>.from((_borrador?['cliente'] as Map?) ?? const <String, dynamic>{});
      for (final List<String> c in _camposDelCliente) {
        _campos[c[0]] = TextEditingController(text: (cliente[c[0]] ?? '').toString());
      }
      _tipoDocumento = (cliente['tipo_documento'] ?? 'CC').toString();
      _plan.text = (_borrador?['plan'] ?? '').toString();
      //  EL PLAN SE ELIGE DE LA LISTA (el usuario, 26/11/2026: «un menú
      //  desplegable con los planes disponibles, así se evita el error al
      //  escoger»). Si lo que dice el ticket no es ninguno, queda sin elegir:
      //  el texto del ticket se muestra al lado, para saber qué pidió.
      if (_planes.isNotEmpty &&
          !_planes.any((Map<String, dynamic> p) => p['nombre'] == _plan.text)) {
        _plan.text = '';
      }
    });
    _seguirSiEspera();
  }

  // ------------------------------------------------------------------------
  //  EL CONTRATO DEL PROVEEDOR (26/11/2026)
  // ------------------------------------------------------------------------
  Map<String, dynamic> get _firmaProveedor =>
      Map<String, dynamic>.from((_contrato?['firma_proveedor'] as Map?) ?? const <String, dynamic>{});

  /// Si el contrato está esperando algo que pasa en el servidor: la
  /// instalación creándose o el contrato del proveedor preparándose.
  bool get _esperandoAlServidor {
    final Map<String, dynamic> fp = _firmaProveedor;
    if (_contrato == null || fp['activa'] != true) return false;
    final String alta = ((_contrato!['alta'] as Map?)?['estado'] ?? '').toString();
    final String estado = (_contrato!['estado'] ?? '').toString();
    if (estado == 'firmado') return alta == 'pedida' || alta == 'en_curso';
    final String f = (fp['estado'] ?? '').toString();
    return f.isEmpty || f == 'pedida';
  }

  void _seguirSiEspera() {
    _releer?.cancel();
    if (!_esperandoAlServidor || _relecturas >= ContratoScreenRelectura.maximas) return;
    _releer = Timer(ContratoScreenRelectura.intervalo, () async {
      _relecturas++;
      await _releerElContrato();
    });
  }

  Future<void> _releerElContrato() async {
    final RespuestaDelServidor r = await widget.api.leer(widget.ordenId);
    if (!mounted) return;
    if (r.cuerpo?['contrato'] is Map) {
      setState(() => _contrato = Map<String, dynamic>.from(r.cuerpo!['contrato'] as Map));
    }
    _seguirSiEspera();
  }

  Future<void> _firmarEnElProveedor() async {
    setState(() {
      _pidiendoEnlace = true;
      _avisoDeFirma = null;
    });
    final ({String? enlace, String? error}) r = await widget.api.enlaceDeFirma(widget.ordenId);
    if (!mounted) return;
    if (r.error != null) {
      setState(() {
        _pidiendoEnlace = false;
        _avisoDeFirma = r.error;
      });
      return;
    }
    final bool abrio = await widget.api.abrir(r.enlace!);
    if (!mounted) return;
    setState(() {
      _pidiendoEnlace = false;
      _avisoDeFirma = abrio
          ? 'Cuando el cliente termine de firmar, vuelve y toca «Ya firmó: comprobar».'
          : 'No se pudo abrir el navegador del teléfono. Intenta de nuevo.';
    });
  }

  Future<void> _comprobarFirma() async {
    setState(() {
      _comprobando = true;
      _avisoDeFirma = null;
    });
    final RespuestaDelServidor r = await widget.api.comprobarFirma(widget.ordenId);
    if (!mounted) return;
    setState(() {
      _comprobando = false;
      if (r.error != null) {
        _avisoDeFirma = r.error;
      } else if (r.cuerpo?['contrato'] is Map) {
        _contrato = Map<String, dynamic>.from(r.cuerpo!['contrato'] as Map);
        if (_firmaProveedor['firmado'] != true) {
          _avisoDeFirma = 'Todavía no aparece la firma en WispHub. Si el cliente ya firmó, '
              'espera unos segundos y vuelve a comprobar.';
        }
      }
    });
  }

  /// El técnico eligió un plan del menú.
  ///
  /// Quedan los servidores DE ESE PLAN, con el del corte del ticket primero y
  /// marcado si el plan lo tiene (`servidor_sugerido`, lo decide el servidor).
  /// El técnico lo puede cambiar.
  void _elegirPlan(String nombre) {
    final Map<String, dynamic>? plan = _planes
        .where((Map<String, dynamic> p) => p['nombre'] == nombre)
        .firstOrNull;
    if (plan == null) return;
    final dynamic sugerido = plan['servidor_sugerido'];
    final List<Map<String, dynamic>> servidores = <Map<String, dynamic>>[
      for (final dynamic s in (plan['servidores'] as List? ?? const <dynamic>[]))
        if (s is Map) Map<String, dynamic>.from(s),
    ]..sort((Map<String, dynamic> a, Map<String, dynamic> b) =>
        (a['id_zona'] == sugerido ? 0 : 1).compareTo(b['id_zona'] == sugerido ? 0 : 1));
    bool esta(dynamic id) => servidores.any((Map<String, dynamic> s) => s['id_zona'] == id);
    final int? zona = servidores.length == 1
        ? servidores.first['id_zona'] as int?
        : esta(sugerido)
            ? sugerido as int
            : (esta(_idZona) ? _idZona : null);
    setState(() {
      _plan.text = nombre;
      _servidores = servidores;
      _idZona = zona;
    });
  }

  List<String> get _tiposDeDocumento => <String>[
        for (final dynamic t in (_paraOtroTitular?['tipos_de_documento'] as List? ?? const <dynamic>[]))
          if ((t ?? '').toString().isNotEmpty) t.toString(),
      ];

  List<Map<String, dynamic>> get _autorizacionesDelOtro => <Map<String, dynamic>>[
        for (final dynamic a in (_paraOtroTitular?['autorizaciones'] as List? ?? const <dynamic>[]))
          if (a is Map && (a['id'] ?? '').toString().isNotEmpty) Map<String, dynamic>.from(a),
      ];

  /// Las que la persona nueva TIENE que aceptar para firmar a su nombre.
  bool get _aceptoLasObligatorias => _autorizacionesDelOtro
      .where((Map<String, dynamic> a) => a['obligatoria'] == true)
      .every((Map<String, dynamic> a) => _aceptadas[a['id']] == true);

  /// El técnico tocó «A nombre de otra persona»: nombre, apellido y documento
  /// quedan vacíos para escribir los de la persona nueva (lo de la solicitud
  /// se guarda para poder volver). Lo demás no se toca.
  void _aNombreDeOtraPersona() {
    setState(() {
      for (final String c in _datosDelTitular) {
        _deLaSolicitud[c] = _campos[c]?.text ?? '';
        _campos[c]?.clear();
      }
      _tipoDelOtro = _tiposDeDocumento.isEmpty ? '' : _tiposDeDocumento.first;
      _aceptadas.clear();
      _otraPersona = true;
    });
  }

  void _volverALaSolicitud() {
    setState(() {
      for (final String c in _datosDelTitular) {
        _campos[c]?.text = _deLaSolicitud[c] ?? '';
      }
      _aceptadas.clear();
      _otraPersona = false;
    });
  }

  /// Si el documento escrito ya no es el de la solicitud, sin haber dicho
  /// «otra persona»: puede ser un número mal escrito en la solicitud, o el
  /// técnico cambiando de persona por el camino equivocado.
  bool get _documentoDistinto {
    final String delBorrador =
        ((_borrador?['cliente'] as Map?)?['numero_documento'] ?? '').toString();
    final String escrito = _campos['numero_documento']?.text ?? '';
    return _borrador?['origen'] == 'solicitud' &&
        delBorrador.trim().isNotEmpty &&
        escrito.trim().isNotEmpty &&
        !mismoDocumento(escrito, delBorrador);
  }

  /// Las coordenadas como las manda el servidor (número o texto), o nulo.
  static ({double lat, double lng})? _punto(dynamic gps) {
    if (gps is! Map) return null;
    final double? lat = double.tryParse('${gps['lat'] ?? ''}');
    final double? lng = double.tryParse('${gps['lng'] ?? ''}');
    if (lat == null || lng == null || (lat == 0 && lng == 0)) return null;
    return (lat: lat, lng: lng);
  }

  void _ponerCoordenadas(double lat, double lng) => setState(() {
        _coordenadas = (lat: lat, lng: lng);
        _coordenadasCorregidas = true;
      });

  Future<void> _elegirEnElMapa() async {
    final ({double lat, double lng})? actual = _coordenadas;
    final ({double lat, double lng})? elegida =
        await Navigator.of(context).push<({double lat, double lng})>(
      MaterialPageRoute<({double lat, double lng})>(
        builder: (_) => ElegirUbicacion(lat: actual?.lat, lng: actual?.lng),
      ),
    );
    if (elegida != null && mounted) _ponerCoordenadas(elegida.lat, elegida.lng);
  }

  Future<void> _usarDondeEstoy() async {
    final Map<String, dynamic> u = await UbicacionDeCaptura.tomar();
    if (!mounted) return;
    final ({double lat, double lng})? p = _punto(u);
    if (p == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('El teléfono no pudo decir dónde estás. Elige el punto en el mapa.')));
      return;
    }
    _ponerCoordenadas(p.lat, p.lng);
  }

  bool get _listo =>
      (_firmaEnElProveedor || !_trazo.vacio) &&
      _idZona != null &&
      (_campos['nombre']?.text.trim().isNotEmpty ?? false) &&
      (_campos['numero_documento']?.text.trim().isNotEmpty ?? false) &&
      (_campos['direccion']?.text.trim().isNotEmpty ?? false) &&
      _plan.text.trim().isNotEmpty &&
      (!_otraPersona || (_tipoDelOtro.isNotEmpty && _aceptoLasObligatorias));

  Future<void> _crear() async {
    setState(() {
      _enviando = true;
      _errorDeEnvio = null;
    });
    //  En el proveedor no hay firma aquí: firma el cliente en WispHub.
    final List<int> firma =
        _firmaEnElProveedor ? const <int>[] : await _trazo.aPng(const Size(600, 300));
    //  Dónde se firmó: el punto real de la casa. Nunca tarda más de su plazo
    //  ni lanza (ver `UbicacionDeCaptura`).
    final Map<String, dynamic> ubicacion = await UbicacionDeCaptura.tomar();
    final Map<String, dynamic> cuerpo = <String, dynamic>{
      'cliente': <String, dynamic>{
        for (final List<String> c in _camposDelCliente) c[0]: _campos[c[0]]!.text.trim(),
        'tipo_documento': _otraPersona ? _tipoDelOtro : _tipoDocumento,
      },
      //  A nombre de otra persona: lo dice, y manda lo que ESA persona aceptó.
      if (_otraPersona) ...<String, dynamic>{
        'titular': 'otro',
        'autorizaciones': <String, bool>{
          for (final Map<String, dynamic> a in _autorizacionesDelOtro)
            a['id'].toString(): _aceptadas[a['id']] == true,
        },
      },
      'plan': _plan.text.trim(),
      'id_zona': _idZona,
      //  Sin `ip`: la asigna el servidor al firmar.
      //  Las coordenadas de la casa, SOLO si el técnico las corrigió.
      if (_coordenadasCorregidas && _coordenadas != null)
        'coordenadas': <String, dynamic>{
          'lat': _coordenadas!.lat,
          'lng': _coordenadas!.lng,
        },
      if (!_firmaEnElProveedor) 'firma_png_base64': base64Encode(firma),
      if (ubicacion.containsKey('lat') && ubicacion.containsKey('lng'))
        'gps': <String, dynamic>{
          'lat': ubicacion['lat'],
          'lng': ubicacion['lng'],
          'precision_m': ubicacion['precision_m'],
        },
    };
    final RespuestaDelServidor r = await widget.api.firmar(widget.ordenId, cuerpo);
    if (!mounted) return;
    setState(() {
      _enviando = false;
      if (r.error != null) {
        _errorDeEnvio = r.error;
      } else if (r.cuerpo?['contrato'] is Map) {
        _contrato = Map<String, dynamic>.from(r.cuerpo!['contrato'] as Map);
      }
    });
    _seguirSiEspera();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.fondo,
      appBar: AppBar(title: Text('Contrato · ${widget.titulo}')),
      body: SafeArea(child: _cuerpo()),
    );
  }

  Widget _cuerpo() {
    if (_cargando) return const Center(child: CircularProgressIndicator());
    if (_errorDeCarga != null) {
      return _Centro(
        icono: Icons.signal_cellular_connected_no_internet_4_bar,
        titulo: 'Necesitas señal para el contrato',
        texto: _errorDeCarga!,
        accion: 'Reintentar',
        alTocar: _cargar,
      );
    }
    if (_contrato != null) return _firmado(_contrato!);
    return _formulario();
  }

  Widget _firmado(Map<String, dynamic> c) {
    final Map<String, dynamic> cliente =
        Map<String, dynamic>.from((c['cliente'] as Map?) ?? const <String, dynamic>{});
    final Map<String, dynamic> servidor =
        Map<String, dynamic>.from((c['servidor'] as Map?) ?? const <String, dynamic>{});
    final String coordenadas = textoDeCoordenadas(c['gps']);
    final String documento =
        '${cliente['tipo_documento'] ?? ''} ${cliente['numero_documento'] ?? ''}'.trim();
    final String ip = (c['ip_elegida'] ?? '').toString();
    final Map<String, dynamic> fp =
        Map<String, dynamic>.from((c['firma_proveedor'] as Map?) ?? const <String, dynamic>{});
    final bool enElProveedor = fp['activa'] == true;
    final bool firmadoEnElProveedor = fp['firmado'] == true;
    return ListView(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.margen, AppSpacing.md, AppSpacing.margen, AppSpacing.xl),
      children: <Widget>[
        DexterBloque(
          titulo: enElProveedor && !firmadoEnElProveedor ? 'Contrato confirmado' : 'Contrato firmado',
          icono: Icons.verified_outlined,
          insignia: enElProveedor && !firmadoEnElProveedor
              ? const DexterPastilla.neutra(texto: 'Por firmar')
              : const DexterPastilla.enRegla(texto: 'Firmado'),
          separacion: AppSpacing.sm,
          children: <Widget>[
            Text('N.º ${c['numero']}',
                style: AppTypography.labelTelemetry.copyWith(color: AppColors.secondary)),
            DexterFilaDeDato(
              icono: Icons.person_outline,
              texto: '${cliente['nombre'] ?? ''} ${cliente['apellido'] ?? ''}'.trim(),
              estilo: AppTypography.cuerpo,
            ),
            if (documento.isNotEmpty)
              DexterFilaDeDato(icono: Icons.badge_outlined, texto: documento),
            if (c['otro_titular'] == true)
              DexterFilaDeDato(
                icono: Icons.swap_horiz,
                texto: 'A nombre de otra persona: aceptó sus datos al firmar.',
                estilo: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
                colorDelIcono: AppColors.outline,
              ),
            DexterFilaDeDato(icono: Icons.speed, texto: (c['plan'] ?? '').toString()),
            DexterFilaDeDato(
              icono: Icons.dns_outlined,
              texto: [(servidor['nombre'] ?? '').toString(), if (ip.isNotEmpty) ip].join(' · '),
            ),
            if (coordenadas.isNotEmpty)
              DexterFilaDeDato(
                icono: Icons.place_outlined,
                texto: coordenadas,
                estilo: AppTypography.labelTelemetry,
              ),
            DexterHundido(
              child: DexterFilaDeDato(
                icono: Icons.picture_as_pdf_outlined,
                texto: enElProveedor
                    ? 'Los datos quedaron en la plataforma; la firma va en el contrato de WispHub.'
                    : 'El PDF con la firma quedó en la plataforma.',
                estilo: AppTypography.cuerpoChico,
                colorDelIcono: AppColors.outline,
              ),
            ),
          ],
        ),
        if (enElProveedor) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          _firmaEnWispHub(c, fp),
        ] else if (c['estado'] != 'en_el_isp') ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          const _Aviso(
            icono: Icons.schedule,
            texto: 'El cliente todavía no se crea en WispHub desde aquí. '
                'Esa parte se está terminando; mientras tanto la oficina lo da '
                'de alta con estos datos.',
          ),
        ],
      ],
    );
  }

  /// Un dato del cliente. La etiqueta va DENTRO del campo (`labelText`): es la
  /// que lee el lector de pantalla, y la que encuentran las pruebas.
  Widget _campo(String clave) {
    final String etiqueta =
        _camposDelCliente.firstWhere((List<String> c) => c[0] == clave)[1];
    return TextField(
      controller: _campos[clave],
      onChanged: (_) => setState(() {}),
      keyboardType: clave == 'telefono' || clave == 'numero_documento'
          ? TextInputType.number
          : (clave == 'correo' ? TextInputType.emailAddress : TextInputType.text),
      style: clave == 'numero_documento' || clave == 'telefono'
          ? AppTypography.dato
          : AppTypography.cuerpo,
      decoration: InputDecoration(labelText: etiqueta),
    );
  }

  /// El tipo de documento de la persona nueva, de la lista del servidor.
  Widget _tipoDeDocumento() => DropdownButtonFormField<String>(
        initialValue: _tipoDelOtro.isEmpty ? null : _tipoDelOtro,
        isExpanded: true,
        icon: const Icon(Icons.expand_more, color: AppColors.secondary),
        borderRadius: AppRadius.brTarjeta,
        style: AppTypography.cuerpo,
        decoration: const InputDecoration(labelText: 'Tipo de documento'),
        items: <DropdownMenuItem<String>>[
          for (final String t in _tiposDeDocumento)
            DropdownMenuItem<String>(value: t, child: Text(t, overflow: TextOverflow.ellipsis)),
        ],
        onChanged: (String? v) {
          if (v != null) setState(() => _tipoDelOtro = v);
        },
      );

  /// Lo que acepta la persona nueva, ahí mismo. Las de la solicitud no le
  /// sirven: las aceptó quien la llenó.
  Widget _autorizacionesDeLaPersonaNueva() => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const SizedBox(height: AppSpacing.xs),
          const _Rotulo('Lo que autoriza esta persona'),
          for (final Map<String, dynamic> a in _autorizacionesDelOtro)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: _Autorizacion(
                texto: (a['texto'] ?? '').toString(),
                obligatoria: a['obligatoria'] == true,
                aceptada: _aceptadas[a['id']] == true,
                alTocar: () => setState(() =>
                    _aceptadas[a['id'].toString()] = !(_aceptadas[a['id']] ?? false)),
              ),
            ),
        ],
      );

  /// Dos datos cortos lado a lado: nombre y apellido, documento y teléfono.
  /// Cada uno con su mitad: con letra grande el texto se corre adentro del
  /// campo, no lo desborda.
  Widget _dosCampos(String a, String b) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(child: _campo(a)),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: _campo(b)),
        ],
      );

  /// El técnico tocó un servidor de la lista.
  void _elegirServidor(int v) {
    if (v != _idZona) setState(() => _idZona = v);
  }

  /// El servidor: si hay uno solo --el del corte del ticket, casi siempre--
  /// se MUESTRA ya asignado; si hay varios, se elige tocando uno.
  Widget _servidor() {
    if (_servidores.isEmpty) {
      return const _Aviso(
        icono: Icons.info_outline,
        texto: 'Tu empresa no ha cargado sus servidores en la plataforma '
            '(Programación → El contrato de instalación).',
      );
    }
    if (_servidores.length == 1) {
      return DexterBaldosaConIcono(
        icono: Icons.dns_outlined,
        rotulo: 'Servidor asignado',
        valor: (_servidores.first['nombre'] ?? '').toString(),
      );
    }
    final bool delCorte = _idZona != null && _idZona == _borrador?['servidor_sugerido'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _Rotulo(delCorte ? 'Servidor · marcado por el corte del ticket' : 'Elige el servidor'),
        for (final Map<String, dynamic> s in _servidores)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs),
            child: _OpcionDeServidor(
              nombre: (s['nombre'] ?? '').toString(),
              elegido: _idZona == s['id_zona'],
              alTocar: () => _elegirServidor(s['id_zona'] as int),
            ),
          ),
      ],
    );
  }

  /// Las coordenadas de la casa: el mapa con el punto, y cómo cambiarlo.
  Widget _ubicacion() {
    final ({double lat, double lng})? c = _coordenadas;
    final String texto = c == null
        ? ''
        : '${c.lat.toStringAsFixed(6)}, ${c.lng.toStringAsFixed(6)}';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _Rotulo(c == null
            ? 'Coordenadas de la instalación'
            : (_coordenadasCorregidas
                ? 'Coordenadas · corregidas por ti'
                : 'Coordenadas · del ticket')),
        const SizedBox(height: AppSpacing.xs),
        if (c == null)
          const DexterBaldosaConIcono(
            icono: Icons.place_outlined,
            rotulo: 'Sin coordenadas en el ticket',
            valor: 'Del teléfono, al firmar',
          )
        else
          MapaDelCliente(
            latitud: c.lat,
            longitud: c.lng,
            alto: 170,
            etiqueta: texto,
            alCorregir: _elegirEnElMapa,
          ),
        const SizedBox(height: AppSpacing.sm),
        Row(children: <Widget>[
          Expanded(
            child: DexterAccionRapida(
              icono: Icons.map_outlined,
              texto: 'Elegir en el mapa',
              alTocar: _elegirEnElMapa,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: DexterAccionRapida(
              icono: Icons.my_location,
              texto: 'Donde estoy',
              alTocar: _usarDondeEstoy,
            ),
          ),
        ]),
      ],
    );
  }

  Widget _selectorDePlan(String planDelTicket) {
    if (_planes.isEmpty) {
      return TextField(
        controller: _plan,
        onChanged: (_) => setState(() {}),
        decoration: const InputDecoration(labelText: 'Plan'),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        DropdownButtonFormField<String>(
          initialValue: _plan.text.isEmpty ? null : _plan.text,
          isExpanded: true,
          hint: const Text('Elige el plan'),
          icon: const Icon(Icons.expand_more, color: AppColors.secondary),
          borderRadius: AppRadius.brTarjeta,
          style: AppTypography.cuerpo.copyWith(fontWeight: FontWeight.w600),
          decoration: const InputDecoration(
            labelText: 'Plan',
            prefixIcon: Icon(Icons.speed, color: AppColors.secondary),
          ),
          items: <DropdownMenuItem<String>>[
            for (final Map<String, dynamic> p in _planes)
              DropdownMenuItem<String>(
                value: p['nombre'].toString(),
                child: Text(p['nombre'].toString(), overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (String? v) {
            if (v != null) _elegirPlan(v);
          },
        ),
        //  Lo que pidió el cliente, a la vista: con eso se elige si el
        //  ticket no dice un plan de la lista.
        if (planDelTicket.isNotEmpty && planDelTicket != _plan.text)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs, left: 2),
            child: DexterFilaDeDato(
              icono: Icons.receipt_long_outlined,
              texto: 'En el ticket dice: «$planDelTicket»',
              estilo: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
              colorDelIcono: AppColors.outline,
            ),
          ),
      ],
    );
  }

  Widget _formulario() {
    final bool deSolicitud = _borrador?['origen'] == 'solicitud';
    final String planDelTicket = (_borrador?['plan_del_ticket'] ?? '').toString().trim();
    return ListView(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.margen, AppSpacing.md, AppSpacing.margen, AppSpacing.xl),
      children: <Widget>[
        DexterBloque(
          titulo: 'El cliente',
          icono: Icons.person_outline,
          insignia: _otraPersona
              ? const DexterPastilla.alerta(texto: 'Otra persona')
              : deSolicitud
                  ? const DexterPastilla.enRegla(texto: 'De la solicitud')
                  : const DexterPastilla.alerta(texto: 'Sin solicitud'),
          separacion: AppSpacing.sm,
          children: <Widget>[
            Text(
              _otraPersona
                  ? 'El contrato va a nombre de otra persona: escribe sus datos con su '
                      'documento a la vista. Teléfono, dirección y lo demás siguen igual.'
                  : deSolicitud
                      ? 'Lo llenó el cliente en la solicitud. Revísalo con el documento.'
                      : 'Sin solicitud: llénalo con el documento a la vista.',
              style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
            ),
            //  A NOMBRE DE OTRA PERSONA (26/11/2026): solo si el servidor
            //  dice qué se le pide a esa persona.
            if (!_otraPersona && _paraOtroTitular != null)
              DexterAccionRapida(
                icono: Icons.swap_horiz,
                texto: 'A nombre de otra persona',
                alTocar: _aNombreDeOtraPersona,
              ),
            //  Uno debajo del otro, a todo el ancho (el usuario, 26/11/2026:
            //  «que salga nombre arriba y apellido abajo, completo»).
            _campo('nombre'),
            _campo('apellido'),
            if (_otraPersona) _tipoDeDocumento(),
            _dosCampos('numero_documento', 'telefono'),
            if (!_otraPersona && _documentoDistinto && _paraOtroTitular != null)
              DexterFilaDeDato(
                icono: Icons.info_outline,
                texto: 'Este no es el documento de la solicitud. Si el contrato va a '
                    'nombre de otra persona, toca «A nombre de otra persona».',
                estilo: AppTypography.cuerpoChico.copyWith(color: AppColors.precaucion),
                colorDelIcono: AppColors.precaucion,
              ),
            if (_otraPersona) ...<Widget>[
              _autorizacionesDeLaPersonaNueva(),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _volverALaSolicitud,
                  icon: const Icon(Icons.undo, size: 18),
                  label: const Text('Volver a los datos de la solicitud'),
                ),
              ),
            ],
            _campo('correo'),
            _campo('direccion'),
            _campo('barrio'),
            //  SIN «HABEAS DATA» NI «CENTRALES DE RIESGO» (el usuario,
            //  26/11/2026: «ya no es necesario»). Siguen en el contrato: el
            //  servidor las toma de la solicitud, que es donde el cliente las
            //  aceptó, y no de esta pantalla.
            //
            //  LAS COORDENADAS (el usuario: «no veo las coordenadas»). Mandan
            //  las del ticket; si no trae, el servidor guarda las de este
            //  teléfono al firmar.
            _ubicacion(),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        DexterBloque(
          titulo: 'El servicio',
          icono: Icons.router_outlined,
          separacion: AppSpacing.md,
          children: <Widget>[
            _selectorDePlan(planDelTicket),
            _servidor(),
            //  LA IP: la asigna el sistema al firmar. Se dice, para que nadie
            //  la busque para elegirla.
            const DexterBaldosaConIcono(
              icono: Icons.lan_outlined,
              rotulo: 'Dirección IP · automática',
              valor: 'Se asigna al firmar',
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (_firmaEnElProveedor)
          DexterBloque(
            titulo: 'La firma, en WispHub',
            icono: Icons.draw_outlined,
            separacion: AppSpacing.sm,
            children: <Widget>[
              Text(
                'El cliente firma el contrato de WispHub después de confirmar. Antes de '
                'confirmar toma la cédula por delante y por detrás y el recibo, y espera a '
                'que suban.',
                style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
              ),
            ],
          )
        else
        DexterBloque(
          titulo: 'Firma del cliente',
          icono: Icons.draw_outlined,
          insignia: _trazo.vacio
              ? null
              : TextButton(
                  style: TextButton.styleFrom(minimumSize: const Size(0, 40)),
                  onPressed: _trazo.limpiar,
                  child: const Text('Borrar'),
                ),
          separacion: AppSpacing.sm,
          children: <Widget>[
            Text('Acepta el contrato y la instalación recibida.',
                style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant)),
            Container(
              height: 190,
              decoration: BoxDecoration(
                color: AppColors.surfaceContainerLow,
                borderRadius: AppRadius.brTarjeta,
                border: Border.all(
                  color: _trazo.vacio ? AppColors.surfaceContainerHigh : AppColors.secondary,
                  width: 1.5,
                ),
              ),
              child: ClipRRect(
                borderRadius: AppRadius.brTarjeta,
                child: Stack(children: <Widget>[
                  //  La línea de firma, como en el papel.
                  Positioned(
                    left: AppSpacing.lg,
                    right: AppSpacing.lg,
                    bottom: 44,
                    child: Container(height: 1, color: AppColors.outline.withValues(alpha: 0.4)),
                  ),
                  if (_trazo.vacio)
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 18,
                      child: Text('Firme aquí con el dedo',
                          textAlign: TextAlign.center,
                          style: AppTypography.cuerpoChico.copyWith(color: AppColors.outline)),
                    ),
                  Positioned.fill(child: LienzoDeFirma(trazo: _trazo)),
                ]),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (_errorDeEnvio != null)
          _Aviso(icono: Icons.error_outline, texto: _errorDeEnvio!),
        SizedBox(
          height: AppSpacing.objetivoTactilAmplio,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.azulAccion,
              shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
            ),
            icon: _enviando
                ? const SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.task_alt),
            //  Corto y con elipsis: con letra grande o pantalla angosta,
            //  «Creando el contrato…» no cabía al lado del indicador.
            label: Text(
                _enviando
                    ? (_firmaEnElProveedor ? 'Confirmando…' : 'Creando…')
                    : (_firmaEnElProveedor ? 'Confirmar contrato' : 'Crear el contrato'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 17)),
            onPressed: _listo && !_enviando ? _crear : null,
          ),
        ),
        if (!_listo && !_enviando)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(_queFalta(), textAlign: TextAlign.center,
                style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant)),
          ),
      ],
    );
  }

  /// El recuadro del contrato de WispHub, según cómo va (26/11/2026).
  Widget _firmaEnWispHub(Map<String, dynamic> c, Map<String, dynamic> fp) {
    final Map<String, dynamic> alta =
        Map<String, dynamic>.from((c['alta'] as Map?) ?? const <String, dynamic>{});
    final String estado = (c['estado'] ?? '').toString();
    final String f = (fp['estado'] ?? '').toString();
    final List<Widget> hijos = <Widget>[];
    DexterPastilla insignia = const DexterPastilla.neutra(texto: 'Esperando');
    String texto;
    bool puedeFirmar = false;
    if (fp['firmado'] == true) {
      insignia = const DexterPastilla.enRegla(texto: 'Firmado');
      texto = 'El cliente firmó el contrato en WispHub.';
    } else if (estado == 'firmado' &&
        (alta['estado'] == 'pedida' || alta['estado'] == 'en_curso')) {
      texto = 'Creando la instalación en WispHub…';
    } else if (estado == 'firmado') {
      insignia = const DexterPastilla.alerta(texto: 'Revisar');
      texto = '${alta['detalle'] ?? 'La instalación no quedó creada en WispHub.'} '
          'Avísale a la oficina.';
    } else if (f == 'lista') {
      insignia = const DexterPastilla.alerta(texto: 'Por firmar');
      texto = 'El contrato de WispHub está listo, con la cédula y el recibo. Pásale el '
          'teléfono al cliente para que lo firme.';
      puedeFirmar = true;
    } else if (f == 'fallida' || f == 'por_revisar') {
      insignia = const DexterPastilla.alerta(texto: 'Revisar');
      texto = '${fp['detalle'] ?? 'El contrato de WispHub no quedó listo.'} '
          'Avísale a la oficina: lo revisan en Instalaciones.';
    } else {
      texto = 'Guardando el contrato en WispHub con la cédula y el recibo…';
    }
    hijos.add(Text(texto,
        style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant)));
    if (_avisoDeFirma != null) {
      hijos.add(Text(_avisoDeFirma!,
          style: AppTypography.cuerpoChico.copyWith(color: AppColors.precaucion)));
    }
    if (puedeFirmar) {
      hijos.add(SizedBox(
        height: AppSpacing.objetivoTactilAmplio,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.azulAccion,
            shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
          ),
          onPressed: _pidiendoEnlace || _comprobando ? null : _firmarEnElProveedor,
          icon: _pidiendoEnlace
              ? const SizedBox(
                  width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Icon(Icons.open_in_new),
          label: Text(_pidiendoEnlace ? 'Abriendo…' : 'Firmar en WispHub',
              maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
      ));
      hijos.add(SizedBox(
        height: AppSpacing.objetivoTactilAmplio,
        child: OutlinedButton.icon(
          onPressed: _pidiendoEnlace || _comprobando ? null : _comprobarFirma,
          icon: _comprobando
              ? const SizedBox(width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.fact_check_outlined),
          label: Text(_comprobando ? 'Comprobando…' : 'Ya firmó: comprobar',
              maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
      ));
    } else if (_esperandoAlServidor) {
      hijos.add(Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: _releerElContrato,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('Actualizar'),
        ),
      ));
    }
    return DexterBloque(
      titulo: 'Firma en WispHub',
      icono: Icons.draw_outlined,
      insignia: insignia,
      separacion: AppSpacing.sm,
      children: hijos,
    );
  }

  String _queFalta() {
    final List<String> f = <String>[
      if (_campos['nombre']?.text.trim().isEmpty ?? true) 'el nombre',
      if (_campos['numero_documento']?.text.trim().isEmpty ?? true) 'el documento',
      if (_campos['direccion']?.text.trim().isEmpty ?? true) 'la dirección',
      if (_plan.text.trim().isEmpty) 'el plan',
      if (_idZona == null) 'el servidor',
      if (_otraPersona && !_aceptoLasObligatorias) 'que la persona autorice sus datos',
      if (!_firmaEnElProveedor && _trazo.vacio) 'la firma del cliente',
    ];
    return f.isEmpty ? '' : 'Falta ${f.join(', ')}.';
  }
}

// ==========================================================================
//  PIEZAS
// ==========================================================================
/// Un rótulo de sección dentro de una tarjeta: chico, en mayúsculas y gris,
/// como los de las baldosas de la ficha.
class _Rotulo extends StatelessWidget {
  const _Rotulo(this.texto);
  final String texto;

  @override
  Widget build(BuildContext context) => Text(
        texto.toUpperCase(),
        style: AppTypography.labelCaption.copyWith(color: AppColors.outline),
      );
}

/// Un servidor para elegir. El elegido se marca con el azul de acción y un
/// borde: con guante y al sol, un punto de radio no se ve.
class _OpcionDeServidor extends StatelessWidget {
  const _OpcionDeServidor({
    required this.nombre,
    required this.elegido,
    required this.alTocar,
  });
  final String nombre;
  final bool elegido;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        selected: elegido,
        child: Material(
          color: elegido ? AppColors.infoFondo : AppColors.surfaceContainerLow,
          borderRadius: AppRadius.brTarjeta,
          child: InkWell(
            onTap: alTocar,
            borderRadius: AppRadius.brTarjeta,
            child: Container(
              constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md, vertical: AppSpacing.sm),
              decoration: BoxDecoration(
                borderRadius: AppRadius.brTarjeta,
                border: Border.all(
                  color: elegido ? AppColors.secondary : AppColors.surfaceContainerHigh,
                  width: 1.5,
                ),
              ),
              child: Row(children: <Widget>[
                Icon(elegido ? Icons.check_circle : Icons.circle_outlined,
                    size: 22, color: elegido ? AppColors.secondary : AppColors.outline),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(nombre,
                      style: AppTypography.etiquetaGrande.copyWith(
                          color: elegido ? AppColors.secondary : AppColors.onSurface)),
                ),
              ]),
            ),
          ),
        ),
      );
}

/// Una autorización que la persona acepta tocándola. Como un servidor: la
/// marcada con el azul de acción y un borde, que se ve al sol.
class _Autorizacion extends StatelessWidget {
  const _Autorizacion({
    required this.texto,
    required this.obligatoria,
    required this.aceptada,
    required this.alTocar,
  });
  final String texto;
  final bool obligatoria;
  final bool aceptada;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) => Semantics(
        checked: aceptada,
        child: Material(
          color: aceptada ? AppColors.infoFondo : AppColors.surfaceContainerLow,
          borderRadius: AppRadius.brTarjeta,
          child: InkWell(
            onTap: alTocar,
            borderRadius: AppRadius.brTarjeta,
            child: Container(
              constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md, vertical: AppSpacing.sm),
              decoration: BoxDecoration(
                borderRadius: AppRadius.brTarjeta,
                border: Border.all(
                  color: aceptada ? AppColors.secondary : AppColors.surfaceContainerHigh,
                  width: 1.5,
                ),
              ),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                Icon(aceptada ? Icons.check_box : Icons.check_box_outline_blank,
                    size: 22, color: aceptada ? AppColors.secondary : AppColors.outline),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                    Text(texto, style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurface)),
                    if (obligatoria)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text('Obligatoria para firmar a su nombre',
                            style: AppTypography.etiquetaChica.copyWith(color: AppColors.outline)),
                      ),
                  ]),
                ),
              ]),
            ),
          ),
        ),
      );
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.icono, required this.texto});
  final IconData icono;
  final String texto;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 12, top: 4),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
            color: AppColors.precaucionFondo, borderRadius: AppRadius.brTarjeta),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Icon(icono, color: AppColors.precaucion),
          const SizedBox(width: 10),
          Expanded(child: Text(texto, style: AppTypography.cuerpoChico)),
        ]),
      );
}

class _Centro extends StatelessWidget {
  const _Centro({
    required this.icono,
    required this.titulo,
    required this.texto,
    required this.accion,
    required this.alTocar,
  });
  final IconData icono;
  final String titulo;
  final String texto;
  final String accion;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
            Icon(icono, size: 48, color: AppColors.textoSecundario),
            const SizedBox(height: 12),
            Text(titulo, style: AppTypography.tituloMedio, textAlign: TextAlign.center),
            const SizedBox(height: 6),
            Text(texto, style: AppTypography.cuerpo, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: alTocar, child: Text(accion)),
          ]),
        ),
      );
}
