// atomic-write.js
// Lock file + atomic write helpers pour status.json.
// Ecriture concurrente safe entre la console (clic UI) et /sdd-full (gates pipeline).
//
// CROSS-LANGUAGE SYMMETRY (load-bearing) : ce module partage le meme
// protocole de lock que .claude/python/sdd_scripts/gate_decide.py :
//   - meme chemin lock : {dirname(filePath)}/.status.lock
//   - meme TTL stale  : 10_000 ms (10000 cote Python)
//   - meme nombre de retries : 5
//   - meme strategie atomique : O_EXCL create
// Toute evolution doit etre repliquee des 2 cotes. Verifie par
// framework_smoke.py check `console-lock-symmetry`.

import { open, writeFile, rename, unlink, readFile, stat } from "node:fs/promises";
import { existsSync, constants as FS_CONSTANTS } from "node:fs";
import { dirname } from "node:path";

const LOCK_TTL_MS = 10_000;       // > 10s = lock stale, on ecrase
const LOCK_RETRIES = 5;
const LOCK_BACKOFF_MS = 50;

async function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

/**
 * Tente d acquerir un lock file via O_EXCL (atomic creation).
 * Throws apres LOCK_RETRIES tentatives.
 */
async function acquireLock(lockPath, ownerId) {
  for (let attempt = 0; attempt < LOCK_RETRIES; attempt++) {
    try {
      const handle = await open(lockPath, FS_CONSTANTS.O_WRONLY | FS_CONSTANTS.O_CREAT | FS_CONSTANTS.O_EXCL);
      await handle.writeFile(`${ownerId}:${Date.now()}`);
      await handle.close();
      return true;
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      // Lock existe deja : check si stale
      try {
        const content = await readFile(lockPath, "utf8");
        const ts = parseInt(content.split(":").pop(), 10);
        if (Number.isFinite(ts) && Date.now() - ts > LOCK_TTL_MS) {
          // Stale → on ecrase
          await unlink(lockPath).catch(() => {});
          continue;
        }
      } catch { /* ignore read errors */ }
      await sleep(LOCK_BACKOFF_MS * (attempt + 1));
    }
  }
  const err = new Error(`[LOCK_HELD] impossible d acquerir ${lockPath} apres ${LOCK_RETRIES} tentatives`);
  err.code = "LOCK_HELD";
  throw err;
}

async function releaseLock(lockPath) {
  await unlink(lockPath).catch(() => { /* deja libere */ });
}

/**
 * Atomic write : tmp + rename. Garantit que le fichier n est jamais lu en etat tronque.
 * Sur Windows NTFS, fs.rename ecrase le fichier cible (Node >= 16).
 */
export async function atomicWriteJson(filePath, obj) {
  const tmp = `${filePath}.tmp.${process.pid}`;
  const json = JSON.stringify(obj, null, 2);
  await writeFile(tmp, json, "utf8");
  await rename(tmp, filePath);
}

/**
 * Read-modify-write atomique avec lock file partage.
 * @param {string} filePath  chemin du JSON cible
 * @param {Function} mutator  (current) => updated  (sync ou async)
 * @param {string} ownerId  identifiant de l ecrivain pour le lock
 */
export async function withLockedWrite(filePath, mutator, ownerId) {
  const lockPath = `${dirname(filePath)}/.status.lock`;
  await acquireLock(lockPath, ownerId);
  try {
    const current = existsSync(filePath)
      ? JSON.parse(await readFile(filePath, "utf8"))
      : { version: 1, FEATs: {}, gates: {} };
    const updated = await mutator(current);
    updated.updatedAt = new Date().toISOString();
    await atomicWriteJson(filePath, updated);
    return updated;
  } finally {
    await releaseLock(lockPath);
  }
}
