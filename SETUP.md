# Investigator Agent UI – Setup Guide

This document describes how to set up and run the Investigator Agent Angular UI, including prerequisites and their versions.

---

## 1. Prerequisites

Install the following on your machine before setting up the project.

| Prerequisite | Minimum Version | Notes |
|-------------|-----------------|--------|
| **Node.js** | 18.19.x, 20.11.x, or 22.x (LTS recommended) | Required for Angular 20. Prefer Node 20 LTS. |
| **npm** | 10.x or later | Usually bundled with Node.js. |
| **Angular CLI** | 20.x | Installed as a project dev dependency; optional global install. |

### Checking versions

```bash
node --version   # e.g. v20.11.0
npm --version   # e.g. 10.2.4
```

### Installing Node.js

- **macOS / Windows:** Download the LTS installer from [nodejs.org](https://nodejs.org/).
- **macOS (Homebrew):** `brew install node@20`
- **Ubuntu/Debian:** Use [NodeSource](https://github.com/nodesource/distributions) or the official Node.js binary distribution for Node 20 LTS.

---

## 2. Project Dependencies (Versions)

The project uses these main dependency versions (from `package.json`):

| Package | Version | Purpose |
|--------|---------|---------|
| Angular (core, common, compiler, etc.) | ^20.3.1 | Framework |
| Angular CLI | ~20.3.2 | Build and serve |
| TypeScript | ~5.9.2 | Language |
| zone.js | ~0.15.0 | Angular change detection |
| jspdf | ^4.2.0 | PDF generation (e.g. approval certificates) |
| Karma / Jasmine | (see package.json) | Unit tests |

---

## 3. Setup Steps

### 3.1 Clone the repository (if not already done)

```bash
git clone <repository-url>
cd investigator_agent_ui
```

### 3.2 Install npm dependencies

```bash
npm install
```

This installs all dependencies listed in `package.json`, including Angular 20 and the Angular CLI.

### 3.3 Configure environment (optional for local dev)

For **local development**, the app uses `src/environments/environment.ts`. Default values:

| Variable | Default | Description |
|----------|---------|-------------|
| `applicationsBaseUrl` | `http://localhost:8001` | Base URL for applications API (list, view, status, inspector-status, etc.). |
| `reviewStreamBaseUrl` | `http://localhost:8001` | Base URL for review stream (e.g. `/review/{id}/stream`, `/review/{id}/results`, `/review/{id}/images`). |
| `reviewStreamAuthToken` | `''` | Optional Bearer token for review-stream endpoints. |
| `apiUrl` | `http://localhost:3000/api` | General API URL if used elsewhere. |

To point to a different backend, edit `src/environments/environment.ts` (and for production, `src/environments/environment.prod.ts`).

### 3.4 Run the development server

```bash
npm start
```

Or, using the Angular CLI directly:

```bash
npx ng serve
```

- App is served at **http://localhost:4200** (or the port shown in the terminal).
- The script in `package.json` uses `--host 0.0.0.0` and `--port 4200` so it’s reachable on the network and from other devices if needed.

### 3.5 Build for production

```bash
npm run build
```

Output is in `dist/investigator-agent/`. Serve that folder with any static file server or your web server (e.g. Nginx, Apache).

For production, configure `src/environments/environment.prod.ts` with the correct `applicationsBaseUrl`, `reviewStreamBaseUrl`, and optional `reviewStreamAuthToken` (if your backend uses them).

---

## 4. Optional: Global Angular CLI

To use the `ng` command globally (e.g. `ng serve`, `ng generate`):

```bash
npm install -g @angular/cli@20
```

Then you can run:

```bash
ng serve
ng build
ng test
```

The project works without a global install by using `npx ng` or the `npm start` / `npm run build` scripts.

---

## 5. Running tests

```bash
npm test
```

Runs unit tests with Karma and Jasmine.

---

## 6. Troubleshooting

| Issue | Suggestion |
|-------|-------------|
| **Node version mismatch** | Use Node 18.19+, 20.11+, or 22.x. Check with `node -v`. |
| **npm install fails** | Delete `node_modules` and `package-lock.json`, then run `npm install` again. |
| **Port 4200 in use** | Run `ng serve --port 4300` (or another port). |
| **API / CORS errors** | Ensure the backend at `applicationsBaseUrl` / `reviewStreamBaseUrl` allows the UI origin (e.g. `http://localhost:4200`) and required headers. |
| **Blank or 404 on refresh** | If using client-side routing in production, configure your server to serve `index.html` for all routes (e.g. try_files in Nginx). |

---

## 7. Summary

- **Prerequisites:** Node.js 18.19+ / 20.11+ / 22.x, npm 10+.
- **Install:** `npm install`
- **Run locally:** `npm start` → open http://localhost:4200
- **Build:** `npm run build` → output in `dist/investigator-agent/`
- **Backend:** Set `applicationsBaseUrl` and `reviewStreamBaseUrl` in `src/environments/environment.ts` (and `environment.prod.ts` for production) to match your API.
