ARG AEW_FRONTEND_BASE=aew-web-builder-base:14e051132580
FROM ${AEW_FRONTEND_BASE}
ARG AEW_FRONTEND_LOCK_SHA256
LABEL org.opencontainers.image.title="AEW Node22 dependency maintenance offline builder"
LABEL org.aew.frontend.lock-sha256="${AEW_FRONTEND_LOCK_SHA256}"
# Replace only this derivative's inputs; historical image IDs remain immutable.
RUN rm -rf /opt/spt-frontend/npm-cache /opt/spt-frontend/package
COPY npm-cache/ /opt/spt-frontend/npm-cache/
COPY package/ /opt/spt-frontend/package/
COPY frontend-npm-manifest.json SHA256SUMS /opt/spt-frontend/
RUN test "$(node --version)" = v22.22.2 && test "$(npm --version)" = 10.9.7 \
    && cd /opt/spt-frontend && sha256sum --check --quiet SHA256SUMS \
    && test "$(sha256sum package/package-lock.json | cut -d ' ' -f 1)" = "$AEW_FRONTEND_LOCK_SHA256"
