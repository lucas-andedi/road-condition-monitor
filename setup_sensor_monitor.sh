#!/bin/bash

# Script d'installation complet pour le moniteur de capteurs Raspberry Pi
# Ce script:
# 1. Installe les dépendances nécessaires
# 2. Configure le script pour démarrer automatiquement au démarrage
# 3. Démarre le service immédiatement

# Couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Nom de l'application
APP_NAME="sensor_monitor"
SCRIPT_NAME="Jean.py"

# Obtenir le chemin absolu du répertoire courant
CURRENT_DIR=$(pwd)
SCRIPT_PATH="$CURRENT_DIR/$SCRIPT_NAME"

# Vérifier si le script existe
if [ ! -f "$SCRIPT_PATH" ]; then
    echo -e "${RED}Erreur: Le fichier $SCRIPT_NAME n'existe pas dans le répertoire courant.${NC}"
    echo -e "Veuillez placer ce script d'installation dans le même répertoire que $SCRIPT_NAME."
    exit 1
fi

echo -e "${BLUE}=== Installation du moniteur de capteurs Raspberry Pi ===${NC}"
echo -e "${YELLOW}Ce script va configurer votre application pour démarrer automatiquement au démarrage.${NC}"
echo ""

# Étape 1: Installer les dépendances
echo -e "${BLUE}[1/5] Installation des dépendances...${NC}"
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev i2c-tools sqlite3

# Activer I2C si ce n'est pas déjà fait
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo -e "${YELLOW}Activation de l'interface I2C...${NC}"
    sudo sh -c 'echo "dtparam=i2c_arm=on" >> /boot/config.txt'
    echo -e "${GREEN}Interface I2C activée. Un redémarrage sera nécessaire pour l'appliquer.${NC}"
fi

# Installer les bibliothèques Python nécessaires
echo -e "${YELLOW}Installation des bibliothèques Python...${NC}"
pip3 install smbus2 pyserial requests

echo -e "${GREEN}Dépendances installées avec succès.${NC}"
echo ""

# Étape 2: Rendre le script exécutable
echo -e "${BLUE}[2/5] Configuration du script Python...${NC}"
chmod +x "$SCRIPT_PATH"

# Vérifier si le shebang est présent, sinon l'ajouter
if ! head -1 "$SCRIPT_PATH" | grep -q "^#!/usr/bin/env python3"; then
    echo -e "${YELLOW}Ajout de la ligne shebang au script...${NC}"
    sed -i '1s/^/#!/usr\/bin\/env python3\n/' "$SCRIPT_PATH"
fi

echo -e "${GREEN}Script Python configuré avec succès.${NC}"
echo ""

# Étape 3: Créer le fichier de service systemd
echo -e "${BLUE}[3/5] Création du service systemd...${NC}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

sudo bash -c "cat > $SERVICE_FILE << EOF
[Unit]
Description=Raspberry Pi Sensor Monitor
After=network.target

[Service]
ExecStart=/usr/bin/python3 $SCRIPT_PATH
WorkingDirectory=$CURRENT_DIR
Restart=always
RestartSec=10
User=$(whoami)
Group=$(id -gn)
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF"

echo -e "${GREEN}Fichier de service créé avec succès.${NC}"
echo ""

# Étape 4: Activer et démarrer le service
echo -e "${BLUE}[4/5] Activation et démarrage du service...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable $APP_NAME
sudo systemctl start $APP_NAME

# Vérifier si le service a démarré correctement
if sudo systemctl is-active --quiet $APP_NAME; then
    echo -e "${GREEN}Service démarré avec succès.${NC}"
else
    echo -e "${RED}Erreur: Le service n'a pas pu démarrer.${NC}"
    echo -e "${YELLOW}Vérifiez les logs avec: sudo journalctl -u $APP_NAME${NC}"
fi
echo ""

# Étape 5: Créer un fichier de log si nécessaire
echo -e "${BLUE}[5/5] Configuration de la journalisation...${NC}"
LOG_FILE="$CURRENT_DIR/sensor_monitor.log"
touch $LOG_FILE
chmod 666 $LOG_FILE
echo -e "${GREEN}Fichier de log créé: $LOG_FILE${NC}"
echo ""

# Résumé et instructions
echo -e "${BLUE}=== Installation terminée ===${NC}"
echo -e "${GREEN}Votre application est maintenant configurée pour démarrer automatiquement au démarrage du Raspberry Pi.${NC}"
echo ""
echo -e "${YELLOW}Commandes utiles:${NC}"
echo -e "  - Vérifier l'état du service: ${BLUE}sudo systemctl status $APP_NAME${NC}"
echo -e "  - Voir les logs du service: ${BLUE}sudo journalctl -u $APP_NAME -f${NC}"
echo -e "  - Redémarrer le service: ${BLUE}sudo systemctl restart $APP_NAME${NC}"
echo -e "  - Arrêter le service: ${BLUE}sudo systemctl stop $APP_NAME${NC}"
echo -e "  - Désactiver le démarrage automatique: ${BLUE}sudo systemctl disable $APP_NAME${NC}"
echo ""

# Vérifier si un redémarrage est nécessaire pour I2C
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo -e "${YELLOW}IMPORTANT: Un redémarrage est nécessaire pour activer l'interface I2C.${NC}"
    echo -e "Voulez-vous redémarrer maintenant? (o/n)"
    read -r response
    if [[ "$response" =~ ^([oO][uU][iI]|[oO])$ ]]; then
        echo -e "${BLUE}Redémarrage du Raspberry Pi...${NC}"
        sudo reboot
    else
        echo -e "${YELLOW}N'oubliez pas de redémarrer plus tard pour activer l'interface I2C.${NC}"
    fi
fi

exit 0

