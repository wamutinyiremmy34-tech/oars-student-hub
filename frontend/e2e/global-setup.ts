import { execSync } from "node:child_process";
import { backendEnv } from "./env";

/** Migrates the E2E database and loads the demo data (the backend virtualenv must be active). */
export default function globalSetup(): void {
  const options = { cwd: "../backend", env: backendEnv(), stdio: "inherit" as const };
  execSync("python -m alembic upgrade head", options);
  execSync("python -m app.cli seed-demo", options);
}
