
$root = "D:\ML"
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "Starting IncidentMind..." -ForegroundColor Cyan
Write-Host ""

# --------------------------------
# Start Docker infrastructure
# --------------------------------

Write-Host "Starting Docker infrastructure..." -ForegroundColor Yellow

Set-Location $root

docker compose up -d

# --------------------------------
# Wait for Kafka
# --------------------------------

Write-Host "Waiting for Kafka to become ready..." -ForegroundColor Yellow

$kafkaReady = $false

while (-not $kafkaReady) {

    docker exec incidentmind-kafka `
        /opt/kafka/bin/kafka-topics.sh `
        --bootstrap-server localhost:9092 `
        --list *> $null

    if ($LASTEXITCODE -eq 0) {

        $kafkaReady = $true

        Write-Host "Kafka is ready!" -ForegroundColor Green

    }
    else {

        Start-Sleep -Seconds 2

    }
}

# --------------------------------
# Ensure required Kafka topics exist
# --------------------------------

Write-Host ""
Write-Host "Checking Kafka topics..." -ForegroundColor Yellow


# Create order-events if it does not exist

docker exec incidentmind-kafka `
    /opt/kafka/bin/kafka-topics.sh `
    --bootstrap-server localhost:9092 `
    --create `
    --if-not-exists `
    --topic order-events `
    --partitions 1 `
    --replication-factor 1


# Create payment-events if it does not exist

docker exec incidentmind-kafka `
    /opt/kafka/bin/kafka-topics.sh `
    --bootstrap-server localhost:9092 `
    --create `
    --if-not-exists `
    --topic payment-events `
    --partitions 1 `
    --replication-factor 1


Write-Host ""
Write-Host "Kafka topics are ready!" -ForegroundColor Green


# --------------------------------
# Start Order Service
# --------------------------------

Write-Host ""
Write-Host "Starting Order Service..." -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\services\order_service'; `$env:PYTHONPATH='$root'; & '$python' -m uvicorn app.main:app --reload --port 8000"
)


# --------------------------------
# Start Payment API
# --------------------------------

Write-Host "Starting Payment API..." -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\services\payment_service'; `$env:PYTHONPATH='$root'; & '$python' -m uvicorn app.main:app --reload --port 8001"
)


# --------------------------------
# Start Payment Consumer
# --------------------------------

Write-Host "Starting Payment Consumer..." -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\services\payment_service'; `$env:PYTHONPATH='$root'; & '$python' -m app.kafka.run_consumer"
)


# --------------------------------
# Start Inventory API
# --------------------------------

Write-Host "Starting Inventory API..." -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\services\inventory_service'; `$env:PYTHONPATH='$root'; & '$python' -m uvicorn app.main:app --reload --port 8002"
)


# --------------------------------
# Start Inventory Consumer
# --------------------------------

Write-Host "Starting Inventory Consumer..." -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\services\inventory_service'; `$env:PYTHONPATH='$root'; & '$python' -m app.kafka.run_consumer"
)


# --------------------------------
# Start Event Processor
# --------------------------------

Write-Host "Starting Event Processor..." -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\event_processor'; `$env:PYTHONPATH='$root\event_processor;$root'; & '$python' -m uvicorn app.main:app --reload --port 8003"
)


# --------------------------------
# Finished
# --------------------------------

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "IncidentMind started successfully!" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Order Service:       http://127.0.0.1:8000/docs"
Write-Host "Payment Service:     http://127.0.0.1:8001/docs"
Write-Host "Inventory Service:   http://127.0.0.1:8002/docs"
Write-Host "Event Processor:     http://127.0.0.1:8003/docs"

