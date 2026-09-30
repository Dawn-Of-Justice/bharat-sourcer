# Deployment and DevOps

> **In one minute.** There is one GCP project (`bharat-sourcer`) in `asia-south1` with billing on and a budget alert set.
> - **Backend:** the Cloud Run service `bs-api` (FastAPI + ADK) and the Cloud Run job `bs-compile`.
> - **Frontend and data:** Firebase Hosting (SPA + `/api/**` rewrite), Firestore, Cloud Storage and Secret Manager.
> - **Pipeline:** GitHub Actions deploys with Workload Identity Federation (no keys in the repo).
>
> Keep `min-instances=1` from 15 Oct to 6 Nov so judges never hit a cold start.

---

## 1. One-time setup

```bash
# project + billing
gcloud projects create bharat-sourcer-2026 --name="Bharat Sourcer"
gcloud config set project bharat-sourcer-2026
gcloud billing projects link bharat-sourcer-2026 --billing-account=XXXX-XXXX-XXXX

# APIs
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com \
  logging.googleapis.com cloudtrace.googleapis.com iamcredentials.googleapis.com \
  youtube.googleapis.com firebase.googleapis.com firebasehosting.googleapis.com \
  firebaseappcheck.googleapis.com cloudtasks.googleapis.com

# Firestore (Native) in Mumbai
gcloud firestore databases create --location=asia-south1

# bucket
gcloud storage buckets create gs://bs-artifacts-bharat-sourcer-2026 --location=asia-south1 --uniform-bucket-level-access

# artifact registry
gcloud artifacts repositories create bs --repository-format=docker --location=asia-south1

# service accounts
gcloud iam service-accounts create bs-api
gcloud iam service-accounts create bs-compile
```

IAM for `bs-api`:

- `roles/datastore.user`
- `roles/storage.objectAdmin` on the bucket
- `roles/secretmanager.secretAccessor`
- `roles/run.developer`, scoped so it can execute the compile job
- `roles/cloudtrace.agent`

IAM for `bs-compile`: `roles/storage.objectCreator` on `jobs/*/compile/` only.

## 2. Gemini API key and billing tier

1. Create the key in Google AI Studio on the **same billed project** (Tier 1 requires linked billing).
2. Confirm that grounding works. The free tier returns "not available".
3. Set a **project spend cap** in AI Studio (e.g. $150) and a **Cloud Billing budget alert** at 50/80/100%.
4. Note the actual RPM/TPM for `gemini-3.8-flash`, `gemini-3.5-flash-lite` and `gemini-3.1-pro-preview` from the rate-limit page, and put them in `config/runtime` for client-side throttling.

## 3. Secrets

```bash
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
gcloud secrets create youtube-api-key --data-file=-
gcloud secrets create digikey-client-id --data-file=-
gcloud secrets create digikey-client-secret --data-file=-
gcloud secrets create mouser-api-key --data-file=-
gcloud secrets create nexar-client-id --data-file=- ; gcloud secrets create nexar-client-secret --data-file=-
```

## 4. Backend image and Cloud Run service

`backend/Dockerfile` (sketch):

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY backend/ .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Deploy:

```bash
gcloud run deploy bs-api \
  --source=backend --region=asia-south1 \
  --service-account=bs-api@bharat-sourcer-2026.iam.gserviceaccount.com \
  --no-cpu-throttling \                # instance-based billing: background workflow keeps CPU
  --timeout=3600 --concurrency=10 --cpu=2 --memory=2Gi \
  --min-instances=0 --max-instances=5 \
  --set-env-vars=GCP_PROJECT=bharat-sourcer-2026,REGION=asia-south1,MODEL_VIDEO=gemini-3.8-flash,MODEL_LITE=gemini-3.5-flash-lite,MODEL_JUDGE=gemini-3.1-pro-preview,MODEL_JUDGE_FALLBACK=gemini-3.8-flash,COUNTRY=IN \
  --set-secrets=GOOGLE_API_KEY=gemini-api-key:latest,YOUTUBE_API_KEY=youtube-api-key:latest,DIGIKEY_CLIENT_ID=digikey-client-id:latest,DIGIKEY_CLIENT_SECRET=digikey-client-secret:latest,MOUSER_API_KEY=mouser-api-key:latest \
  --allow-unauthenticated
```

