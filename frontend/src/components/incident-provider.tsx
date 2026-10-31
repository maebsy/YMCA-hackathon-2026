"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { assessIncident, getFilingDocument, getFilingReport } from "@/lib/api";
import { buildFilingRequest, buildIncidentInput, draftBlockers, getAssessmentGaps, initialIncidentForm, qualifyPrivacyDraft } from "@/lib/incident";
import type { AssessResponse, FilingKind, FilingReport, FilingRequest, IncidentForm } from "@/types/incident";

export type IncidentEvidence = { repo: string; fingerprint: string; title: string; finding: unknown };
export type IncidentDocument = { report: FilingReport; markdown: string; edited: boolean; revision: number; body: FilingRequest };
const kinds: FilingKind[] = ["incident_24h", "privacy_72h"];

function useIncidentState() {
  const [form, setForm] = useState<IncidentForm>({ ...initialIncidentForm, incidentTypes: [] });
  const [evidence, setEvidence] = useState<IncidentEvidence[]>([]);
  const [step, setStep] = useState(0);
  const [revision, setRevision] = useState(0);
  const [assessment, setAssessment] = useState<{ result: AssessResponse; revision: number } | null>(null);
  const [documents, setDocuments] = useState<Partial<Record<FilingKind, IncidentDocument>>>({});
  const [busy, setBusy] = useState({ assessment: false, incident_24h: false, privacy_72h: false });
  const [errors, setErrors] = useState({ assessment: "", incident_24h: "", privacy_72h: "" });
  const version = useRef(0);
  const sequence = useRef({ assessment: 0, incident_24h: 0, privacy_72h: 0 });
  const pending = useRef({ assessment: false, incident_24h: false, privacy_72h: false });

  useEffect(() => {
    const tokens = sequence.current;
    return () => { tokens.assessment++; for (const kind of kinds) tokens[kind]++; };
  }, []);

  function changed() {
    version.current++;
    setRevision(version.current);
    sequence.current.assessment++;
    for (const kind of kinds) sequence.current[kind]++;
    pending.current = { assessment: false, incident_24h: false, privacy_72h: false };
    setBusy({ ...pending.current });
    setErrors({ assessment: "", incident_24h: "", privacy_72h: "" });
  }

  function updateForm<K extends keyof IncidentForm>(key: K, value: IncidentForm[K]) {
    changed();
    setForm(previous => ({ ...previous, [key]: value }));
  }

  // One change for several facts (e.g. importing scan records), so drafts go stale once.
  function applyFacts(patch: Partial<IncidentForm>) {
    if (!Object.keys(patch).length) return;
    changed();
    setForm(previous => ({ ...previous, ...patch }));
  }

  function toggleEvidence(item: IncidentEvidence) {
    const exists = evidence.some(value => value.repo === item.repo && value.fingerprint === item.fingerprint);
    if (!exists && evidence.length >= 50) return;
    changed();
    setEvidence(previous => exists
      ? previous.filter(value => value.repo !== item.repo || value.fingerprint !== item.fingerprint)
      : [...previous, item]);
  }

  async function assess(): Promise<boolean> {
    if (pending.current.assessment) return false;
    let input;
    try { input = buildIncidentInput(form); }
    catch (caught) { setErrors(previous => ({ ...previous, assessment: message(caught) })); setStep(0); return false; }
    const token = ++sequence.current.assessment;
    const requestedRevision = version.current;
    pending.current.assessment = true;
    setBusy(previous => ({ ...previous, assessment: true }));
    setErrors(previous => ({ ...previous, assessment: "" }));
    try {
      const result = await assessIncident(input);
      if (token !== sequence.current.assessment) return false;
      setAssessment({ result, revision: requestedRevision });
      setStep(1);
      return true;
    } catch (caught) {
      if (token === sequence.current.assessment) setErrors(previous => ({ ...previous, assessment: message(caught) }));
      return false;
    } finally {
      if (token === sequence.current.assessment) {
        pending.current.assessment = false;
        setBusy(previous => ({ ...previous, assessment: false }));
      }
    }
  }

  async function generate(kind: FilingKind, replaceEdited = false) {
    if (pending.current[kind] || (documents[kind]?.edited && !replaceEdited)) return;
    const blockers = draftBlockers(form)[kind];
    if (blockers.length) {
      setErrors(previous => ({ ...previous, [kind]: `초안을 만들기 전에 확인해 주세요: ${blockers.join(", ")}. 확인하지 못한 내용을 ‘대응 중’·‘최초 신고’·‘통지하지 않음’ 같은 기본값으로 채우지 않습니다.` }));
      return;
    }
    const gaps = getAssessmentGaps(form, kind);
    let body: FilingRequest;
    try { body = buildFilingRequest(form, evidence.map(item => item.finding)); }
    catch (caught) { setErrors(previous => ({ ...previous, [kind]: message(caught) })); return; }
    const token = ++sequence.current[kind];
    const requestedRevision = version.current;
    pending.current[kind] = true;
    setBusy(previous => ({ ...previous, [kind]: true }));
    setErrors(previous => ({ ...previous, [kind]: "" }));
    try {
      const [rawReport, rawMarkdown] = await Promise.all([getFilingReport(body, kind), getFilingDocument(body, kind, "markdown")]);
      if (token !== sequence.current[kind]) return;
      const { report, markdown } = qualifyPrivacyDraft(rawReport, rawMarkdown, gaps);
      setDocuments(previous => ({ ...previous, [kind]: { report, markdown, edited: false, revision: requestedRevision, body } }));
    } catch (caught) {
      if (token === sequence.current[kind]) setErrors(previous => ({ ...previous, [kind]: message(caught) }));
    } finally {
      if (token === sequence.current[kind]) {
        pending.current[kind] = false;
        setBusy(previous => ({ ...previous, [kind]: false }));
      }
    }
  }

  function editDocument(kind: FilingKind, markdown: string) {
    sequence.current[kind]++;
    pending.current[kind] = false;
    setBusy(previous => ({ ...previous, [kind]: false }));
    setDocuments(previous => {
      const document = previous[kind];
      return document ? { ...previous, [kind]: { ...document, markdown, edited: true } } : previous;
    });
  }

  // One action: check filing duties, then draft every document whose required facts are known.
  // Edited drafts are kept; the document card asks before replacing them.
  async function prepare() {
    if (!await assess()) return;
    const blockers = draftBlockers(form);
    await Promise.all(kinds.filter(kind => !blockers[kind].length).map(kind => generate(kind)));
  }

  return { form, updateForm, applyFacts, evidence, toggleEvidence, step, setStep, revision, assessment, documents, busy, errors, assess, generate, prepare, editDocument };
}

function message(caught: unknown) { return caught instanceof Error ? caught.message : "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."; }

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
