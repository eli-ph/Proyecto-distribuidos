from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
# Permitir conexiones desde cualquier origen en la red local
socketio = SocketIO(app, cors_allowed_origins="*")

# Simulamos la lista de asistencia en memoria (Estado del Servidor)
asistencias = []

@app.route('/')
def vista_laptop():
    """Pantalla principal que verá la profesora en la laptop."""
    return render_template('laptop.html')

@app.route('/marcar')
def vista_telefono():
    """Interfaz liviana que cargará el teléfono del alumno."""
    return render_template('telefono.html')

@app.route('/api/asistencia', methods=['POST'])
def registrar_asistencia():
    """Endpoint REST que recibe el pase de lista del cliente (Teléfono)."""
    data = request.get_json()
    nombre = data.get('nombre', 'Alumno Anónimo')
    
    # Marca de tiempo generada en el servidor para consistencia
    hora_actual = datetime.now().strftime("%H:%M:%S")
    
    nuevo_registro = {
        'nombre': nombre,
        'hora': hora_actual,
        'ip_cliente': request.remote_addr
    }
    
    asistencias.append(nuevo_registro)
    
    # EMISIÓN DISTRIBUIDA: Notifica inmediatamente a la pantalla de la laptop por WebSockets
    socketio.emit('nueva_asistencia', nuevo_registro)
    
    return jsonify({
        'status': 'ok',
        'mensaje': f'Asistencia registrada exitosamente a las {hora_actual}'
    }), 200

if __name__ == '__main__':
    # '0.0.0.0' permite que otros dispositivos en la red local accedan al servidor
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)