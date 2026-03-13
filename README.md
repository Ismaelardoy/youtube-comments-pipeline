<div align="center">

# 🎬 YouTube Comments Pipeline

**A production-ready, fully containerised data pipeline for extracting, cleaning, and storing YouTube comments at scale.**

Built with Python · Azure Functions · Docker · YouTube Data API v3

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![Azure Functions](https://img.shields.io/badge/Azure-Functions-0078D4?logo=microsoft-azure)](https://azure.microsoft.com/en-us/products/functions)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

This pipeline automatically searches YouTube for videos on specific topics, extracts their comments, cleans the text (removes HTML, URLs, emojis), and saves everything as structured JSON files — locally or in Azure Blob Storage.

It is a versatile engine for building high-fidelity datasets from YouTube, enabling deep analysis of audience engagement, sentiment, and trends across any category — from viral Shorts to long-form videos in any niche.

## ⚡ Quick Guide

1. **Configure**: Copy `.env.example` to `.env` and enter your `YOUTUBE_API_KEY`.
2. **Launch**: `docker compose up --build` (mandatory for the first run).
3. **Control**:
   - Toggle `IS_SHORT=true` or `false` to switch between Shorts or long-form videos.
   - Toggle `UPLOAD_TO_CLOUD=true` or `false` for Azure upload vs local storage.
   - Edit `THEMES_LIST` to use your own search terms.
4. **Clean Restart**: Use `docker compose down && docker compose up` to start a fresh batch.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Smart search** | Finds videos by topic, picking a random date since Jan 2025 to maximise variety |
| 🧹 **Text cleaning** | Strips HTML tags, entities, raw URLs, and emojis from every comment |
| 📄 **Rich metadata** | Each comment includes author, like count, its own date, and the **video's publication date** |
| 📦 **Dual storage** | Save JSON locally or upload to Azure Blob Storage — controlled by one flag |
| 🔄 **Shorts & long-form** | One flag (`is_short`) switches between YouTube Shorts and regular videos |
| 🔁 **Batch mode** | Cycles through 14 research themes without repetition |
| 🛡️ **Retry logic** | Exponential back-off on YouTube API and Azure Storage failures |
| 🐳 **One-command setup** | `docker compose up --build` starts everything |
| ☁️ **Azure-ready** | Deploy to Azure Functions with zero code changes |

---

## 🏗️ Architecture

```
┌───────────────────────────────┐    HTTP GET (JSON payload)    ┌──────────────────────────────────┐
│     batch_launcher.py         │ ────────────────────────────▶ │     function_app.py              │
│                               │                               │     (Azure Function)             │
│  Picks a random theme         │                               │                                  │
│  Loops N times                │                               │  1. Search YouTube for videos    │
│  Retries on network errors    │                               │  2. Fetch video publish dates    │
└───────────────────────────────┘                               │  3. Paginate through comments    │
                                                                │  4. Clean & filter text          │
                                                                │  5. Save JSON → local_data_lake/ │
                                                                └──────────────────────────────────┘
```

Both components run as separate Docker containers. The launcher waits for the Function to pass its health check before sending the first request. Output files appear **directly** in `local_data_lake/` on your machine in real time via a Docker bind-mount.

---

## 📁 Project Structure

```
youtube-comments-pipeline/
│
├── src/                         ← Shared business logic
│   ├── config/settings.py       ← All environment variables in one place
│   ├── models/comment.py        ← CommentRecord data type
│   ├── utils/text_cleaner.py    ← HTML / URL / emoji removal
│   ├── utils/file_naming.py     ← JSON filename generator
│   ├── services/youtube_service.py   ← YouTube API client + retries
│   └── services/storage_service.py  ← Azure Blob + local file output
│
├── function_app.py              ← Azure Function HTTP trigger
├── batch_launcher.py            ← Batch orchestrator
│
├── tests/smoke_tests.py         ← Quick sanity checks
│
├── Dockerfile                   ← Image for the Azure Function
├── Dockerfile.launcher          ← Image for the batch launcher
├── docker-compose.yml           ← Orchestrates both containers
├── requirements.txt             ← Python dependencies
├── host.json                    ← Azure Functions runtime config
│
├── .env.example                 ← ⬅ Copy this to .env and fill in your keys
├── .env                         ← Your secrets (gitignored, never committed)
└── local_data_lake/             ← Output folder — JSON files appear here (gitignored)
```

---

## 🚀 Quick Start (Docker — Recommended)

### What You'll Need

1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — installed and running
2. **A YouTube Data API v3 key** — get one free at [console.cloud.google.com](https://console.cloud.google.com/)
   - Create a project → Enable *YouTube Data API v3* → Credentials → Create API Key
3. *(Optional)* An Azure Storage connection string — only if you want cloud upload

### Steps

**1. Clone the repository**
```bash
git clone https://github.com/Ismaelardoy/youtube-comments-pipeline.git
cd youtube-comments-pipeline
```

**2. Configure your secrets**
```bash
cp .env.example .env
```
Open `.env` and fill in at minimum:
```env
YOUTUBE_API_KEY=AIza...your_key_here...
```

**3. Launch everything**
```bash
docker compose up --build
```

Docker will build both containers, wait for the Function to start, then run the launcher automatically. **JSON files appear in `local_data_lake/`** on your machine in real time.

**4. Stop**
```bash
docker compose down
```

---

## 🛠️ Running Without Docker (Local Dev)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your environment variables
$env:YOUTUBE_API_KEY = "your_key_here"   # PowerShell
export YOUTUBE_API_KEY="your_key_here"   # macOS / Linux

# 4. Terminal 1 — Start the Azure Function locally
func start

# 5. Terminal 2 — Run the batch launcher
python batch_launcher.py
```

> **Tip:** Install [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local) for the `func` command: `npm install -g azure-functions-core-tools@4`

---

## ⚙️ Configuration Reference

All settings are read from **environment variables** — set them in your `.env` file.

| Variable | Required | Default | Description |
|---|---|---|---|
| `YOUTUBE_API_KEY` | ✅ Yes | — | Your YouTube Data API v3 key |
| `AZURE_STORAGE_CONNECTION_STRING` | Only for cloud upload | — | Azure Blob Storage connection string |
| `DATA_LAKE_PATH` | No | `./local_data_lake` | Output directory (inside container: `/data/local_data_lake`) |
| `BLOB_CONTAINER_NAME` | No | `youtube-comments` | Azure Blob container name |
| `GLOBAL_COMMENT_LIMIT` | No | `10000` | Max comments to collect per run |
| `IS_SHORT` | No | `true` | `true` = Only Shorts \| `false` = Long-form videos |
| `UPLOAD_TO_CLOUD` | No | `false` | `true` = Upload to Azure \| `false` = Save local JSON |
| `SEARCH_START_DATE` | No | *2025-01-01* | ISO-8601 start date (e.g. `2025-01-01T00:00:00Z`) |
| `SEARCH_END_DATE` | No | `now` | ISO-8601 end date |
| `TOTAL_REQUESTS` | No | `2` | Number of themed requests per batch |
| `WAIT_TIME_SECONDS` | No | `4` | Seconds to wait between requests |
| `THEMES_LIST` | No | *(14 defaults)* | Comma-separated list of search themes |

## 💡 Usage Tips & Docker Hygiene

### When to use `--build`?
Docker images represent a "snapshot" of the code at a specific time.

- **Use `docker compose up --build`** if you modified:
  - Any Python code file (`.py`)
  - The `requirements.txt` file (new dependencies)
  - Any `Dockerfile`

- **Use `docker compose up`** (without build) if you only modified:
  - The `.env` file (themes, keys, limits, or Shorts/Cloud toggles)

### Fresh Start
To clear old states and start a completely new batch:
```bash
docker compose down && docker compose up
```
This is the safest way to ensure a new run starts with the latest configuration and clean logs.

## 📡 API Reference

```
GET /api/extract_youtube_comments
```

Parameters can be sent as a **query string** or **JSON body**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `theme` | `string` | — | Search topic (e.g. `"science documentary"`) |
| `video_id` | `string` | — | Extract comments from a specific video ID |
| `is_short` | `bool` | `false` | `true` = YouTube Shorts only |
| `upload_to_cloud` | `bool` | `true` | `false` = save locally; `true` = Azure Blob |

> Provide either `theme` **or** `video_id` (not necessarily both).

**Example:**
```bash
curl "http://localhost:7071/api/extract_youtube_comments" \
  -H "Content-Type: application/json" \
  -d '{"theme": "science documentary", "is_short": false, "upload_to_cloud": false}'
```

**Success response:**
```json
{
  "status": "success",
  "comments_extracted": 8432,
  "videos_processed": 47,
  "saved_to": "local file './local_data_lake/megablob_science_documentary_20250313120000.json'",
  "filename": "megablob_science_documentary_20250313120000.json"
}
```

---

## 📄 Output JSON Schema

Each file is a JSON array. Every element is one cleaned comment:

```json
{
  "videoId": "dQw4w9WgXcQ",
  "videoPublishedAt": "2025-01-15T18:00:00Z",
  "theme": "science documentary",
  "is_short": false,
  "author": "@username",
  "text": "This is the clean, sanitized comment text.",
  "likeCount": 42,
  "publishedAt": "2025-03-01T12:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `videoId` | `string` | YouTube video ID |
| `videoPublishedAt` | `string \| null` | When the **video** was published (ISO-8601) |
| `theme` | `string \| null` | Search theme used to find the video |
| `is_short` | `boolean` | Whether the video is a YouTube Short |
| `author` | `string \| null` | Comment author display name |
| `text` | `string` | Cleaned comment text |
| `likeCount` | `integer` | Likes on the comment |
| `publishedAt` | `string \| null` | When the **comment** was posted (ISO-8601) |

---

## 🎯 Theme Catalogue

The launcher shuffles and exhausts all 14 themes before repeating:

```
Superficial / Impulsive          Informational / Analytical       Polarised / Debate
──────────────────────────────   ─────────────────────────────   ──────────────────
celebrity gossip                 science documentary             politics debate
funny pranks                     history explained               conspiracy theory
daily vlog                       video essay
influencer apology               philosophy lecture
gaming drama                     personal finance
viral challenges                 tech gadget review
```

---

## ☁️ Deploying to Azure

**1.** Set `upload_to_cloud` to `true` (via your `.env` or request payload).

**2.** Deploy the Function:
```bash
func azure functionapp publish <your-function-app-name>
```

**3.** Add these Application Settings in the Azure Portal:

| Setting | Value |
|---|---|
| `YOUTUBE_API_KEY` | Your API key |
| `AZURE_STORAGE_CONNECTION_STRING` | Your storage connection string |
| `GLOBAL_COMMENT_LIMIT` | `10000` |

---

## 🧪 Smoke Tests

```bash
# Windows
.venv\Scripts\python.exe tests\smoke_tests.py

# macOS / Linux
python tests/smoke_tests.py
```

Expected output:
```
text_cleaner .............. PASSED
file_naming ............... PASSED
Settings .................. PASSED

All smoke tests PASSED.
```

---

## 📦 Dependencies

| Package | Version | Purpose |
|---|---|---|
| `azure-functions` | latest | Azure Functions runtime |
| `google-api-python-client` | ≥ 2.126 | YouTube Data API v3 |
| `azure-storage-blob` | ≥ 12.19 | Azure Blob Storage client |
| `emoji` | ≥ 2.11 | Emoji removal |
| `tenacity` | ≥ 8.2 | Retry logic with exponential back-off |
| `typing_extensions` | ≥ 4.9 | TypedDict support |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
