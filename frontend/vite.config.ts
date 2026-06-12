import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://localhost:8000",
      "/config": "http://localhost:8000",
      "/threads": "http://localhost:8000",
      "/chat": "http://localhost:8000",
      "/mock": "http://localhost:8000",
    },
  },
});
