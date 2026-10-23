import 'dart:async';

import 'package:flutter/material.dart';

import 'core/avisos/avisos_push.dart';
import 'core/api/api_endpoints.dart';
import 'core/storage/secure_storage_service.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/app_shell.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final storage = SecureStorageService();

  // El servidor elegido manda desde el primer pedido del arranque.
  //
  // La URL vive en el almacenamiento seguro, pero `ApiEndpoints` la lee de
  // una variable que arranca con el valor de compilacion. Sin esta linea, la
  // aplicacion elegia el servidor recien al iniciar sesion, y todo lo que
  // pasara antes -- refrescar el token de una sesion ya abierta, por ejemplo
  // -- salia al servidor equivocado.
  ApiEndpoints.baseUrl = await storage.getBaseUrl();

  final hasSession = await storage.hasValidSession();

  // EL PUSH SE ENCIENDE DESPUES DE RUNAPP, Y A PROPOSITO
  // ----------------------------------------------------
  // Registrar el telefono habla con Firebase y con el servidor. Esperarlo acá
  // dejaría la pantalla en blanco mientras el técnico está parado frente a una
  // casa, por algo que no necesita para trabajar. Sin sesión no se enciende: el
  // registro es un pedido autenticado, y el token se ata a una persona.
  runApp(DexterCampoApp(hasValidSession: hasSession));

  if (hasSession) {
    unawaited(AvisosPush().arrancar());
  }
}

class DexterCampoApp extends StatelessWidget {
  final bool hasValidSession;

  const DexterCampoApp({super.key, required this.hasValidSession});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Dexter IA',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      // Sin sesión no hay contenedor: el shell existe solo del otro lado del
      // login, igual que antes lo hacía la pantalla de jornada.
      home: hasValidSession ? AppShell() : const LoginScreen(),
    );
  }
}
