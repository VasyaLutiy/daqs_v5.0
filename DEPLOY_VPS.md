# Deploy On Remote VPS

This runbook deploys the new React frontend and the FastAPI backend from this repo onto a remote VPS with Docker Compose.

## What gets deployed

- `daqs`: backend container with FastAPI on `8001` and Streamlit debug UI on `8501`
- `daqs_web`: Next.js React frontend on `3000`

## 1. Prepare the VPS

Recommended baseline:

- Ubuntu 22.04 or 24.04
- 2 vCPU
- 4 GB RAM
- 20+ GB disk
- Docker Engine with Compose plugin installed

Install Docker on a fresh Ubuntu box:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
newgrp docker
```

## 2. Open the required ports

If you want the simplest direct-IP deployment:

- `22` for SSH
- `3000` for the React frontend
- `8001` for the public backend API

If you do not need Streamlit remotely, do not open `8501`.

Example with `ufw`:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 3000/tcp
sudo ufw allow 8001/tcp
sudo ufw enable
sudo ufw status
```

## 3. Clone the project

```bash
cd /opt
sudo mkdir -p daqs
sudo chown "$USER":"$USER" daqs
cd daqs
git clone <YOUR_REPO_URL> .
```

## 4. Create the production `.env`

Copy the template and fill the real values:

```bash
cp env.example .env
nano .env
```

Minimum required values:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_real_key
GEMINI_MODEL=gemini-3-flash-preview
NEXT_PUBLIC_API_BASE=http://YOUR_VPS_PUBLIC_IP:8001
FRONTEND_ORIGINS=http://YOUR_VPS_PUBLIC_IP:3000
```

If you deploy behind domains instead of raw IPs:

```env
NEXT_PUBLIC_API_BASE=https://api.your-domain.com
```

Important:

- `NEXT_PUBLIC_API_BASE` is baked into the React build.
- If you change it later, rebuild `daqs_web` with `docker compose up -d --build daqs_web`.
- `FRONTEND_ORIGINS` must include the exact browser origin of your frontend (scheme + host + port), otherwise FastAPI will block preflight with CORS error.

## 5. Build and start the stack

```bash
docker compose up -d --build
```

This will:

- build the backend image from the repo `Dockerfile`
- build the frontend image from `frontend/Dockerfile`
- start both services

## 6. Verify health

Check containers:

```bash
docker compose ps
```

Check backend health:

```bash
curl -fsS http://127.0.0.1:8001/health
```

Check frontend response:

```bash
curl -I http://127.0.0.1:3000
```

Check logs if something is wrong:

```bash
docker compose logs -f --tail=200 daqs
docker compose logs -f --tail=200 daqs_web
```

## 7. Access the app

Direct access:

- React frontend: `http://YOUR_VPS_PUBLIC_IP:3000`
- Backend API: `http://YOUR_VPS_PUBLIC_IP:8001/health`

The Streamlit debug UI is also exposed by default on `8501`, but it is not part of the new production frontend and should usually stay firewalled.

## 8. Update deployment

```bash
cd /opt/daqs
git pull --ff-only
docker compose up -d --build
```

If you changed only the public backend URL for the React app:

```bash
docker compose up -d --build daqs_web
```

## 9. Persistent data

The compose file already persists:

- `player_state.json`
- generated static assets in Docker volume `daqs_static`
- logs in Docker volume `daqs_logs`

Inspect volumes:

```bash
docker volume ls | grep daqs
```

## 10. Recommended hardening

For a quick test deployment, direct ports are enough. For a real public deployment, use a reverse proxy in front of this stack.

Recommended production shape:

- expose only `80/443` publicly
- proxy frontend to `localhost:3000`
- proxy API to `localhost:8001`
- keep `8501` closed
- use HTTPS

If you move to a reverse proxy later, update `.env`:

```env
NEXT_PUBLIC_API_BASE=https://api.your-domain.com
```

Then rebuild:

```bash
docker compose up -d --build daqs_web
```
