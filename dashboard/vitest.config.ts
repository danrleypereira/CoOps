import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    // Tests exercise the *configured* data source by default; the "unconfigured"
    // (fail-closed) behaviour is asserted explicitly by stubbing VITE_GITHUB_ORG
    // to an empty value in the relevant tests.
    env: {
      VITE_GITHUB_ORG: 'test-org',
      VITE_GITHUB_REPO: 'test-repo',
    },
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'src/setupTests.ts',
        '**/*.config.ts',
        '**/*.d.ts',
        '**/types.ts',
        'src/main.tsx',
        'src/types/**',           
        '**/types/**',            
        '**/*.test.{ts,tsx}',     
        '**/*.spec.{ts,tsx}',    
      ],
      include: ['src/**/*.{ts,tsx}'],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 60,
        statements: 60,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});