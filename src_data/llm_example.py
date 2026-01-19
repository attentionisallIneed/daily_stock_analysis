import openai
import requests
import json
import os

API_KEY = "sk-antigravity"
BASE_URL = "http://127.0.0.1:8045/v1"

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)

models = client.models.list()
all_model_ids = [m.id for m in models.data]
print(f"Available Models (first 10): {all_model_ids[:20]}")

def test_chat():
    print("Testing Chat (Gemini 3 Pro High)...")
    try:
        response = client.chat.completions.create(
            model="gemini-3-pro-high",
            messages=[{"role": "user", "content": "你好，请自我介绍"}],
            stream=False
        )
        print(f"Chat Response: {response.choices[0].message.content}\n")
    except Exception as e:
        print(f"Chat Test Failed: {e}\n")

import base64


def test_image():
    print("Testing Image Generation (Model: gemini-3-pro-image)...")
    try:
        response = client.images.generate(
            model="gemini-3-pro-image",
            prompt="A futuristic city with flying cars, cyberpunk style, high detail, 8k resolution",
            n=1,
            size="1024x1024", 
            response_format="b64_json"
        )
        
        if response.data:
            img_data = response.data[0]
            if getattr(img_data, 'b64_json', None):
                # Save base64 to file
                output_path = "test_scripts/test_image.jpg"
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(img_data.b64_json))
                print(f"Image saved to {output_path}")
            elif hasattr(img_data, 'url') and img_data.url:
               print(f"Image Response URL: {img_data.url}")
            else:
               print(f"Unknown image response data: {img_data}")
        else:
             print("Empty image response data.")

    except Exception as e:
        print(f"Image Test Failed: {e}\n")

# ... (video test stays same, just ensuring indent/context is fine if needed, but replace_content targets specific block)

if __name__ == "__main__":
    test_chat()
    # test_image()