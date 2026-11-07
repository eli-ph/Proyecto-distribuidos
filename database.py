import sqlite3

DB_NAME = "asistencia.db"

def init_db():
    #tablas
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alumnos (
            numero_de_cuenta TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            asistencias INTEGER DEFAULT 0,
            retardos INTEGER DEFAULT 0,
            faltas INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  
            numero_de_cuenta TEXT,
            hora TEXT,
            estado TEXT,
            color TEXT,
            ip_cliente TEXT,
            FOREIGN KEY (numero_de_cuenta) REFERENCES alumnos (numero_de_cuenta)
        )
    ''')
    
    ALUMNOS_INSCRITOS = [
        ("318000001", "Elizabeth Portilla Hermenegildo"),
        ("318000002", "Kristoff Pineda González"),
        ("318000003", "Maria Fernanda Hernández López"),
        ("318000004", "Gabriel Martínez"),
        ("318000005", "Diego Antonio Ramírez"),
    ]
    
    for cuenta, nombre in ALUMNOS_INSCRITOS:
        cursor.execute('''
            INSERT OR IGNORE INTO alumnos (numero_de_cuenta, nombre, asistencias, retardos, faltas)
            VALUES (?, ?, 0, 0, 0)
        ''', (cuenta, nombre))
        
    conn.commit()
    conn.close()

def obtener_todos_alumnos_dict():
    """info de los alumnos ordenados por cuenta."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM alumnos')
    rows = cursor.fetchall()
    conn.close()
    
    # regresamos con el número de cuenta como llave principal
    return {row['numero_de_cuenta']: {
        'nombre': row['nombre'],
        'asistencias': row['asistencias'],
        'retardos': row['retardos'],
        'faltas': row['faltas']
    } for row in rows}

def buscar_alumno_por_cuenta(cuenta_ingresada):
    """buscamos alumno por su número de cuenta."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM alumnos WHERE numero_de_cuenta = ?', (cuenta_ingresada.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def actualizar_y_registrar(cuenta, estado, color, hora_str, ip_cliente):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if estado == "Asistencia":
        cursor.execute('UPDATE alumnos SET asistencias = asistencias + 1 WHERE numero_de_cuenta = ?', (cuenta,))
    elif estado == "Retardo":
        cursor.execute('UPDATE alumnos SET retardos = retardos + 1 WHERE numero_de_cuenta = ?', (cuenta,))
    else:
        cursor.execute('UPDATE alumnos SET faltas = faltas + 1 WHERE numero_de_cuenta = ?', (cuenta,))
        
    cursor.execute('''
        INSERT INTO registros (numero_de_cuenta, hora, estado, color, ip_cliente)
        VALUES (?, ?, ?, ?, ?)
    ''', (cuenta, hora_str, estado, color, ip_cliente))
    
    conn.commit()
    conn.close()

def obtener_historial_por_cuenta(cuenta):
    """resumen por número de cuenta."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM alumnos WHERE numero_de_cuenta = ?', (cuenta.strip(),))
    alumno_row = cursor.fetchone()
    
    if not alumno_row:
        conn.close()
        return None
        
    cursor.execute('SELECT * FROM registros WHERE numero_de_cuenta = ?', (cuenta.strip(),))
    registros_rows = cursor.fetchall()
    conn.close()
    
    return {
        'numero_de_cuenta': alumno_row['numero_de_cuenta'],
        'alumno': alumno_row['nombre'],
        'asistencias': alumno_row['asistencias'],
        'retardos': alumno_row['retardos'],
        'faltas': alumno_row['faltas'],
        'registros': [dict(r) for r in registros_rows]
    }