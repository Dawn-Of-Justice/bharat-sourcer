$ErrorActionPreference = 'Stop'

$project = 'hackathon-510415'
$region = 'asia-south1'
$service = 'bharat-sourcer-web'
$serviceAccountName = 'bharat-sourcer-web'
$serviceAccount = "$serviceAccountName@$project.iam.gserviceaccount.com"
$backendUrl = 'https://bharat-sourcer-integration-diahnrbuna-el.a.run.app'
$secret = 'bharat-sourcer-integration-key'
$gcloud = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'

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

    & $gcloud run deploy $service "--project=$project" "--region=$region" '--source=.' "--service-account=$serviceAccount" '--port=8080' '--cpu=1' '--memory=512Mi' '--min-instances=0' '--max-instances=1' '--concurrency=20' '--timeout=120' "--set-env-vars=BACKEND_BASE_URL=$backendUrl" "--set-secrets=INTEGRATION_KEY=${secret}:latest" --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Cloud Run frontend deployment failed' }

    $url = & $gcloud run services describe $service "--project=$project" "--region=$region" '--format=value(status.url)' --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Cloud Run deployed, but its URL could not be read' }
    Write-Output "Deployed frontend: $url"
} finally {
    Pop-Location
}
