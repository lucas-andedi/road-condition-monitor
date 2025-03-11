import mysql.connector
from datetime import datetime
import json

class Database:
    def __init__(self, host="localhost", user="root", password="", database="road_monitor"):
        """
        Initialise la connexion à la base de données MySQL.
        
        Args:
            host (str): Hôte MySQL (par défaut: localhost)
            user (str): Nom d'utilisateur MySQL (par défaut: root)
            password (str): Mot de passe MySQL (par défaut: vide)
            database (str): Nom de la base de données (par défaut: road_monitor)
        """
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database
        }
        self.init_db()

    def get_connection(self):
        """Établit et retourne une connexion à la base de données."""
        return mysql.connector.connect(**self.config)

    def init_db(self):
        """Initialise la base de données avec les tables nécessaires."""
        # Créer la base de données si elle n'existe pas
        conn = mysql.connector.connect(
            host=self.config['host'],
            user=self.config['user'],
            password=self.config['password']
        )
        cursor = conn.cursor()
        
        # Créer la base de données si elle n'existe pas
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
        cursor.execute(f"USE {self.config['database']}")
        
        # Table pour les données des capteurs
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS donnees_routieres (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME NOT NULL,
            accelerometer_x FLOAT,
            accelerometer_y FLOAT,
            accelerometer_z FLOAT,
            latitude FLOAT,
            longitude FLOAT,
            altitude FLOAT,
            satellites INT,
            road_condition VARCHAR(10)
        )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()

    def save_sensor_data(self, data):
        """Enregistre les données des capteurs dans la base de données."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Extraire les données
        timestamp = data.get('timestamp', datetime.now().isoformat())
        # Convertir le timestamp ISO en datetime MySQL
        try:
            timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            timestamp_dt = datetime.now()
        
        # Valeurs par défaut
        accel_x = accel_y = accel_z = lat = lon = alt = satellites = None
        road_condition = 'unknown'
        
        # Extraire les données de l'accéléromètre
        if data.get('accelerometer'):
            accel_x = data['accelerometer'].get('x')
            accel_y = data['accelerometer'].get('y')
            accel_z = data['accelerometer'].get('z')
            
            # Déterminer l'état de la route
            if accel_y is not None:
                y_accel = abs(accel_y)
                if y_accel > 15000:
                    road_condition = 'bad'
                elif y_accel > 10000:
                    road_condition = 'fair'
                else:
                    road_condition = 'good'
        
        # Extraire les données GPS
        if data.get('gps'):  # Vérifier si gps existe et n'est pas None
            lat = data['gps'].get('latitude')
            lon = data['gps'].get('longitude')
            alt = data['gps'].get('altitude')
            satellites = data['gps'].get('satellites')
        
        # Insérer les données dans la base de données
        query = '''
        INSERT INTO donnees_routieres 
        (timestamp, accelerometer_x, accelerometer_y, accelerometer_z, 
         latitude, longitude, altitude, satellites, road_condition)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        cursor.execute(query, (
            timestamp_dt, accel_x, accel_y, accel_z, 
            lat, lon, alt, satellites, road_condition
        ))
        
        conn.commit()
        last_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return last_id

    def get_history(self, limit=1000, start_date=None, end_date=None, condition=None):
        """Récupère l'historique des données des capteurs."""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)  # Pour obtenir les résultats sous forme de dictionnaires
        
        query = "SELECT * FROM donnees_routieres WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND timestamp >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= %s"
            params.append(end_date)
        
        if condition:
            query += " AND road_condition = %s"
            params.append(condition)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Convertir les résultats en liste de dictionnaires
        result = []
        for row in rows:
            # Convertir datetime en string ISO
            row['timestamp'] = row['timestamp'].isoformat() if row['timestamp'] else None
            
            result.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'accelerometer': {
                    'x': row['accelerometer_x'],
                    'y': row['accelerometer_y'],
                    'z': row['accelerometer_z']
                },
                'gps': {
                    'latitude': row['latitude'],
                    'longitude': row['longitude'],
                    'altitude': row['altitude'],
                    'satellites': row['satellites']
                },
                'road_condition': row['road_condition']
            })
        
        cursor.close()
        conn.close()
        return result

    def get_road_condition_history(self, limit=1000, start_date=None, end_date=None, condition=None):
        """Récupère l'historique des états de route avec coordonnées GPS."""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT timestamp, latitude, longitude, road_condition 
        FROM donnees_routieres 
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
        params = []
        
        if start_date:
            query += " AND timestamp >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= %s"
            params.append(end_date)
        
        if condition:
            query += " AND road_condition = %s"
            params.append(condition)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for row in rows:
                # Convertir datetime en string ISO
                row['timestamp'] = row['timestamp'].isoformat() if row['timestamp'] else None
                
                # S'assurer que les coordonnées sont des nombres
                lat = row['latitude']
                lng = row['longitude']
                
                if lat is not None and lng is not None:
                    result.append({
                        'timestamp': row['timestamp'],
                        'latitude': float(lat),
                        'longitude': float(lng),
                        'condition': row['road_condition']
                    })
            
            return result
        except Exception as e:
            print(f"Error in get_road_condition_history: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_statistics(self):
        """Récupère des statistiques sur les données enregistrées."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Nombre total d'enregistrements
        cursor.execute("SELECT COUNT(*) FROM donnees_routieres")
        stats['total_records'] = cursor.fetchone()[0]
        
        # Répartition des états de route
        cursor.execute("""
        SELECT road_condition, COUNT(*) as count 
        FROM donnees_routieres 
        GROUP BY road_condition
        """)
        road_conditions = {}
        for row in cursor.fetchall():
            road_conditions[row[0]] = row[1]
        stats['road_conditions'] = road_conditions
        
        # Premier et dernier enregistrement
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM donnees_routieres")
        first_last = cursor.fetchone()
        stats['first_record'] = first_last[0].isoformat() if first_last[0] else None
        stats['last_record'] = first_last[1].isoformat() if first_last[1] else None
        
        cursor.close()
        conn.close()
        return stats