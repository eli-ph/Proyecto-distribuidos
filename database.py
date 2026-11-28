import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

# Busca el archivo en la direccion exacta donde se encuentra el .py  que contiene esta linea
DB_NAME = Path(__file__).resolve().parent / "registros.db" 

@contextmanager
def conectar():
    conn = sqlite3.connect(DB_NAME) # Establece la conexion
    conn.row_factory = sqlite3.Row # Row permite acceder a los datos por nombre de la columna, como si fuera una diccionario
    conn.execute("PRAGMA foreign_keys = ON")

    try:
      yield conn # Entrega la conxion para usar el with, pausa la funcion mientras se hacen las consultas
      conn.commit() # Si no hay errores guarda los cambios
    except Exception:
      conn.rollback() # Revierte los cambios en caso de error
      raise # Informa del error al programa principal
    finally:
      conn.close() # Cierra la DB

def init_db():

    tablas_requeridas = { 
        "alumnos", "clases", "inscripciones", "sesiones", "dispositivos", "registros"
    }

    with conectar() as conn:
        filas = conn.execute("""
            SELECT name FROM sqlite_master Where type='table'
        """).fetchall()

    tablas_existentes = {fila["name"] for fila in filas}

    faltantes = tablas_requeridas - tablas_existentes

    if faltantes:
       raise RuntimeError(f"La base de datos no tiene las tablas requeridas: " f"{', '.join(sorted(faltantes))}")

# --------------------
# Alumnos
# --------------------

def crear_alumno(numero_de_cuenta, nombre): 
    '''Permite registrar a un alumno nuevo.'''
    with conectar() as conn:
        cursor = conn.execute("""
            INSERT INTO alumnos (numero_de_cuenta, nombre) VALUES (?, ?)""", (numero_de_cuenta.strip(), nombre.strip())
        )
        return cursor.lastrowid

def obtener_alumnos(solo_activos=False):
    '''Obetener una lista de alumnos registrados'''
    consulta = """SELECT id_alumno, numero_de_cuenta, nombre, activo From alumnos"""

    if solo_activos:
        consulta += " Where activo = 1"

    consulta += " ORDER BY numero_de_cuenta"

    with conectar() as conn:
        filas = conn.execute(consulta).fetchall()
        return [dict(fila) for fila in filas]

def buscar_alumno_por_cuenta(cuenta):
    with conectar() as conn:
        fila = conn.execute("""
            SELECT id_alumno, numero_de_cuenta, nombre, activo FROM alumnos WHERE numero_de_cuenta = ?""", (cuenta.strip(),)
        ).fetchone()

        return dict(fila) if fila else None

def buscar_alumno_por_id(id_alumno):
    with conectar() as conn:
        fila = conn.execute("""
            SELECT id_alumno, numero_de_cuenta, nombre, activo FROM alumnos WHERE id_alumno = ?""", (id_alumno,)
        ).fetchone()

        return dict(fila) if fila else None

def actualizar_alumno(id_alumno, numero_de_cuenta, nombre):
    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE alumnos SET numero_de_cuenta = ?, nombre = ? where id_alumno = ?""", (numero_de_cuenta.strip(), nombre.strip(), id_alumno)
        )

        return cursor.rowcount > 0

def cambiar_estado_alumno(id_alumno, activo): # Maneja alta (1) y baja (0) 
    """Activa (1) o da de baja (0) a un alumno en el sistema."""
    estado_activo = int(bool(activo))

    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE alumnos SET activo = ? WHERE id_alumno = ?""", (estado_activo, id_alumno)
        )

        # Si se da de baja al alumno, limpia registros pendientes en sesiones activas
        if estado_activo == 0:
            conn.execute("""
                DELETE FROM registros
                WHERE estado = 'pendiente'
                  AND id_inscripcion IN (
                      SELECT id_inscripcion FROM inscripciones WHERE id_alumno = ?
                  )
                  AND id_sesion IN (
                      SELECT id_sesion FROM sesiones WHERE estado = 'activa'
                  )
            """, (id_alumno,))

        return cursor.rowcount > 0

# --------------------
# Clases
# --------------------

def crear_clase(nombre, descripcion=None):
    with conectar() as conn:
        cursor = conn.execute("""
            INSERT INTO clases (nombre, descripcion) VALUES (?, ?)""", (nombre.strip(), descripcion)
        )

        return cursor.lastrowid

