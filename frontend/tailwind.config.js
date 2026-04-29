/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#202326",
        muted: "#6d7280",
        shell: "#f7f5f0",
        card: "#fffdf8",
        line: "#e7e1d7",
        charge: "#2f9d66",
        idle: "#b8bbc2",
        discharge: "#df6b45",
        price: "#365f93",
      },
      boxShadow: {
        soft: "0 18px 50px rgba(43, 39, 32, 0.08)",
        card: "0 10px 30px rgba(43, 39, 32, 0.06)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
};
