"use strict";
// Service worker de Xena : seulement les notifications push (pas de cache hors ligne).

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data?.text() || "" }; }
  // Safari exige une notification visible pour chaque push reçu
  event.waitUntil(self.registration.showNotification(data.title || "Xena", {
    body: data.body || "",
    tag: data.tag || undefined,
    renotify: !!data.tag,
    data: { url: data.url || "/" },
    icon: "/static/icons/xena-192.png",
    badge: "/static/icons/xena-192.png",
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of windows) {
      if (w.url.startsWith(self.location.origin)) {
        await w.focus();
        try { await w.navigate(url); } catch { w.postMessage({ open: url }); }
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});
