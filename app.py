from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from datetime import datetime
import database
import sqlite3

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

database.init_db()

TOLERANCIA_MINUTOS = 15 # Puede ser NONE entonces cualquier llegada es asistencia

# -------------------
# Sesión vigente
# -------------------

def obtener_sesion_vigente():
    """
    Devuelve la sesión activa, pero antes la cierra si ya pasó su hora
    límite y avisa al dashboard del profesor.
    """
    cerrada = database.cerrar_sesion_vencida()

    if cerrada:
        socketio.emit('sesion_finalizada', {
            'id_sesion': cerrada, 'automatica': True
        })

    return database.obtener_sesion_activa()

# -------------------
# Vistas
# -------------------

@app.route('/')
def vista_laptop():
    return render_template('laptop.html')

@app.route('/lista-general')
def vista_lista_general():
    clases = database.obtener_clases(solo_activas=True)

    # La clase se elige con ?clase=ID; si no se indica o no existe, se usa la primera.
    id_clase = request.args.get('clase', type=int)
    clase = next((c for c in clases if c['id_clase'] == id_clase), None)

    if clase is None and clases:
        clase = clases[0]

    alumnos = database.obtener_lista_general(clase['id_clase']) if clase else []
    sesiones_historial = database.obtener_historial_sesiones_clase(clase['id_clase']) if clase else []  
    total_sesiones = (
        database.contar_sesiones_finalizadas_y_programadas(clase['id_clase'])
        if clase else 0
    )
    return render_template(
        'lista_general.html',
        clases=clases,
        clase=clase,
        alumnos=alumnos,
        total_sesiones=total_sesiones,
        sesiones_historial=sesiones_historial  
    )

@app.route('/alumno/<cuenta>')
def vista_perfil_alumno(cuenta):
    datos = database.obtener_historial_por_cuenta(cuenta)
    if not datos:
        return "Alumno no encontrado", 404
    return render_template('perfil_alumno.html', cuenta=cuenta)

@app.route('/marcar')
def vista_telefono():
    return render_template('telefono.html')

# -------------------
# Asistencias
# -------------------

@app.route('/api/sesion/iniciar', methods=['POST'])
def iniciar_sesion():
    data = request.get_json(silent=True) or {}
    id_sesion = data.get('id_sesion')

    if not id_sesion:
        return jsonify({'status': 'error', 'mensaje': 'No se indicó la sesión.'
        }), 400

    try:
        id_sesion = int(id_sesion)
        resultado = database.iniciar_sesion(id_sesion)

        if not resultado:
            return jsonify({
                'status': 'error', 'mensaje': 'No se pudo iniciar la sesión. Verifica que esté programada y que no exista otra sesión activa.'
            }), 409

    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'mensaje': 'No se pudo iniciar la sesion'
        }), 409

    sesion = database.obtener_sesion_activa()

    socketio.emit('sesion_iniciada', sesion)

    return jsonify({
        'status': 'ok', 'mensaje': 'Sesion iniciada', 'sesion': sesion
    }), 200

@app.route('/api/sesion/finalizar', methods=['POST'])
def terminar_sesion():
    sesion = obtener_sesion_vigente()

    if not sesion:
        return jsonify({
            'status': 'error', 'mensaje': 'No existe sesion activa'
        }), 409

    resultado = database.finalizar_sesion(sesion['id_sesion'])

    if not resultado:
        return jsonify({
            'status': 'error', 'mensaje': 'No se pudo finalizar la sesion.'
        }), 409

    socketio.emit('sesion_finalizada', {
        'id_sesion': sesion['id_sesion']
    })

    return jsonify({
        'status': 'ok', 'mensaje': 'Sesion finalizada, los registros pendientes se marcaron como faltas.'
    }), 200

@app.route('/api/sesion/activa', methods=['GET'])
def consultar_sesion_activa():
    sesion = obtener_sesion_vigente()

    if not sesion:
        return jsonify({
            'status': 'error', 'mensaje': 'No existe una sesión activa.'
        }), 404

    return jsonify(sesion), 200

# -------------------
# Tolerancia
# -------------------

