/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        tg: {
          bg:       "var(--tg-theme-bg-color, #ffffff)",
          text:     "var(--tg-theme-text-color, #000000)",
          hint:     "var(--tg-theme-hint-color, #999999)",
          link:     "var(--tg-theme-link-color, #2481cc)",
          btn:      "var(--tg-theme-button-color, #2481cc)",
          "btn-txt":"var(--tg-theme-button-text-color, #ffffff)",
          "sec-bg": "var(--tg-theme-secondary-bg-color, #f1f1f1)",
        },
      },
    },
  },
  plugins: [],
};
