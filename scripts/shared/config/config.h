/*
 * Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
 * All rights reserved.
 * Use of this source code is governed by BSD 3-Clause license that can be
 * found in the LICENSE file.
 *
 * Static libsmb2 config header — installed as include/config.h by
 * prepare_libsmb2_sources() in place of upstream's CMake ConfigureChecks.
 * One header, per-platform #ifdef sections; every toolchain we target is
 * known, so nothing needs to be probed at configure time.
 *
 * The HAVE_ARC4RANDOM_BUF / HAVE_GETRANDOM / HAVE_DEV_URANDOM defines feed
 * smb2_random_bytes() (lib/init.c) — the CSPRNG used for the client
 * challenge, preauth salt and CCM nonce. Every platform must hit a real
 * entropy source; the weak random() fallback is a last resort only.
 */
#ifndef _LIBSMB2_CONFIG_H_
#define _LIBSMB2_CONFIG_H_
/* #undef HAVE_LIBKRB5 */
/* #undef HAVE_GSSAPI_GSSAPI_H */
/* #undef HAVE_DCERPC_FULL */          /* full DCE/RPC stays in libdcerpc */
#define PACKAGE "libsmb2"
#define PACKAGE_VERSION "6.1.0"
#define VERSION "6.1.0"
#if defined(__APPLE__)
#define HAVE_ARPA_INET_H 1
#define HAVE_ARC4RANDOM_BUF 1
#define HAVE_DLFCN_H 1
#define HAVE_FCNTL_H 1
#define HAVE_INTTYPES_H 1
#define HAVE_NETDB_H 1
#define HAVE_NETINET_IN_H 1
#define HAVE_NETINET_TCP_H 1
#define HAVE_POLL_H 1
#define HAVE_SOCKADDR_LEN 1
#define HAVE_SOCKADDR_STORAGE 1
#define HAVE_LINGER 1
#define HAVE_STDINT_H 1
#define HAVE_STDIO_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_STRINGS_H 1
#define HAVE_SYS_IOCTL_H 1
#define HAVE_SYS_POLL_H 1
#define HAVE_SYS_SOCKET_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_SYS_UIO_H 1
#define HAVE_SYS_TIME_H 1
#define HAVE_SYS_UNISTD_H 1
#define HAVE_SYS_ERRNO_H 1
#define HAVE_TIME_H 1
#define HAVE_UNISTD_H 1
#define HAVE_ERRNO_H 1
#define STDC_HEADERS 1
#elif defined(__ANDROID__)
#define HAVE_ARPA_INET_H 1
/* bionic has arc4random_buf since API 21 — safely below our minSdk. */
#define HAVE_ARC4RANDOM_BUF 1
#define HAVE_FCNTL_H 1
#define HAVE_INTTYPES_H 1
#define HAVE_NETDB_H 1
#define HAVE_NETINET_IN_H 1
#define HAVE_NETINET_TCP_H 1
#define HAVE_POLL_H 1
#define HAVE_SOCKADDR_STORAGE 1
#define HAVE_LINGER 1
#define HAVE_STDINT_H 1
#define HAVE_STDIO_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_STRINGS_H 1
#define HAVE_SYS_IOCTL_H 1
#define HAVE_SYS_SOCKET_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_SYS_UIO_H 1
#define HAVE_TIME_H 1
#define HAVE_UNISTD_H 1
#define HAVE_ERRNO_H 1
#define STDC_HEADERS 1
#elif defined(_WIN32)
#define HAVE_STDINT_H 1
#define HAVE_STDIO_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_FCNTL_H 1
#define HAVE_TIME_H 1
#define HAVE_ERRNO_H 1
#define HAVE_INTTYPES_H 1
#define STDC_HEADERS 1
#else /* Linux (glibc — both docker cross toolchains) */
#define HAVE_ARPA_INET_H 1
#define HAVE_DLFCN_H 1
#define HAVE_FCNTL_H 1
/* glibc >= 2.25 in both docker cross toolchains. */
#define HAVE_GETRANDOM 1
#define HAVE_SYS_RANDOM_H 1
#define HAVE_DEV_URANDOM 1
#define HAVE_INTTYPES_H 1
#define HAVE_NETDB_H 1
#define HAVE_NETINET_IN_H 1
#define HAVE_NETINET_TCP_H 1
#define HAVE_POLL_H 1
#define HAVE_SOCKADDR_STORAGE 1
#define HAVE_LINGER 1
#define HAVE_STDINT_H 1
#define HAVE_STDIO_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_STRINGS_H 1
#define HAVE_SYS_IOCTL_H 1
#define HAVE_SYS_POLL_H 1
#define HAVE_SYS_SOCKET_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_SYS_UIO_H 1
#define HAVE_SYS_TIME_H 1
#define HAVE_TIME_H 1
#define HAVE_UNISTD_H 1
#define HAVE_ERRNO_H 1
#define STDC_HEADERS 1
#endif
#ifndef _U_
#define _U_
#endif
#endif
