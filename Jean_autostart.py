#!/usr/bin/env python3
import serial
import requests
import time
import sqlite3
import json
import os
import logging
from datetime import datetime
import threading
import signal
import sys

# Essayer d'importer les bibliothèques matérielles, sinon utiliser le mode simulation
try:
    import smbus2 as smbus
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    print("Avertissement: smbus2 non disponible. Mode simulation activé pour l'accéléromètre.")

# Configuration
DASHBOARD_URL = "http://172.20.10.3:5000/data"  # URL de votre serveur Flask
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensor_data.db")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensor_monitor.log")
SYNC_INTERVAL = 30                              # Intervalle de synchronisation en secondes
SAMPLE_INTERVAL = 1                             # Intervalle d'échantillonnage en secondes

# Configuration du logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Adresses et registres du MPU-6050
MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B

# Constantes pour la conversion des valeurs brutes en m/s²
# Le MPU-6050 a une sensibilité de 16384 LSB/g en mode ±2g
# 1g = 9.81 m/s²
ACCEL_SCALE_FACTOR = 16384.0  # LSB/g
GRAVITY = 9.81  # m/s²

# Variables globales
running = True
sync_thread = None
data_collection_thread = None
connection_status = False

class LocalDatabase:
    def __init__(self, db_path):
        """Initialise la base de données SQLite locale"""
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Crée la table pour stocker les données des capteurs"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                data TEXT NOT NULL,
                synced INTEGER DEFAULT 0
            )
            ''')
            
            conn.commit()
            conn.close()
            logging.info("Base de données locale initialisée avec succès")
        except Exception as e:
            logging.error(f"Erreur lors de l'initialisation de la base de données locale: {e}")
    
    def save_data(self, data):
        """Enregistre les données dans la base de données locale"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO sensor_data (timestamp, data, synced) VALUES (?, ?, ?)",
                (data["timestamp"], json.dumps(data), 0)
            )
            
            conn.commit()
            conn.close()
            logging.debug(f"Données enregistrées localement: {data['timestamp']}")
            return True
        except Exception as e:
            logging.error(f"Erreur lors de l'enregistrement local des données: {e}")
            return False
    
    def get_unsynced_data(self, limit=50):
        """Récupère les données non synchronisées"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, timestamp, data FROM sensor_data WHERE synced = 0 ORDER BY timestamp ASC LIMIT ?",
                (limit,)
            )
            
            rows = cursor.fetchall()
            result = []
            
            for row in rows:
                id, timestamp, data_json = row
                result.append({
                    "id": id,
                    "timestamp": timestamp,
                    "data": json.loads(data_json)
                })
            
            conn.close()
            return result
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des données non synchronisées: {e}")
            return []
    
    def mark_as_synced(self, ids):
        """Marque les données comme synchronisées"""
        if not ids:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convertir la liste d'IDs en chaîne pour la requête SQL
            id_str = ','.join(['?'] * len(ids))
            cursor.execute(f"UPDATE sensor_data SET synced = 1 WHERE id IN ({id_str})", ids)
            
            conn.commit()
            conn.close()
            logging.info(f"Données marquées comme synchronisées: {len(ids)} enregistrements")
        except Exception as e:
            logging.error(f"Erreur lors du marquage des données synchronisées: {e}")

def mpu_init(bus):
    """
    Initialiser le MPU-6050 en mettant son registre de gestion de l'alimentation à 0 (activation du capteur).
    """
    try:
        bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)
        return True
    except Exception as e:
        logging.error(f"Erreur lors de l'initialisation du MPU-6050: {e}")
        return False

def read_raw_data(bus, addr):
    """
    Lire les données brutes de l'accéléromètre du MPU-6050 à l'adresse spécifiée.
    """
    try:
        high = bus.read_byte_data(MPU_ADDR, addr)
        low = bus.read_byte_data(MPU_ADDR, addr + 1)
        value = (high << 8) + low
        if value > 32768:
            value -= 65536  # Convertir en nombre négatif si nécessaire
        return value
    except Exception as e:
        logging.error(f"Erreur lors de la lecture des données brutes: {e}")
        return 0

def convert_to_ms2(raw_value):
    """
    Convertit les valeurs brutes de l'accéléromètre en m/s².
    
    Le MPU-6050 a une sensibilité de 16384 LSB/g en mode ±2g.
    1g = 9.81 m/s²
    
    Args:
        raw_value: Valeur brute de l'accéléromètre
        
    Returns:
        float: Valeur en m/s²
    """
    return (raw_value / ACCEL_SCALE_FACTOR) * GRAVITY

def parse_gpgga(gpgga_string):
    """
    Analyser la chaîne de données NMEA $GPGGA pour en extraire les informations GPS.
    """
    parts = gpgga_string.split(',')
    if len(parts) < 15:
        return None
    try:
        time = parts[1][:2] + ':' + parts[1][2:4] + ':' + parts[1][4:6]
        latitude = float(parts[2][:2]) + float(parts[2][2:]) / 60
        if parts[3] == 'S':
            latitude = -latitude
        longitude = float(parts[4][:3]) + float(parts[4][3:]) / 60
        if parts[5] == 'W':
            longitude = -longitude
        altitude = float(parts[9])
        satellites = int(parts[7])
        return {
            "time": time,
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "satellites": satellites
        }
    except (ValueError, IndexError):
        return None

def send_to_dashboard(sensor_data):
    """
    Envoyer les données du capteur au tableau de bord via une requête HTTP POST.
    Retourne True si l'envoi a réussi, False sinon.
    """
    try:
        response = requests.post(DASHBOARD_URL, json=sensor_data, timeout=5)
        if response.status_code == 200:
            logging.info("Données envoyées avec succès")
            return True
        else:
            logging.warning(f"Erreur lors de l'envoi des données: {response.status_code}")
            return False
    except requests.RequestException as e:
        logging.error(f"Erreur de connexion: {e}")
        return False

def check_connection():
    """Vérifie si la connexion au serveur est disponible"""
    try:
        response = requests.get(DASHBOARD_URL, timeout=2)
        return response.status_code == 200
    except:
        return False

def setup_gps():
    """
    Initialiser la connexion série avec le module GPS.
    """
    try:
        ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
        ser.flush()
        logging.info('****** GPS Device Connected ******')
        return ser
    except Exception as e:
        logging.error(f"Erreur lors de l'initialisation du GPS: {e}")
        return None

def setup_mpu():
    """
    Initialiser le bus I2C et le MPU-6050.
    """
    if not HARDWARE_AVAILABLE:
        logging.warning("Matériel non disponible, mode simulation activé")
        return None
        
    try:
        bus = smbus.SMBus(1)
        if mpu_init(bus):
            logging.info('****** MPU-6050 Initialized ******')
            return bus
        else:
            return None
    except Exception as e:
        logging.error(f"Erreur lors de l'initialisation du MPU-6050: {e}")
        return None

def collect_sensor_data(ser, bus):
    """
    Collecter les données GPS et d'accéléromètre, puis les formater pour l'envoi.
    """
    sensor_data = {
        "timestamp": datetime.now().isoformat(),
        "gps": None,
        "accelerometer": None
    }

    # Lire les données GPS
    if ser and ser.in_waiting > 0:
        try:
            line = ser.readline().decode('utf-8').rstrip()
            if line.startswith('$GPGGA'):
                gps_data = parse_gpgga(line)
                if gps_data:
                    sensor_data["gps"] = gps_data
                    logging.debug("Données GPS extraites")
        except Exception as e:
            logging.error(f"Erreur lors de la lecture du GPS: {e}")

    # Lire les données de l'accéléromètre
    if bus:
        try:
            # Lire les valeurs brutes
            accel_x_raw = read_raw_data(bus, ACCEL_XOUT_H)
            accel_y_raw = read_raw_data(bus, ACCEL_XOUT_H + 2)
            accel_z_raw = read_raw_data(bus, ACCEL_XOUT_H + 4)
            
            # Stocker à la fois les valeurs brutes et les valeurs converties
            sensor_data["accelerometer"] = {
                "x_raw": accel_x_raw,
                "y_raw": accel_y_raw,
                "z_raw": accel_z_raw,
                "x": convert_to_ms2(accel_x_raw),
                "y": convert_to_ms2(accel_y_raw),
                "z": convert_to_ms2(accel_z_raw)
            }
            logging.debug(f"Données accéléromètre extraites: X={accel_x_raw}, Y={accel_y_raw}, Z={accel_z_raw}")
        except Exception as e:
            logging.error(f"Erreur lors de la lecture de l'accéléromètre: {e}")
    else:
        # Mode simulation pour l'accéléromètre
        import random
        # Générer des valeurs brutes simulées
        accel_x_raw = random.randint(-2000, 2000)
        accel_y_raw = random.randint(-14000, -12000)
        accel_z_raw = random.randint(-8000, -6000)
        
        # Stocker à la fois les valeurs brutes et les valeurs converties
        sensor_data["accelerometer"] = {
            "x_raw": accel_x_raw,
            "y_raw": accel_y_raw,
            "z_raw": accel_z_raw,
            "x": convert_to_ms2(accel_x_raw),
            "y": convert_to_ms2(accel_y_raw),
            "z": convert_to_ms2(accel_z_raw)
        }
        logging.debug("Données accéléromètre simulées générées")
        
    # Mode simulation pour le GPS si nécessaire
    if not sensor_data["gps"]:
        import random
        # Coordonnées par défaut avec légère variation aléatoire
        sensor_data["gps"] = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "latitude": -4.3250 + random.uniform(-0.01, 0.01),
            "longitude": 15.3100 + random.uniform(-0.01, 0.01),
            "altitude": 280 + random.uniform(-5, 5),
            "satellites": random.randint(4, 12)
        }
        logging.debug("Données GPS simulées générées")

    return sensor_data

def data_collection_loop(ser, bus, db):
    """Boucle de collecte des données"""
    global running
    
    logging.info("Démarrage de la collecte de données")
    
    while running:
        try:
            # Collecter les données des capteurs
            data = collect_sensor_data(ser, bus)
            
            # Enregistrer les données localement
            db.save_data(data)
            
            # Attendre l'intervalle d'échantillonnage
            time.sleep(SAMPLE_INTERVAL)
        except Exception as e:
            logging.error(f"Erreur dans la boucle de collecte: {e}")
            time.sleep(1)

def sync_data_loop(db):
    """Boucle de synchronisation des données"""
    global running, connection_status
    
    logging.info("Démarrage de la synchronisation des données")
    
    while running:
        try:
            # Vérifier la connexion au serveur
            connection_status = check_connection()
            
            if connection_status:
                # Récupérer les données non synchronisées
                unsynced_data = db.get_unsynced_data()
                
                if unsynced_data:
                    logging.info(f"Tentative de synchronisation de {len(unsynced_data)} enregistrements")
                    
                    # Envoyer les données au serveur
                    synced_ids = []
                    for item in unsynced_data:
                        if send_to_dashboard(item["data"]):
                            synced_ids.append(item["id"])
                    
                    # Marquer les données comme synchronisées
                    if synced_ids:
                        db.mark_as_synced(synced_ids)
                        logging.info(f"Synchronisation réussie pour {len(synced_ids)} enregistrements")
            else:
                logging.warning("Pas de connexion au serveur, synchronisation reportée")
            
            # Attendre l'intervalle de synchronisation
            time.sleep(SYNC_INTERVAL)
        except Exception as e:
            logging.error(f"Erreur dans la boucle de synchronisation: {e}")
            time.sleep(SYNC_INTERVAL)

def signal_handler(sig, frame):
    """Gestionnaire de signal pour arrêter proprement le programme"""
    global running
    logging.info("Signal d'arrêt reçu, arrêt du programme...")
    running = False
    sys.exit(0)

def main():
    """
    Fonction principale pour exécuter la collecte et l'envoi des données.
    """
    global sync_thread, data_collection_thread, running
    
    # Configurer le gestionnaire de signal pour l'arrêt propre
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialisation de la base de données locale
    db = LocalDatabase(DATABASE_PATH)
    
    # Initialisation des capteurs
    ser = setup_gps()
    bus = setup_mpu()
    
    try:
        # Démarrer le thread de collecte de données
        data_collection_thread = threading.Thread(target=data_collection_loop, args=(ser, bus, db))
        data_collection_thread.daemon = True
        data_collection_thread.start()
        
        # Démarrer le thread de synchronisation
        sync_thread = threading.Thread(target=sync_data_loop, args=(db,))
        sync_thread.daemon = True
        sync_thread.start()
        
        logging.info("Programme démarré avec succès")
        
        # Boucle principale pour maintenir le programme en cours d'exécution
        while running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logging.info("Programme arrêté par l'utilisateur")
        running = False
        
        if ser:
            ser.close()
        
        # Attendre que les threads se terminent
        if data_collection_thread and data_collection_thread.is_alive():
            data_collection_thread.join(timeout=2)
        if sync_thread and sync_thread.is_alive():
            sync_thread.join(timeout=2)

if __name__ == '__main__':
    # Afficher un message de démarrage
    print("Démarrage du moniteur de capteurs Raspberry Pi...")
    print(f"Les logs seront enregistrés dans: {LOG_FILE}")
    
    # Démarrer le programme principal
    main()

