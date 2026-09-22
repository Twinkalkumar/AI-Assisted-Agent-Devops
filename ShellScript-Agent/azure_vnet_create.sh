#!/bin/bash

#########################################################
# Description: Create VPN in Azure
# - Create resource group
# - Create Virtual network in existing resource group
# - Create address prefixes 10.0.0.0/16
# - Create a frontend subnet
# - Create subnet prefixes 10.0.1.0/24
# - Location should be eastus
#
# - Verify if user has az cli installed, user might be using windows, linux or mac.
# - Verify if az cli is configured
#########################################################

# Variables
RESOURCE_GROUP="rg_2"
LOCATION="eastus"
VNET_NAME="vnet_2"
VNET_ADDRESS_PREFIX="10.0.0.0/16"
FRONTEND_SUBNET_NAME="frontend"
FRONTEND_SUBNET_PREFIX="10.0.1.0/24"

# Check if az cli is installed
if ! command -v az &> /dev/null
then
    echo "az cli could not be found, please install it first."
    exit
fi

# Check if az cli is configured
if ! az account show &> /dev/null
then
    echo "az cli is not configured, please run 'az login' first."
    exit
fi

# Create resource group if it doesn't exist
if ! az group show --name "$RESOURCE_GROUP" &> /dev/null
then
    echo "Resource group '$RESOURCE_GROUP' does not exist. Creating it..."
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
fi

# Create virtual network if it doesn't exist
if ! az network vnet show --name "$VNET_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null
then
    echo "Virtual network '$VNET_NAME' does not exist. Creating it..."
    az network vnet create \
        --name "$VNET_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --address-prefix "$VNET_ADDRESS_PREFIX" \
        --location "$LOCATION"
fi

# Create frontend subnet if it doesn't exist
if ! az network vnet subnet show --name "$FRONTEND_SUBNET_NAME" --vnet-name "$VNET_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null
then
    echo "Frontend subnet '$FRONTEND_SUBNET_NAME' does not exist. Creating it..."
    az network vnet subnet create \
        --name "$FRONTEND_SUBNET_NAME" \
        --vnet-name "$VNET_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --address-prefix "$FRONTEND_SUBNET_PREFIX"
    echo "Frontend subnet '$FRONTEND_SUBNET_NAME' created successfully."
fi
