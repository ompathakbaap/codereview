/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d0f14",
        surface: "#13161e",
        border: "#1e2330",
        accent: "#00e5ff",
        "accent-dim": "#00b4cc",
        bug: "#ff4d6d",
        security: "#ff6b35",
        style: "#7c83fd",
        performance: "#f9c74f",
        info: "#90e0ef",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "monospace"],
        sans: ["'DM Sans'", "sans-serif"],
      },
    },
  },
  plugins: [],
};