def obtener_clases(solo_activas=False):
    consulta = """SELECT id_clase, nombre, descripcion, activo FROM clases"""

    if solo_activas:
        consulta += " WHERE activo = 1"

    consulta += " ORDER BY nombre"

    with conectar() as conn:
        filas = conn.execute(consulta).fetchall()
        return [dict(fila) for fila in filas]

def obtener_clase(id_clase):
    with conectar() as conn:
        fila = conn.execute("""
            SELECT id_clase, nombre, descripcion, activo FROM clases WHERE id_clase = ?""", (id_clase,)
        ).fetchone()

        return dict(fila) if fila else None

def actualizar_clase(id_clase, nombre, descripcion=None):
    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE clases SET nombre = ?, descripcion = ? WHERE id_clase = ?""", (nombre.strip(), descripcion, id_clase)
        )

        return cursor.rowcount > 0

def cambiar_estado_clase(id_clase, activo):
    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE clases SET activo = ? WHERE id_clase = ?""", (int(activo), id_clase)
        )

        return cursor.rowcount > 0

# --------------------
# Inscripciones
# --------------------

def inscribir_alumno(id_alumno, id_clase):
    """
    Inscribe un alumno en una clase.

    Si ya existe una inscripción inactiva, la reactiva.
    Si ya está activa, no genera otra inscripción.
    """

    with conectar() as conn:

        inscripcion = conn.execute("""
            SELECT id_inscripcion, activo FROM inscripciones WHERE id_alumno = ? AND id_clase = ?""", (id_alumno, id_clase)
        ).fetchone()

        if inscripcion:
            if not inscripcion["activo"]:
                conn.execute("""
                    UPDATE inscripciones SET activo = 1 WHERE id_inscripcion = ?""", (inscripcion["id_inscripcion"],)
                )

            return inscripcion["id_inscripcion"]

        cursor = conn.execute("""
            INSERT INTO inscripciones (id_alumno, id_clase) VALUES (?, ?)""", (id_alumno, id_clase)
        )

        return cursor.lastrowid

def obtener_inscripciones(id_clase=None, solo_activas=False):
    """
    Obtiene las inscripciones.

    Puede filtrarse por clase y por estado.
    """

    consulta = """SELECT i.id_inscripcion, i.id_alumno, i.id_clase, i.fecha_inscripcion, i.activo AS inscripcion_activa, a.numero_de_cuenta, a.nombre, a.activo AS alumno_activo, c.nombre AS clase FROM inscripciones AS i JOIN alumnos AS a ON i.id_alumno = a.id_alumno JOIN clases AS c ON i.id_clase = c.id_clase WHERE 1 = 1"""

    parametros = []

    if id_clase is not None:
        consulta += " AND i.id_clase = ?"
        parametros.append(id_clase)

    if solo_activas:
        consulta += " AND i.activo = 1 AND a.activo = 1"

    consulta += " ORDER BY a.numero_de_cuenta"

    with conectar() as conn:
        filas = conn.execute(consulta, parametros).fetchall()
        return [dict(fila) for fila in filas]

def cambiar_estado_inscripcion(id_inscripcion, activo): #  Maneja alta (1) y baja (0) de inscripción 
    """Activa (1) o da de baja (0) una inscripción en una clase."""
    estado_activo = int(bool(activo))

    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE inscripciones SET activo = ? WHERE id_inscripcion = ?""", (estado_activo, id_inscripcion)
        )

        # Si se da de baja la inscripción, limpia registros pendientes en sesiones activas
        if estado_activo == 0:
            conn.execute("""
                DELETE FROM registros
                WHERE estado = 'pendiente'
                  AND id_inscripcion = ?
                  AND id_sesion IN (
                      SELECT id_sesion FROM sesiones WHERE estado = 'activa'
                  )
            """, (id_inscripcion,))

        return cursor.rowcount > 0

def registrar_asistencia(id_sesion, id_inscripcion, id_dispositivo, fecha_hora, estado):
    """Actualiza el registro de asistencia de un alumno."""

    with conectar() as conn:

        # Comprobar que la inscripción pertenecea la clase de la sesión.
        cursor = conn.execute("""
            SELECT r.id_registro FROM registros AS r JOIN sesiones AS s ON r.id_sesion = s.id_sesion JOIN inscripciones AS i ON r.id_inscripcion = i.id_inscripcion WHERE r.id_sesion = ? AND r.id_inscripcion = ? AND i.id_clase = s.id_clase AND i.activo = 1 AND r.estado = 'pendiente'""", (id_sesion, id_inscripcion)
        )

        registro = cursor.fetchone()

        if not registro:
            return False

        cursor = conn.execute("""UPDATE registros SET id_dispositivo = ?, fecha_hora = ?, estado = ? WHERE id_registro = ? """, (id_dispositivo,fecha_hora, estado.lower(), registro["id_registro"])
        )

        return cursor.rowcount > 0

ESTADOS_VALIDOS = {"pendiente", "asistencia", "retardo", "falta"}
def actualizar_estado_registro(id_registro, nuevo_estado, fecha_hora=None): # <-- NUEVO
    """Modifica el estado (asistencia, retardo, falta, pendiente) de un registro específico."""
    estado_limpio = nuevo_estado.strip().lower()
    if estado_limpio not in ESTADOS_VALIDOS:
        raise ValueError(f"Estado no válido: {nuevo_estado}")

    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE registros
            SET estado = ?, fecha_hora = COALESCE(?, fecha_hora)
            WHERE id_registro = ?
        """, (estado_limpio, fecha_hora, id_registro))

        return cursor.rowcount > 0

