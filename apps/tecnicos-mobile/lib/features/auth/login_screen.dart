import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';
import '../../core/storage/ciclo_de_vida_local.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../shell/app_shell.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController(
    text: kDebugMode ? 'carlos.tecnico@rapilink.com' : '',
  );
  final _passwordController = TextEditingController();
  // El servidor que se fijó al compilar (`--dart-define=BACKEND_URL=...`).
  //
  // Antes, en depuración, este campo forzaba `127.0.0.1:8000` e ignoraba lo
  // que se hubiera pasado al compilar: apuntar la aplicación a otro backend
  // parecía funcionar y no tenía ningún efecto, había que corregirlo a mano en
  // cada arranque. Ahora el valor de compilación manda, y en depuración sigue
  // siendo editable para poder cambiarlo sin recompilar.
  final _serverUrlController = TextEditingController(
    text: ApiEndpoints.defaultEnvironmentUrl,
  );

  final _storage = SecureStorageService();
  final _apiClient = ApiClient();
  final _syncService = SyncQueueService();

  bool _isLoading = false;
  bool _showPassword = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _checkExistingSession();
  }

  Future<void> _checkExistingSession() async {
    final hasSession = await _storage.hasValidSession();
    if (hasSession && mounted) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => AppShell()),
      );
    }
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final baseUrl = kDebugMode
          ? _serverUrlController.text.trim()
          : ApiEndpoints.defaultEnvironmentUrl;
      await _storage.setBaseUrl(baseUrl);

      final response = await _apiClient.post(
        ApiEndpoints.login,
        data: {
          'email': _emailController.text.trim(),
          'password': _passwordController.text,
        },
      );

      dynamic rawData = response.data;
      if (rawData is String) {
        try {
          rawData = jsonDecode(rawData);
        } catch (_) {}
      }

      if (response.statusCode == 200 && rawData is Map) {
        final data = Map<String, dynamic>.from(rawData);
        final accessToken = data['access_token'] ?? data['access'];
        final refreshToken = data['refresh_token'] ?? data['refresh'];
        final currentOrg = data['current_org'] is Map ? data['current_org'] : {};
        final user = data['user'] is Map ? data['user'] : {};

        // La identidad sale SIEMPRE de la respuesta del servidor, nunca de
        // algo que el teléfono pueda elegir: es la que particiona todo lo que
        // se guarda localmente.
        //
        // Y sin valores de relleno. Antes, una respuesta sin organización
        // caía en una organización inventada y una sin perfil en un perfil
        // inventado: dos personas distintas en esa situación compartían una
        // misma partición ficticia, y una veía las órdenes de la otra. Justo
        // el agujero que el resto de este trabajo cierra. Más abajo se
        // rechaza el ingreso si falta alguno de los dos.
        final orgId = currentOrg['id']?.toString() ?? '';
        final orgName = currentOrg['name']?.toString() ?? 'Organización';
        final email = user['email']?.toString() ?? _emailController.text.trim();
        String profileId = user['profile_id']?.toString() ?? user['id']?.toString() ?? '';
        String name = user['name']?.toString() ?? 'Carlos Técnico';

        // 1. Guardar tokens de autenticación
        await _storage.saveTokens(
          accessToken: accessToken,
          refreshToken: refreshToken,
        );

        // 2. Invocar bootstrap para obtener el profile_id de campo y capacidades
        try {
          final bootRes = await _apiClient.get(ApiEndpoints.bootstrap);
          dynamic bootData = bootRes.data;
          if (bootData is String) {
            try {
              bootData = jsonDecode(bootData);
            } catch (_) {}
          }
          if (bootRes.statusCode == 200 && bootData is Map) {
            final u = bootData['usuario'] is Map ? bootData['usuario'] : {};
            if (u['id'] != null) profileId = u['id'].toString();
            if (u['nombre'] != null) name = u['nombre'].toString();
          }
        } catch (_) {}

        // Fail-closed: sin identidad completa no se entra.
        //
        // Sin organización no hay órdenes que ver -- todo el backend filtra
        // por ella -- así que entrar igual solo serviría para dejar datos
        // bajo una identidad que no identifica a nadie. Se cierra la sesión
        // que se acababa de abrir para no dejar tokens sueltos.
        if (orgId.isEmpty || profileId.isEmpty) {
          await _storage.clearSession();
          if (mounted) {
            setState(() {
              _isLoading = false;
              _errorMessage = 'Tu cuenta entró, pero no tiene una organización '
                  'ni un perfil activos. Pedile a un administrador que te '
                  'asigne uno antes de volver a intentar.';
            });
          }
          return;
        }

        await _storage.saveSessionData(
          orgId: orgId,
          orgName: orgName,
          profileId: profileId,
          email: email,
          name: name,
        );

        // 3. Dejar el teléfono limpio de lo que no es de quien acaba de entrar.
        //
        // Un teléfono de cuadrilla pasa de mano en mano. Lo que dejó la cuenta
        // anterior no se puede mostrar acá -- el filtro por identidad ya lo
        // impide -- pero tampoco tiene por qué seguir en el disco: son nombres,
        // direcciones y fotos de casas de clientes.
        //
        // Lo único que sobrevive es el trabajo ajeno SIN SUBIR. Ese no se
        // borra: no es de quien entra, así que no lo ve, pero destruirlo
        // tampoco le corresponde a esta pantalla. Vuelve cuando esa cuenta
        // entre de nuevo.
        try {
          final limpieza = await CicloDeVidaLocal(LocalDatabase()).prepararPara(
            orgId: orgId,
            profileId: profileId,
          );
          if (limpieza.hayTrabajoAjenoRetenido) {
            debugPrint(
              '[sesion] se conservaron datos sin sincronizar de '
              '${limpieza.aisladas.length} cuenta(s) anterior(es) en este equipo.',
            );
          }
        } catch (e) {
          // Que la limpieza falle no puede impedir entrar a trabajar: se
          // reintenta en el próximo inicio de sesión.
          debugPrint('[sesion] no se pudo preparar el almacenamiento local: $e');
        }

        // 4. Descargar órdenes iniciales
        await _syncService.procesarCola();

        if (mounted) {
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(builder: (_) => AppShell()),
          );
        }
      } else {
        setState(() {
          _errorMessage = 'Credenciales no válidas.';
        });
      }
    } on DioException catch (dioErr) {
      String? serverDetail;
      if (dioErr.response?.data is Map) {
        serverDetail = dioErr.response?.data['detail']?.toString() ??
            dioErr.response?.data['error']?.toString();
      } else if (dioErr.response?.data != null) {
        serverDetail = dioErr.response?.data.toString();
      }
      setState(() {
        if (serverDetail != null && serverDetail.isNotEmpty) {
          _errorMessage = serverDetail;
        } else if (dioErr.response?.statusCode == 401 || dioErr.response?.statusCode == 400) {
          _errorMessage = 'Email o contraseña incorrectos.';
        } else {
          _errorMessage = 'Error de conexión: ${dioErr.message}';
        }
      });
    } catch (e) {
      setState(() {
        _errorMessage = 'Error inesperado: $e';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(
                    Icons.handyman_rounded,
                    size: 64,
                    color: AppTheme.primaryBlue,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'DEXTER IA',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w900,
                      color: AppTheme.primaryDark,
                      letterSpacing: 1.5,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Operaciones y Cuadrillas en Terreno',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  const SizedBox(height: 32),
                  if (_errorMessage != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppTheme.errorRed.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: AppTheme.errorRed.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: AppTheme.errorRed, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(color: AppTheme.errorRed, fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  if (kDebugMode) ...[
                    TextFormField(
                      controller: _serverUrlController,
                      decoration: const InputDecoration(
                        labelText: 'Servidor Backend (Debug Dev)',
                        prefixIcon: Icon(Icons.dns_outlined),
                        helperText: 'Herramienta de desarrollo. En producción viene fijada por build.',
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Correo electrónico',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    validator: (value) =>
                        value == null || value.isEmpty ? 'Ingrese su correo' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _passwordController,
                    obscureText: !_showPassword,
                    decoration: InputDecoration(
                      labelText: 'Contraseña',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _showPassword ? Icons.visibility_off : Icons.visibility,
                        ),
                        onPressed: () {
                          setState(() {
                            _showPassword = !_showPassword;
                          });
                        },
                      ),
                    ),
                    validator: (value) =>
                        value == null || value.isEmpty ? 'Ingrese su contraseña' : null,
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: _isLoading ? null : _handleLogin,
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : const Text('INGRESAR AL SISTEMA'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
