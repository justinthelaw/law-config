ARG TOOLCHAIN
FROM ${TOOLCHAIN} AS toolchain
FROM buildpack-deps@sha256:0ac99c7dcee4d051ea036dd4dc6db33cef4c5d2088c0bed4001d81e3d6cf53bd
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends qemu-system-x86=1:7.2+dfsg-7+deb12u18+b3 linux-image-amd64=6.1.190-1 busybox-static cpio kmod
COPY --from=toolchain / /guest/
RUN mkdir -p /guest/work /guest/setup /guest/deps /guest/opt/codex/codex-resources && cp /bin/busybox /guest/opt/codex/busybox
COPY init /worker-init
COPY mkinit /worker-mkinit
RUN sh /worker-mkinit
