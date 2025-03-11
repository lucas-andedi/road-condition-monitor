import mysql.connector
import random
from datetime import datetime, timedelta
from math import sin, cos, radians, sqrt, degrees, atan2

# Configuration MySQL
DB_CONFIG = {
    'host': 'localhost',
    'user': 'admin',
    'password': 'admin',
    'database': 'road_monitor'
}

# Itinéraire Aller : Gare Centrale -> Aéroport
ROUTE_ALLER = [
    # Boulevard du 30 Juin (Centre-ville)
    {
        'nom': 'Boulevard du 30 Juin',
        'points': [
            (-4.3250, 15.3100),
            (-4.3300, 15.3250),
            (-4.3400, 15.3500)
        ],
        'largeur': 0.15,
        'etat': 'good'
    },
    # Boulevard Triomphal (Zone rénovée)
    {
        'nom': 'Boulevard Triomphal',
        'points': [
            (-4.3400, 15.3500),
            (-4.3500, 15.3650),
            (-4.3600, 15.3800)
        ],
        'largeur': 0.18,
        'etat': 'good'
    },
    # Boulevard Lumumba (Artère secondaire)
    {
        'nom': 'Boulevard Lumumba',
        'points': [
            (-4.3600, 15.3800),
            (-4.3750, 15.4000),
            (-4.3850, 15.4200)
        ],
        'largeur': 0.20,
        'etat': 'fair'
    },
    # Route des Poids Lourds (Zone industrielle)
    {
        'nom': 'Route des Poids Lourds',
        'points': [
            (-4.3850, 15.4200),
            (-4.3900, 15.4350),
            (-4.3833, 15.4417)  # Aéroport
        ],
        'largeur': 0.25,
        'etat': 'fair'
    }
]

# Itinéraire Retour : Aéroport -> Gare Centrale
ROUTE_RETOUR = [
    # Route de la Libération (ex 24 Novembre)
    {
        'nom': 'Route de la Libération',
        'points': [
            (-4.3833, 15.4417),
            (-4.3950, 15.4300),
            (-4.4050, 15.4100)
        ],
        'largeur': 0.22,
        'etat': 'fair'
    },
    # Avenue Kabinda (Zone dégradée)
    {
        'nom': 'Avenue Kabinda',
        'points': [
            (-4.4050, 15.4100),
            (-4.4150, 15.3900),
            (-4.4250, 15.3700)
        ],
        'largeur': 0.18,
        'etat': 'bad'
    },
    # Avenue Nyangwe (Prolongement dégradé)
    {
        'nom': 'Avenue Nyangwe',
        'points': [
            (-4.4250, 15.3700),
            (-4.4100, 15.3500),
            (-4.3950, 15.3300)
        ],
        'largeur': 0.15,
        'etat': 'bad'
    },
    # Boulevard Sendwe (Artère secondaire)
    {
        'nom': 'Boulevard Sendwe',
        'points': [
            (-4.3950, 15.3300),
            (-4.3800, 15.3150),
            (-4.3650, 15.3000)
        ],
        'largeur': 0.16,
        'etat': 'fair'
    },
    # Avenue de la Démocratie (Retour vers centre)
    {
        'nom': 'Avenue de la Démocratie',
        'points': [
            (-4.3650, 15.3000),
            (-4.3500, 15.2900),
            (-4.3250, 15.3100)  # Gare Centrale
        ],
        'largeur': 0.14,
        'etat': 'bad'
    }
]

# Paramètres généraux
PLAGE_ALTITUDE = (275.0, 285.0)
PLAGE_SATELLITES = (6, 9)
VARIATION_GPS = 0.0002  # 20m de variation
DUREE_TRAJET = 45  # Minutes pour un trajet complet

def distance_gps(point1, point2):
    """Calcule la distance en km entre deux points GPS"""
    lat1, lon1 = point1
    lat2, lon2 = point2
    return sqrt((lat2-lat1)**2 + (lon2-lon1)**2) * 111

def generer_chemin_continu():
    """Génère un trajet continu avec aller-retour alternés"""
    while True:
        # 50% de chances de prendre l'aller ou le retour
        if random.random() < 0.5:
            for segment in ROUTE_ALLER:
                yield from parcourir_segment(segment)
        else:
            for segment in ROUTE_RETOUR:
                yield from parcourir_segment(segment)

def parcourir_segment(segment):
    """Parcourt un segment routier avec variation réaliste"""
    points = segment['points']
    etat = segment['etat']
    largeur = segment['largeur']
    
    for i in range(len(points)-1):
        a = points[i]
        b = points[i+1]
        distance = distance_gps(a, b)
        steps = int(distance / 0.2)  # 200m entre chaque point
        
        for _ in range(steps):
            t = random.random()
            lat = a[0] + t*(b[0]-a[0])
            lon = a[1] + t*(b[1]-a[1])
            
            # Variation latérale
            angle = random.uniform(-90, 90)
            lat += (largeur/2 * 0.009) * sin(radians(angle)) * random.uniform(-1,1)
            lon += (largeur/2 * 0.009) * cos(radians(angle)) * random.uniform(-1,1)
            
            yield (round(lat,6), round(lon,6)), etat

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

while current <= fin:
    try:
        (lat, lon), etat = next(chemin)
    except StopIteration:
        chemin = generer_chemin_continu()
        continue
    
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