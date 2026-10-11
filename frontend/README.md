# Agentic SRE dashboard

Run `npm ci` then `npm run dev` and open http://localhost:5173. The API must run on port 8000;
Vite proxies `/api` and `/ws`. Provision accounts using the instructions in the repository README.

`npm run build` writes `dist`; the backend and combined Docker image serve that build.
The dashboard defaults to its own origin. Set `VITE_API_BASE_URL` at build time for a separate backend,
and allow the frontend origin in the API's `ALLOWED_ORIGINS` environment configuration.

`npm run lint` checks the React code. The application uses real account login, authenticates its
WebSocket in the first message, and reconnects interrupted telemetry streams. It displays synthetic
services and simulated recovery actions; evaluation timings measure the isolated harness.
