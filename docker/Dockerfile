FROM ubuntu:24.04

# Native x86_64 GCC + cross-compile toolchains for Linux aarch64 and Windows
# (x86_64 via MinGW-w64, arm64 via LLVM-MinGW downloaded below).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc-aarch64-linux-gnu \
    libc6-dev-arm64-cross \
    gcc-mingw-w64-x86-64 \
    ca-certificates \
    curl \
    python3 \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# LLVM-MinGW provides aarch64-w64-mingw32-clang for Windows arm64.
# Pinned release; bump the URL when newer toolchains land.
ARG LLVM_MINGW_RELEASE=20240619
RUN curl -fsSL -o /tmp/llvm-mingw.tar.xz \
      "https://github.com/mstorsjo/llvm-mingw/releases/download/${LLVM_MINGW_RELEASE}/llvm-mingw-${LLVM_MINGW_RELEASE}-ucrt-ubuntu-20.04-x86_64.tar.xz" \
    && mkdir -p /opt/llvm-mingw \
    && tar -xJf /tmp/llvm-mingw.tar.xz -C /opt/llvm-mingw --strip-components=1 \
    && rm /tmp/llvm-mingw.tar.xz
ENV PATH=/opt/llvm-mingw/bin:$PATH

WORKDIR /build/scripts
