// Next.js 16 flat ESLint yapılandırması: eslint-config-next artık düz (flat) config
// dizileri ihraç eder — FlatCompat gerekmez (Next 16'da `next lint` kaldırıldı).

import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...coreWebVitals,
  ...typescript,
  {
    rules: {
      // Türkçe metinde kesme işareti (ör. "API'ye") yaygındır; escape zorunluluğu
      // gereksiz gürültü yaratır (ruff'ta RUF001-003'ü kapatmamıza paralel).
      "react/no-unescaped-entities": "off",
    },
  },
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
];

export default eslintConfig;
