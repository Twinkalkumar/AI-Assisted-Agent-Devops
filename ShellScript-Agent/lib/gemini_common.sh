#!/bin/bash

#########################################################
# Shared helpers for Gemini-backed generator scripts.
# Meant to be sourced, not executed directly.
#########################################################

MODEL="gemini-3.6-flash"
API_URL="https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent"

install_jq() {
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y jq
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y jq
    elif command -v yum &> /dev/null; then
        sudo yum install -y jq
    elif command -v brew &> /dev/null; then
        brew install jq
    elif command -v apk &> /dev/null; then
        sudo apk add jq
    else
        echo "Could not detect a supported package manager (apt-get, dnf, yum, brew, apk) to install jq automatically."
        return 1
    fi
}

ensure_dependencies() {
    if ! command -v curl &> /dev/null
    then
        echo "curl could not be found, please install it first."
        exit 1
    fi

    if ! command -v jq &> /dev/null
    then
        echo "jq could not be found. Attempting to install it..."
        if ! install_jq || ! command -v jq &> /dev/null
        then
            echo "Failed to install jq automatically. Please install it manually."
            exit 1
        fi
        echo "jq installed successfully."
    fi
}

ensure_api_key() {
    if [[ -z "$GOOGLE_API_KEY" ]]; then
        read -rsp "GOOGLE_API_KEY is not set. Please enter your Google API key: " GOOGLE_API_KEY
        echo
        export GOOGLE_API_KEY

        if [[ -z "$GOOGLE_API_KEY" ]]; then
            echo "No API key provided, exiting."
            exit 1
        fi
    fi
}

call_gemini_api() {
    local prompt="$1"

    local payload
    payload=$(jq -n --arg text "$prompt" '{contents: [{parts: [{text: $text}]}]}')

    local response
    response=$(curl -s -X POST "${API_URL}?key=${GOOGLE_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$payload")

    echo "$response" | jq -r '.candidates[0].content.parts[0].text // "Error generating content. Response: \(.)"'
}
