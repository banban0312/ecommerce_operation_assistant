import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // standalone 产物只携带生产运行所需文件，供多阶段 Docker 构建使用。
  output: "standalone",
  // 隐藏默认响应头，减少不必要的框架信息暴露。
  poweredByHeader: false,
};

export default nextConfig;
