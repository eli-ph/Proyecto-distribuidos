from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime, time
import database

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

database.init_db()

HORA_CLASE = time(9, 0, 0)      # Hora de entrada 09:00 AM
TOLERANCIA_MINUTOS = 15         # Minutos de tolerancia
RETARDO_MAX_MINUTOS = 30        # Límite para retardo

@app.route('/')
def vista_laptop():
    return render_template('laptop.html')

@app.route('/lista-general')
def vista_lista_general():
    alumnos_dict = database.obtener_todos_alumnos_dict()
    return render_template('lista_general.html', alumnos=alumnos_dict)

@app.route('/marcar')
def vista_telefono():
    return render_template('telefono.html')

@app.route('/api/asistencia', methods=['POST'])
def registrar_asistencia():
    data = request.get_json()
    cuenta_ingresada = data.get('numero_de_cuenta', '').strip()
    
    # Validar si el número de cuenta existe en la BD
    alumno_info = database.buscar_alumno_por_cuenta(cuenta_ingresada)
    
    if not alumno_info:
        return jsonify({
            'status': 'error', 
            'mensaje': 'Número de cuenta no registrado. Verifica tus datos.'
        }), 400

    nombre_oficial = alumno_info['nombre']
    cuenta = alumno_info['numero_de_cuenta']
    
    ahora = datetime.now()
    hora_actual_time = ahora.time()
    hora_str = ahora.strftime("%H:%M:%S")

    # Definimos asistencia, retardo o falta según la hora de llegada
    minutos_clase = HORA_CLASE.hour * 60 + HORA_CLASE.minute
    minutos_llegada = hora_actual_time.hour * 60 + hora_actual_time.minute
    diff_minutos = minutos_llegada - minutos_clase

    # Asignamos directamente el código de color hexadecimal
    if diff_minutos <= TOLERANCIA_MINUTOS:
        estado = "Asistencia"
        color = "#34d399"  
    elif diff_minutos <= RETARDO_MAX_MINUTOS:
        estado = "Retardo"
        color = "#fbbf24"  
    else:
        estado = "Falta"
        color = "#f87171"  

    ip_cliente = request.remote_addr

    # Registramos en la base
    database.actualizar_y_registrar(cuenta, estado, color, hora_str, ip_cliente)

    nuevo_registro = {
        'nombre': nombre_oficial,
        'numero_de_cuenta': cuenta,
        'hora': hora_str,
        'estado': estado,
        'color': color,
        'ip_cliente': ip_cliente
    }

    socketio.emit('nueva_asistencia', nuevo_registro)

    return jsonify({
        'status': 'ok',
        'mensaje': f'¡Registrado como {nombre_oficial}! Estado: {estado}'
    }), 200

@app.route('/api/historial/<cuenta>', methods=['GET'])
def obtener_historial(cuenta):
    datos = database.obtener_historial_por_cuenta(cuenta)
    
    if not datos:
        return jsonify({'error': 'Alumno no encontrado'}), 404
    
    return jsonify(datos), 200

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)