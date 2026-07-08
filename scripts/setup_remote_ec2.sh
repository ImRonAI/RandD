#!/usr/bin/env bash
set -euo pipefail

echo "=== 1. Updating System Packages ==="
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev nginx rsync git curl ufw

echo "=== 2. Setting Up Backend Python Environment ==="
cd /var/www/strqc/backend
# Delete existing venv to ensure clean permissions
rm -rf venv
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "=== 3. Setting Remote Directory Permissions for Nginx ==="
# Ensure Nginx (www-data) can read the frontend/dist folder
find /var/www/strqc -type d -exec chmod 755 {} +
find /var/www/strqc -type f -exec chmod 644 {} +
# Restore execute permissions on binaries and scripts
if [ -d "/var/www/strqc/backend/venv/bin" ]; then
  find /var/www/strqc/backend/venv/bin -type f -exec chmod +x {} +
fi
if [ -d "/var/www/strqc/scripts" ]; then
  chmod +x /var/www/strqc/scripts/*
fi

echo "=== 4. Configuring Nginx ==="
if sudo [ -f "/etc/letsencrypt/live/44-193-208-77.sslip.io/fullchain.pem" ]; then
  echo "SSL certificate found. Writing HTTPS configuration..."
  cat << 'EOF' | sudo tee /etc/nginx/sites-available/strqc
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name 44-193-208-77.sslip.io;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name 44-193-208-77.sslip.io;

    ssl_certificate /etc/letsencrypt/live/44-193-208-77.sslip.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/44-193-208-77.sslip.io/privkey.pem;

    root /var/www/strqc/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /workspace {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
EOF
else
  echo "No SSL certificate found. Writing HTTP configuration..."
  cat << 'EOF' | sudo tee /etc/nginx/sites-available/strqc
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    root /var/www/strqc/frontend/dist;
    index index.html;

    server_name _;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /workspace {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
EOF
fi

# Enable the new configuration as default
sudo ln -sf /etc/nginx/sites-available/strqc /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "=== 5. Configuring Systemd Service for Backend ==="
cat << 'EOF' | sudo tee /etc/systemd/system/strqc-backend.service
[Unit]
Description=STR QC Backend Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/var/www/strqc/backend
ExecStart=/var/www/strqc/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
Environment=PATH=/var/www/strqc/backend/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EnvironmentFile=/var/www/strqc/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable strqc-backend.service
sudo systemctl restart strqc-backend.service

echo "=== 6. Configuring Firewall ==="
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "=== Remote Setup Complete! ==="
