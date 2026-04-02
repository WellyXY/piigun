# Parrot API — Complete Usage Guide

## 📋 Table of Contents

1. [API Overview](#api-overview)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
4. [Usage Examples](#usage-examples)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)
7. [FAQ](#faq)

---

## 🌟 API Overview

Parrot API is an image-to-video generation service. Upload a portrait image, select a position, and receive a generated video — optionally with audio.

### Basic Information

- **API Base URL**: `https://www.racoonn.me`
- **Authentication**: `X-API-Key` header
- **Request Format**: JSON
- **Video Output**: MP4, 25 fps, 1024×1536

---

## 🔐 Authentication

All requests require an API key passed in the header.

```
X-API-Key: pk_your_key_here
```

**API Key Format**: `pk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

> ⚠️ Keep your API key private. Do not expose it in client-side code.

---

## 🛠 API Endpoints

### 1. Generate Video (POST)

Convert a static image into a video.

- **URL**: `POST /v1/generate`
- **Content-Type**: `application/json`

### Request Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `image_url` | String | Yes* | Publicly accessible URL of the input image |
| `image_base64` | String | Yes* | Base64-encoded image (alternative to `image_url`) |
| `position` | String | No | Scene type — defaults to `cowgirl` |
| `duration` | Integer | No | Video length in seconds, 5–10 (default: `10`) |
| `seed` | Integer | No | For reproducibility (default: random) |
| `include_audio` | Boolean | No | Enable dirty talk audio (default: `false`) |
| `audio_description` | String | No | What the character says — only used when `include_audio` is `true`. Leave empty for the built-in default |
| `callback_url` | String | No | Webhook URL called when the job completes or fails |

*One of `image_url` or `image_base64` is required.

### Supported Positions

| Value | Description |
|---|---|
| `cowgirl` | Cowgirl (default) |
| `reverse_cowgirl` | Reverse cowgirl |
| `missionary` | Missionary |
| `doggy` | Doggy style |
| `blow_job` | Blow job |
| `masturbation` | Masturbation |

### Request Example

```bash
curl -X POST 'https://www.racoonn.me/v1/generate' \
  -H 'X-API-Key: pk_your_key_here' \
  -H 'Content-Type: application/json' \
  -d '{
    "image_url": "https://example.com/photo.jpg",
    "position": "cowgirl",
    "duration": 10,
    "include_audio": true
  }'
```

### Response Example

```json
{
  "job_id": "job_abc123def456",
  "status": "queued",
  "position": 1
}
```

---

### 2. Get Job Status (GET)

Check the status of a generation job.

- **URL**: `GET /v1/jobs/{job_id}`

### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `job_id` | String | Yes | Job ID returned from the generate endpoint |

### Request Example

```bash
curl -X GET 'https://www.racoonn.me/v1/jobs/job_abc123def456' \
  -H 'X-API-Key: pk_your_key_here'
```

### Response Status

| Status | Description |
|---|---|
| `queued` | Waiting in queue |
| `processing` | Running on GPU |
| `completed` | Done — `video_url` is populated |
| `failed` | Failed — see `error` field |

### Response Examples

**Queued:**
```json
{
  "job_id": "job_abc123def456",
  "status": "queued",
  "progress": 0.0,
  "video_url": null
}
```

**Processing:**
```json
{
  "job_id": "job_abc123def456",
  "status": "processing",
  "progress": 0.7,
  "video_url": null
}
```

**Completed:**
```json
{
  "job_id": "job_abc123def456",
  "status": "completed",
  "progress": 1.0,
  "video_url": "https://pub-xxx.r2.dev/job_abc123def456.mp4"
}
```

**Failed:**
```json
{
  "job_id": "job_abc123def456",
  "status": "failed",
  "progress": 0.0,
  "error": "Invalid image URL"
}
```

---

## 💡 Usage Examples

### Complete Workflow

#### Step 1: Submit a Job

```bash
curl -X POST 'https://www.racoonn.me/v1/generate' \
  -H 'X-API-Key: pk_your_key_here' \
  -H 'Content-Type: application/json' \
  -d '{
    "image_url": "https://example.com/photo.jpg",
    "position": "doggy",
    "duration": 10,
    "include_audio": true,
    "audio_description": "moan softly and whisper yes",
    "callback_url": "https://your-server.com/webhook"
  }'
```

**Response:**
```json
{ "job_id": "job_abc123def456", "status": "queued", "position": 1 }
```

#### Step 2: Poll for Status

```bash
curl 'https://www.racoonn.me/v1/jobs/job_abc123def456' \
  -H 'X-API-Key: pk_your_key_here'
```

#### Step 3: Download the Video

Once `status` is `completed`, use `video_url` to download or display the video.

---

### Python Example

```python
import requests
import time

API_KEY = "pk_your_key_here"
BASE_URL = "https://www.racoonn.me"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def generate_video(image_url, position="cowgirl", duration=10,
                   include_audio=False, audio_description=""):
    response = requests.post(
        f"{BASE_URL}/v1/generate",
        headers=headers,
        json={
            "image_url": image_url,
            "position": position,
            "duration": duration,
            "include_audio": include_audio,
            "audio_description": audio_description,
        }
    )
    response.raise_for_status()
    return response.json()["job_id"]

def wait_for_completion(job_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        res = requests.get(f"{BASE_URL}/v1/jobs/{job_id}", headers=headers)
        data = res.json()
        status = data["status"]
        print(f"Status: {status} ({int(data.get('progress', 0) * 100)}%)")
        if status == "completed":
            return data["video_url"]
        if status == "failed":
            raise Exception(f"Job failed: {data.get('error')}")
        time.sleep(5)
    raise TimeoutError("Job timed out")

# Usage
job_id = generate_video(
    image_url="https://example.com/photo.jpg",
    position="missionary",
    include_audio=True
)
print(f"Job ID: {job_id}")

video_url = wait_for_completion(job_id)
print(f"Video ready: {video_url}")
```

---

### JavaScript (Node.js) Example

```javascript
const fetch = require('node-fetch');

const API_KEY = 'pk_your_key_here';
const BASE_URL = 'https://www.racoonn.me';

const headers = {
  'X-API-Key': API_KEY,
  'Content-Type': 'application/json'
};

async function generateVideo({ imageUrl, position = 'cowgirl', duration = 10,
                                includeAudio = false, audioDescription = '' }) {
  const res = await fetch(`${BASE_URL}/v1/generate`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      image_url: imageUrl,
      position,
      duration,
      include_audio: includeAudio,
      audio_description: audioDescription,
    })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
  return data.job_id;
}

async function waitForCompletion(jobId, timeout = 120000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const res = await fetch(`${BASE_URL}/v1/jobs/${jobId}`, { headers });
    const data = await res.json();
    console.log(`Status: ${data.status} (${Math.round((data.progress || 0) * 100)}%)`);
    if (data.status === 'completed') return data.video_url;
    if (data.status === 'failed') throw new Error(`Job failed: ${data.error}`);
    await new Promise(r => setTimeout(r, 5000));
  }
  throw new Error('Job timed out');
}

