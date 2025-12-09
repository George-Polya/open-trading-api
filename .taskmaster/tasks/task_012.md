# Task ID: 12

**Title:** Deployment Automation and CI/CD Pipeline Setup

**Status:** pending

**Dependencies:** 9 ✓, 10 ✓, 11 ✓

**Priority:** medium

**Description:** Establish a robust deployment pipeline using Docker for containerization, Docker Compose for orchestration, and GitHub Actions for automated testing and delivery.

**Details:**

Implementation steps:

1. **Backend Containerization (FastAPI)**:
   - Create a `Dockerfile.backend` using a multi-stage build approach (`python:3.11-slim`).
   - **Builder Stage**: Install build dependencies and compile Python packages.
   - **Runtime Stage**: minimal image; copy installed packages.
   - **Critical**: Since Task #9 uses Docker-out-of-Docker (DooD), install the Docker CLI in the runtime image and ensure the entrypoint creates the `docker` group with the host's GID if necessary.

2. **Frontend Containerization (React)**:
   - Create `Dockerfile.frontend`.
   - **Build Stage**: Node.js base, run `npm run build`.
   - **Serve Stage**: Nginx base (alpine), copy build artifacts to `/usr/share/nginx/html`, and include a custom `nginx.conf` for SPA routing (fallback to index.html).

3. **Production Orchestration**:
   - Create `docker-compose.prod.yml` defining services: `backend`, `frontend` (Nginx), and `redis`.
   - Map the host's `/var/run/docker.sock` to the backend container to support the execution sandbox (Task #9).
   - Configure environment variables via `.env` file loading for secure secret management.

4. **GitHub Actions CI (`.github/workflows/ci.yml`)**:
   - Trigger on Pull Requests and Pushes to `main`.
   - **Backend Job**: Setup Python, install dependencies, run `ruff` (lint), `mypy` (types), and `pytest` with coverage.
   - **Frontend Job**: Setup Node, install deps, run `npm run lint` and `npm run test`.

5. **GitHub Actions CD (`.github/workflows/cd.yml`)**:
   - Trigger on tags or push to `main` (after CI pass).
   - Login to GitHub Container Registry (GHCR).
   - Build and push tagged Docker images (e.g., `ghcr.io/org/project-backend:v1.0.0`).
   - Generate release notes automatically based on commit messages.

6. **Health Checks**:
   - Implement a `/health` endpoint in FastAPI that verifies Redis connectivity and Docker socket access.
   - Configure `HEALTHCHECK` instructions in Dockerfiles.

**Test Strategy:**

1. **Local Pipeline Verification**: Run `act` (locally) or push a test PR to verify the GitHub Actions workflow executes `ruff`, `mypy`, and `pytest` correctly and fails on errors.
2. **Container Build Test**: Execute `docker build` for both backend and frontend locally to ensure multi-stage builds succeed and image sizes are optimized.
3. **Orchestration Test**: Run `docker-compose -f docker-compose.prod.yml up` locally. Verify:
   - Frontend loads in browser.
   - Backend API responds.
   - **Crucial**: Backend can successfully spawn a sibling container (validating the socket mount from Task #9).
4. **Deployment Dry-Run**: detailed verification of the CD workflow by pushing a test tag and confirming the image appears in the container registry.
