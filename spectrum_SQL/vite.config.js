import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import fs from 'fs';
import path from 'path';

// Attempt to read the server configuration dynamically so frontend proxy matches backend
let backendPort = 8000;
try {
  // Using process.cwd() since __dirname is not available in ES modules
  const configPath = path.resolve(process.cwd(), '../nvidia/server_config.json');
  if (fs.existsSync(configPath)) {
    const serverConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (serverConfig.port) {
      backendPort = serverConfig.port;
    }
  }
} catch (e) {
  console.warn("Could not read server_config.json, defaulting backend proxy port to 8000");
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      }
    }
  }
})
