$ErrorActionPreference = 'Stop'

$project = 'hackathon-510415'
$region = 'asia-south1'
$service = 'bharat-sourcer-web'
$serviceAccountName = 'bharat-sourcer-web'
$serviceAccount = "$serviceAccountName@$project.iam.gserviceaccount.com"
$backendUrl = 'https://bharat-sourcer-integration-diahnrbuna-el.a.run.app'
$secret = 'bharat-sourcer-integration-key'
$gcloud = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$localConfig = Join-Path $PSScriptRoot '..\.env.local'
$firebaseNames = @('VITE_FIREBASE_API_KEY', 'VITE_FIREBASE_AUTH_DOMAIN', 'VITE_FIREBASE_PROJECT_ID', 'VITE_FIREBASE_APP_ID')
$firebaseConfig = @{}
if (-not (Test-Path -LiteralPath $localConfig)) { throw 'frontend/.env.local with Firebase web configuration is required' }
foreach ($line in Get-Content -LiteralPath $localConfig) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
        $firebaseConfig[$matches[1]] = $matches[2].Trim('"', "'")
    }
}
foreach ($name in $firebaseNames) {
    if (-not $firebaseConfig[$name]) { throw "Missing $name in frontend/.env.local" }
}
if ($firebaseConfig['VITE_FIREBASE_PROJECT_ID'] -ne $project) { throw 'Firebase project does not match the deployment project' }
$publicEnv = @(
    "BACKEND_BASE_URL=$backendUrl",
    "FIREBASE_API_KEY=$($firebaseConfig['VITE_FIREBASE_API_KEY'])",
    "FIREBASE_AUTH_DOMAIN=$($firebaseConfig['VITE_FIREBASE_AUTH_DOMAIN'])",
    "FIREBASE_PROJECT_ID=$($firebaseConfig['VITE_FIREBASE_PROJECT_ID'])",
    "FIREBASE_APP_ID=$($firebaseConfig['VITE_FIREBASE_APP_ID'])"
) -join ','

if (-not (Test-Path -LiteralPath $gcloud)) { throw "Google Cloud CLI not found at $gcloud" }
$active = @(& $gcloud auth list --filter='status:ACTIVE' --format='value(account)' 2>$null)
if (-not $active.Count -or -not $active[0]) { throw 'Run gcloud auth login with a project-authorized account first.' }

Push-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
try {
    & $gcloud secrets describe $secret "--project=$project" '--format=value(name)' --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Secret $secret is unavailable" }

    $existingAccounts = @(& $gcloud iam service-accounts list "--project=$project" "--filter=email:$serviceAccount" '--format=value(email)' --quiet)
    if ($LASTEXITCODE -ne 0) { throw 'Could not list service accounts' }
    if ($existingAccounts -notcontains $serviceAccount) {
        & $gcloud iam service-accounts create $serviceAccountName '--display-name=Bharat Sourcer frontend proxy' "--project=$project" --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Could not create frontend service account' }
    }

    & $gcloud run deploy $service "--project=$project" "--region=$region" '--source=.' "--service-account=$serviceAccount" '--port=8080' '--cpu=1' '--memory=512Mi' '--min-instances=0' '--max-instances=1' '--concurrency=20' '--timeout=120' "--set-env-vars=$publicEnv" "--set-secrets=INTEGRATION_KEY=${secret}:latest" --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Cloud Run frontend deployment failed' }

    $url = & $gcloud run services describe $service "--project=$project" "--region=$region" '--format=value(status.url)' --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Cloud Run deployed, but its URL could not be read' }
    Write-Output "Deployed frontend: $url"
} finally {
    Pop-Location
}
