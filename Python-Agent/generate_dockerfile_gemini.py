import google.generativeai as genai
import os

# Set your API key here
os.environ["GOOGLE_API_KEY"] = "xxxxxxxxxxxxxxxxxxxxxxxx"

# Configure the Gemini model
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-3.6-flash')

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
    response = model.generate_content(prompt.format(language=language))
    return response.text

if __name__ == '__main__':
    language = input("Enter ther programming langauge:")
    dockerfile = generate_dockerfile(language)
    print("\nGenerated Dockerfile:\n")
    print(dockerfile)