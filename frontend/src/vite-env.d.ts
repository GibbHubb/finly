/// <reference types="vite/client" />

// Vite's ambient types. Without this file `import.meta.env` is not declared and
// tsc fails with TS2339 on every VITE_* read (useTransactionSocket.ts), which
// broke `npm run build` since build is `tsc && vite build`.
