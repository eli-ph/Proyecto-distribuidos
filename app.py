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
# Vistas
# -------------------

@app.route('/')
def vista_laptop():
    return render_template('laptop.html')

@app.route('/lista-general')
def vista_lista_general():
    alumnos = database.obtener_alumnos()
    return render_template('lista_general.html', alumnos=alumnos)

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
        return jsonify({'status': 'error', 'mensaje': 'No se undic[o la sesion'
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
    sesion = database.obtener_sesion_activa()

    if not sesion:
        return jsonify({
            'status': 'error', 'mensaje': 'No existe sesion activa'
        }), 409

    resultado = database.finalizar_sesion(sesion['id_sesion'])

    if not resultado:
        return jsonfy({
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
    sesion = database.obtener_sesion_activa()

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
    sesion = database.obtener_sesion_activa()
    if not sesion:
        return jsonify({
            'status': 'error', 'mensaje': 'No hay una sesión activa.'
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
# Solicitar hiostrial
# -------------------

@app.route('/api/historial/<cuenta>', methods=['GET'])
def obtener_historial(cuenta):

    sesion = database.obtener_sesion_activa()

    if not sesion:
        return jsonify({
            'status': 'error', 'mensaje': 'No existe una sesión activa para consultar el historial.'
        }), 409

    datos = database.obtener_historial_por_cuenta(
        cuenta, sesion['id_sesion']
    )

    if not datos:
        return jsonify({
            'status': 'error', 'mensaje': 'Alumno no encontrado.'
        }), 404

    return jsonify(datos), 200

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

    id_sesion = database.iniciar_sesion_tiempo_real(int(id_clase))

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