# --------------------
# Historial y lista general
# --------------------

# Columnas que cuentan asistencias, retardos y faltas (los pendientes no cuentan).
# Las consultas que las usan ignoran registros de sesiones que ya no existen.
CONTEO_ESTADOS = """
    COALESCE(SUM(r.estado = 'asistencia'), 0) AS asistencias,
    COALESCE(SUM(r.estado = 'retardo'), 0) AS retardos,
    COALESCE(SUM(r.estado = 'falta'), 0) AS faltas
"""

def calcular_porcentaje(asistencias, retardos, faltas):
    """Porcentaje de asistencias sobre el total de sesiones registradas."""
    total = asistencias + retardos + faltas
    return round(asistencias / total * 100, 2) if total else 0

def obtener_historial_por_cuenta(cuenta):
    """
    Obtiene el historial de un alumno en todas las clases donde está inscrito.
    """
    with conectar() as conn:
        alumno = conn.execute("""
            SELECT id_alumno, numero_de_cuenta, nombre, activo FROM alumnos WHERE numero_de_cuenta = ?""", (cuenta.strip(),) #  incluye activo
        ).fetchone()

        if not alumno:
            return None

        clases = conn.execute(f"""
            SELECT i.id_inscripcion, c.id_clase, c.nombre AS clase, {CONTEO_ESTADOS} FROM inscripciones AS i JOIN clases AS c ON i.id_clase = c.id_clase LEFT JOIN registros AS r ON r.id_inscripcion = i.id_inscripcion AND r.id_sesion IN (SELECT id_sesion FROM sesiones) WHERE i.id_alumno = ? GROUP BY i.id_inscripcion ORDER BY c.nombre""", (alumno["id_alumno"],)
        ).fetchall()

        historial = []

        for clase in clases:
            registros = conn.execute("""
                SELECT r.id_registro, s.fecha, s.hora_inicio, s.hora_fin, r.fecha_hora, r.estado FROM registros AS r JOIN sesiones AS s ON r.id_sesion = s.id_sesion WHERE r.id_inscripcion = ? AND r.estado != 'pendiente' ORDER BY s.fecha DESC, s.hora_inicio DESC""", (clase["id_inscripcion"],) # <-- MODIFICADO: incluye r.id_registro
            ).fetchall()

            actividad = conn.execute("""
                SELECT s.fecha, r.estado, COUNT(*) AS cantidad FROM registros AS r JOIN sesiones AS s ON r.id_sesion = s.id_sesion WHERE r.id_inscripcion = ? AND r.estado != 'pendiente' GROUP BY s.fecha, r.estado ORDER BY s.fecha""", (clase["id_inscripcion"],)
            ).fetchall()

            historial.append({
                "id_inscripcion": clase["id_inscripcion"], # <-- MODIFICADO: expone id_inscripcion
                "id_clase": clase["id_clase"],
                "clase": clase["clase"],
                "resumen": {
                    "asistencias": clase["asistencias"],
                    "retardos": clase["retardos"],
                    "faltas": clase["faltas"],
                    "porcentaje": calcular_porcentaje(
                        clase["asistencias"], clase["retardos"], clase["faltas"]
                    )
                },
                "registros": [dict(r) for r in registros],
                "actividad": [dict(a) for a in actividad]
            })

        return {
            "alumno": {
                "id_alumno": alumno["id_alumno"],
                "numero_de_cuenta": alumno["numero_de_cuenta"],
                "nombre": alumno["nombre"],
                "activo": alumno["activo"] # <-- MODIFICADO: expone activo
            },
            "clases": historial
        }

