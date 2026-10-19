Phase 2 backend notes

Overview
- JWT-based authentication using `/api/token` (OAuth2 password flow).
- New RBAC roles: `student`, `support`, `financial`, `admin`.
- Dashboard endpoints under `/api/v1/dashboard` (protected by JWT):
  - `/financeiro` (ADMIN, FINANCIAL)
  - `/alunos` (ADMIN, SUPPORT)
  - `/cursos` (ADMIN, SUPPORT)
  - `/audit` (ADMIN only)

Quickstart (development)
1. Install dependencies:
```powershell
python -m pip install -r requirements.txt
```
2. Set environment variables (optional admin bootstrap):
```powershell
setx ADMIN_EMAIL "admin@example.com"
setx ADMIN_PASSWORD "YourSecurePassword"
```
3. Run the backend from the `backend/` folder:
```powershell
python app.py
```
4. Obtain token (example using `curl`):
```powershell
curl -X POST -F "username=admin@example.com" -F "password=YourSecurePassword" http://localhost:8000/api/token
```

Notes
- The database is SQLite located at `backend/db.sqlite`.
- Audit logs are written to `audit_logs` table automatically for admin course changes.
