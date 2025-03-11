import serial
import requests
import time
from datetime import datetime
import smbus2 as smbus

# URL de votre dashboard (à remplacer par l'URL réelle de votre serveur Flask)
DASHBOARD_URL = "http://172.20.10.3:5000"

# Adresses et registres du MPU-6050
MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B

def mpu_init(bus):
    """
    Initialiser le MPU-6050 en mettant son registre de gestion de l'alimentation à 0 (activation du capteur).
    """
    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

def read_raw_data(bus, addr):
    """
    Lire les données brutes de l'accéléromètre du MPU-6050 à l'adresse spécifiée.
    """
    high = bus.read_byte_data(MPU_ADDR, addr)
    low = bus.read_byte_data(MPU_ADDR, addr + 1)
    value = (high << 8) + low
    if value > 32768:
        value -= 65536  # Convertir en nombre négatif si nécessaire
    return value

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
    """
    try:
        response = requests.post(DASHBOARD_URL, json=sensor_data)
        if response.status_code == 200:
            print("Données envoyées avec succès")
        else:
            print(f"Erreur lors de l'envoi des données: {response.status_code}")
    except requests.RequestException as e:
        print(f"Erreur de connexion: {e}")

def setup_gps():
    """
    Initialiser la connexion série avec le module GPS.
    """
    ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
    ser.flush()
    print('****** GPS Device Connected ******')
    return ser

def setup_mpu():
    """
    Initialiser le bus I2C et le MPU-6050.
    """
    bus = smbus.SMBus(1)
    mpu_init(bus)  # Pass the bus object to mpu_init
    print('****** MPU-6050 Initialized ******')
    return bus

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
    if ser.in_waiting > 0:
        line = ser.readline().decode('utf-8').rstrip()
        if line.startswith('$GPGGA'):
            gps_data = parse_gpgga(line)
            if gps_data:
                sensor_data["gps"] = gps_data
                print("Données GPS extraites:", gps_data)

    # Lire les données de l'accéléromètre
    accel_x = read_raw_data(bus, ACCEL_XOUT_H)
    accel_y = read_raw_data(bus, ACCEL_XOUT_H + 2)
    accel_z = read_raw_data(bus, ACCEL_XOUT_H + 4)
    sensor_data["accelerometer"] = {
        "x": accel_x,
        "y": accel_y,
        "z": accel_z
    }
    print(f"Accel X: {accel_x}, Accel Y: {accel_y}, Accel Z: {accel_z}")

    return sensor_data

def main():
    """
    Fonction principale pour exécuter la collecte et l'envoi des données.
    """
    # Initialisation
    ser = setup_gps()
    bus = setup_mpu()

    # Boucle infinie pour collecter et envoyer les données toutes les secondes
    while True:
        sensor_data = collect_sensor_data(ser, bus)
        send_to_dashboard(sensor_data)
        time.sleep(1)  # Délai d'une seconde entre chaque lecture

if __name__ == '__main__':
    main()