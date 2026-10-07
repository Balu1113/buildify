# Buildify Student Project Manager

## Render deployment

Deploy this directory as a Render Blueprint. The included `render.yaml` creates
one Docker web service and a Postgres database; the web service serves both the
React dashboard and Django API from the same URL.

Before the first deploy, provide at least one AI provider credential in Render:
`GEMINI_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`. Render generates
`DJANGO_SECRET_KEY` and injects `DATABASE_URL` automatically.

Generated projects run as child processes inside the Buildify web service. The
dashboard preview routes frontend assets and `/api/*` calls through the project
preview endpoint, allowing generated frontend and backend applications to run
together behind the single public Render URL. These processes and their
installed dependencies are ephemeral: users can rerun a project after a
service restart, while generated source files remain in Postgres.