def obtener_lista_general(id_clase):
    """Resumen de asistencias, retardos y faltas de cada alumno inscrito en una clase."""
    with conectar() as conn:
        filas = conn.execute(f"""
            SELECT a.id_alumno, i.id_inscripcion, a.numero_de_cuenta, a.nombre, {CONTEO_ESTADOS}
            FROM inscripciones AS i
            JOIN alumnos AS a ON i.id_alumno = a.id_alumno
            LEFT JOIN registros AS r ON r.id_inscripcion = i.id_inscripcion AND r.id_sesion IN (SELECT id_sesion FROM sesiones)
            WHERE i.id_clase = ? AND i.activo = 1 AND a.activo = 1
            GROUP BY i.id_inscripcion
            ORDER BY a.numero_de_cuenta""", (id_clase,) # incluye id_alumno, id_inscripcion y filtra a.activo = 1
        ).fetchall()

    lista = []

    for fila in filas:
        alumno = dict(fila)
        alumno["porcentaje"] = calcular_porcentaje(
            alumno["asistencias"], alumno["retardos"], alumno["faltas"]
        )
        lista.append(alumno)

    return lista

# Historial / resumen de sesiones para una clase
def obtener_historial_sesiones_clase(id_clase):
    """Devuelve cada sesión de una clase con el conteo de asistencias, retardos y faltas."""
    with conectar() as conn:
        filas = conn.execute(f"""
            SELECT
                s.id_sesion,
                s.fecha,
                s.hora_inicio,
                COALESCE(s.hora_fin, '-') AS hora_fin,
                s.estado,
                {CONTEO_ESTADOS}
            FROM sesiones AS s
            LEFT JOIN registros AS r ON r.id_sesion = s.id_sesion
            WHERE s.id_clase = ?
            GROUP BY s.id_sesion
            ORDER BY s.fecha DESC, s.hora_inicio DESC
        """, (id_clase,)).fetchall()

        return [dict(f) for f in filas]

def contar_sesiones_finalizadas(id_clase):
    """Número de sesiones ya finalizadas de una clase."""

    with conectar() as conn:
        fila = conn.execute("""
            SELECT COUNT(*) AS total FROM sesiones WHERE id_clase = ? AND estado = 'finalizada'""", (id_clase,)
        ).fetchone()

        return fila["total"]

def contar_sesiones_finalizadas_y_programadas(id_clase):
    """Total de sesiones finalizadas y programadas de una clase."""
    with conectar() as conn:
        fila = conn.execute("""
            SELECT COUNT(*) AS total
            FROM sesiones
            WHERE id_clase = ? AND estado IN ('finalizada', 'programada')
        """, (id_clase,)).fetchone()

        return fila["total"]
# --------------------
# Sesiones
# --------------------

def iniciar_sesion(id_sesion):
    """Activa una sesión y asigna pendiente a cada allumno."""

    with conectar() as conn:

        # Evitar que dos sesiones estén activas simultáneamente.
        conn.execute("BEGIN IMMEDIATE")

        sesion = conn.execute("""
            SELECT id_sesion, id_clase, estado FROM sesiones WHERE id_sesion = ?""", (id_sesion,)
        ).fetchone()

        if not sesion or sesion["estado"] != "programada":
            return False

        otra_sesion = conn.execute("""
            SELECT id_sesion FROM sesiones WHERE estado = 'activa' LIMIT 1"""
        ).fetchone()

        if otra_sesion:
            return False

        # Crear un registro pendiente por cada inscripción activa de un alumno activo en la clase.
        conn.execute("""
            INSERT INTO registros (id_sesion, id_inscripcion, estado) SELECT ?, i.id_inscripcion, 'pendiente' FROM inscripciones AS i JOIN alumnos AS a ON i.id_alumno = a.id_alumno WHERE i.id_clase = ? AND i.activo = 1 AND a.activo = 1""", (id_sesion, sesion["id_clase"])
        )

        # Activar la sesión.
        conn.execute("""
            UPDATE sesiones SET estado = 'activa' WHERE id_sesion = ?""", (id_sesion,)
        )

        return True

