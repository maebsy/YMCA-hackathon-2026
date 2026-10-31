// Presentation only: the server report and prepared Markdown remain unchanged.
const documentCSS = `
:root { color-scheme:light; }
@media(prefers-color-scheme:dark) { :root:not([data-theme="light"]) { --fg:#fafafa;--muted:#a1a1aa;--line:#3f3f46;--bg:#111113;--soft:#18181b;--danger:#ff938c;--danger-bg:#412422;--warning:#ffd08a;--warning-bg:#3d301c;--ok:#8de3b8;--ok-bg:#19382a;--info:#a6caff;--info-bg:#20334d;--muted-bg:#27272a;color-scheme:dark; } }
:root[data-theme="dark"] { --fg:#fafafa;--muted:#a1a1aa;--line:#3f3f46;--bg:#111113;--soft:#18181b;--danger:#ff938c;--danger-bg:#412422;--warning:#ffd08a;--warning-bg:#3d301c;--ok:#8de3b8;--ok-bg:#19382a;--info:#a6caff;--info-bg:#20334d;--muted-bg:#27272a;color-scheme:dark; }
html,body { height:auto; min-height:0; overflow:hidden; }
main { min-width:0; padding:20px 8px 24px; }
table { table-layout:fixed; } th,td { overflow-wrap:anywhere; }
@media(max-width:440px) { body { font-size:13px; } main { padding-inline:0; } h1 { font-size:22px; } h2 { font-size:17px; } th,td { padding:7px; } .card { padding:12px; } }
@media print { html,body { overflow:visible; } }
`;

export function reportDocumentHtml(html: string): string {
  const style = `<style data-report-presentation>${documentCSS}</style>`;
  return /<\/head>/i.test(html) ? html.replace(/<\/head>/i, style + "</head>") : style + html;
}

export function mountReportDocument(frame: HTMLIFrameElement): () => void {
  const doc = frame.contentDocument;
  if (!doc) return () => {};
  const main = doc.querySelector("main") ?? doc.body;
  if (!main) return () => {};
  const size = () => { frame.style.height = `${Math.ceil(main.getBoundingClientRect().height) + 2}px`; };
  const theme = () => { doc.documentElement.dataset.theme = document.documentElement.dataset.theme ?? "dark"; size(); };
  theme();
  // Observe content width/height, not iframe/root height, to allow shrinking without a resize loop.
  const resize = new ResizeObserver(size);
  resize.observe(main);
  const themes = new MutationObserver(theme);
  themes.observe(document.documentElement, { attributes:true, attributeFilter:["data-theme"] });
  let disposed = false;
  void doc.fonts?.ready.then(() => { if (!disposed) size(); });
  return () => { disposed = true; resize.disconnect(); themes.disconnect(); };
}
