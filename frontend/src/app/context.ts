import { createContext, useContext } from "react";
import type { Catalog } from "../types/synthesis";

export type PageId = "command" | "explorer" | "reliability" | "extremes" | "lab" | "operations" | "verification";

export type AppState = {
  catalog: Catalog | null;
  catalogError: string | null;
  /** Selected 00Z cycle (ISO); undefined lets the backend pick the latest complete one. */
  cycle: string | undefined;
  navigate: (page: PageId, params?: Record<string, string>) => void;
  params: URLSearchParams;
};

export const AppContext = createContext<AppState>({
  catalog: null,
  catalogError: null,
  cycle: undefined,
  navigate: () => undefined,
  params: new URLSearchParams(),
});

export const useApp = () => useContext(AppContext);
