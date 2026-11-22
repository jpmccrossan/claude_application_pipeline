import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development (npm run dev) the API runs separately: python -m server --no-browser
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765", "/fonts": "http://127.0.0.1:8765" } },
  build: { outDir: "dist", emptyOutDir: true },
});
