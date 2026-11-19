import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Narrowly resolve allowed tunnel host:
// Prioritizes explicit hostname from FRONTEND_PUBLIC_URL or TUNNEL_HOST,
// and falls back to '.trycloudflare.com' for Cloudflare Quick Tunnel testing.
const resolveAllowedHosts = () => {
  const explicitUrl = process.env.FRONTEND_PUBLIC_URL || process.env.TUNNEL_HOST;
  if (explicitUrl) {
    try {
      const hostname = new URL(explicitUrl.startsWith('http') ? explicitUrl : `https://${explicitUrl}`).hostname;
      if (hostname) return [hostname];
    } catch {
      const trimmed = explicitUrl.replace(/^https?:\/\//, '').split('/')[0].split(':')[0];
      if (trimmed) return [trimmed];
    }
  }
  return ['.trycloudflare.com'];
};

// ESM-compatible local development HTTPS certificate resolution:
// Standard HTTP is used by default for local development (http://localhost:5173).
// Local HTTPS can be enabled by setting VITE_HTTPS=true or HTTPS=true when certs exist in frontend/certs.
const resolveHttpsConfig = () => {
  if (process.env.VITE_HTTPS !== 'true' && process.env.HTTPS !== 'true') {
    return false;
  }
  try {
    const certsDir = fileURLToPath(new URL('./certs', import.meta.url));
    const certPath = path.join(certsDir, 'cert.pem');
    const keyPath = path.join(certsDir, 'key.pem');
    if (fs.existsSync(certPath) && fs.existsSync(keyPath)) {
      return {
        cert: fs.readFileSync(certPath),
        key: fs.readFileSync(keyPath)
      };
    }
  } catch (err) {
    console.warn('[Vite HTTPS] Failed to read local certificates, falling back to HTTP:', err.message);
  }
  return false;
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    https: resolveHttpsConfig(),
    allowedHosts: resolveAllowedHosts(),
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true
      }
    }
  }
})
