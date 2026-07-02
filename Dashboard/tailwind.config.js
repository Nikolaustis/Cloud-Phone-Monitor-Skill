/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#f6f8fc",
        panel: "#ffffff",
        ink: "#172033",
        muted: "#667085",
        line: "#dfe5f0",
        primary: "#2563eb",
        secondary: "#7c3aed",
        success: "#059669",
        warning: "#d97706",
        danger: "#dc2626",
      },
      boxShadow: {
        panel: "0 10px 28px rgba(20, 31, 51, 0.07)",
      },
      borderRadius: {
        xl: "0.75rem",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
