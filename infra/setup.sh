#!/usr/bin/env bash
# =============================================================================
# EF Automation - Azure Infrastructure Setup
# Run once to provision all required Azure resources.
# Prerequisites: az CLI logged in (az login), correct subscription selected.
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
RESOURCE_GROUP="rg-ef-automation"
LOCATION="eastus"                        # Change to your preferred region
STORAGE_ACCOUNT="stefautomation"         # Must be globally unique, 3-24 lowercase alphanum
FUNCTION_APP="func-ef-automation"        # Must be globally unique
KEY_VAULT="kv-ef-automation"             # Must be globally unique, 3-24 chars
APP_SERVICE_PLAN=""                      # Leave empty for Consumption plan

SENDER_EMAIL="it-automation-service@netradyne.com"
IT_EMAIL="it-operations@netradyne.com"
# ──────────────────────────────────────────────────────────────────────────────

echo "=== Step 1: Create Resource Group ==="
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

echo ""
echo "=== Step 2: Create Storage Account (hosts Function code + Table Storage) ==="
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output table

echo ""
echo "=== Step 3: Create Azure Table Storage tables ==="
az storage table create --name "UserTracking"  --account-name "$STORAGE_ACCOUNT"
az storage table create --name "AuditLog"      --account-name "$STORAGE_ACCOUNT"
az storage table create --name "EmailLog"      --account-name "$STORAGE_ACCOUNT"
echo "Tables created: UserTracking, AuditLog, EmailLog"

echo ""
echo "=== Step 4: Create Key Vault ==="
az keyvault create \
  --name "$KEY_VAULT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --enable-rbac-authorization true \
  --output table

echo ""
echo "=== Step 5: Create Function App (Consumption plan, Python 3.11) ==="
az functionapp create \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-account "$STORAGE_ACCOUNT" \
  --consumption-plan-location "$LOCATION" \
  --runtime python \
  --runtime-version "3.11" \
  --functions-version 4 \
  --os-type Linux \
  --assign-identity '[system]' \
  --output table

echo ""
echo "=== Step 6: Retrieve Managed Identity Principal ID ==="
PRINCIPAL_ID=$(az functionapp identity show \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId \
  --output tsv)
echo "Managed Identity Principal ID: $PRINCIPAL_ID"

echo ""
echo "=== Step 7: Grant Managed Identity access to Storage Tables ==="
STORAGE_ID=$(az storage account show \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query id --output tsv)

az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Storage Table Data Contributor" \
  --scope "$STORAGE_ID" \
  --output table

echo ""
echo "=== Step 8: Grant Managed Identity access to Key Vault Secrets ==="
KV_ID=$(az keyvault show --name "$KEY_VAULT" --query id --output tsv)
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID" \
  --output table

echo ""
echo "=== Step 9: Store SMTP password in Key Vault ==="
echo ">>> You will be prompted to enter the SMTP app password for $SENDER_EMAIL"
read -rsp "Enter SMTP app password: " SMTP_PASSWORD
echo ""
az keyvault secret set \
  --vault-name "$KEY_VAULT" \
  --name "smtp-password" \
  --value "$SMTP_PASSWORD" \
  --output table
echo "SMTP password stored in Key Vault as 'smtp-password'"

echo ""
echo "=== Step 10: Configure Function App Settings ==="
STORAGE_CONN=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString --output tsv)

TENANT_ID=$(az account show --query tenantId --output tsv)

az functionapp config appsettings set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    "AZURE_TENANT_ID=$TENANT_ID" \
    "STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT" \
    "KEY_VAULT_NAME=$KEY_VAULT" \
    "SMTP_SERVER=smtp.office365.com" \
    "SMTP_PORT=587" \
    "SENDER_EMAIL=$SENDER_EMAIL" \
    "IT_EMAIL=$IT_EMAIL" \
    "RECOVERY_GRACE_DAYS=30" \
  --output table

echo ""
echo "========================================================================"
echo "Infrastructure setup COMPLETE."
echo ""
echo "NEXT STEP: Run infra/assign_permissions.ps1 in PowerShell to grant"
echo "the Managed Identity its Microsoft Graph API permissions."
echo ""
echo "Managed Identity Principal ID: $PRINCIPAL_ID"
echo "Save this value - you will need it in assign_permissions.ps1"
echo "========================================================================"
