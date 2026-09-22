import ollama

PROMPT = """
Only Generate an ideal dockerfile for {language} with best prectices. Do not provide any description
include:
- base image 
- installing dependencies
- setting working directory
- adding source code
- running the application
"""

def generate_dockerfile(language):
    response = ollama.chat(model='llama3.2:1b',messages=[{'role': 'user', 'content': PROMPT.format(language=language)}])
    return response['message']['content']

if __name__ == '__main__':
    language = input("Enter ther programming langauge:")
    dockerfile = generate_dockerfile(language)
    print("\nGenerated Dockerfile:\n")
    print(dockerfile)