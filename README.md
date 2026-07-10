# ERP Co-Pilot: Linux Deployment Guide GR

This guide walks you through deploying the ERP Co-Pilot (FastAPI Backend + React/Vite Frontend) onto a fresh Linux server (e.g., Ubuntu 22.04 LTS).

> **IMPORTANT**
> Because this application uses `FlagEmbedding/Transformers` for local machine learning models, **you must ensure the server has adequate RAM** before running `pip install` to avoid compilation errors during the build phase of these heavy libraries.

---

## 1. System Requirements
- **OS:** Ubuntu 22.04 LTS (Recommended)
- **RAM:** Minimum 4GB (8GB Recommended due to the `BGE-M3` embedding model and Pandas data manipulation).
- **CPU:** 2+ Cores

---

## 2. Install OS-Level Dependencies

Before installing Python or Node packages, you need the system-level build tools.

### 2.1 Update System & Install Build Tools
```bash
sudo apt-get update
sudo apt-get install -y build-essential curl git software-properties-common
```

---

## 3. Backend Deployment (FastAPI)

### 3.1 Install Python 3.10+ & Virtual Environment
```bash
sudo apt-get install -y python3 python3-pip python3-venv
```

### 3.2 Setup the Environment
```bash
# Clone your code (or copy it over)
git clone <your-repo-url>
cd <your-repo-folder>

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate
```

### 3.3 Install Python Dependencies
```bash
# Install the requirements (FastAPI, SQLAlchemy, PyTorch, etc.)
pip install -r requirements.txt
```
> **NOTE:** The installation of `torch` and `transformers` might take a few minutes as they are large machine learning libraries.

### 3.4 Environment Variables
Create a `.env` file inside the `nvidia` folder:
```bash
nano nvidia/.env
```
Paste your secrets:
```ini
DB_CONNECTION_STRING="sqlite:///spectrum.db"  # Example SQLAlchemy string
GEMINI_API_KEY="your-gemini-key"
QDRANT_API_KEY="your-qdrant-cloud-key"  # (If using Qdrant Cloud)
```

### 3.5 Initial Setup (Database & Vector Store)
If you are deploying for the first time and using the local Qdrant embedded mode, you must build the vector store:
```bash
python nvidia/vector_store.py
```

### 3.6 Run the Server
For production, run the server using `uvicorn` without the `--reload` flag. You can run it in the background using `nohup`, or ideally set it up as a `systemd` service.
```bash
uvicorn main:app --app-dir nvidia --host 0.0.0.0 --port 8000
```

---

## 4. Frontend Deployment (React / Vite)

### 4.1 Install Node.js & npm
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 4.2 Build the Frontend
```bash
cd spectrum_SQL
npm install
npm run build
```
This will generate a `dist` folder containing static HTML/JS/CSS files.

### 4.3 Serve the Frontend
For a production environment, it is highly recommended to serve the `dist` folder using a web server like **Nginx**, rather than running the Vite dev server (`npm run dev`).

**Install Nginx:**
```bash
sudo apt-get install nginx
```

**Configure Nginx to serve the React app and proxy the API:**
```bash
sudo nano /etc/nginx/sites-available/default
```

Replace the contents with:
```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    # Serve the React App
    location / {
        root /path/to/your/project/spectrum_SQL/dist;
        index index.html index.htm;
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_addrs;
    }
}
```

**Restart Nginx:**
```bash
sudo systemctl restart nginx
```

---

## 5. Final Checklist
- [ ] Are the Python dependencies fully installed in the virtual env (`SQLAlchemy`, `aiosqlite`, etc.)?
- [ ] Have you generated the local `new_qdrant_db` or pointed to Qdrant Cloud?
- [ ] Did you build the React app (`npm run build`)?
- [ ] Is Nginx running and pointing to the correct `dist` folder?

Your app is now live!
