import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({plugins:[react(),tailwindcss()],build:{sourcemap:false,target:'es2022'},server:{port:5173,proxy:{'/api':{target:'https://localhost:8443',secure:false},'/media':{target:'https://localhost:8443',secure:false}}}})
