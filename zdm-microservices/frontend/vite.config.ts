import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const backendProxy = {
  target: 'https://localhost:8001',
  changeOrigin: true,
  secure: false,
};

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/metadata': backendProxy,
      '/projects': backendProxy,
      '/dbconnections': backendProxy,
      '/responsefiles': backendProxy,
      '/saved-jobs': backendProxy,
      '/jobs': backendProxy,
      '/joblogs': backendProxy,
      '/credential-wallets': backendProxy,
      '/wallets': backendProxy,
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: './src/test/setup.ts',
  },
});
