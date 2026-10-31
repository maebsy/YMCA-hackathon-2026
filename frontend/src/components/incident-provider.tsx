"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

function useIncidentState() {
  const [facts, setFacts] = useState({ service: "", date: "", observation: "", action: "" });
  const [draft, setDraft] = useState("");
  return { facts, setFacts, draft, setDraft };
}

type IncidentState = ReturnType<typeof useIncidentState>;
const IncidentContext = createContext<IncidentState | null>(null);

export function IncidentProvider({ children }: { children: ReactNode }) {
  const state = useIncidentState();
  return <IncidentContext.Provider value={state}>{children}</IncidentContext.Provider>;
}

export function useIncident() {
  const state = useContext(IncidentContext);
  if (!state) throw new Error("IncidentProvider is required");
  return state;
}
