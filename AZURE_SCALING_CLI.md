# Azure Scaling - Quick CLI Reference

## Prerequisites

Install Azure CLI if not already installed:
```bash
# Windows (PowerShell)
winget install -e --id Microsoft.AzureCLI

# Or download from: https://aka.ms/installazurecliwindows
```

Login to Azure:
```bash
az login
```

Set your subscription (if you have multiple):
```bash
az account list --output table
az account set --subscription "Your Subscription Name"
```

---

## Step 1: Scale App Service to Multiple Instances

### Get Your App Service Details

```bash
# List all App Services
az webapp list --output table

# Get your App Service name and resource group
APP_NAME="your-app-service-name"
RESOURCE_GROUP="your-resource-group-name"
```

### Scale to 2 Instances

```bash
# Scale to 2 instances
az appservice plan update \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --number-of-workers 2

# Verify scaling
az appservice plan show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "sku.capacity" \
  --output tsv
```

### Scale to 3+ Instances

```bash
# Scale to 3 instances
az appservice plan update \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --number-of-workers 3
```

---

## Step 2: Create Azure Redis Cache

### Create Redis Cache

```bash
# Set variables
REDIS_NAME="your-app-redis"  # Must be globally unique
RESOURCE_GROUP="your-resource-group-name"
LOCATION="eastus"  # Use same region as your App Service

# Create Redis Cache (Basic C0 - 250 MB)
az redis create \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Basic \
  --vm-size c0

# For production, use Standard tier:
az redis create \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard \
  --vm-size c1
```

### Get Redis Connection Details

```bash
# Get Redis hostname
az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "hostName" \
  --output tsv

# Get Redis access keys
az redis list-keys \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "primaryKey" \
  --output tsv
```

### Construct Redis URL

```bash
# Get values
REDIS_HOST=$(az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "hostName" \
  --output tsv)

REDIS_KEY=$(az redis list-keys \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "primaryKey" \
  --output tsv)

# Construct Redis URL
REDIS_URL="redis://:${REDIS_KEY}@${REDIS_HOST}:6380/0"
echo "Redis URL: $REDIS_URL"
```

---

## Step 3: Configure App Service with Redis

### Add Redis URL to App Service

```bash
# Set variables
APP_NAME="your-app-service-name"
RESOURCE_GROUP="your-resource-group-name"

# Add REDIS_URL environment variable
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings REDIS_URL="$REDIS_URL"

# Verify it was set
az webapp config appsettings list \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "[?name=='REDIS_URL'].value" \
  --output tsv
```

### Restart App Service

```bash
az webapp restart \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP
```

---

## Step 4: Verify Configuration

### Check Instance Count

```bash
az appservice plan show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "sku.capacity" \
  --output tsv
```

### Check App Service Logs

```bash
# Stream logs to see Redis connection status
az webapp log tail \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP
```

Look for:
```
[SESSION] Redis session storage enabled (distributed sessions)
```

### Test Health Endpoint

```bash
# Get your app URL
APP_URL=$(az webapp show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "defaultHostName" \
  --output tsv)

# Test health endpoint
curl https://${APP_URL}/health
```

---

## Optional: Configure Auto-Scaling

### Create Auto-Scale Rule

```bash
# Get App Service Plan name
APP_SERVICE_PLAN=$(az appservice plan list \
  --resource-group $RESOURCE_GROUP \
  --query "[0].name" \
  --output tsv)

# Create auto-scale settings (scale between 2-5 instances based on CPU)
az monitor autoscale create \
  --name "${APP_SERVICE_PLAN}-autoscale" \
  --resource-group $RESOURCE_GROUP \
  --resource "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Web/serverfarms/${APP_SERVICE_PLAN}" \
  --min-count 2 \
  --max-count 5 \
  --count 2

# Add scale-out rule (when CPU > 70%)
az monitor autoscale rule create \
  --autoscale-name "${APP_SERVICE_PLAN}-autoscale" \
  --resource-group $RESOURCE_GROUP \
  --condition "Percentage CPU > 70 avg 5m" \
  --scale out 1

# Add scale-in rule (when CPU < 30%)
az monitor autoscale rule create \
  --autoscale-name "${APP_SERVICE_PLAN}-autoscale" \
  --resource-group $RESOURCE_GROUP \
  --condition "Percentage CPU < 30 avg 5m" \
  --scale in 1
```

---

## Complete Script Example

Save this as `scale-azure-app.sh`:

```bash
#!/bin/bash

# Configuration
APP_NAME="your-app-service-name"
RESOURCE_GROUP="your-resource-group-name"
REDIS_NAME="your-app-redis"
LOCATION="eastus"
INSTANCE_COUNT=2

echo "=== Scaling Azure App Service ==="

# Step 1: Scale App Service
echo "Step 1: Scaling App Service to $INSTANCE_COUNT instances..."
az appservice plan update \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --number-of-workers $INSTANCE_COUNT

# Step 2: Create Redis Cache (if it doesn't exist)
echo "Step 2: Creating Redis Cache..."
az redis create \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard \
  --vm-size c1 \
  --output none 2>/dev/null || echo "Redis cache already exists or creation failed"

# Step 3: Get Redis connection details
echo "Step 3: Getting Redis connection details..."
REDIS_HOST=$(az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "hostName" \
  --output tsv)

REDIS_KEY=$(az redis list-keys \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "primaryKey" \
  --output tsv)

REDIS_URL="redis://:${REDIS_KEY}@${REDIS_HOST}:6380/0"

# Step 4: Configure App Service
echo "Step 4: Configuring App Service with Redis..."
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings REDIS_URL="$REDIS_URL" \
  --output none

# Step 5: Restart App Service
echo "Step 5: Restarting App Service..."
az webapp restart \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --output none

echo "=== Scaling Complete ==="
echo "Instance count: $INSTANCE_COUNT"
echo "Redis URL configured: Yes"
echo ""
echo "Check logs to verify Redis connection:"
echo "az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
```

Make it executable and run:
```bash
chmod +x scale-azure-app.sh
./scale-azure-app.sh
```

---

## Troubleshooting Commands

### Check App Service Status

```bash
az webapp show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "state" \
  --output tsv
```

### Check Redis Status

```bash
az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "provisioningState" \
  --output tsv
```

### View All App Service Settings

```bash
az webapp config appsettings list \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --output table
```

### Test Redis Connection

```bash
# Install redis-cli if needed
# Windows: choco install redis-64
# Linux: sudo apt-get install redis-tools

REDIS_HOST=$(az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "hostName" \
  --output tsv)

REDIS_KEY=$(az redis list-keys \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "primaryKey" \
  --output tsv)

redis-cli -h $REDIS_HOST -p 6380 -a $REDIS_KEY ping
# Should return: PONG
```

---

## Cost Estimation

### Check Current Costs

```bash
# View App Service Plan pricing
az appservice plan show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "sku" \
  --output json

# View Redis pricing
az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "sku" \
  --output json
```

---

## Summary

**Quick Commands:**

```bash
# Scale to 2 instances
az appservice plan update --name $APP_NAME --resource-group $RESOURCE_GROUP --number-of-workers 2

# Create Redis
az redis create --name $REDIS_NAME --resource-group $RESOURCE_GROUP --location $LOCATION --sku Standard --vm-size c1

# Configure Redis URL
az webapp config appsettings set --name $APP_NAME --resource-group $RESOURCE_GROUP --settings REDIS_URL="$REDIS_URL"

# Restart
az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP
```

For detailed explanations, see `AZURE_SCALING_GUIDE.md`.
