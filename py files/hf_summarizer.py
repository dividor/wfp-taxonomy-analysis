import os
import requests
import time

# from transformers import AutoTokenizer

MODEL_NAME = 'meta-llama/Llama-3.1-8B-Instruct:novita'
# tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
API_URL = "https://router.huggingface.co/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {os.environ['HF_TOKEN']}",
    "Content-Type": "application/json",
}

SUMMARY_PROMPT_TEMPLATE = (
    "Rewrite the following representative sentences into a single, coherent abstract written as one paragraph "
    "Clearly state the evaluation objective, methodology, key findings, and implications. "
    "Do not add new information or interpretation. "
    "Use clear, professional humanitarian evaluation language.\n\n"
    "{text}"
)


class HFSummarizer:
    def __init__(self,
                 model_url="https://router.huggingface.co/hf-inference/models/facebook/bart-large-cnn",
                 max_length=250,
                 min_length=80,
                 retries=3,
                 sleep_time=3):

        self.api_url = model_url
        self.headers = {
            "Authorization": f"Bearer {os.environ.get('HF_TOKEN')}"
        }
        self.max_length = max_length
        self.min_length = min_length
        self.retries = retries
        self.sleep_time = sleep_time

    
    def chunk_by_tokens(self, text, max_tokens=900):
        tokens = tokenizer.encode(text, truncation=False)
        for i in range(0, len(tokens), max_tokens):
            yield tokenizer.decode(
                tokens[i:i + max_tokens],
                skip_special_tokens=True
            )

    import time

    def call_llm(self, payload, headers, retries=3):
        for attempt in range(retries):
            r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
    
            if r.status_code in (429, 503):
                wait = 5 * (attempt + 1)
                time.sleep(wait)
                continue
    
            raise Exception(f"HF API Error: {r.status_code}, {r.text}")
    
        raise Exception("Max retries exceeded")



    def summarize_text(self, text, max_tokens=400):

        if not isinstance(text, str) or len(text.strip()) < 50:
            return ""
    
        prompt = SUMMARY_PROMPT_TEMPLATE.format(text=text)
    
        payload = {
            "model": "meta-llama/Llama-3.1-8B-Instruct:novita",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
    
        API_URL = "https://router.huggingface.co/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.environ.get('HF_TOKEN')}",
            "Content-Type": "application/json",
        }

        
        response = self.call_llm(payload, headers)

        return response


    def summarize_sentences(self, sentences):

        # Case 1: sentences accidentally passed as a string
        if isinstance(sentences, str):
            text = sentences
    
        # Case 2: sentences is a list
        elif isinstance(sentences, list):
    
            # Fix character-tokenized sentences
            cleaned = []
            for s in sentences:
                if isinstance(s, str):
                    # collapse character-level spacing
                    cleaned.append("".join(s.split()))
                else:
                    raise TypeError(f"Unexpected sentence type: {type(s)}")
    
            text = " ".join(cleaned)
    
        else:
            raise TypeError(f"Unexpected input type: {type(sentences)}")

        
        return self.summarize_text(text)
