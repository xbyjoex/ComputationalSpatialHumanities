/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        display: ['"IBM Plex Sans Condensed"', '"IBM Plex Sans"', "sans-serif"],
      },
      colors: {
        gotham: {
          950: "#06090c",
          900: "#0a1015",
          850: "#0e151c",
          800: "#121b23",
          750: "#17222c",
          700: "#1e2e3a",
          600: "#2b4253",
          500: "#3d5a6e",
          400: "#678599",
          300: "#93afc0",
          200: "#c6d8e2",
          100: "#e7f0f6",
        },
        signal: {
          cyan: "#53b9e8",
          bright: "#9adcff",
          green: "#3dd68c",
          amber: "#ffb02e",
          red: "#ff6e5e",
          violet: "#9d8cff",
        },
        // Legacy alias — mapped onto the cyan signal ramp
        brand: {
          50: "#eaf6fc",
          100: "#d3edf9",
          300: "#9adcff",
          400: "#53b9e8",
          500: "#3fa3d4",
          600: "#2f86b3",
          700: "#256c91",
          900: "#0f2733",
        },
      },
      animation: {
        led: "led 2.4s ease-in-out infinite",
        rise: "rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
      keyframes: {
        led: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
        rise: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "none" },
        },
      },
    },
  },
  plugins: [],
};
