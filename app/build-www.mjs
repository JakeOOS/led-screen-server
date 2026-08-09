/**
 * Build the web assets Capacitor packages into the APK/AAB.
 *
 * control.html is the single source of the UI and stays that way — this script
 * copies it to www/index.html and injects the two things the packaged build
 * needs that the browser-served /app route does not:
 *
 *   VOXEL_API_BASE   inside the app the page origin is https://localhost, so
 *                    relative /api paths would hit the WebView. control.html
 *                    reads window.VOXEL_API_BASE and prefixes calls with it.
 *   manifest + icons  so the same file also works as an installable PWA when
 *                    served from the web.
 *
 * Run:  npm run build:www      (from the app/ directory)
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "control.html");
const OUT = join(HERE, "www", "index.html");

// The deployed backend. Override for a staging build:
//   VOXEL_API_BASE=https://staging.example.com npm run build:www
const API_BASE = (
  process.env.VOXEL_API_BASE || "https://led-screen-server.onrender.com"
).replace(/\/$/, "");

let html = readFileSync(SRC, "utf8");

// Injected ahead of the page script, which reads it on first line.
const inject = [
  `<link rel="manifest" href="manifest.webmanifest">`,
  `<link rel="icon" href="icons/favicon-32.png" sizes="32x32">`,
  `<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">`,
  `<script>window.VOXEL_API_BASE=${JSON.stringify(API_BASE)};</script>`,
].join("\n");

if (!html.includes("</head>")) throw new Error("control.html has no </head>");
html = html.replace("</head>", `${inject}\n</head>`);

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, html);

console.log(`www/index.html  <-  control.html   (API_BASE ${API_BASE})`);
