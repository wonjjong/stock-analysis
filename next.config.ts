import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 크롤러·인사이트가 Node 소켓을 쓰는 `pg`를 거쳐 DB에 붙는다. 서버 번들에 넣지 않고
  // 런타임에서 그대로 require 하게 둔다.
  serverExternalPackages: ["pg"],
};

export default nextConfig;
