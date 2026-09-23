# -*- coding: utf-8 -*-
"""Rutas del modulo de operaciones. Ninguna ejecuta acciones externas."""

from django.urls import path

from operaciones import views

app_name = "operaciones"

urlpatterns = [
    path("propuestas/", views.PropuestasView.as_view(), name="propuestas"),
    path("propuestas/<uuid:propuesta_id>/", views.PropuestaDetalleView.as_view(),
         name="propuesta-detalle"),
    path("propuestas/<uuid:propuesta_id>/revisar/",
         views.RevisarPropuestaView.as_view(), name="propuesta-revisar"),
    path("propuestas/<uuid:propuesta_id>/cancelar/",
         views.CancelarPropuestaView.as_view(), name="propuesta-cancelar"),
    path("supervisor/ciclo/", views.CicloSupervisorView.as_view(), name="ciclo"),
    #  A-3.3. GET lista, POST registra. Sin PUT ni DELETE a proposito: la
    #  politica de correccion todavia no esta definida (ver DisponibilidadView).
    path("disponibilidad/", views.DisponibilidadView.as_view(),
         name="disponibilidad"),
    #  Los planes semanales de la organizacion. GET y solo GET: existe porque
    #  'campo/trabajos/<pk>/programar/' pide un 'programacion_semanal_id' que
    #  hasta ahora no se podia averiguar por la API.
    path("programacion/", views.ProgramacionesView.as_view(),
         name="programaciones"),
    #  M03-C. Publicar un plan semanal: borrador -> publicada, y nada mas.
    #  No ejecuta la programacion ni toca ninguna orden.
    #  M03-E2. Lectura de la jornada, en orden reproducible. Es un GET: no
    #  reordena, no recompacta y no resuelve empates -- los cuenta.
    path("programacion/jornada/", views.JornadaView.as_view(),
         name="programacion-jornada"),
    #  M03-E5-B. Secuenciar la jornada entera en UNA transaccion. No reprograma
    #  ninguna orden ni toca su asignacion: solo el orden propuesto.
    path("programacion/jornada/secuenciar/",
         views.SecuenciarJornadaView.as_view(), name="jornada-secuenciar"),
    #  M03-E4. Cambiar el orden propuesto de una linea. NO reprograma: no toca
    #  'programada_para', ni el dia, ni el plan, ni ninguna otra linea.
    path("programacion/linea/<uuid:linea_id>/secuencia/",
         views.SecuenciaLineaView.as_view(), name="linea-secuencia"),
    #  M03-G. Capacidad operacional de una jornada. Es un GET y solo un GET:
    #  no reprograma, no reasigna y no guarda ningun "porcentaje de capacidad".
    #  M02. Actividades operativas: lo que falta hacer. Cuatro rutas, y las
    #  transiciones son explicitas -- no hay PATCH sobre 'estado_operativo'.
    #  Ninguna ejecuta acciones externas.
    path("actividades/", views.ActividadesView.as_view(), name="actividades"),
    path("actividades/<uuid:actividad_id>/",
         views.ActividadDetalleView.as_view(), name="actividad-detalle"),
    path("actividades/<uuid:actividad_id>/transicion/",
         views.TransicionActividadView.as_view(), name="actividad-transicion"),
    #  M09-M. Los dos asistentes operativos. Escriben propuestas en la cola que
    #  ya existe y nada mas: no programan, no asignan y no ejecutan.
    #  El dominio va en el cuerpo, no en la ruta: un '<str:>' en el path
    #  habria necesitado una excepcion en el guarda de rutas malformadas.
    path("asistentes/", views.AsistenteView.as_view(), name="asistente"),
    #  M11. Indicadores y reportes. Son GET y solo GET: no guardan ningun KPI,
    #  no crean actividad de negocio y no corren el ciclo del Supervisor.
    path("indicadores/", views.IndicadoresView.as_view(), name="indicadores"),
    path("actividad-supervisor/", views.ActividadSupervisorView.as_view(),
         name="actividad-supervisor"),
    path("reportes/", views.ReportesView.as_view(), name="reportes"),
    path("capacidad/jornada/", views.CapacidadJornadaView.as_view(),
         name="capacidad-jornada"),
    path("programacion/<uuid:programacion_id>/publicar/",
         views.PublicarProgramacionView.as_view(), name="programacion-publicar"),
    #  El ultimo paso del ciclo del plan: publicada -> cerrada. 'cerrada' estaba
    #  declarada desde M03 y ninguna funcion la asignaba.
    path("programacion/<uuid:programacion_id>/cerrar/",
         views.CerrarProgramacionView.as_view(), name="programacion-cerrar"),
]
