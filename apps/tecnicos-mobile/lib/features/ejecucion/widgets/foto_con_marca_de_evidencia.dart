/// LA FOTO DE UNA EVIDENCIA, CON LA MARCA QUE VA A LLEVAR (13/11/2026).
///
/// La miniatura de cada requisito muestra la foto ENTERA --no recortada-- con
/// la banda de la empresa en su lugar real. Antes era `BoxFit.cover` en 140 px
/// de alto, y un recorte esconde justo el borde donde va la banda. Tocarla la
/// abre a pantalla completa, donde la banda se lee y se puede acercar.
///
/// Lo que se ve acá es una VISTA PREVIA: el archivo lo marca el servidor al
/// subir (ver `core/marca/marca_de_agua.dart`). Por eso el texto de la
/// pantalla completa dice «así sale», no «así quedó».
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import '../../../core/marca/marca_de_agua.dart';
import '../../../core/marca/marca_de_agua_local.dart';
import '../../../core/theme/app_theme.dart';

/// Los datos de la foto a partir de la fila local de `cola_evidencias`.
///
/// `capturada_en` está en milisegundos y `metadatos_captura_json` es el mismo
/// texto que sube: la vista previa lee exactamente lo que el servidor va a
/// recibir, no una copia aparte.
DatosDeLaFoto datosDeLaFila(
  MarcaDeLaEmpresa marca,
  Map<String, dynamic> fila, {
  required bool esCaptura,
}) {
  final dynamic ms = fila['capturada_en'];
  Map<String, dynamic> metadatos = const <String, dynamic>{};
  final dynamic crudo = fila['metadatos_captura_json'];
  if (crudo is String && crudo.isNotEmpty) {
    try {
      final dynamic j = jsonDecode(crudo);
      if (j is Map) metadatos = Map<String, dynamic>.from(j);
    } catch (_) {}
  }
  return marca.datosDe(
    fecha: ms is int ? DateTime.fromMillisecondsSinceEpoch(ms) : null,
    metadatos: metadatos,
    esCaptura: esCaptura,
    esFirma: esRequisitoDeFirma((fila['requisito_id'] ?? '').toString()),
  );
}

class MiniaturaConMarca extends StatelessWidget {
  const MiniaturaConMarca({
    super.key,
    required this.archivo,
    required this.marca,
    required this.datos,
    this.alto = 180,
  });

  final File archivo;
  final MarcaDeLaEmpresa marca;
  final DatosDeLaFoto datos;
  final double alto;

  @override
  Widget build(BuildContext context) {
    final bool conBanda = seEstampa(marca.configuracion, datos,
        hayLogo: marca.logo != null);
    return Semantics(
      button: true,
      label: conBanda
          ? 'Ver la foto con la marca de la empresa'
          : 'Ver la foto en grande',
      child: GestureDetector(
        onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => FotoConMarcaPantallaCompleta(
            archivo: archivo,
            marca: marca,
            datos: datos,
          ),
        )),
        child: ClipRRect(
          borderRadius: AppRadius.brTarjeta,
          child: Container(
            height: alto,
            width: double.infinity,
            color: const Color(0xFF111111),
            child: Stack(
              children: <Widget>[
                Positioned.fill(
                  child: FotoConMarca(
                    imagen: FileImage(archivo),
                    configuracion: marca.configuracion,
                    datos: datos,
                    logo: marca.logo,
                  ),
                ),
                const Positioned(
                  right: 6,
                  top: 6,
                  child: _InsigniaAmpliar(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _InsigniaAmpliar extends StatelessWidget {
  const _InsigniaAmpliar();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.55),
          borderRadius: BorderRadius.circular(6),
        ),
        child: const Icon(Icons.zoom_out_map, size: 16, color: Colors.white),
      );
}

class FotoConMarcaPantallaCompleta extends StatelessWidget {
  const FotoConMarcaPantallaCompleta({
    super.key,
    required this.archivo,
    required this.marca,
    required this.datos,
  });

  final File archivo;
  final MarcaDeLaEmpresa marca;
  final DatosDeLaFoto datos;

  @override
  Widget build(BuildContext context) {
    final bool conBanda = seEstampa(marca.configuracion, datos,
        hayLogo: marca.logo != null);
    final String pie = conBanda
        ? 'Así sale la foto en la plataforma y en el ticket.'
        : (marca.configuracion.activa
            ? 'Esta imagen no lleva marca (firma o captura de pantalla).'
            : 'Tu empresa no tiene la marca de agua prendida.');
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Vista previa'),
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Expanded(
              child: InteractiveViewer(
                maxScale: 6,
                child: Center(
                  child: FotoConMarca(
                    imagen: FileImage(archivo),
                    configuracion: marca.configuracion,
                    datos: datos,
                    logo: marca.logo,
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Text(
                pie,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
