import sqlite3
from pathlib import Path
from contextlib import contextmanager

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
    with connectar() as conn:
        cursor = conn.execute("""
            INSERT INTO alumnos (numero_de_cuenta, nombre) VALUES (?, ?)""", (numero_de_cuenta.strip(), nombre.strip())
        )
        return cursor.lastrowid

def obtener_alumnos(solo_activos=False):
    '''Obetener una lista de alumnos registrados'''
    consulta = """SELECT id_alumno, numero_de_cuenta, nombre, activo From alumnos"""

    if solo_activos:
        consulta += " Where activo = 1"

    consulta += "Order by numero_de_cuenta"

    with conectar() as conn:
        filas = conn.execute(consulta).fetchall()
        return [dict(fila) for fila in filas]

def buscar_alumno_por_cuenta(cuenta):
    with connectar() as conn:
        fila = conn.execute("""
            SELECT id_alumno, numero_de_cuenta, nombre, activo FROM alumnos WHERE numero_de_cuenta = ?""", (cuenta.strip(),)
        ).fetchone()

        return dict(fila) if fila else None

def buscar_alumno_por_id(id_alumno):
    with connectar() as conn:
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

def cambiar_estado_alumno(id_alumno, activo):
    with connectar() as conn:
        cursor = conn.execute("""
            UPDATE alumnos SET activo = ? WHERE id_alumno = ?""", (int(activo), id_alumno)
        )

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
        consulta += "WHERE activo = 1"

    consulta += "ORDER BY nombre"

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

def cambiar_estado_inscripcion(id_inscripcion, activo):
    """Activa o desactiva una inscripción."""

    with conectar() as conn:
        cursor = conn.execute("""
            UPDATE inscripciones SET activo = ? WHERE id_inscripcion = ?""", (int(activo), id_inscripcion)
        )

        return cursor.rowcount > 0

def buscar_alumno_por_cuenta(cuenta_ingresada):
    """buscamos alumno por su número de cuenta."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM alumnos WHERE numero_de_cuenta = ?', (cuenta_ingresada.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

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

def obtener_historial_por_cuenta(cuenta, id_sesion):
        retardos = resumen["retardos"]
        faltas = resumen["faltas"]

        total = asistencias + retardos + faltas

        porcentaje = (
            asistencias / total * 100
            if total else 0
        )

        # Registros detallados.
        registros = conn.execute("""
            SELECT s.fecha, s.hora_inicio, s.hora_fin, r.fecha_hora, r.estado FROM registros AS r JOIN inscripciones AS i ON r.id_inscripcion = i.id_inscripcion JOIN sesiones AS s ON r.id_sesion = s.id_sesion WHERE i.id_alumno = ? AND s.id_clase = ? ORDER BY s.fecha DESC, s.hora_inicio DESC""", (id_alumno, id_clase)
        ).fetchall()

        # Actividad agrupada por fecha.
        actividad = conn.execute("""
            SELECT s.fecha, r.estado, COUNT(*) AS cantidad FROM registros AS r JOIN inscripciones AS i ON r.id_inscripcion = i.id_inscripcion JOIN sesiones AS s ON r.id_sesion = s.id_sesion WHERE i.id_alumno = ? AND s.id_clase = ? GROUP BY s.fecha, r.estado ORDER BY s.fecha""", (id_alumno, id_clase)
        ).fetchall()

        return {
            "alumno": {
                "id_alumno": id_alumno,
                "numero_de_cuenta": alumno["numero_de_cuenta"],
                "nombre": alumno["nombre"],
                "clase": alumno["clase"]
            },
            "resumen": {
                "asistencias": asistencias,
                "retardos": retardos,
                "faltas": faltas,
                "porcentaje": round(porcentaje, 2)
            },
            "registros": [dict(r) for r in registros],
            "actividad": [dict(a) for a in actividad]
        }

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
            UPDATE sesiones SET estado = 'finalizada' WHERE id_sesion = ?""", (id_sesion,)
        )

        return True

def obtener_inscripcion_activa(id_alumno, id_clase):
    """Obtiene la inscripción activa de un alumno en una clase."""

    with conectar() as conn:
        fila = conn.execute("""
            SELECT id_inscripcion FROM inscripciones WHERE id_alumno = ? AND id_clase = ? AND activo = 1""", (id_alumno, id_clase)
        ).fetchone()

        return dict(fila) if fila else None