For judging (15 Oct to 6 Nov): `gcloud run services update bs-api --min-instances=1 --region=asia-south1`.

## 5. Compile job

`compile-job/Dockerfile`:

```dockerfile
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y curl ca-certificates python3 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=/usr/local/bin sh
RUN arduino-cli config init && \
    arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json && \
    arduino-cli config add board_manager.additional_urls https://arduino.esp8266.com/stable/package_esp8266com_index.json && \
    arduino-cli core update-index && \
    arduino-cli core install arduino:avr esp32:esp32 esp8266:esp8266 && \
    arduino-cli lib install "Adafruit SSD1306" "Adafruit SH110X" "Adafruit BME280 Library" "Adafruit BMP280 Library" \
      "Adafruit NeoPixel" "DHT sensor library" "NewPing" "AccelStepper" "TMCStepper" "OneWire" "DallasTemperature"
COPY compile-job/entrypoint.py /entrypoint.py
ENTRYPOINT ["python3", "/entrypoint.py"]
```

⚠️ The ESP32 core makes the image large (GBs). Build it once and keep it cached in Artifact Registry. Add the RP2040 core (earlephilhower) only if the eval set needs it.

```bash
gcloud run jobs deploy bs-compile --image=asia-south1-docker.pkg.dev/bharat-sourcer-2026/bs/compile:latest \
  --region=asia-south1 --service-account=bs-compile@… --cpu=2 --memory=4Gi --task-timeout=300 --max-retries=0
```

The API runs the job with overrides: `gcloud run jobs execute bs-compile --args=gs://…/sketch.zip,esp32:esp32:esp32 --wait`, or the equivalent Admin API call from Python.

## 6. Frontend and Firebase

`firebase.json`:

```json
{
  "hosting": {
    "public": "frontend/dist",
    "rewrites": [
      {"source": "/api/**", "run": {"serviceId": "bs-api", "region": "asia-south1"}},
      {"source": "**", "destination": "/index.html"}
    ],
    "headers": [{"source": "/.well-known/ucp-agent.json", "headers": [{"key": "Content-Type", "value": "application/json"}]}]
  },
  "firestore": {"rules": "infra/firestore.rules", "indexes": "infra/firestore.indexes.json"}
}
```

Remember that **Hosting rewrites time out at 60 s**. Only short calls (create job, confirm, choose, plan, export) go through `/api`. Long-running work is observed via Firestore.

Deploy: `npm --prefix frontend run build && firebase deploy --only hosting,firestore`.

App Check: register the web app with reCAPTCHA Enterprise, enforce it on the backend by verifying the `X-Firebase-AppCheck` header, and use a debug token in dev.

## 7. CI/CD (GitHub Actions)

- Auth via **Workload Identity Federation** (`google-github-actions/auth`). No JSON keys.
- **On PR:** lint (ruff, eslint), unit tests (rules engine!), type check, `gitleaks`, a frontend build, and a **smoke eval** (3 cached projects, offline fixtures).
- **On push to `main`:** deploy `bs-api-dev` and a Hosting preview channel.
- **On tag `v*`:** deploy prod, run the full eval (15 projects) and post a metrics summary as a job artifact.

## 8. Observability

| What | How |
|---|---|
| Logs | Structured JSON with `job_id`, `node`, `model`, `latency_ms`, `tokens_in/out`, `grounding_queries` |
| Traces | ADK OpenTelemetry → Cloud Trace. Take one screenshot of a full trace for the deck |
| Metrics | Log-based metrics for jobs per hour, p50/p95 job duration, grounding queries per job, cost per job (estimate), failure rate by node |
| Alerts | Error rate > 20% for 10 min; budget 80% |
| Dashboard | A small Cloud Monitoring dashboard, which also makes a good screenshot for "production-ready" |

## 9. Runbook (demo and judging period)

| Symptom | Action |
|---|---|
| Gemini 429s | Lower fan-out concurrency via `config/runtime`; switch the judge to the fallback model |
| Grounding quota near the cap | Set `TIER_C_ENABLED=false` (Tiers A/B plus cache still work) |
| Store adapter failing | Disable it in `config/runtime.sellers.<name>.enabled` |
| A demo video's result looks bad | Pre-warm the library entries for all demo projects on 15 Oct and re-check daily |
| Cold starts | Confirm min-instances=1; `/healthz` ping from Cloud Scheduler every 5 min |
