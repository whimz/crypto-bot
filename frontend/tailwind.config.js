/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    // Matches the breakpoints already used by hand-written rules in index.css
    // (480px mobile collapse, 640px filter stacking, 840px activity-log table).
    screens: {
      xs: "480px",
      sm: "640px",
      md: "840px",
      lg: "1024px",
      xl: "1280px",
    },
    extend: {
      colors: {
        bg: "var(--bg)",
        "bg-card": "var(--bg-card)",
        border: "var(--border)",
        text: "var(--text)",
        "text-dim": "var(--text-dim)",
        green: "var(--green)",
        red: "var(--red)",
        orange: "var(--orange)",
        accent: "var(--accent)",
      },
    },
  },
  plugins: [],
};
