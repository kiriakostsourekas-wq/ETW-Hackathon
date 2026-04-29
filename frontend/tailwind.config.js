/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        dashboard: {
          bg: "#0f0f0f",
          nav: "#111111",
          card: "#1a1a1a",
          border: "#2a2a2a",
          muted: "#888888",
          accent: "#d4f700",
          blue: "#4fc3f7",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 0 0 1px #2a2a2a",
        active: "0 0 0 1px #d4f700, 0 0 22px rgba(212, 247, 0, 0.12)",
      },
    },
  },
  plugins: [],
};
