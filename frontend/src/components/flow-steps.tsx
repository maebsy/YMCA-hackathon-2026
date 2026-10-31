import { Check } from "lucide-react";

export default function FlowSteps({ step }: { step: 1 | 2 | 3 | 4 }) {
  return <nav className="flow-steps" aria-label="점검 체험 순서"><ol>
    {["URL 입력", "점검 체험", "결과 확인", "수정 안내"].map((label, index) => <li key={label} className={index + 1 === step ? "current" : index + 1 < step ? "complete" : ""} aria-current={index + 1 === step ? "step" : undefined}>
      <span>{index + 1 < step ? <Check size={12}/> : index + 1}</span><span>{label}</span>
    </li>)}
  </ol></nav>;
}
