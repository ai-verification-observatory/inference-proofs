import type { NextConfig } from "next";

// Static export: every page is plain HTML on the CDN, readable without client JavaScript (RFC-0009 §Site).
const config: NextConfig = { output: "export", trailingSlash: true, poweredByHeader: false };

export default config;
