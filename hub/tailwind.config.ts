import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#0A192F",
          light: "#112240",
          lighter: "#233554",
        },
        teal: {
          DEFAULT: "#20B2AA",
          light: "#64FFDA",
        },
        slate: {
          900: "#0F172A",
          800: "#1E293B",
          100: "#F1F5F9",
        }
      },
      fontFamily: {
        inter: ["Inter", "sans-serif"],
        roboto: ["Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
