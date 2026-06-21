# Compresser seulement creds.json (fichier essentiel Baileys)
$credsPath = "session_data\creds.json"
if (-not (Test-Path $credsPath)) {
    Write-Host "ERREUR: $credsPath introuvable"
    exit 1
}
$bytes = [IO.File]::ReadAllBytes($credsPath)
$b64 = [Convert]::ToBase64String($bytes)
Write-Host "Taille creds.json: $($bytes.Length) bytes"
$b64 | gh secret set WHATSAPP_CREDS_JSON
Write-Host "Session uploadee sur GitHub (secret: WHATSAPP_CREDS_JSON) !"
