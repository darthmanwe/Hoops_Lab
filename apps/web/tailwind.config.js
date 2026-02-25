/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/app/**/*.{js,jsx}",
    "./src/components/**/*.{js,jsx}",
    "./src/lib/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#04050b",
          900: "#090f1f",
          800: "#0d1831",
        },
        court: {
          500: "#f39237",
          400: "#f5a14f",
          300: "#f8ba7b",
        },
        neon: {
          500: "#3f88ff",
          400: "#5ba0ff",
          300: "#87bbff",
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(91,160,255,0.25), 0 8px 30px rgba(6,14,35,0.55)",
      },
      backgroundImage: {
        "court-grid":
          "radial-gradient(circle at 20% 20%, rgba(245,161,79,0.08), transparent 25%), radial-gradient(circle at 80% 10%, rgba(91,160,255,0.08), transparent 30%), linear-gradient(120deg, rgba(9,15,31,0.98), rgba(4,5,11,0.98))",
      },
    },
  },
  plugins: [],
};
