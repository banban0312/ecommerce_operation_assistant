import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  // 使用 Next.js 核心网页指标和 TypeScript 推荐规则。
  ...nextVitals,
  ...nextTs,
  // 构建产物和 Next.js 自动生成的类型文件不参与源码检查。
  globalIgnores([".next/**", "out/**", "next-env.d.ts"]),
]);
