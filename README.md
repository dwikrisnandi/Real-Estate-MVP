# Real Estate Property & Agent Scraper 🏠

> **Enterprise Value:** A heavy-duty pipeline that continuously monitors real estate portals, extracts agent/owner data, and executes automated inquiry messages for property acquisition or B2B PropTech sales.

Designed for **Real Estate Investment Firms** and PropTech companies dealing with high-volume, continuously updating property listings.

## 🛠 Technical Highlights

*   **Relational Database Persistence (SQLite):** Unlike basic scripts that spit out text files, this pipeline persists data directly into a relational database.
*   **Advanced SQL UPSERTs:** Uses `ON CONFLICT DO UPDATE` constraints to handle duplicate property listings efficiently. If an agent updates their profile, the database updates the record seamlessly without throwing locks or duplicating data.
*   **Indexed Outreach Queues:** The `outreach_logs` and `leads` tables are structurally linked and indexed, ensuring the outreach bot can process thousands of pending leads with O(1) lookup times.
*   **Playwright DOM Parsing:** Capable of navigating complex map-based real estate interfaces and extracting hidden contact nodes.

## 🚀 Deployment

```bash
# Initialize DB and start pipeline via Docker
docker-compose up -d

# Or run locally
python run_scraper.py
```
