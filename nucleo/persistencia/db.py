# -*- coding: utf-8 -*-
"""
================================================================================
 PERSISTENCIA  --  SQLite local, mismo esquema que supabase/01_schema.sql
================================================================================

Por que existe
--------------
Nada se guardaba en ningun lado: nucleo/canales/api.py mantenia sesion e
historial solo en memoria del proceso, perdidos en cada reinicio. Sin
persistencia no hay forma de saber "cuando fue el ultimo contacto con este
lead", que es el prerrequisito de cualquier agente proactivo (seguimiento
de ventas, recordatorios).

Por que SQLite y no Supabase
------------------------------
Las credenciales de Supabase en .env no son reales: son los JWT de
demostracion publicos que trae cualquier instalacion self-hosted sin
configurar (`iss: "supabase-demo"`), y DATABASE_URL tiene el placeholder
'your-tenant-id' sin rellenar. Provisionar un proyecto real es una decision
de ustedes (la region se elige una sola vez, antes de crear el proyecto).

Las tablas de aca reproducen a proposito las columnas de
asistente.conversations/asistente.messages (supabase/01_schema.sql) --
sin RLS, sin roles de Postgres, sin pgvector, eso es exclusivo de la
migracion futura. Migrar de esto a Supabase real deberia ser sobre todo
un volcado de datos, no una reescritura.

Que NO guarda
--------------
Igual que el resto del proyecto: nunca la respuesta cruda de una API de
negocio (WispHub, BottleCRM...) -- eso lo decide nucleo/seguridad/
listas_blancas.py antes de que el dato llegue aca. Lo que se guarda es la
conversacion (lo que el usuario escribio, lo que el asistente respondio),
igual que ya decidia el PRD para 'messages'.
================================================================================
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

RUTA_DB_POR_DEFECTO = "datos/asistente.db"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    canal TEXT NOT NULL,
    usuario_externo TEXT NOT NULL,
    rol_efectivo TEXT,
    estado TEXT NOT NULL DEFAULT 'abierta',
    escalada_a_humano INTEGER NOT NULL DEFAULT 0,
    motivo_escalamiento TEXT,
    creado_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizado_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (tenant, canal, usuario_externo)
);

CREATE INDEX IF NOT EXISTS conversations_tenant_idx
    ON conversations (tenant, estado, actualizado_en DESC);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    rol TEXT NOT NULL,
    contenido TEXT,
    creado_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS messages_conv_idx
    ON messages (conversation_id, creado_en);
"""


def _ruta_db() -> Path:
    ruta = Path(os.environ.get("RUTA_DB", RUTA_DB_POR_DEFECTO))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


@contextmanager
def conectar():
    con = sqlite3.connect(_ruta_db())
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(_ESQUEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def registrar_mensaje(tenant: str, canal: str, usuario_externo: str,
                      rol_efectivo: str, rol: str, contenido: str) -> None:
    """
    Une una fila de conversacion (crea si no existe) con una fila de
    mensaje, y actualiza 'actualizado_en' -- es la unica señal que necesita
    un scheduler para saber "hace cuanto no le escribimos a este usuario".
    """
    with conectar() as con:
        con.execute(
            """INSERT INTO conversations (tenant, canal, usuario_externo, rol_efectivo)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (tenant, canal, usuario_externo) DO UPDATE SET
                   actualizado_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                   rol_efectivo = excluded.rol_efectivo""",
            (tenant, canal, usuario_externo, rol_efectivo))
        conv_id = con.execute(
            """SELECT id FROM conversations
               WHERE tenant = ? AND canal = ? AND usuario_externo = ?""",
            (tenant, canal, usuario_externo)).fetchone()[0]
        con.execute(
            "INSERT INTO messages (conversation_id, rol, contenido) VALUES (?, ?, ?)",
            (conv_id, rol, contenido))


def ultima_actividad(tenant: str, canal: str | None = None) -> list[dict]:
    """Una fila por conversacion: usuario_externo + cuando fue la ultima vez
    que se le escribio o respondio. Insumo del detector de seguimientos."""
    with conectar() as con:
        con.row_factory = sqlite3.Row
        if canal:
            filas = con.execute(
                """SELECT canal, usuario_externo, rol_efectivo, estado, actualizado_en
                   FROM conversations WHERE tenant = ? AND canal = ?
                   ORDER BY actualizado_en DESC""",
                (tenant, canal)).fetchall()
        else:
            filas = con.execute(
                """SELECT canal, usuario_externo, rol_efectivo, estado, actualizado_en
                   FROM conversations WHERE tenant = ?
                   ORDER BY actualizado_en DESC""",
                (tenant,)).fetchall()
        return [dict(f) for f in filas]
