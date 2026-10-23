// 돌봄케어 설치(PWA) 서비스 워커.
// 화면과 데이터는 항상 서버에서 받는다. 로그인 정보와 일정·기록이 오래된 캐시로 보이지 않도록
// HTML과 /api 요청은 캐시하지 않고, 공용 스크립트·스타일·아이콘만 보관한다.
const CACHE = 'dolbomcare-shell-v1';
const SHELL = [
  '/pages/menu.js',
  '/pages/theme.css',
  '/assets/brand/icon-192.png',
  '/assets/brand/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return;
  }
  if (!SHELL.includes(url.pathname)) {
    return;
  }
  // 공용 파일은 서버에서 먼저 받고, 연결이 안 되면 보관본을 쓴다
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
