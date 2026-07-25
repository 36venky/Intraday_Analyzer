import { useEffect, useRef } from "react";

export function useInterval(callback, delay) {
  const savedCb = useRef(callback);
  useEffect(() => { savedCb.current = callback; }, [callback]);
  useEffect(() => {
    if (delay === null) return;
    const id = setInterval(() => savedCb.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}
