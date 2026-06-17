import sys
import os
import google.generativeai as genai
import ollama
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

GOOGLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview"
]

OLLAMA_MODELS = [
    "llama3.1",
    "phi3",
    "deepseek-r1:1.5b"
]

def prompt_model(model: str, prompt: str) -> str:
    try:
        if model in GOOGLE_MODELS:
            gemini = genai.GenerativeModel(model)
            response = gemini.generate_content(prompt)
            return response.text

        elif model in OLLAMA_MODELS:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response['message']['content']

        else:
            return f"Error: Model '{model}' is not recognized."

    except Exception as e:
        return f"[Gemini Error] {str(e)}"  


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: uv run prompt_model.py <model> <prompt>")
        sys.exit(1)

    model = sys.argv[1]
    prompt = sys.argv[2]

    print("\n--- RESPONSE ---\n")
    print(prompt_model(model, prompt))