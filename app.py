from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO
import json
import csv
from io import StringIO
from datetime import datetime, timedelta
from database import Database

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration de la base de données MySQL
DB_CONFIG = {
    'host': 'localhost',
    'user': 'admin',
    'password': 'admin',
    'database': 'road_monitor'
}

# Initialiser la base de données
db = Database(**DB_CONFIG)

# Store the latest sensor data
latest_sensor_data = {}

# Store road condition history (in-memory cache)
road_condition_history = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data', methods=['POST'])
def receive_data():
    global latest_sensor_data, road_condition_history
    data = request.json
    
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400
    
    latest_sensor_data = data
    
    # Calculer l'état de la route
    if data.get('accelerometer'):
        # Vérifier si les données sont déjà converties ou si ce sont des valeurs brutes
        if 'y_raw' in data['accelerometer']:
            # Utiliser la valeur brute pour déterminer l'état de la route
            y_accel = abs(data['accelerometer'].get('y_raw', 0))
        else:
            # Utiliser la valeur y directement
            y_accel = abs(data['accelerometer'].get('y', 0))
            # Si c'est une valeur en m/s², la reconvertir en valeur brute pour la comparaison
            if abs(y_accel) < 100:  # Si la valeur est petite, c'est probablement en m/s²
                y_accel = y_accel * 16384.0 / 9.81  # Reconversion approximative
        
        # Déterminer l'état de la route basé sur les valeurs brutes
        if y_accel > 15000:
            road_condition = 'bad'
        elif y_accel > 10000:
            road_condition = 'fair'
        else:
            road_condition = 'good'
        
        # Ajouter l'état de la route à l'historique
        if data.get('gps') and data['gps'] is not None:
            road_point = {
                'latitude': data['gps'].get('latitude'),
                'longitude': data['gps'].get('longitude'),
                'condition': road_condition,
                'timestamp': data.get('timestamp', datetime.now().isoformat())
            }
            road_condition_history.append(road_point)
            
            # Garder seulement les 100 derniers points en mémoire
            road_condition_history = road_condition_history[-100:]
    
    try:
        # Sauvegarder les données dans la base de données
        db.save_sensor_data(data)
        
        # Émettre les données à tous les clients connectés
        socketio.emit('sensor_update', {
            'sensor_data': data,
            'road_condition_history': road_condition_history
        })
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error saving data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/', methods=['POST'])
def receive_data_alt():
    """Route alternative pour recevoir les données."""
    return receive_data()

@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/api/history')
def get_history():
    limit = request.args.get('limit', 1000, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    condition = request.args.get('condition')
    
    history = db.get_history(limit, start_date, end_date, condition)
    return jsonify(history)

@app.route('/api/road-history')
def get_road_history():
    limit = request.args.get('limit', 1000, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    condition = request.args.get('condition')
    
    history = db.get_road_condition_history(limit, start_date, end_date, condition)
    return jsonify(history)

@app.route('/api/statistics')
def get_statistics():
    stats = db.get_statistics()
    return jsonify(stats)

@app.route('/api/export-csv')
def export_csv():
    """Exporte l'historique des données au format CSV."""
    limit = request.args.get('limit', 1000, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    condition = request.args.get('condition')
    
    # Récupérer les données
    history = db.get_history(limit, start_date, end_date, condition)
    
    # Créer un fichier CSV en mémoire
    output = StringIO()
    writer = csv.writer(output)
    
    # Écrire l'en-tête
    writer.writerow([
        'ID', 'Timestamp', 'Accelerometer X (m/s²)', 'Accelerometer Y (m/s²)', 'Accelerometer Z (m/s²)',
        'Latitude', 'Longitude', 'Altitude', 'Satellites', 'Road Condition'
    ])
    
    # Écrire les données
    for item in history:
        # Convertir les valeurs brutes en m/s² si nécessaire
        accel_x = item['accelerometer']['x']
        accel_y = item['accelerometer']['y']
        accel_z = item['accelerometer']['z']
        
        # Si les valeurs sont grandes, ce sont probablement des valeurs brutes
        if abs(accel_x) > 100:
            accel_x = (accel_x / 16384.0) * 9.81
        if abs(accel_y) > 100:
            accel_y = (accel_y / 16384.0) * 9.81
        if abs(accel_z) > 100:
            accel_z = (accel_z / 16384.0) * 9.81
            
        writer.writerow([
            item['id'],
            item['timestamp'],
            round(accel_x, 3),
            round(accel_y, 3),
            round(accel_z, 3),
            item['gps']['latitude'],
            item['gps']['longitude'],
            item['gps']['altitude'],
            item['gps']['satellites'],
            item['road_condition']
        ])
    
    # Préparer la réponse
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=road_data_{timestamp}.csv"}
    )

@app.route('/generate-report/<timestamp>')
def generate_report(timestamp):
    # Code pour générer un rapport PDF (comme précédemment)
    # ...
    pass

@socketio.on('connect')
def handle_connect():
    # Envoyer les dernières données aux clients nouvellement connectés
    socketio.emit('sensor_update', {
        'sensor_data': latest_sensor_data,
        'road_condition_history': road_condition_history
    })

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

