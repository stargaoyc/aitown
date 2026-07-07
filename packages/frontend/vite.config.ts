import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { TanStackRouterVite } from '@tanstack/router-vite-plugin';
import path from 'node:path';

export default defineConfig({
  plugins: [
    // TanStack Router 自动路由和代码分割
    TanStackRouterVite({ autoCodeSplitting: true }),
    // React 插件，内置 Babel 配置用于 React Compiler
    react({
      babel: {
        plugins: [
          // 直接使用 babel-plugin-react-compiler，无需预设
          ['babel-plugin-react-compiler', { target: '19' }], // 对应 React 19
        ],
      },
    }),
    // Tailwind CSS Vite 插件（V4 版本）
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    target: 'es2024', // 现代浏览器支持
  },
});