import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';

export default ({ mode }) => {
  // Load environment variables based on the current mode (e.g., 'development', 'production')
  const env = loadEnv(mode, process.cwd());

  return defineConfig({
    plugins: [vue()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },
    server: {
      host: '0.0.0.0',
      port: parseInt(env.VITE_PORT),  // Access the port directly from the env object
      open: env.VITE_OPEN_BROWSER === 'false' ? false : true,  // Use the environment variable to control browser opening, default to true
    },
  });
};