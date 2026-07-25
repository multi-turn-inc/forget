#!/usr/bin/env node

import { main } from "../src/cli.js";

for (const stream of [process.stdout, process.stderr]) {
  stream.on("error", (error) => {
    if (error?.code === "EPIPE") process.exit(0);
    throw error;
  });
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`forget-connect: ${message}`);
  process.exitCode = 1;
});
