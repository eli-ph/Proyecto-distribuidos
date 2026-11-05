from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime, time

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- BASE DE DATOS (Lista de alumnos) ---
ALUMNOS_INSCRITOS = [
    "Elizabeth Portilla Hermenegildo",
    "Diego Ramírez",
    "Celeste",
    "Juan Pérez",
    "Ana Gómez"
]

asistencias = []

alumnos_db = {nombre: {'asistencias': 0, 'retardos': 0, 'faltas': 0, 'registros': []} for nombre in ALUMNOS_INSCRITOS}

HORA_CLASE = time(9, 0, 0)      # Hora de entrada 09:00 AM
TOLERANCIA_MINUTOS = 15         # Minutos de tolerancia
RETARDO_MAX_MINUTOS = 30        # Límite para retardo

@app.route('/')
def vista_laptop():
    """Dashboard en tiempo real de asistencias del día."""
    return render_template('laptop.html')

@app.route('/lista-general')
def vista_lista_general():
    """Nueva vista que muestra la lista general de alumnos y su estatus acumulado."""
    return render_template('lista_general.html', alumnos=alumnos_db)

@app.route('/marcar')
def vista_telefono():
    return render_template('telefono.html')

@app.route('/api/asistencia', methods=['POST'])
def registrar_asistencia():
    data = request.get_json()
    nombre_ingresado = data.get('nombre', '').strip()
    
    nombre_oficial = None
    for alumno in ALUMNOS_INSCRITOS:
        if alumno.lower() == nombre_ingresado.lower():
            nombre_oficial = alumno
            break

    if not nombre_oficial:
        return jsonify({
            'status': 'error', 
            'mensaje': 'Nombre no registrado o incorrecto. Verifica tus datos.'
        }), 400

    ahora = datetime.now()
    hora_actual_time = ahora.time()
    hora_str = ahora.strftime("%H:%M:%S")

    # Dfinimos asistencia, retardo o falta según la hora de llegada
    minutos_clase = HORA_CLASE.hour * 60 + HORA_CLASE.minute
    minutos_llegada = hora_actual_time.hour * 60 + hora_actual_time.minute
    diff_minutos = minutos_llegada - minutos_clase

    if diff_minutos <= TOLERANCIA_MINUTOS:
        estado = "Asistencia"
        color = "#34d399"
        alumnos_db[nombre_oficial]['asistencias'] += 1
    elif diff_minutos <= RETARDO_MAX_MINUTOS:
        estado = "Retardo"
        color = "#fbbf24"
        alumnos_db[nombre_oficial]['retardos'] += 1
    else:
        estado = "Falta"
        color = "#f87171"
        alumnos_db[nombre_oficial]['faltas'] += 1

    nuevo_registro = {
        'nombre': nombre_oficial,
        'hora': hora_str,
        'estado': estado,
        'color': color,
        'ip_cliente': request.remote_addr
    }

    asistencias.append(nuevo_registro)
    alumnos_db[nombre_oficial]['registros'].append(nuevo_registro)

    socketio.emit('nueva_asistencia', nuevo_registro)

    return jsonify({
        'status': 'ok',
        'mensaje': f'¡Registrado como {nombre_oficial}! Estado: {estado}'
    }), 200

@app.route('/api/historial/<nombre>', methods=['GET'])
def obtener_historial(nombre):
    nombre_oficial = next((a for a in ALUMNOS_INSCRITOS if a.lower() == nombre.strip().lower()), None)
    
    if not nombre_oficial:
        return jsonify({'error': 'Alumno no encontrado'}), 404
        
    datos = alumnos_db[nombre_oficial]
    return jsonify({
        'alumno': nombre_oficial,
        'asistencias': datos['asistencias'],
        'retardos': datos['retardos'],
        'faltas': datos['faltas'],
        'registros': datos['registros']
    }), 200

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)