# Corpus documental

Los documentos fuente de cada tenant, uno por carpeta:

```
corpus/
  rapilink/
    G-GO-06.docx
    ...
  <otro-isp>/
```

**No se versionan.** Son binarios, pesan, y llevan procedimientos internos de
cada empresa. La fuente de verdad al ingerirlos pasa a ser Supabase Storage
(`asistente.documents.storage_path`), con su hash para detectar recargas.

## Formatos

| | |
|---|---|
| `.docx` | **Preferido.** Los titulos son estilos y las tablas son objetos: se fragmenta por seccion real y las tablas llegan enteras |
| `.md` | Igual de bueno; la estructura es explicita |
| `.pdf` | Ultimo recurso. No tiene estructura: los titulos son texto mas grande y las tablas son lineas con texto en coordenadas. Se reconstruyen por heuristica y a veces mal |

## A qué agente le llega (tabla de metadatos)

Un documento sin esta tabla no lo ve **ningún** agente — no es un descuido,
es la protección por defecto (fail-closed): asignarlo a un rol es un paso a
propósito, no algo que se pueda olvidar en silencio.

Las primeras filas del `.docx` traen una tabla de dos filas, encabezado y
valor:

| codigo | version | fecha | roles |
|---|---|---|---|
| G-GO-06 | 01 | 2026-08-01 | soporte, facturacion |

`roles` son los nombres tal cual figuran en `tenants/<slug>.config.yaml`
(`roles.*`), separados por coma. Un nombre que no exista ahí hace fallar la
carga con un error claro (`cli/cargar_corpus.py`), no se sube a medias.
Un documento puede aplicar a más de un rol; alcanza con listarlos todos.