def obtener_sesion_activa():
    """Devuelve la sesión activa, si existe."""

    with conectar() as conn:

        sesion = conn.execute("""
            SELECT s.id_sesion, s.id_clase, s.fecha, s.hora_inicio, s.hora_fin, s.estado, c.nombre AS clase FROM sesiones AS s JOIN clases AS c ON s.id_clase = c.id_clase WHERE s.estado = 'activa' LIMIT 1"""
        ).fetchone()

        return dict(sesion) if sesion else None

def finalizar_sesion(id_sesion):
    """Finaliza una sesión y convierte pendientes en faltas."""
    hora_fin_actual = datetime.now().strftime("%H:%M")

    with conectar() as conn:

        conn.execute("BEGIN IMMEDIATE")

        sesion = conn.execute("""
            SELECT id_sesion, estado FROM sesiones WHERE id_sesion = ?""", (id_sesion,)
        ).fetchone()

        if not sesion or sesion["estado"] != "activa":
            return False

        # Los alumnos que no registraron asistencia o retardo reciben falta.
        conn.execute("""
            UPDATE registros SET estado = 'falta' WHERE id_sesion = ? AND estado = 'pendiente'""", (id_sesion,)
        )

        # Cambiar el estado de la sesión.
        conn.execute("""
            UPDATE sesiones SET estado = 'finalizada', hora_fin = ? WHERE id_sesion = ?
        """, (hora_fin_actual, id_sesion))

        return True

def obtener_inscripcion_activa(id_alumno, id_clase):
    """Obtiene la inscripción activa de un alumno en una clase."""

    with conectar() as conn:
        fila = conn.execute("""
            SELECT id_inscripcion FROM inscripciones WHERE id_alumno = ? AND id_clase = ? AND activo = 1""", (id_alumno, id_clase)
        ).fetchone()

        return dict(fila) if fila else None


def obtener_clases_activas():
    """Obtiene las materias disponibles para iniciar clase."""
    with conectar() as conn:
        filas = conn.execute("""
            SELECT id_clase, nombre, descripcion FROM clases WHERE activo = 1 Order BY nombre
        """).fetchall()
        return [dict(f) for f in filas]

def iniciar_sesion_tiempo_real(id_clase, hora_cierre=None):
    """
    Crea una nueva sesión en tiempo real y la activa.

    hora_cierre ("HH:MM") es la hora límite: si el profesor no finaliza
    la sesión, se cierra sola a esa hora. Si es None, no hay cierre automático.
    """
    ahora = datetime.now()
    fecha = ahora.strftime("%Y-%m-%d")
    hora_inicio = ahora.strftime("%H:%M")

    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")

        # Verificar que la sesion no exista
        otra = conn.execute("""
            SELECT id_sesion FROM sesiones WHERE estado = 'activa' LIMIT 1
        """).fetchone()

        if otra:
            return None

        cursor = conn.execute("""
            INSERT INTO sesiones (id_clase, fecha, hora_inicio, hora_fin, estado) VALUES (?, ?, ?, ?, 'activa')
        """, (id_clase, fecha, hora_inicio, hora_cierre))

        id_sesion = cursor.lastrowid

        # Marcar como pendiente a todos los alumnos inscritos
        conn.execute("""
            INSERT INTO registros (id_sesion, id_inscripcion, estado) SELECT ?, i.id_inscripcion, 'pendiente' FROM inscripciones AS i JOIN alumnos AS a ON i.id_alumno = a.id_alumno WHERE i.id_clase = ? AND i.activo = 1 AND a.activo = 1
        """, (id_sesion, id_clase))

        return id_sesion

def cerrar_sesion_vencida():
    """
    Si la sesión activa ya pasó su hora límite, la finaliza:
    los pendientes pasan a falta y se conserva la hora límite como hora de fin.

    Devuelve el id de la sesión cerrada, o None si no se cerró ninguna.
    """
    ahora = datetime.now()

    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")

        sesion = conn.execute("""
            SELECT id_sesion, fecha, hora_fin FROM sesiones WHERE estado = 'activa' LIMIT 1
        """).fetchone()

        if not sesion or not sesion["hora_fin"]:
            return None

        cierre = datetime.fromisoformat(f"{sesion['fecha']} {sesion['hora_fin']}")

        if ahora < cierre:
            return None

        conn.execute("""
            UPDATE registros SET estado = 'falta' WHERE id_sesion = ? AND estado = 'pendiente'
        """, (sesion["id_sesion"],))

        conn.execute("""
            UPDATE sesiones SET estado = 'finalizada' WHERE id_sesion = ?
        """, (sesion["id_sesion"],))

        return sesion["id_sesion"]
