# Real Estate Automation & Outreach 🏠

> **Business Value:** Automatically scrapes property agents and owners from real estate portals and executes personalized inquiry messages, replacing hours of manual prospecting with a highly reliable, Dockerized system.

This project is tailored specifically for **Real Estate Agencies**, Investors, or PropTech companies that rely on high-volume property lead generation.

---

## 💼 Core Competencies

1. **Lead Scraper**: Targets Real Estate portals, navigates via pagination, and extracts Agent/Owner Names, contact URLs, and IDs.
2. **Outreach Bot**: Logs into the platform and executes targeted inquiry messages with human-like interaction patterns (±20% timing jitter).

---

## 🛠 Features

*   **Robust DOM Parsing**: Uses Playwright to handle dynamic property listings.
*   **Enterprise Architecture**: Configured via a central `config.json`. Docker-compose ready for VPS deployment.
*   **Audit Trail**: Logs all actions (sent, skipped, failed) to `logs/real_estate_outreach_log.csv` using Loguru.

---

## 🚀 Deployment

```bash
# Setup Env Vars
export RE_USERNAME="your_email@domain.com"
export RE_PASSWORD="secure_pass"

# Run via Docker
docker-compose up -d
```
