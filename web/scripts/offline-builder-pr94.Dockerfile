ARG AEW_PR94_BASE=aew-pr94-base:ef83c04ea3f4
FROM ${AEW_PR94_BASE}
LABEL org.opencontainers.image.title="AEW PR94 corrected Node22 offline builder"
LABEL org.opencontainers.image.revision="7fed3028b9152e0345130824479d7eddb05d52ea"
# Replace this derivative's cache only; the historical image remains immutable.
RUN rm -rf /opt/spt-frontend/npm-cache /opt/spt-frontend/package
COPY npm-cache/ /opt/spt-frontend/npm-cache/
COPY package/ /opt/spt-frontend/package/
COPY frontend-npm-manifest.json SHA256SUMS /opt/spt-frontend/
RUN cd /opt/spt-frontend && sha256sum --check --quiet SHA256SUMS && node --version && npm --version