@app.route('/api/configuracion/tolerancia', methods=['POST'])
def modificar_tolerancia():
    global TOLERANCIA_MINUTOS

    data = request.get_json(silent=True) or {}
    tolerancia = data.get('tolerancia')

    if tolerancia == 'toda_sesion':
        TOLERANCIA_MINUTOS = None
    else:
        try:
            tolerancia = int(tolerancia)

            if tolerancia < 0:
                raise ValueError

        except (ValueError, TypeError):
            return jsonify({
                'status': 'error', 'mensaje': 'La tolerancia debe ser un número de minutos igual o mayor que cero, o toda_sesion.'
            }), 400

        TOLERANCIA_MINUTOS = tolerancia

    return jsonify({
        'status': 'ok', 'tolerancia': (
            'toda_sesion'
            if TOLERANCIA_MINUTOS is None
            else TOLERANCIA_MINUTOS
        )
    }), 200

# ------------------------
# Registrar Asistencia
# ------------------------

@app.route('/api/asistencia', methods=['POST'])
def registrar_asistencia():
    data = request.get_json(silent=True) or {}
    cuenta = data.get('numero_de_cuenta', '').strip()

    if not cuenta:
        return jsonify({
            'status': 'error', 'mensaje': 'Debes introducir tu número de cuenta.'
        }), 400

    # 1. Identificar al alumno
    alumno = database.buscar_alumno_por_cuenta(cuenta)
    if not alumno or not alumno['activo']:
        return jsonify({
            'status': 'error', 'mensaje': 'Número de cuenta no registrado o alumno inactivo.'
        }), 404

    # 2. Obtener la sesión activa
    sesion = obtener_sesion_vigente()
    if not sesion:
        return jsonify({
            'status': 'error', 'mensaje': 'No hay una sesión activa.'
        }), 409

    # Rechazar si la sesión activa quedó abierta de otro día (el profesor olvidó finalizarla)
    if sesion['fecha'] != datetime.now().strftime("%Y-%m-%d"):
        return jsonify({
            'status': 'error', 'mensaje': 'La sesión activa es de otro día. El profesor debe finalizarla.'
        }), 409

    # 3. Comprobar que el alumno esté inscrito en esa clase
    inscripcion = database.obtener_inscripcion_activa(
        alumno['id_alumno'], sesion['id_clase']
    )
    if not inscripcion:
        return jsonify({
            'status': 'error', 'mensaje': 'No estás inscrito en esta clase.'
        }), 403

    # 4. Validaciones de horario
    ahora = datetime.now()

    # Validar hora de inicio (si la sesión la define)
    if sesion.get('hora_inicio'):
        inicio = datetime.fromisoformat(f"{sesion['fecha']} {sesion['hora_inicio']}")
        if ahora < inicio:
            return jsonify({
                'status': 'error', 'mensaje': 'La sesión todavía no ha comenzado.'
            }), 409

    # Validar hora de fin SOLO si la sesión tiene hora de fin programada
    if sesion.get('hora_fin'):
        fin = datetime.fromisoformat(f"{sesion['fecha']} {sesion['hora_fin']}")
        if ahora >= fin:
            return jsonify({
                'status': 'error', 'mensaje': 'El horario de la sesión ha terminado.'
            }), 409

    # 5. Determinar asistencia o retardo
    if TOLERANCIA_MINUTOS is None or not sesion.get('hora_inicio'):
        estado = 'asistencia'
    else:
        minutos_transcurridos = (ahora - inicio).total_seconds() / 60
        if minutos_transcurridos <= TOLERANCIA_MINUTOS:
            estado = 'asistencia'
        else:
            estado = 'retardo'

    hora_registro = ahora.strftime("%Y-%m-%d %H:%M:%S")
    id_dispositivo = None  # Pendiente de implementar identificador por UUID

    # 6. Guardar registro en la base de datos
    try:
        resultado = database.registrar_asistencia(
            sesion['id_sesion'],
            inscripcion['id_inscripcion'],
            id_dispositivo,
            hora_registro,
            estado
        )
    except sqlite3.Error:
        app.logger.exception("Error al registrar asistencia.")
        return jsonify({
            'status': 'error', 'mensaje': 'Ocurrió un error al guardar el registro.'
        }), 500

    if not resultado:
        return jsonify({
            'status': 'error', 'mensaje': 'La asistencia ya fue registrada o no existe un registro pendiente.'
        }), 409

    # 7. Notificar a la interfaz del profesor por WebSockets
    nuevo_registro = {
        'nombre': alumno['nombre'],
        'numero_de_cuenta': alumno['numero_de_cuenta'],
        'hora': hora_registro,
        'estado': estado,
        'id_sesion': sesion['id_sesion']
    }

    socketio.emit('nueva_asistencia', nuevo_registro)

    return jsonify({
        'status': 'ok',
        'mensaje': f"¡Registro realizado! Estado: {estado}.",
        'registro': nuevo_registro
    }), 200

