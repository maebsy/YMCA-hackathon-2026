"use client";

import Link from "next/link";
import { useRepository } from "@/components/repository-provider";
import { REPOSITORY_RESULT_PATH } from "@/lib/repository-routes";

export default function VerifyReturnLink() {
  const { result } = useRepository();
  return <Link className="vp-back" href={result ? REPOSITORY_RESULT_PATH : "/"}>
    {result ? "← 결과로 돌아가기" : "← 저장소 입력으로"}
  </Link>;
}
