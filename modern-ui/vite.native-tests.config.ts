// Isolated test harness: never used by npm run build or the Dockerfile.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: [{ find: './auth/AuthProvider', replacement: fileURLToPath(new URL('./tests/AuthFixture.tsx', import.meta.url)) }] },
  server: { host: '127.0.0.1', port: 4174, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8765' } },
})
