import type { NextConfig } from "next";
import baseConfig from "./next.config";

// Desktop WebView loads pre-rendered files from the Tauri asset origin, so the
// production server/runtime features from next.config.ts are not available.
const desktopConfig: NextConfig = {
  ...baseConfig,
  output: "export",
  images: {
    unoptimized: true,
  },
  trailingSlash: true,
};

export default desktopConfig;
