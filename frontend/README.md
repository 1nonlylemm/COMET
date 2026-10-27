# COMET frontend

React 19 application built with Vite. See the [root README](../README.md) for
backend, environment and Docker setup.

Use Node.js 22 and install the locked dependencies with `npm ci`.

- `npm run dev`: start development server.
- `npm run lint`: run ESLint.
- `npm run test`: run Vitest once.
- `npm run build`: produce the production bundle in `dist/`.
- `npm run preview`: preview the built bundle locally.

`VITE_API_URL` selects the API base URL; the production Docker build uses `/api`.
Never place secrets in frontend environment variables or source files.
