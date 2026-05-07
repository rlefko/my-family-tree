import { z } from "zod";

const Env = z.object({
  VITE_API_BASE_URL: z.string().url().default("http://localhost:8000"),
  VITE_APP_NAME: z.string().default("My Family Tree"),
});

export const env = Env.parse({
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  VITE_APP_NAME: import.meta.env.VITE_APP_NAME ?? "My Family Tree",
});
