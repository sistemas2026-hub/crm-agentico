# Fuentes de Dexter Campo

Las dos familias del sistema visual "Field Ops Precision" van empaquetadas en la
aplicación. No se descargan en tiempo de ejecución: el técnico trabaja sin
conexión, y una fuente que no llega deja la pantalla con otra tipografía.

| Familia | Uso | Origen | Versión | Licencia |
|---|---|---|---|---|
| Geist | Texto de interfaz | <https://github.com/vercel/geist-font> (release oficial) | v1.7.2 | SIL Open Font License 1.1 — `OFL-Geist.txt` |
| JetBrains Mono | Datos técnicos: mediciones, seriales, códigos, identificadores | <https://github.com/JetBrains/JetBrainsMono> (release oficial) | v2.304 | SIL Open Font License 1.1 — `OFL-JetBrainsMono.txt` |

La OFL permite empaquetar y redistribuir las fuentes dentro de una aplicación,
incluso comercial, mientras se conserve el aviso de copyright y la licencia
—por eso los dos `OFL-*.txt` viven acá al lado y no se borran—, y siempre que
no se vendan las fuentes por separado.

## Pesos incluidos, y por qué solo esos

Se incluyen únicamente los que la escala tipográfica usa. Cada peso de más son
unos 125 KB (Geist) o 270 KB (JetBrains Mono) dentro del instalador, sin que
nada los muestre.

| Archivo | Peso | Dónde se usa |
|---|---|---|
| `Geist-Regular.ttf` | 400 | Cuerpo y texto chico |
| `Geist-Medium.ttf` | 500 | Cuerpo grande |
| `Geist-SemiBold.ttf` | 600 | Títulos medianos y chicos, botones |
| `Geist-Bold.ttf` | 700 | Título grande |
| `JetBrainsMono-Medium.ttf` | 500 | Etiquetas técnicas chicas |
| `JetBrainsMono-SemiBold.ttf` | 600 | Etiquetas técnicas grandes |
| `JetBrainsMono-Bold.ttf` | 700 | Mediciones (potencia, metraje, conteos) |

No se incluye ninguna cursiva: el diseño no usa ninguna.

## Cómo se nombran en el código

Los nombres de las familias viven **solo** en `lib/core/theme/app_typography.dart`
(`AppTypography.familiaTexto` y `AppTypography.familiaMono`). Ningún widget
escribe `'Geist'` ni `'JetBrainsMono'` directamente, así que cambiar de
tipografía es tocar un archivo.

## Al actualizar una versión

Bajar el `.zip` del release oficial del repositorio de arriba, copiar solo los
pesos de la tabla, reemplazar también el `OFL-*.txt` que venga en ese release y
actualizar la versión en esta tabla.
