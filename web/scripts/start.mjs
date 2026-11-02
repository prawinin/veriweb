import { cp, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const server = new URL(".next/standalone/server.js", root);
await access(server);
await cp(
  new URL(".next/static", root),
  new URL(".next/standalone/.next/static", root),
  { recursive: true },
);
process.env.HOSTNAME = process.env.HOST || "127.0.0.1";
process.env.PORT ||= "3000";
const port = Number(process.env.PORT);
if (!Number.isInteger(port) || port < 0 || port > 65535)
  throw new Error("PORT must be between 0 and 65535");
process.chdir(fileURLToPath(root));
await import(server.href);
