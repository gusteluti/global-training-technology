Angular SPA (Fase 2)

Quickstart
1. From `frontend/` run:
```powershell
npm install
npx ng serve --open
```

2. The app expects the backend to be available at the same origin (use a proxy or run backend on `http://localhost:8000`).

Notes
- Login form posts to `/api/token` and stores the JWT in `localStorage`.
- Admin dashboard consumes `/api/v1/dashboard/*` endpoints and requires a valid token with appropriate role.
