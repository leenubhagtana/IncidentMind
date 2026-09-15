$root = "D:\ML"

Write-Host ""
Write-Host "Stopping IncidentMind..." -ForegroundColor Yellow
Write-Host ""

# Stop Docker infrastructure

Set-Location $root

Write-Host "Stopping Docker containers..." -ForegroundColor Yellow
docker compose down

Write-Host ""
Write-Host "Docker infrastructure stopped." -ForegroundColor Green

Write-Host ""
Write-Host "Please close the Python service PowerShell windows." -ForegroundColor Cyan
Write-Host ""
Write-Host "IncidentMind stopped." -ForegroundColor Cyan
