export type RepoPrefix = { owner: string; partial: string };

// normalizeRepositoryUrl과 같은 GitHub owner 규칙: 1~39자, 양끝 영숫자, 연속 '-' 금지.
function validOwner(owner: string): boolean {
  return /^[a-z\d](?:[a-z\d-]{0,37}[a-z\d])?$/i.test(owner) && !owner.includes("--");
}

/** Expand only owner/repository shorthand; validate the resulting address at submission. */
export function repositoryInputUrl(value: string): string {
  const trimmed = value.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  const owner = /^([^/]+)\//.exec(trimmed)?.[1];
  return owner && validOwner(owner) ? `https://github.com/${trimmed}` : trimmed;
}

export function parseRepoPrefix(value: string): RepoPrefix | null {
  const github = /^(?:https:\/\/)?github\.com\/([^/]+)\/([a-z\d_.-]*)$/i.exec(value);
  const pages = /^(?:https:\/\/)?([^/.]+)\.github\.io\/([a-z\d_.-]*)$/i.exec(value);
  const short = /^([^/]+)\/([a-z\d_.-]*)$/i.exec(value);
  const match = github ?? pages ?? short;
  return match && validOwner(match[1]) ? { owner: match[1], partial: match[2] } : null;
}

// 임시값: 공개 API의 IP별 시간당 60회 한도를 아끼기 위한 캐시 시간.
const SUCCESS_CACHE_MS = 60_000;
const FAILURE_CACHE_MS = 30_000;
const cache = new Map<string, { expires: number; promise: Promise<string[]> }>();

export function loadPublicRepos(owner: string, fetchImpl: typeof fetch = fetch): Promise<string[]> {
  if (!validOwner(owner)) return Promise.resolve([]);
  const key = owner.toLowerCase();
  const saved = cache.get(key);
  if (saved && saved.expires > Date.now()) return saved.promise;
  const entry = { expires: Infinity, promise: Promise.resolve<string[]>([]) };
  // 요청 중인 Promise도 먼저 공유합니다. fetch가 동기적으로 실패해도 실패 캐시를 남깁니다.
  entry.promise = Promise.resolve().then(async () => {
    try {
      const response = await fetchImpl(`https://api.github.com/users/${key}/repos?per_page=100&sort=updated&type=owner`, {
        headers: { Accept: "application/vnd.github+json" },
        credentials: "omit",
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error("Public repository request failed");
      const body: unknown = await response.json();
      if (!Array.isArray(body) || !body.every(item => item && typeof item === "object" &&
        typeof item.name === "string" && /^[a-z\d_.-]{1,100}$/i.test(item.name) && item.name !== "." && item.name !== "..")) {
        throw new Error("Invalid public repository response");
      }
      entry.expires = Date.now() + SUCCESS_CACHE_MS;
      return body.map(item => item.name as string);
    } catch {
      entry.expires = Date.now() + FAILURE_CACHE_MS;
      return [];
    }
  });
  cache.set(key, entry);
  return entry.promise;
}

export function bestCompletion(partial: string, names: readonly string[]): { name: string; remainder: string } | null {
  if (!partial) return null;
  const name = names.find(name => name.toLowerCase().startsWith(partial.toLowerCase()));
  return name ? { name, remainder: name.slice(partial.length) } : null;
}

export function canCompleteInput(input: {
  inputType: string; isComposing: boolean; value: string;
  selectionStart: number | null; selectionEnd: number | null;
}): boolean {
  return input.inputType === "insertText" && !input.isComposing &&
    input.selectionStart === input.value.length && input.selectionEnd === input.value.length;
}

/** API 갱신 순서를 유지하되 시작 일치를 포함 일치보다 먼저 표시합니다. */
export function matchingRepos(partial: string, names: readonly string[]): string[] {
  const query = partial.toLowerCase();
  return [...names.filter(name => name.toLowerCase().startsWith(query)),
    ...names.filter(name => !name.toLowerCase().startsWith(query) && name.toLowerCase().includes(query))];
}
