#!/bin/bash

# Exit on any error
set -e

echo "Starting setup..."

# 1. Update system and install dependencies
echo "Updating packages and installing Python 3 dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip

# 2. Setup Virtual Environment
echo "Setting up Python virtual environment..."
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# 3. Install requirements
echo "Installing Python requirements..."
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

# 4. Create .env file if it doesn't exist
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env file from .env.example..."
    cp "$APP_DIR/.env.example" "$ENV_FILE"

    # Update AGGREGATOR_URL to point to the server IP
    sed -i 's|AGGREGATOR_URL=.*|AGGREGATOR_URL=http://212.113.116.26:8080|' "$ENV_FILE"
    echo "Please edit the $ENV_FILE file to fill in your API tokens and credentials."
else
    echo ".env file already exists, skipping creation."
fi

# 5. Create Systemd Service
SERVICE_NAME="vpnbot.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
USER=$(whoami)

echo "Creating systemd service..."

sudo bash -c "cat > $SERVICE_PATH << EOF
[Unit]
Description=VPN Bot and Aggregator Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/python $APP_DIR/run.py
Restart=always
RestartSec=10
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=multi-user.target
EOF"

# 6. Enable and Start the Service
echo "Reloading systemd, enabling and starting the service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Setup complete! The service is running."
echo "You can check the status with: sudo systemctl status $SERVICE_NAME"
echo "You can view logs with: sudo journalctl -u $SERVICE_NAME -f"
