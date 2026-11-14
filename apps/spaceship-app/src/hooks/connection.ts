import { createContext, useContext } from "react";

export type ConnectionState = "unknown" | "online" | "offline";

/** Polling hooks report whether the service answered (any HTTP status) or not. */
export type ConnectionReporter = (reachable: boolean) => void;

export const ConnectionContext = createContext<ConnectionReporter>(() => {});

export function useConnectionReporter(): ConnectionReporter {
  return useContext(ConnectionContext);
}
