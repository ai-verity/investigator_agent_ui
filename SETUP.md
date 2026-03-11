# Investigator Agent UI – Setup Guide

Steps to run this Angular application on a new machine.

---

## 1. Prerequisites

Install on the new machine:

| Requirement | Version / Notes |
|-------------|-----------------|
| **Node.js** | v18.x or v20.x (LTS). Check: `node -v` |
| **npm**     | v9+ (comes with Node). Check: `npm -v` |

- Download Node.js: https://nodejs.org/  
- Or use a version manager: **nvm**, **fnm**, or **volta**.

---

## 2. Get the project on the machine

**Option A – Git**

```bash
git clone <repository-url> investigator_agent_ui
cd investigator_agent_ui
```

**Option B – Copy project folder**

Copy the entire project directory (including `src/`, `angular.json`, `package.json`, etc.) to the new machine and `cd` into it.

---

## 3. Install dependencies

From the project root:

```bash
npm install
```

This installs Angular 20, jsPDF, and other dependencies from `package.json`.  
If you see audit warnings, you can run `npm audit fix` (optional).

---

## 4. Configure environment (API URLs)

The app talks to backend APIs. Set the base URLs (and optional auth) in:

**Development:** `src/environments/environment.ts`

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:3000/api',
  applicationsBaseUrl: 'http://localhost:8001',   // Applications & review APIs
  reviewStreamBaseUrl: 'http://localhost:8001',   // Review stream & images
  reviewStreamAuthToken: '',                      // Optional Bearer token for review APIs
};
```

**Production:** `src/environments/environment.prod.ts`

```typescript
export const environment = {
  production: true,
  apiUrl: '/api',
  applicationsBaseUrl: 'https://your-api-server.com',  // Your production API base URL
  reviewStreamBaseUrl: 'https://your-api-server.com', // Same or different for review
};
```

- Replace `http://localhost:8001` with your backend base URL if it runs elsewhere.  
- If the review/stream endpoints need a Bearer token, set `reviewStreamAuthToken` (or wire your auth service to provide it).

---

## 5. Run the application

**Development server:**

```bash
npm start
```

- App is served at: **http://localhost:4200**  
- Uses `ng serve --host 0.0.0.0 --port 4200` so it’s reachable from other devices on the network.  
- Changes in code trigger a reload.

**Production build (optional):**

```bash
npm run build
```

- Output is in `dist/investigator-agent/`.  
- Serve that folder with any static file server (e.g. Nginx, Apache, or `npx serve dist/investigator-agent`).

---

## 6. Backend / API expectations

The UI assumes these backend services (or proxies) are available:

| Purpose              | Default URL                     | Used for |
|----------------------|----------------------------------|----------|
| Applications API     | `applicationsBaseUrl` (e.g. 8001) | List apps, view application, start app, SOW, uploads, inspector feedback, feedback PATCH |
| Review stream        | `reviewStreamBaseUrl/review/{app_id}/stream` | Step 4 agent stream (New Application) |
| Review results       | `reviewStreamBaseUrl/review/{app_id}/results` | Findings (Step 5, admin AI findings) |
| Review images        | `reviewStreamBaseUrl/review/{app_id}/images`  | Blueprint & photos (View Application, admin) |

- View Application and dashboard (admin/user) need the **applications** and **review** APIs to be running (or proxied) at the configured base URLs.  
- CORS must allow the UI origin (e.g. `http://localhost:4200` in dev).

---

## 7. Quick checklist

- [ ] Node.js v18+ or v20+ and npm installed  
- [ ] Project on machine (clone or copy)  
- [ ] `npm install` completed  
- [ ] `src/environments/environment.ts` updated with correct API base URL(s)  
- [ ] Backend (or mock) running at the configured URL  
- [ ] `npm start` and open http://localhost:4200  

---

## 8. Troubleshooting

| Issue | What to try |
|-------|---------------------|
| `npm install` fails | Use Node v18 or v20; delete `node_modules` and `package-lock.json`, run `npm install` again. |
| Blank page / 404 | Confirm you open `http://localhost:4200` (and that the dev server is running). |
| API errors / CORS | Ensure backend allows the UI origin and that `applicationsBaseUrl` / `reviewStreamBaseUrl` point to the correct host/port. |
| Review stream not loading | If the review API requires auth, set `reviewStreamAuthToken` or ensure your auth service provides a valid Bearer token. |

For production, also set `applicationsBaseUrl` and `reviewStreamBaseUrl` in `environment.prod.ts` and build with `npm run build`.
