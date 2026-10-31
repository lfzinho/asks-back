// Firebase setup shared by every page. On localhost it talks to the local emulators.
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js";
import { getAuth, connectAuthEmulator } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";
import { getFirestore, connectFirestoreEmulator } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";
import { getStorage, connectStorageEmulator, ref, getDownloadURL } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js";

const config = await (await fetch("/__/firebase/init.json")).json();
// Sign in through the site's own domain: Google redirects then stay first-party, which Safari and
// Chrome's storage partitioning require. Firebase Hosting serves /__/auth/handler on every hosted domain.
if (/\.(web\.app|firebaseapp\.com)$/.test(location.hostname)) config.authDomain = location.host;

export const app = initializeApp(config);
export const auth = getAuth(app);
export const db = getFirestore(app);
export const storage = getStorage(app);
export const usingEmulator = ["localhost", "127.0.0.1"].includes(location.hostname);

if (usingEmulator) {
  connectAuthEmulator(auth, "http://127.0.0.1:9098", { disableWarnings: true });
  connectFirestoreEmulator(db, "127.0.0.1", 8085);
  connectStorageEmulator(storage, "127.0.0.1", 9198);
}

const urls = new Map();
/** Download URL for a Storage path (cached). */
export function fileUrl(path) {
  if (!urls.has(path)) {
    const p = getDownloadURL(ref(storage, path));
    p.catch(() => urls.delete(path));
    urls.set(path, p);
  }
  return urls.get(path);
}
