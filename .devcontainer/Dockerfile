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
        # Flutter Linux desktop build deps
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

# ── Flutter SDK ───────────────────────────────────────────────────────────────
# Installed as root into /opt so all users can run it.
ARG FLUTTER_VERSION=3.27.4
RUN curl -fsSL \
      "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
      -o /tmp/flutter.tar.xz \
    && tar -xf /tmp/flutter.tar.xz -C /opt \
    && rm /tmp/flutter.tar.xz \
    && /opt/flutter/bin/flutter --version \
    && /opt/flutter/bin/flutter precache --no-android --no-ios --no-web --linux

ENV PATH="/opt/flutter/bin:${PATH}"

# ── Non-root user (matches VS Code devcontainer convention) ───────────────────
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} \
    && mkdir -p /home/${USERNAME}/.azure \
    && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

# Allow vscode user to run flutter (pub cache lives in $HOME)
RUN /opt/flutter/bin/flutter config --no-analytics

USER ${USERNAME}
WORKDIR /workspace

# ── Python tooling ────────────────────────────────────────────────────────────
ENV PATH="/home/${USERNAME}/.local/bin:/opt/flutter/bin:${PATH}"
RUN pip install --user --upgrade pip
