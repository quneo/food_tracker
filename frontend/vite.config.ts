import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: {
    rollupOptions: {
      output: {
        // Libraries change rarely: separate files stay cached across app releases.
        manualChunks: {
          react: [
            'react',
            'react-dom',
            'react-dom/client',
            'react-router-dom',
            '@tanstack/react-query',
          ],
          ui: ['radix-ui', 'vaul', 'sonner', 'motion', 'react-day-picker', 'date-fns'],
        },
      },
    },
  },
})
