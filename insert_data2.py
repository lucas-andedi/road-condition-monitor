import mysql.connector
import random
import requests
import pandas as pd
from datetime import datetime, timedelta
from math import sin, cos, radians, sqrt

# Configuration MySQL
DB_CONFIG = {
    'host': 'localhost',
    'user': 'admin',
    'password': 'admin',
    'database': 'road_monitor'
}

# Paramètres OpenStreetMap (bbox ajusté pour Kinshasa)
OVERPASS_URL = "http://overpass-api.de/api/interpreter"
KINSHASA_BBOX = "-4.5,15.0,-4.2,15.5"  # Bbox correct pour Kinshasa

# Paramètres généraux
PLAGE_ALTITUDE = (275.0, 285.0)
PLAGE_SATELLITES = (6, 9)
VARIATION_GPS = 0.0002  # 20m de variation

def recuperer_routes_osm():
    """Récupère les routes de Kinshasa depuis OpenStreetMap"""
    query = f"""
    [out:json][timeout:250];
    (
      way["highway"~"primary|secondary|tertiary|residential|unclassified|trunk|service|road"]({KINSHASA_BBOX});
    );
    out body;
    >;
    out skel qt;
    """
    
    try:
        response = requests.get(OVERPASS_URL, params={'data': query}, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        nodes = {}
        for element in data['elements']:
            if element['type'] == 'node':
                nodes[element['id']] = (element['lat'], element['lon'])
        
        routes = []
        for element in data['elements']:
            if element['type'] == 'way' and 'nodes' in element:
                coordinates = []
                for node_id in element['nodes']:
                    if node_id in nodes:
                        coordinates.append(nodes[node_id])
                
                if coordinates:
                    routes.append({
                        'nom': element.get('tags', {}).get('name', 'Unnamed'),
                        'type': element.get('tags', {}).get('highway', 'unknown'),
                        'coordinates': coordinates
                    })
        
        print(f"Routes trouvées : {len(routes)}")
        return routes
        
    except Exception as e:
        print(f"Erreur lors de la récupération OSM : {str(e)}")
        return []

# Récupération des routes OSM
print("Récupération des données OpenStreetMap...")
routes_osm = recuperer_routes_osm()

if not routes_osm:
    print("Aucune route trouvée. Vérifiez votre connexion internet et les paramètres OSM.")
    exit()

# Conversion en format ZONES_SPECIFIQUES
ZONES_SPECIFIQUES = []
for route in routes_osm:
    # Détermination de l'état en fonction du type de route
    if route['type'] in ['primary', 'trunk']:
        etat = 'good'
    elif route['type'] in ['secondary', 'tertiary']:
        etat = 'fair'
    else:
        etat = 'bad' if random.random() > 0.5 else 'fair'
    
    # Création de segments continus
    segments = []
    for i in range(len(route['coordinates'])-1):
        a = route['coordinates'][i]
        b = route['coordinates'][i+1]
        segments.append({
            'debut': a,
            'fin': b,
            'largeur': 0.02 + 0.01*random.random(),  # 20-30m de largeur
            'etat': etat
        })
    
    ZONES_SPECIFIQUES.append({
        'nom': route['nom'],
        'segments': segments
    })

def distance_gps(point1, point2):
    """Calcule la distance en km entre deux points GPS"""
    lat1, lon1 = point1
    lat2, lon2 = point2
    return sqrt((lat2-lat1)**2 + (lon2-lon1)**2) * 111

def generer_chemin_continu():
    """Génère un trajet continu le long des routes OSM"""
    while True:
        if not ZONES_SPECIFIQUES:
            raise ValueError("Aucune route disponible")
            
        route = random.choice(ZONES_SPECIFIQUES)
        for segment in route['segments']:
            a = segment['debut']
            b = segment['fin']
            distance = distance_gps(a, b)
            steps = max(1, int(distance / 0.2))  # 200m entre points
            
            for _ in range(steps):
                t = random.random()
                lat = a[0] + t*(b[0]-a[0])
                lon = a[1] + t*(b[1]-a[1])
                
                # Variation latérale
                angle = random.uniform(-90, 90)
                lat += (segment['largeur']/2 * 0.009) * sin(radians(angle)) * random.uniform(-1,1)
                lon += (segment['largeur']/2 * 0.009) * cos(radians(angle)) * random.uniform(-1,1)
                
                yield (round(lat,6), round(lon,6)), segment['etat']

def accelerometre_realiste(etat):
    """Simule des données d'accéléromètre selon l'état de la route"""
    base = {
        'good': {'x': -1200, 'y': -13800, 'z': -7400},
        'fair': {'x': -2000, 'y': -14300, 'z': -7700},
        'bad': {'x': -3200, 'y': -15200, 'z': -8100}
    }[etat]
    
    return {
        'x': base['x'] + random.randint(-150, 150),
        'y': base['y'] + random.randint(-200, 200),
        'z': base['z'] + random.randint(-150, 150)
    }

# Connexion et création de la table
conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS donnees_routieres (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp DATETIME,
                    accelerometer_x INT,
                    accelerometer_y INT,
                    accelerometer_z INT,
                    latitude DECIMAL(8,6),
                    longitude DECIMAL(8,6),
                    altitude DECIMAL(5,1),
                    satellites TINYINT,
                    road_condition VARCHAR(20)
                )''')

# Génération des données
current = datetime(2025, 2, 1, 7, 0, 0)
fin = datetime(2025, 3, 5, 18, 0, 0)
chemin = generer_chemin_continu()
total = 0

print("Génération des données...")
while current <= fin:
    try:
        (lat, lon), etat = next(chemin)
    except StopIteration:
        print("Aucune route disponible - Fin prématurée")
        break
    
    acc = accelerometre_realiste(etat)
    donnee = (
        current.strftime("%Y-%m-%d %H:%M:%S"),
        acc['x'],
        acc['y'],
        acc['z'],
        lat,
        lon,
        round(random.uniform(*PLAGE_ALTITUDE), 1),
        random.randint(*PLAGE_SATELLITES),
        etat
    )
    
    cursor.execute('''INSERT INTO donnees_routieres 
                    (timestamp, accelerometer_x, accelerometer_y, accelerometer_z,
                     latitude, longitude, altitude, satellites, road_condition)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''', donnee)
    
    total += 1
    current += timedelta(seconds=12 + random.randint(-3, 3))  # 12s ±3s

conn.commit()
conn.close()
print(f"Insertion terminée! {total} enregistrements créés.")