# YouTube Comments Pipeline 🎬

> A fully reproducible, plug-and-play data pipeline for extracting and sanitizing YouTube comments at scale — built with Python, Azure Functions, and Docker.

This project was developed as part of a Master's Thesis (TFM) to analyze **critical thinking levels** in YouTube comments across different content categories. By collecting comments from long-form and short-form videos, the resulting dataset can be used to measure cognitive engagement patterns depending on video theme and format.

---

## ✨ Features

- 🎯 **Theme-based extraction** — Randomly cycles through 14 macro-themes without repetition until all are covered
- 🧹 **Automatic text sanitization** — Removes HTML tags, HTML entities, raw URLs, and emojis from comment text
- 📦 **Dual storage modes** — Save locally to `local_data_lake/` or upload directly to Azure Blob Storage
- 🔄 **Dual format support** — Extract from long-form videos or YouTube Shorts via a single flag
- 🐳 **Docker-ready** — Fully containerized and reproducible with a single `docker-compose up` command
- ☁️ **Azure-native** — Designed to deploy to Azure Functions with zero changes

---

## 🏗️ Architecture

```
┌─────────────────────────────┐        HTTP POST (JSON payload)       ┌────────────────────────────────────┐
│   batch_launcher.py         │  ────────────────────────────────────▶ │   function_app.py                  │
│                             │                                         │   (Azure Function)                 │
│  - Picks a random theme     │                                         │                                    │
│  - Sends: theme,            │                                         │  1. Searches YouTube API for       │
│    is_short, upload_to_cloud│                                         │     videos matching the theme      │
│  - Loops N times            │                                         │  2. Extracts up to 10,000 comments │
└─────────────────────────────┘                                         │  3. Cleans text (HTML, emojis...)  │
                                                                        │  4. Saves to local_data_lake/      │
                                                                        │     or Azure Blob Storage          │
                                                                        └────────────────────────────────────┘
```

---

## 📁 Project Structure

```
tfm-youtube-comments-pipeline/
├── function_app.py          # Core Azure Function (YouTube extraction + sanitization)
├── batch_launcher.py        # Script to trigger the function in batch mode
├── requirements.txt         # Python dependencies for the Azure Function
├── host.json                # Azure Functions runtime configuration
├── Dockerfile               # Container image for the Azure Function
├── Dockerfile.launcher      # Container image for the batch launcher
├── docker-compose.yml       # Orchestrates both containers together
├── .env.example             # Template for secrets (safe to commit)
├── .env                     # Your real secrets (gitignored, never committed)
└── local_data_lake/         # Output directory for local JSON files (gitignored)
```

---

## 🚀 Quick Start (Docker — Recommended)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A [YouTube Data API v3](https://console.cloud.google.com/) key
- *(Optional)* An Azure Storage connection string (only if `upload_to_cloud: True`)

### Steps

**1. Clone the repository**
```bash
git clone https://github.com/Ismaelardoy/tfm-youtube-comments-pipeline.git
cd tfm-youtube-comments-pipeline
```

**2. Configure your secrets**
```bash
cp .env.example .env
```
Open `.env` and fill in your values:
```env
YOUTUBE_API_KEY=AIza...your_key_here...
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
```

**3. Launch everything**
```bash
docker-compose up --build
```

That's it. Docker will:
1. Build the Azure Function container
2. Build the Batch Launcher container
3. Wait until the Function is healthy
4. Automatically start extracting comments

JSON files will appear in `local_data_lake/` on your machine in real time.

**4. Stop**
```bash
docker-compose down
```

---

## 🛠️ Manual Setup (without Docker)

```bash
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy and fill in your settings
cp local.settings.json.example local.settings.json  # edit with your API keys

# Terminal 1 — Start the Azure Function locally
func start

# Terminal 2 — Run the batch launcher
python batch_launcher.py
```

---

## ⚙️ Configuration

### `batch_launcher.py` — Key Parameters

| Variable | Default | Description |
|---|---|---|
| `TOTAL_REQUESTS` | `3` | Number of extraction rounds to run |
| `WAIT_TIME_SECONDS` | `4` | Cooldown between requests (seconds) |
| `is_short` | `False` | `True` = YouTube Shorts only; `False` = Long-form videos only |
| `upload_to_cloud` | `False` | `True` = upload JSON to Azure Blob Storage; `False` = save to `local_data_lake/` |

```python
payload = {
    "theme": selected_theme,   # Randomly chosen from THEMES list
    "is_short": False,         # False = long videos, True = Shorts
    "upload_to_cloud": False   # False = local_data_lake/, True = Azure Blob
}
```

### Theme Rotation

The launcher automatically **shuffles and cycles** through all 14 themes without repeating until the full list is exhausted:

```python
THEMES = [
    # Impulsive / superficial engagement
    'celebrity gossip', 'funny pranks', 'daily vlog',
    'influencer apology', 'gaming drama', 'viral challenges',

    # Informational / analytical engagement
    'science documentary', 'history explained', 'video essay',
    'philosophy lecture', 'personal finance', 'tech gadget review',

    # Polarized / debate topics
    'politics debate', 'conspiracy theory'
]
```

---

## 🧪 How the Extraction Works

Each request to the Azure Function follows this pipeline:

### 1. Video Discovery
The function uses the YouTube Data API to search for videos published after **January 1st, 2025** matching the given theme. A random date within the range is chosen each time to maximize variety.

```python
search_request = youtube.search().list(
    part="snippet",
    q=search_query,
    type="video",
    videoDuration=video_duration,   # "long" or "short"
    relevanceLanguage="en",
    publishedAfter=random_published_after,
    maxResults=50
)
```

### 2. Comment Extraction
Comments are paginated and collected from all found videos until a **global limit of 10,000 comments** is reached.

### 3. Text Sanitization
Every comment passes through `clean_comment_text()` before being saved:

```python
def clean_comment_text(text: str) -> str:
    text = html.unescape(text)              # &#39; → '
    text = re.sub(r'<[^>]+>', ' ', text)   # Remove <br>, <a href...>, etc.
    text = re.sub(r'http[s]?://\S+', '', text)  # Remove URLs
    text = emoji.replace_emoji(text, replace='') # Remove emojis
    text = re.sub(r'\s+', ' ', text).strip()     # Normalize whitespace
    return text
```

Empty comments (e.g. those that were *only* emojis or links) are discarded automatically.

### 4. Output JSON Schema
Each comment is saved with the following structure:

```json
{
    "videoId": "dQw4w9WgXcQ",
    "theme": "music video",
    "is_short": false,
    "author": "@username",
    "text": "This is the clean, sanitized comment text.",
    "likeCount": 42,
    "publishedAt": "2025-03-01T12:00:00Z"
}
```

---

## ☁️ Deploying to Azure

When you're ready to run this in the cloud, set `upload_to_cloud: True` in `batch_launcher.py` and deploy the Function:

```bash
func azure functionapp publish <your-function-app-name>
```

Make sure your Azure Function App has the following Application Settings configured:
- `YOUTUBE_API_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `azure-functions` | Azure Functions runtime |
| `google-api-python-client` | YouTube Data API v3 |
| `azure-storage-blob` | Azure Blob Storage client |
| `emoji` | Emoji detection and removal |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
