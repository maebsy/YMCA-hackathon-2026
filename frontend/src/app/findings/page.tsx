"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useRepository } from "@/components/repository-provider";
import { REPOSITORY_RESULT_PATH } from "@/lib/repository-routes";

export default function Page() {
  const { restored, result } = useRepository();
  const router = useRouter();
  useEffect(() => {
    if (restored) router.replace(result ? REPOSITORY_RESULT_PATH : "/");
  }, [restored, result, router]);
  return <main id="main" className="workspace container" tabIndex={-1}><p role="status">검사 기록을 확인하고 있습니다.</p></main>;
}
