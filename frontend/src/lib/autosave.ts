// MCP용 결과 파일 자동 저장 (크롬·엣지의 File System Access API).
// 웹페이지는 사용자 PC 경로에 마음대로 쓸 수 없어서, 처음 한 번 사용자가 저장할 파일을 고르면 그 파일 핸들을
// 브라우저 내부 DB(IndexedDB)에 저장소별로 기억해 두고, 검사가 끝날 때마다 같은 파일을 덮어씁니다.
// 브라우저를 다시 열면 권한을 한 번 다시 확인해야 할 수 있습니다(사용자 클릭 필요).

/* eslint-disable @typescript-eslint/no-explicit-any */

export type AutoSaveState = "unsupported" | "off" | "on" | "needs-permission";

const DB = "72hours";
const STORE = "mcp-autosave";

export function autoSaveSupported(): boolean {
  return typeof window !== "undefined" && typeof (window as any).showSaveFilePicker === "function";
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function withStore<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const req = run(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

async function loadHandle(repository: string): Promise<any | null> {
  try {
    return (await withStore("readonly", (s) => s.get(repository))) ?? null;
  } catch {
    return null; // 비공개 창 등 DB를 못 쓰면 자동 저장 꺼짐으로 봅니다
  }
}

async function permission(handle: any, ask: boolean): Promise<boolean> {
  const opts = { mode: "readwrite" };
  if ((await handle.queryPermission?.(opts)) === "granted") return true;
  // requestPermission 은 사용자 클릭 안에서만 동작합니다
  return ask ? (await handle.requestPermission?.(opts)) === "granted" : false;
}

/** 이 저장소의 자동 저장 상태 (클릭 없이 확인) */
export async function autoSaveState(repository: string): Promise<AutoSaveState> {
  if (!autoSaveSupported()) return "unsupported";
  const handle = await loadHandle(repository);
  if (!handle) return "off";
  return (await permission(handle, false)) ? "on" : "needs-permission";
}

async function write(handle: any, text: string): Promise<void> {
  // createWritable 은 임시 파일에 쓴 뒤 close 때 바꿔치기해서, MCP가 쓰는 도중의 파일을 읽지 않습니다
  const writable = await handle.createWritable();
  await writable.write(text);
  await writable.close();
}

/** 버튼 클릭: 저장할 파일을 고르고 기억한 뒤 바로 한 번 저장 */
export async function enableAutoSave(repository: string, fileName: string, text: string): Promise<boolean> {
  let handle: any;
  try {
    handle = await (window as any).showSaveFilePicker({
      suggestedName: fileName,
      types: [{ description: "72hours MCP 결과", accept: { "application/json": [".json"] } }],
    });
  } catch {
    return false; // 사용자가 취소
  }
  await withStore("readwrite", (s) => s.put(handle, repository));
  await write(handle, text);
  return true;
}

/** 버튼 클릭: 브라우저를 다시 연 뒤 권한을 다시 허용하고 저장 */
export async function resumeAutoSave(repository: string, text: string): Promise<boolean> {
  const handle = await loadHandle(repository);
  if (!handle || !(await permission(handle, true))) return false;
  await write(handle, text);
  return true;
}

/** 검사 결과가 바뀌었을 때 자동 호출. 권한이 없으면 쓰지 않고 상태만 돌려줍니다 */
export async function autoSave(repository: string, text: string): Promise<AutoSaveState> {
  if (!autoSaveSupported()) return "unsupported";
  const handle = await loadHandle(repository);
  if (!handle) return "off";
  if (!(await permission(handle, false))) return "needs-permission";
  await write(handle, text);
  return "on";
}

export async function disableAutoSave(repository: string): Promise<void> {
  try {
    await withStore("readwrite", (s) => s.delete(repository));
  } catch {
    /* 지울 것이 없으면 그대로 */
  }
}
