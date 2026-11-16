import { tmpdir } from "node:os";
import { join } from "node:path";

export const API_PORT = 8001;
export const WEB_PORT = 5174;
export const API = `http://localhost:${API_PORT}/api/v1`;

/** The E2E backend uses its OWN database and storage folder, so it never touches development data. */
export function backendEnv(): Record<string, string> {
  const inherited = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  return {
    ...inherited,
    APP_ENV: "development",
    LOG_FORMAT: "console",
    DATABASE_URL:
      process.env.E2E_DATABASE_URL ?? "postgresql+psycopg://oars:oars_dev_password@localhost:5432/oars_e2e",
    STORAGE_LOCAL_PATH: join(tmpdir(), "oars-e2e-storage"),
    CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
    AUTH_RATE_LIMIT_ATTEMPTS: "1000",
    MAX_OUTSTANDING_PICKUP_ORDERS: "50", // repeated test runs must not trip the pay-on-pickup abuse limit
  };
}
