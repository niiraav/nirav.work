"use client";
import { useEffect } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_MSW === "true") {
      import("../mocks/browser").then(({ worker }) =>
        worker.start({ onUnhandledRequest: "bypass" })
      );
    }
  }, []);
  return <>{children}</>;
}
