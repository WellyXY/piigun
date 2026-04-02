# Parrot API

## Authentication

Pass your API key in every request header:

```
X-API-Key: pk_your_key_here
```

---

## Generate a Video

### `POST /v1/generate`

```json
{
  "image_url": "https://...",
  "position": "cowgirl",
  "duration": 10,
  "seed": 42,
  "include_audio": false,
  "audio_description": "",
  "callback_url": "https://..."
}
```

| Field | Required | Description |
|---|---|---|
| `image_url` | Yes* | URL of the input image |
| `image_base64` | Yes* | Base64-encoded image (alternative to `image_url`) |
| `position` | No | Scene type — defaults to `cowgirl` |
| `duration` | No | Seconds, 5–10 (default: `10`) |
| `seed` | No | For reproducibility (default: random) |
| `include_audio` | No | Enable dirty talk audio (default: `false`) |
| `audio_description` | No | What the character says — only used when `include_audio` is `true`. Leave empty for the built-in default |
| `callback_url` | No | Webhook URL called on completion or failure |

*One of `image_url` or `image_base64` is required.

**Supported positions**

```
blow_job  cowgirl  doggy  handjob  lift_clothes  masturbation  missionary  reverse_cowgirl
```

**Response**

```json
{
  "job_id": "job_abc123",
  "status": "queued",
  "position": 1
}
```

---

## Get Job Status

### `GET /v1/jobs/{job_id}`

```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "progress": 1.0,
  "video_url": "https://..."
}
```

Poll every 3–5 seconds until `status` is `completed` or `failed`.

---

## Webhook Payload

```json
{
  "event": "job.completed",
  "job_id": "job_abc123",
  "video_url": "https://..."
}
```

```json
{
  "event": "job.failed",
  "job_id": "job_abc123",
  "error": "..."
}
```
