#!/bin/bash

#########################################################
# Description: Create or tear down a VNet in Azure
# Usage: azure_vnet_create_terdown.sh {create|teardown}
#
# create   - Create resource group (if missing), VNet, and frontend subnet
# teardown - Delete the VNet (and its subnets) if it exists
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

ACTION="$1"

usage() {
    echo "Wrong parameter passed. Usage: $0 {create|teardown}"
    exit 1
}

if [[ -z "$ACTION" ]]; then
    usage
fi

# Check if az cli is installed
if ! command -v az &> /dev/null
then
    echo "az cli could not be found, please install it first."
    exit 1
fi

# Check if az cli is configured
if ! az account show &> /dev/null
then
    echo "az cli is not configured, please run 'az login' first."
    exit 1
fi

create_vnet() {
    # Create resource group if it doesn't exist
    if ! az group show --name "$RESOURCE_GROUP" &> /dev/null
    then
        echo "Resource group '$RESOURCE_GROUP' does not exist. Creating it..."
        if ! az group create --name "$RESOURCE_GROUP" --location "$LOCATION"; then
            echo "Failed to create resource group '$RESOURCE_GROUP'."
            exit 1
        fi
    fi

    # Create virtual network if it doesn't exist
    if ! az network vnet show --name "$VNET_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null
    then
        echo "Virtual network '$VNET_NAME' does not exist. Creating it..."
        if ! az network vnet create \
            --name "$VNET_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --address-prefix "$VNET_ADDRESS_PREFIX" \
            --location "$LOCATION"; then
            echo "Failed to create virtual network '$VNET_NAME'."
            exit 1
        fi
    fi

    # Create frontend subnet if it doesn't exist
    if ! az network vnet subnet show --name "$FRONTEND_SUBNET_NAME" --vnet-name "$VNET_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null
    then
        echo "Frontend subnet '$FRONTEND_SUBNET_NAME' does not exist. Creating it..."
        if ! az network vnet subnet create \
            --name "$FRONTEND_SUBNET_NAME" \
            --vnet-name "$VNET_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --address-prefix "$FRONTEND_SUBNET_PREFIX"; then
            echo "Failed to create frontend subnet '$FRONTEND_SUBNET_NAME'."
            exit 1
        fi
    fi

    echo "VNet '$VNET_NAME' and subnet '$FRONTEND_SUBNET_NAME' are ready."
}

teardown_vnet() {
    if ! az network vnet show --name "$VNET_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null
    then
        echo "Virtual network '$VNET_NAME' does not exist. Nothing to remove."
        exit 0
    fi

    echo "Deleting virtual network '$VNET_NAME' (and its subnets)..."
    if ! az network vnet delete --name "$VNET_NAME" --resource-group "$RESOURCE_GROUP"; then
        echo "Failed to delete virtual network '$VNET_NAME'."
        exit 1
    fi

    echo "VNet '$VNET_NAME' removed successfully."
}

case "$ACTION" in
    create)
        create_vnet
        ;;
    teardown)
        teardown_vnet
        ;;
    *)
        usage
        ;;
esac
