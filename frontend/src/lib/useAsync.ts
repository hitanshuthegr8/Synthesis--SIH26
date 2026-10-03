import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api";

export type Async<T> = {
  status: "idle" | "loading" | "success" | "error";
  data: T | null;
  error: string | null;
  reload: () => void;
};

/** Run an async loader whenever `deps` change; stale responses from superseded calls are dropped. */
export function useAsync<T>(loader: (() => Promise<T>) | null, deps: unknown[]): Async<T> {
  const [state, setState] = useState<Omit<Async<T>, "reload">>({ status: "idle", data: null, error: null });
  const [nonce, setNonce] = useState(0);
  const call = useRef(0);
  useEffect(() => {
    if (!loader) {
      setState({ status: "idle", data: null, error: null });
      return;
    }
    const id = ++call.current;
    setState((previous) => ({ status: "loading", data: previous.data, error: null }));
    loader().then(
      (data) => { if (id === call.current) setState({ status: "success", data, error: null }); },
      (error: unknown) => {
        if (id !== call.current) return;
        setState({ status: "error", data: null, error: error instanceof ApiError || error instanceof Error ? error.message : "Request failed" });
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { ...state, reload };
}
