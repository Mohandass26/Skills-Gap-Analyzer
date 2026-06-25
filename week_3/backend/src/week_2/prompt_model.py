import os
import sys
import ollama
from google import genai
from dotenv import load_dotenv

load_dotenv()

SECRET_PATH = "/run/secrets/gemini_api_key"
if os.path.exists(SECRET_PATH):
    with open(SECRET_PATH, "r", encoding="utf-8") as f:
        os.environ["GEMINI_API_KEY"] = f.read().strip()

ollama_client = ollama.Client()
gemini_client = None


def get_gemini_client():
    global gemini_client
    if gemini_client is None:
        gemini_client = genai.Client()  # reads GEMINI_API_KEY (or GOOGLE_API_KEY) from env
    return gemini_client


OLLAMA_MODELS = {
    "llama3.1",
    "phi3",
    "deepseek-r1:1.5b",
    "gemma3:1b",
}

GEMINI_MODELS = {
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
}


def prompt_model(llm_model: str, prompt: str) -> str | None:
    llm_model = llm_model.strip()
    prompt = prompt.strip()

    if not llm_model or not prompt:
        print("Error: <model> and <prompt> cannot be empty.")
        return None

    try:
        if llm_model in OLLAMA_MODELS:
            response = ollama_client.generate(
                model=llm_model,
                prompt=prompt,
            )
            return response.response

        elif llm_model in GEMINI_MODELS:
            client = get_gemini_client()
            response = client.models.generate_content(
                model=llm_model,
                contents=prompt,
            )
            return response.text

        else:
            return (
                f"[Error] Unknown model: '{llm_model}'. Supported models: "
                f"{sorted(OLLAMA_MODELS | GEMINI_MODELS)}"
            )

    except Exception as e:
        return f"[{llm_model} Error] {e}"


def main():
    if len(sys.argv) != 3:
        print("Usage: python prompt_model.py <model> <prompt>")
        print(f"Ollama models : {sorted(OLLAMA_MODELS)}")
        print(f"Gemini models : {sorted(GEMINI_MODELS)}")
        sys.exit(1)

    response = prompt_model(sys.argv[1], sys.argv[2])
    if response is not None:
        print("\n--- RESPONSE ---\n")
        print(response)


if __name__ == "__main__":
    main()