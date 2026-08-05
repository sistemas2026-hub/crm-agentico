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
