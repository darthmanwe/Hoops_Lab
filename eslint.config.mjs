import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default [
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/.wrangler/**",
      "**/dist/**",
      "**/build/**",
      "**/coverage/**",
      "services/ml/**",
      "data/**",
      // Generated. Regenerate with `npm run gen`.
      "apps/web/src/lib/api/generated/**",
      "contracts/**",
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ["**/*.{js,mjs,jsx,ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // Unused args are allowed only when explicitly marked with a leading
      // underscore, so "I know this is unused" is always a deliberate signal.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // The whole point of the revamp is that every served value is typed and
      // traceable. `any` re-opens the `Record<string, unknown>` hole.
      "@typescript-eslint/no-explicit-any": "error",
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },

  // The Worker runs on workerd, not Node. Node globals here are a bug.
  {
    files: ["apps/api/**/*.ts"],
    languageOptions: { globals: { ...globals.worker } },
  },

  prettier,
];
