<p align="center">
  <img src="docs/images/logo.png" alt="Project Field Mouse" width="325">
</p>

<h1 align="center">Project Field Mouse</h1>

<p align="center">
  <strong>Nature Connected.</strong>
</p>

<p align="center">
An open-source wildlife monitoring platform for Raspberry Pi that combines automated acoustic recording, BirdNET-powered species identification, intelligent verification, and a modern web dashboard to deliver reliable long-term biodiversity observations.
</p>

<p align="center">
  <a href="#overview"><strong>Overview</strong></a> •
  <a href="#features"><strong>Features</strong></a> •
  <a href="#architecture"><strong>Architecture</strong></a> •
  <a href="#getting-started"><strong>Getting Started</strong></a> •
  <a href="#roadmap"><strong>Roadmap</strong></a> •
  <a href="#contributing"><strong>Contributing</strong></a>
</p>

---

![Project Field Mouse Dashboard](docs/images/dashboard-home.png)

---

# Overview

Project Field Mouse is an open-source wildlife monitoring platform designed for reliable, unattended deployment on inexpensive Raspberry Pi hardware.

The platform continuously records environmental audio, analyzes recordings using BirdNET, applies multiple verification layers to improve detection quality, stores observations locally, and presents results through a responsive web dashboard.

While the initial release focuses on bird monitoring, the architecture is designed to expand to additional taxa including frogs, mammals, and insects without significant architectural changes.

Project goals include:

- Reliable long-term field deployment
- Low-cost hardware requirements
- High-quality species observations
- Modern web-based visualization
- Extensible open-source architecture

---

# Features

## Wildlife Monitoring

- Automated scheduled audio recording
- BirdNET species identification
- Multi-stage detection verification
- Species activity history
- Life List generation
- Audio playback for detections

## Dashboard

- Responsive web interface
- Activity timeline
- Species detail pages
- Device status monitoring
- Mobile-friendly design
- Search and filtering

## Platform

- Raspberry Pi optimized
- SQLite storage
- Flask web application
- Systemd service management
- Automatic storage retention
- Health monitoring
- Configuration management

---

# Architecture

```
USB Microphone
      │
      ▼
Audio Recorder
      │
      ▼
BirdNET Analysis
      │
      ▼
Verification Pipeline
      │
      ▼
SQLite Database
      │
      ▼
Flask Dashboard
```

---

# Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python |
| Web Framework | Flask |
| Database | SQLite |
| AI | BirdNET |
| Hardware | Raspberry Pi 5 |
| Services | systemd |
| Operating System | Raspberry Pi OS / Linux |

---

# Project Structure

```
project-field-mouse/
├── app/
├── docs/
├── scripts/
├── services/
├── tests/
└── config/
```

---

# Getting Started

```bash
git clone https://github.com/amcowden97/project-field-mouse.git
cd project-field-mouse
```

See the documentation for installation, hardware setup, configuration, and deployment instructions.

The current release candidate is `1.0.0-rc1`. Before deploying it, review the
[release notes](RELEASE_NOTES.md), follow the
[installation guide](docs/INSTALLATION.md), and complete the
[release checklist](docs/RELEASE_CHECKLIST.md). Operational guidance is in the
[operations guide](docs/OPERATIONS.md).

---

# Roadmap

### RC1

- Bird monitoring
- Automated recording
- BirdNET integration
- Verification pipeline
- Modern dashboard
- Species pages
- Life List
- Device monitoring

### Future

- Frog monitoring
- Mammal monitoring
- Multiple stations
- Cloud synchronization
- Mobile application
- Community deployments

---

# Documentation

Documentation includes:

- Installation Guide
- Quick Start
- Hardware Setup
- Raspberry Pi Configuration
- Architecture Overview
- API Documentation
- Troubleshooting
- FAQ
- Contributor Guide
- [Repository Maintenance Policy](docs/REPOSITORY_MAINTENANCE_POLICY.md)

---

# Contributing

Contributions of all sizes are welcome.

Please review **CONTRIBUTING.md** before opening an issue or pull request.

---

# License

Distributed under the [Apache License 2.0](LICENSE).

---

<p align="center">

**Project Field Mouse**

Nature Connected.

Open-source wildlife monitoring built for the Raspberry Pi.

</p>
