"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

type Simulation = { status: "idle" | "running" | "complete" | "cancelled"; phase: number; context: string };

function useDemoState() {
  const pathname = usePathname();
  const [website, setWebsite] = useState("");
  const [simulation, setSimulation] = useState<Simulation>({ status: "idle", phase: 0, context: "" });
  const [marked, setMarked] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("전체");
  const [status, setStatus] = useState("전체");
  const [facts, setFacts] = useState({ service: "", date: "", observation: "", action: "" });
  const [draft, setDraft] = useState("");

  const startSimulation = useCallback((context: string) => {
    setMarked([]); setSearch(""); setPriority("전체"); setStatus("전체");
    setSimulation({ status: "running", phase: 0, context });
  }, []);
  const advanceSimulation = useCallback(() => {
    setSimulation(previous => previous.status !== "running" ? previous : previous.phase >= 3
      ? { ...previous, status: "complete", phase: 4 }
      : { ...previous, phase: previous.phase + 1 });
  }, []);
  const cancelSimulation = useCallback(() => {
    setSimulation(previous => previous.status === "running" ? { ...previous, status: "cancelled" } : previous);
  }, []);
  useEffect(() => {
    if (pathname === "/scan") return;
    const timer = setTimeout(cancelSimulation, 0);
    return () => clearTimeout(timer);
  }, [pathname, cancelSimulation]);
  const showSample = useCallback(() => {
    setSimulation({ status: "idle", phase: 0, context: "" });
    setMarked([]); setSearch(""); setPriority("전체"); setStatus("전체");
  }, []);

  return {
    website, setWebsite, submitted: simulation.context, phase: simulation.phase,
    running: simulation.status === "running", ready: simulation.status === "complete",
    startSimulation, advanceSimulation, cancelSimulation, showSample,
    marked, setMarked, search, setSearch, priority, setPriority, status, setStatus,
    facts, setFacts, draft, setDraft,
  };
}

type DemoState = ReturnType<typeof useDemoState>;
const DemoContext = createContext<DemoState | null>(null);
export function DemoProvider({ children }: { children: ReactNode }) {
  const state = useDemoState();
  return <DemoContext.Provider value={state}>{children}</DemoContext.Provider>;
}
export function useDemo() {
  const state = useContext(DemoContext);
  if (!state) throw new Error("DemoProvider is required");
  return state;
}