# -------------------
# Solicitar historial
# -------------------

@app.route('/api/historial/<cuenta>', methods=['GET'])
def obtener_historial(cuenta):

    datos = database.obtener_historial_por_cuenta(cuenta)

    if not datos:
        return jsonify({
            'status': 'error', 'mensaje': 'Número de cuenta no registrado.'
        }), 404

    return jsonify(datos), 200

# Modificar estado de un registro específico

@app.route('/api/registros/<int:id_registro>', methods=['PATCH'])
def actualizar_registro(id_registro):
    data = request.get_json(silent=True) or {}
    nuevo_estado = data.get('estado', '').strip().lower()

    try:
        ok = database.actualizar_estado_registro(id_registro, nuevo_estado)
    except ValueError as e:
        return jsonify({'status': 'error', 'mensaje': str(e)}), 400

    if not ok:
        return jsonify({'status': 'error', 'mensaje': 'Registro no encontrado.'}), 404

    socketio.emit('registro_actualizado', {'id_registro': id_registro, 'estado': nuevo_estado})
    return jsonify({'status': 'ok', 'mensaje': 'Registro actualizado.'}), 200

# Cambiar estado (alta/baja) de un alumno a nivel general

@app.route('/api/alumnos/<int:id_alumno>/estado', methods=['POST'])
def cambiar_estado_alumno_api(id_alumno):
    data = request.get_json(silent=True) or {}
    if 'activo' not in data:
        return jsonify({'status': 'error', 'mensaje': 'Falta el campo activo.'}), 400

    activo = int(bool(data['activo']))
    ok = database.cambiar_estado_alumno(id_alumno, activo)

    if not ok:
        return jsonify({'status': 'error', 'mensaje': 'Alumno no encontrado.'}), 404

    socketio.emit('alumno_estado_actualizado', {'id_alumno': id_alumno, 'activo': activo})
    return jsonify({'status': 'ok', 'mensaje': 'Estado del alumno actualizado.'}), 200

# Cambiar estado (alta/baja) de la inscripción de un alumno en una clase

@app.route('/api/inscripciones/<int:id_inscripcion>/estado', methods=['POST'])
def cambiar_estado_inscripcion_api(id_inscripcion):
    data = request.get_json(silent=True) or {}
    if 'activo' not in data:
        return jsonify({'status': 'error', 'mensaje': 'Falta el campo activo.'}), 400

    activo = int(bool(data['activo']))
    ok = database.cambiar_estado_inscripcion(id_inscripcion, activo)

    if not ok:
        return jsonify({'status': 'error', 'mensaje': 'Inscripción no encontrada.'}), 404

    socketio.emit('inscripcion_actualizada', {'id_inscripcion': id_inscripcion, 'activo': activo})
    return jsonify({'status': 'ok', 'mensaje': 'Inscripción actualizada.'}), 200

# -------------------
# Iniciar Sesion
# -------------------

@app.route('/api/clases/activas', methods=['GET'])
def api_obtener_clases():
    clases = database.obtener_clases_activas()
    return jsonify(clases), 200

@app.route('/api/sesion/iniciar-tiempo-real', methods=['POST'])
def api_iniciar_sesion_tiempo_real():
    data = request.get_json(silent=True) or {}
    id_clase = data.get('id_clase')

    if not id_clase:
        return jsonify({'status': 'error', 'mensaje': 'Selecciona una clase.'}), 400

    # Hora límite ("HH:MM"); vacío o None = sin cierre automático.
    hora_cierre = data.get('hora_cierre') or None

    if hora_cierre:
        try:
            cierre = datetime.strptime(hora_cierre, "%H:%M").time()
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'mensaje': 'La hora límite no es válida.'}), 400

        if cierre <= datetime.now().time():
            return jsonify({
                'status': 'error', 'mensaje': 'La hora límite debe ser posterior a la hora actual.'
            }), 400

    # Si la sesión anterior ya pasó su hora límite, se cierra antes de crear la nueva.
    obtener_sesion_vigente()

    id_sesion = database.iniciar_sesion_tiempo_real(int(id_clase), hora_cierre)

    if not id_sesion:
        return jsonify({
            'status': 'error',
            'mensaje': 'Ya existe una sesión activa o no se pudo crear.'
        }), 409

    sesion = database.obtener_sesion_activa()
    socketio.emit('sesion_iniciada', sesion)

    return jsonify({'status': 'ok', 'sesion': sesion}), 200

# -------------------
# Proceso
# -------------------

if __name__ == '__main__':
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True
    )


