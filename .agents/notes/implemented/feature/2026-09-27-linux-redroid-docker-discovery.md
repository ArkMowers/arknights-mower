---
title: Linux Redroid Local Docker Discovery & Binding
status: implemented
category: feature
date: 2026-09-27
---

# Linux Redroid Local Docker Discovery & Binding

[English](2026-09-27-linux-redroid-docker-discovery.md) | [中文](2026-09-27-linux-redroid-docker-discovery.zh.md)

## 1. Context & Motivation
Redroid (Remote Android in Docker) provides containerized Android on Linux hosts. `linux.redroid` integrates restricted read-only discovery against local Docker sockets without requiring elevated daemon permissions.

---

## 2. Invariants & Guarantees

- **[INV-01] Local Socket Only**: Connects strictly to `unix:///var/run/docker.sock`; rejects Podman, Kubernetes/Swarm orchestrated pods, and remote TCP sockets.
- **[INV-02] Environment Isolation**: Strips `DOCKER_HOST`, `DOCKER_CONTEXT`, and `DOCKER_TLS` environment variables to enforce local context.
- **[INV-03] Strict Image Whitelist**: Accepts only images from `redroid/redroid` repositories (with tags or digests).
- **[INV-04] Loopback Port Binding**: Target host port mapped from `5555/tcp` must bind to loopback (`127.0.0.1` or `::1`); rejects unexposed or non-loopback bindings.
- **[INV-05] Controlled Start**: Stopped containers require explicit user authorization before issuing `docker start`; automatic image pulls or port mutations are prohibited.

---

## 3. Technical Contract & Inspect Observations

| Property | Purpose |
| :--- | :--- |
| `Id`, `Name` | Immutable 64-hex container ID and display name |
| `Config.Image` | Whitelist validation (`redroid/redroid`) |
| `Config.Labels` | Rejection of `io.kubernetes.` and `com.docker.swarm.` containers |
| `State.Status` | Classification (`running`, `stopped`, `restarting`) |
| `NetworkSettings.Ports["5555/tcp"]` | Resolution of published `HostPort` |

---

## 4. Verification

- Unit tests: `device_redroid_tests.py`, `device_redroid_io_tests.py`, `device_redroid_route_tests.py`.
- Tested branches: Multi-container filtering, dynamic port changes, paused container rejection, malformed JSON handling.
