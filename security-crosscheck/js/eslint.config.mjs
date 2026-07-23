// Only the eslint-plugin-security rules that fall inside the scope the MODScan
// security lens claims: code execution, process spawning, dynamic loading.
// Its other rules (unsafe regex, object injection, timing attacks, fs filenames,
// pseudo-random bytes) are deliberately left off — the lens does not claim them,
// so counting them would measure a promise never made.
import security from "eslint-plugin-security";

export default [
  {
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
    languageOptions: { ecmaVersion: "latest", sourceType: "module" },
    plugins: { security },
    rules: {
      "security/detect-eval-with-expression": "error", // code_exec
      "security/detect-child-process": "error",        // process
      "security/detect-non-literal-require": "error",  // dynamic_load
    },
  },
];
