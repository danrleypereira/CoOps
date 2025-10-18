import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Dynamic base path: use root for dev, repo name for GitHub Pages
  base: process.env.NODE_ENV === 'production' && process.env.VITE_REPO_NAME
    ? `/${process.env.VITE_REPO_NAME}/`
    : '/',
})
