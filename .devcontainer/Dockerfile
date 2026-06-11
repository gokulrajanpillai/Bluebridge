FROM python:3.12-slim-bookworm

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        lsb-release \
        git \
        unzip \
        xz-utils \
        zip \
        # Flet web-mode runtime
        libglib2.0-0 \
        libgl1 \
        # Flutter Linux desktop build deps (used by flet build linux)
        clang \
        cmake \
        ninja-build \
        pkg-config \
        libgtk-3-dev \
        libblkid-dev \
        liblzma-dev \
        libstdc++-12-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Azure CLI ─────────────────────────────────────────────────────────────────
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && az --version

# ── Non-root user (matches VS Code devcontainer convention) ───────────────────
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} \
    && mkdir -p /home/${USERNAME}/.azure \
    && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

USER ${USERNAME}
WORKDIR /workspace

# ── Python tooling ────────────────────────────────────────────────────────────
# flet 0.80+ downloads and manages its own Flutter at first `flet build` run.
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"
RUN pip install --user --upgrade pip
