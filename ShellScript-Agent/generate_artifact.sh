#!/bin/bash

#########################################################
# Description: Generic entrypoint that generates config
# artifacts (Dockerfile, Kubernetes YAML, ...) using the
# Google Gemini API. Prompt templates live in ./prompts/
# as *.prompt files - add a new file there to support a
# new artifact type, no script changes needed.
#########################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPTS_DIR="${SCRIPT_DIR}/prompts"

# shellcheck source=lib/gemini_common.sh
source "${SCRIPT_DIR}/lib/gemini_common.sh"

ensure_dependencies
ensure_api_key

prompt_files=("${PROMPTS_DIR}"/*.prompt)

if [[ ! -e "${prompt_files[0]}" ]]; then
    echo "No prompt templates found in ${PROMPTS_DIR}"
    exit 1
fi

echo "Select an artifact type to generate:"
select prompt_file in "${prompt_files[@]##*/}"; do
    if [[ -n "$prompt_file" ]]; then
        break
    fi
    echo "Invalid selection, please try again."
done

artifact_type="${prompt_file%.prompt}"
template=$(<"${PROMPTS_DIR}/${prompt_file}")

read -rp "Enter the input for '${artifact_type}': " USER_INPUT

final_prompt=$(printf "$template" "$USER_INPUT")

echo -e "\nGenerated ${artifact_type}:\n"
call_gemini_api "$final_prompt"
