export type QueuedOperation = { id: string; inspectionId?: string; kind: string; path: string; method: string; body?: unknown; dependsOn?: string[]; createdAt: string; attempts: number; status: "queued" | "syncing" | "failed"; error?: string };
const DB = "vantage-field-v1", OPS = "operations", BLOBS = "blobs";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => { const req = indexedDB.open(DB, 1); req.onupgradeneeded = () => { const db = req.result; if (!db.objectStoreNames.contains(OPS)) db.createObjectStore(OPS, { keyPath: "id" }); if (!db.objectStoreNames.contains(BLOBS)) db.createObjectStore(BLOBS); }; req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error); });
}
async function transact<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> { const db = await open(); return new Promise((resolve, reject) => { const tx = db.transaction(store, mode); const req = fn(tx.objectStore(store)); req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error); tx.oncomplete = () => db.close(); }); }
export const fieldQueue = {
  put: (op: QueuedOperation) => transact(OPS, "readwrite", s => s.put(op)),
  list: () => transact<QueuedOperation[]>(OPS, "readonly", s => s.getAll()),
  remove: (id: string) => transact(OPS, "readwrite", s => s.delete(id)),
  putBlob: (id: string, blob: Blob) => transact(BLOBS, "readwrite", s => s.put(blob, id)),
  getBlob: (id: string) => transact<Blob | undefined>(BLOBS, "readonly", s => s.get(id)),
  removeBlob: (id: string) => transact(BLOBS, "readwrite", s => s.delete(id)),
  async enqueue(input: Omit<QueuedOperation, "createdAt" | "attempts" | "status">) { const op: QueuedOperation = { ...input, createdAt: new Date().toISOString(), attempts: 0, status: "queued" }; await this.put(op); return op; },
};
