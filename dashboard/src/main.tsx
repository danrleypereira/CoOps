import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './index.css';
import App from './App.tsx';

/**
 * Application Entry Point
 *
 * Initializes the React application with routing support.
 * The basename is dynamically set based on Vite's base config:
 * - Development: "/" (from vite.config.ts)
 * - Production: "/{REPO_NAME}/" (from VITE_REPO_NAME env var)
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <App />
    </BrowserRouter>
  </StrictMode>
);
