# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# One stage per job, so each image carries only its own toolchain:
#
#   docker build --target linux   -t libsmb2-build-linux   ./docker/
#   docker build --target windows -t libsmb2-build-windows ./docker/
#   docker build --target verify  -t libsmb2-build-verify  ./docker/
#
#   linux   : ubuntu:20.04, gcc + the aarch64 cross gcc. glibc 2.31, so the
#             libraries it links load on every distro since Ubuntu 20.04 and
#             Debian 11.
#   windows : ubuntu:24.04 + llvm-mingw (clang, lld, UCRT) for both x86_64 and
#             arm64. Nothing else on PATH provides a mingw compiler.
#   verify  : ubuntu:20.04 + binutils, LLVM tools and gcc: inspects every
#             binary (exports, glibc floor, alignment, imports, Mach-O
#             minimum OS) and dlopens the ones this host can load, on the
#             oldest glibc the Linux libraries promise to support.
#
# Base images are pinned by digest and llvm-mingw by SHA-256, so an image
# built later holds the same toolchain. The orchestrator tags each image with
# a hash of this file and rebuilds it when the file changes. The Android NDK
# is not here: build_libsmb2_android.sh runs on the host (or on the CI
# runner) with the pinned NDK.

# ══════════════════════════════════════════════════════════════════════════════
FROM ubuntu:20.04@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214 AS linux

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc \
      libc6-dev \
      gcc-aarch64-linux-gnu \
      libc6-dev-arm64-cross \
      ca-certificates \
      curl \
      python3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /scripts

# ══════════════════════════════════════════════════════════════════════════════
FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55 AS windows

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      python3 \
      xz-utils \
    && rm -rf /var/lib/apt/lists/*

# llvm-mingw for the host arch (x86_64 runners, or arm64 under Apple Silicon).
ARG LLVM_MINGW_RELEASE=20260922
ARG LLVM_MINGW_SHA256_X86_64=bb7bb7654b33d5aa8712acb837c963b2e0c56352560c76105270a3268c665c21
ARG LLVM_MINGW_SHA256_AARCH64=07d21263c56bfe9a713db6fdb3f7434bf4c121a005e40397d3b4c0170fb06769
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) arch=x86_64;  sum="$LLVM_MINGW_SHA256_X86_64" ;; \
      arm64) arch=aarch64; sum="$LLVM_MINGW_SHA256_AARCH64" ;; \
      *) echo "unsupported host arch" >&2; exit 1 ;; \
    esac; \
    name="llvm-mingw-${LLVM_MINGW_RELEASE}-ucrt-ubuntu-22.04-${arch}"; \
    curl -fsSL --retry 3 -o /tmp/llvm-mingw.tar.xz \
      "https://github.com/mstorsjo/llvm-mingw/releases/download/${LLVM_MINGW_RELEASE}/${name}.tar.xz"; \
    echo "${sum}  /tmp/llvm-mingw.tar.xz" | sha256sum -c -; \
    mkdir -p /opt/llvm-mingw; \
    tar -xJf /tmp/llvm-mingw.tar.xz -C /opt/llvm-mingw --strip-components=1; \
    rm /tmp/llvm-mingw.tar.xz
ENV PATH=/opt/llvm-mingw/bin:$PATH
WORKDIR /scripts

# ══════════════════════════════════════════════════════════════════════════════
FROM ubuntu:20.04@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214 AS verify

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      binutils \
      binutils-aarch64-linux-gnu \
      gcc \
      libc6-dev \
      llvm-10 \
      python3 \
      unzip \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/usr/lib/llvm-10/bin:$PATH
WORKDIR /scripts
