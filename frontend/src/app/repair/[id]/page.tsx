import { notFound } from "next/navigation";
import Workspace from "@/components/workspace";
import { findings } from "@/lib/sample";

export const dynamicParams = false;
export function generateStaticParams() { return findings.map(({ id }) => ({ id })); }
export default async function RepairPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!findings.some(finding => finding.id === id)) notFound();
  return <Workspace view="repair" findingId={id}/>;
}
