import os
import json
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
load_dotenv()
def query_llm(prompt: str, image_base64: str = None) -> str:
    """
    Sends a prompt (and optional base64 image) to the Hugging Face API.
    Replaces the local Ollama usage.
    """
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN environment variable not set. Please set it to your Hugging Face Access Token.")

    # Using the standard official model ID for Qwen2.5-VL-7B
    model_id = "Qwen/Qwen2.5-VL-7B-Instruct"
    
    client = InferenceClient(api_key=token)
    
    # Build the message content list
    content = []
    
    # Qwen-VL expects standard multimodal message format
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
        })
        
    content.append({
        "type": "text",
        "text": prompt
    })
    
    messages = [
        {
            "role": "user",
            "content": content
        }
    ]
    
    try:
        print(f"\\n[{'='*40}]")
        print(f"[DEBUG LLM] Attempting connection to Hugging Face API...")
        print(f"[DEBUG LLM] Target Host: api-inference.huggingface.co")
        
        import socket
        try:
            ip = socket.gethostbyname('api-inference.huggingface.co')
            print(f"[DEBUG LLM] DNS Resolution Success! IP: {ip}")
        except Exception as dns_e:
            print(f"[DEBUG LLM] DNS RESOLUTION FAILED FOR 'api-inference.huggingface.co'!")
            print(f"[DEBUG LLM] DNS Error Details: {dns_e}")
            print(f"[DEBUG LLM] Note: If DNS fails here, the following HTTP request is guaranteed to fail.")
        
        print(f"[{'='*40}]\\n")

        # We increase max_tokens slightly just to be safe for large JSON outputs
        response = client.chat_completion(
            model=model_id,
            messages=messages,
            max_tokens=4096, 
            temperature=0.1 # Keep temperature low for deterministic JSON/analysis
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error querying Hugging Face API: {e}")
        # Return a fallback string that won't crash the JSON parsers upstream
        return f'{{"error": "HF API Request Failed", "details": "{str(e)}" }}'
