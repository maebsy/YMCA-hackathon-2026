import Link from "next/link";
export default function NotFound() { return <main id="main" className="container empty-state" tabIndex={-1}><p className="eyebrow">404 · PAGE NOT FOUND</p><h1>이 페이지는 찾을 수 없어요.</h1><p>주소를 확인하거나 URL 입력부터 다시 시작해 보세요.</p><Link className="button primary" href="/">URL 입력으로 돌아가기</Link></main>; }