// Usage
(async () => {
  const jobId = await generateVideo({
    imageUrl: 'https://example.com/photo.jpg',
    position: 'cowgirl',
    includeAudio: true,
    audioDescription: 'whisper softly'
  });
  console.log(`Job ID: ${jobId}`);

  const videoUrl = await waitForCompletion(jobId);
  console.log(`Video ready: ${videoUrl}`);
})();
```

---

## ❌ Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|---|---|---|
| `400` | Bad request — invalid parameters | Check request body |
| `401` | Missing or invalid API key | Verify your `X-API-Key` |
| `403` | API key disabled | Contact support |
| `422` | Validation error — missing required field | Check required parameters |
| `500` | Server error | Retry after a moment |

### Error Response Examples

**Missing API Key (401)**
```json
{ "detail": "Missing API key" }
```

**Invalid Position (422)**
```json
{
  "detail": "Invalid position 'xyz'. Available: cowgirl, missionary, ..."
}
```

**No Image Provided (422)**
```json
{
  "detail": "Either image_url or image_base64 must be provided"
}
```

---

## 🚀 Best Practices

### 1. Use Webhooks Over Polling

Set `callback_url` to receive instant notification on completion instead of polling.

```json
{ "callback_url": "https://your-server.com/parrot-webhook" }
```

Webhook payload:
```json
{
  "event": "job.completed",
  "job_id": "job_abc123",
  "video_url": "https://..."
}
```

### 2. Image Guidelines

- **Format**: JPEG, PNG, WebP
- **Orientation**: Portrait preferred
- **Subject**: Single person, clear face, well-lit
- **URL**: Must be publicly accessible (CDN, S3, R2)

### 3. Polling Strategy

- Poll every **5 seconds**
- Set a **120-second timeout**
- Handle `failed` status explicitly

### 4. Audio Description Tips

When `include_audio` is `true` and you want custom dialogue:

- Write what the character says in natural language
- Keep it concise — a sentence or two
- Leave `audio_description` empty to use the optimized built-in default

---

## ❓ FAQ

**Q: What happens if I don't pass `position`?**
A: Defaults to `cowgirl`.

**Q: Can I pass a custom video prompt?**
A: No — the API uses built-in optimized prompts per position. Custom prompt fields are ignored.

**Q: What image formats are supported?**
A: JPEG, PNG, WebP. JPEG recommended for best compatibility.

**Q: Can I use `image_base64` instead of a URL?**
A: Yes. Pass the raw base64 string (no `data:image/...` prefix needed).

**Q: What if my job fails?**
A: Check the `error` field in the job status response. Common causes: inaccessible image URL, unsupported image format, or server overload. Retry with corrected parameters.

**Q: Is there a concurrency limit?**
A: Jobs are processed sequentially per GPU. Submit multiple jobs and they will queue automatically.

**Q: How do I get an API key?**
A: Contact the Parrot team directly.
