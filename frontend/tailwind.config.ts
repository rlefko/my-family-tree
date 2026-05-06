// Tailwind v4 sources its theme from @theme blocks in src/styles/globals.css
// rather than a JS config file. This file is kept for tooling that expects
// a tailwind.config.* to exist (Prettier plugin, IDE plugins, shadcn).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
};
