#!/usr/bin/env python3

import json
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import copy
# import boto3
from botocore.config import Config
import time
from loguru import logger
from recursive.memory import caches
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI
import os

# Load environment variables from api_key.env if it exists (try multiple locations)
dotenv_paths = ['api_key.env', '../api_key.env', os.path.join(os.path.dirname(__file__), '../../api_key.env')]
for path in dotenv_paths:
    if os.path.exists(path):
        load_dotenv(dotenv_path=path)
        break

# Also check for temporary environment files passed from the frontend
current_dir = os.path.dirname(os.path.abspath(__file__))
task_env_file = os.environ.get('TASK_ENV_FILE')
if task_env_file and os.path.exists(task_env_file):
    load_dotenv(dotenv_path=task_env_file, override=True)


class OpenAIApiException(Exception):
    def __init__(self, msg, error_code):
        self.msg = msg
        self.error_code = error_code

def format_tool_response_to_claude(tool_response):
    content_claude = []
    for msg_info in tool_response['choices']:
        msg_info = msg_info['message']
        if 'tool_calls' not in msg_info:
            msg_new = {"type": "text", "text": msg_info["content"]}
        else:
            tool_msg = msg_info["tool_calls"][0]
            msg_new = {
                "type": "tool_use", 
                "id": tool_msg["id"], 
                "name": tool_msg["function"]["name"], 
                "input": json.loads(tool_msg["function"]["arguments"])
            }
        content_claude.append(msg_new)
    
    stop_reason = tool_response['choices'][0]['finish_reason']
    if stop_reason == 'tool_calls': stop_reason = 'tool_use'
    response_new = {
        "id": tool_response['id'],
        "type": "message",
        "role": "assistant",
        "model": tool_response['model'],
        "content": content_claude,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": tool_response['usage']
    }
    return response_new



class OpenAIApiProxy():
    def __init__(self, verbose=False):
        # verbose=True dumps full LLM request/response to engine.log (~40KB per call).
        # Keep it False for production; enable temporarily for debugging.
        retry_strategy = Retry(
            total=5,  # Maximum number of retry attempts (including the initial request)
            backoff_factor=2,  # Increased wait time for stability
            status_forcelist=[429, 500, 502, 503, 504],  # List of status codes that require retry
            allowed_methods=["POST"]  # Only retry POST requests
        )
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.MAX_RETRIES = 10  # Reduced from 100 to avoid infinite loops
        self.BACKOFF_FACTOR = 2  # Exponential backoff: 2, 4, 8, 16 seconds
        self.RETRY_CODES = (429, 500, 502, 503, 504)
        self.TIMEOUT = 180  # 3 minutes timeout per request
        self.verbose = verbose
    
    def call_embedding(self, model, text):
        """
        Call an OpenAI-compatible embedding endpoint.
        Model name, API key and base URL can be overridden via environment variables:
        - OPENAI_EMBEDDING_MODEL / model argument
        - OPENAI or OPENAI_EMBEDDING_API_KEY
        - OPENAI_BASE_URL or OPENAI_EMBEDDING_BASE_URL
        text: a single string or a list of strings.
        """
        if isinstance(text, str):
            text = [text]

        model = model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        api_key = os.environ.get("OPENAI_EMBEDDING_API_KEY") or os.environ.get("OPENAI", "")
        base_url = os.environ.get("OPENAI_EMBEDDING_BASE_URL") or os.environ.get("OPENAI_BASE_URL", "")

        if base_url:
            url = base_url.rstrip("/") + "/v1/embeddings"
        else:
            url = "https://api.openai.com/v1/embeddings"

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        params_gpt = {
            "model": model,
            "input": text,
            "encoding_format": "float",
        }

        for attempt in range(self.MAX_RETRIES):
            current_headers = headers.copy()
            try:
                response = self.session.post(
                    url,
                    headers=current_headers,
                    json=params_gpt,
                    timeout=300,
                    proxies=None,
                )
                if response.status_code not in self.RETRY_CODES:
                    response.raise_for_status()
                    break
                else:
                    print(f"Received status code {response.status_code} at attempt {attempt + 1}. Retrying..., the response is {response.text}", flush=True)
            except requests.exceptions.RequestException as e:
                print(f"Error making request (attempt {attempt + 1}): {e}", flush=True)
                if attempt == self.MAX_RETRIES - 1:
                    raise

            if attempt < self.MAX_RETRIES - 1:
                sleep_time = self.BACKOFF_FACTOR
                print(f"Waiting for {sleep_time} seconds before next attempt...", flush=True)
                time.sleep(sleep_time)

        data = response.json()
        return data


    def call(self, model, messages, no_cache = False, overwrite_cache=False, tools=None, temperature=None, headers={}, use_official=None, **kwargs):
        assert tools is None
        messages = copy.deepcopy(messages)
        
        # Check if model name includes openrouter model identifier
        if any(provider in model for provider in ["google/", "anthropic/", "meta/", "mistral/"]):
            use_official = "openrouter"

        is_gpt = True if "gpt" in model or "o1" in model else False
    
        params_gpt = {
            "model": model,
            "messages": messages,
            "max_tokens": 8192,
        }
        
        if "claude" in model:
            use_official = "anthropic"
        
        if self.verbose:
            logger.info("=" * 80)
            logger.info(f"LLM CALL - Model: {model}, Temperature: {temperature}")
            logger.info("Messages: {}".format(json.dumps(messages, ensure_ascii=False, indent=4)))
            logger.info("=" * 80)
        
        if temperature is not None:
            params_gpt["temperature"] = temperature

        if 'o1' in model:
            url = ''
            api_key = ""
            params_gpt["max_tokens"] = 32768
        elif "gpt" in model:
            url = "https://api.openai.com/v1/chat/completions"
            api_key = str(os.getenv('OPENAI'))
        elif "claude" in model:
            url = 'https://api.anthropic.com/v1/messages'
            api_key = str(os.getenv('CLAUDE'))
        elif "nebulacoder" in model:
            # Use the specific API endpoint for NebulaCoder
            url = 'https://nebulacoder-maas.zte.com.cn/v1/chat/completions'
            api_key = os.getenv('NEBULACODER')
            if not api_key or api_key == 'None':
                logger.error("NebulaCoder API key is missing or empty")
                raise ValueError("NebulaCoder API key is required but not provided")

            # Optimize parameters for faster response
            params_gpt["max_tokens"] = 4096  # Reduced from 8192 for faster generation
            params_gpt["stream"] = False  # Disable streaming for batch processing

            # Add custom headers for better performance
            headers['X-Request-Time'] = str(int(time.time()))
            headers['X-Model-Version'] = 'v8.0'
        elif "deepseek" in model:
            url = 'https://api.deepseek.com/v1/chat/completions'
            api_key = os.getenv('DEEPSEEK')
            if not api_key or api_key == 'None':
                logger.error("DeepSeek API key is missing or empty")
                raise ValueError("DeepSeek API key is required but not provided")
        elif use_official == "openrouter" or "openrouter" in model:
            # Use OpenRouter API
            url = "https://openrouter.ai/api/v1/chat/completions"
            api_key = str(os.getenv('OPENROUTER'))
            # Add HTTP-Referer and X-Title headers for OpenRouter
            headers['HTTP-Referer'] = os.getenv('OPENROUTER_REFERER', '')
            headers['X-Title'] = os.getenv('OPENROUTER_TITLE', '')
        elif "gemini" in model:
            # For Gemini, we'll use the Google API directly, not REST API
            api_key = str(os.getenv('GEMINI'))
            genai.configure(api_key=api_key)
            url = None  # Not used for Gemini

        if "o1" in model:
            if "temperature" in params_gpt:
                del params_gpt["temperature"]
        
        headers['Content-Type'] = headers['Content-Type'] if 'Content-Type' in headers else 'application/json'
        headers['Authorization'] = "Bearer " + api_key

        params_gpt.update(kwargs)
        
        
        # Cache
        
        if not no_cache:
            cache_name = "OpenAIApiProxy.call"
            from copy import deepcopy
            call_args_dict = deepcopy(params_gpt)
            llm_cache = caches["llm"]
            if not overwrite_cache:
                cache_result = llm_cache.get_cache(cache_name, call_args_dict)
                if cache_result is not None:
                    return cache_result
        
        if use_official == 'anthropic':
            headers = {
                'content-type': 'application/json',
                'anthropic-version': '2023-06-01',
                'x-api-key': api_key
            }
            if messages[0]['role'] == 'system':
                params_gpt['system'] = messages.pop(0)['content']
        
        # Handle OpenRouter API via official OpenAI client
        if use_official == "openrouter":
            try:
                site_url = os.getenv('OPENROUTER_REFERER', '')
                site_name = os.getenv('OPENROUTER_TITLE', '')
                
                # Initialize OpenAI client with OpenRouter base URL
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                )
                
                # Prepare extra headers
                extra_headers = {}
                if site_url:
                    extra_headers["HTTP-Referer"] = site_url
                if site_name:
                    extra_headers["X-Title"] = site_name
                
                # Create completion
                completion = client.chat.completions.create(
                    extra_headers=extra_headers,
                    model=model,  # e.g. "google/gemini-2.5-pro-preview"
                    messages=messages,
                    temperature=temperature if temperature is not None else 0.7,
                    **kwargs
                )
                
                # Format response to match expected output
                result = [{
                    "message": {
                        "content": completion.choices[0].message.content
                    }
                }]
                
                # Cache if needed
                if not no_cache:
                    llm_cache.save_cache(cache_name, call_args_dict, result)
                
                return result
                
            except Exception as e:
                logger.error(f"Error with OpenRouter API: {e}")
                raise
                
        # Handle Gemini API
        if "gemini" in model:
            try:
                # Process messages for Gemini format
                gemini_messages = []
                system_prompt = None
                
                for msg in messages:
                    role = msg['role']
                    content = msg['content']
                    
                    if role == 'system':
                        system_prompt = content
                    elif role == 'user':
                        gemini_messages.append({"role": "user", "parts": [{"text": content}]})
                    elif role == 'assistant':
                        gemini_messages.append({"role": "model", "parts": [{"text": content}]})
                
                # Set up Gemini model
                generation_config = {}
                if temperature is not None:
                    generation_config["temperature"] = temperature
                
                # Create the model with system instruction if available
                if system_prompt:
                    gemini_model = genai.GenerativeModel(
                        model_name=model,
                        system_instruction=system_prompt,
                        generation_config=generation_config
                    )
                else:
                    gemini_model = genai.GenerativeModel(
                        model_name=model,
                        generation_config=generation_config
                    )
                
                # Start chat and get response
                chat = gemini_model.start_chat(history=gemini_messages[:-1] if gemini_messages else [])
                last_message = gemini_messages[-1]["parts"][0]["text"] if gemini_messages else ""
                response = chat.send_message(last_message)
                
                # Get token usage estimates for Gemini
                # Gemini doesn't provide token counts directly, so we use a rough estimate
                # This is a simplified approach - for production, consider using a proper tokenizer
                input_tokens = sum(len(msg.get("parts", [{}])[0].get("text", "").split()) * 1.3 for msg in gemini_messages)
                output_tokens = len(response.text.split()) * 1.3
                
                # Format response to match what call_llm expects - simple message with content
                result = [{
                    "message": {
                        "content": response.text
                    }
                }]
                
                # Cache if needed
                if not no_cache:
                    llm_cache.save_cache(cache_name, call_args_dict, result)
                
                return result
                
            except Exception as e:
                logger.error(f"Error with Gemini API: {e}")
                raise

        for attempt in range(self.MAX_RETRIES):
            current_headers = headers.copy()
            try:
                # Use longer timeout for slower models like NebulaCoder
                request_timeout = 600 if "nebulacoder" in model else 300

                response = self.session.post(
                    url,
                    headers=current_headers,
                    json=params_gpt,
                    timeout=request_timeout,
                )
                if response.status_code not in self.RETRY_CODES:
                    response.raise_for_status()
                    break  # Successful response, exit the loop
                else:
                    if "maximum context length is" in str(response.text) or "maximum length" in str(response.text):
                        logger.error("Error Process {} with the maximum context length exceeds. Sys messages is {}".format(model, messages[0]))
                        # just return None
                        return None

                    logger.warning(f"Received status code {response.status_code} at attempt={attempt + 1}. Response: {response.text[:200]}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error making request (attempt {attempt + 1}): {e}")
                if attempt == self.MAX_RETRIES - 1:  # Last attempt
                    raise  # Re-raise the last exception if all attempts fail

            # Optimized backoff strategy
            if attempt < self.MAX_RETRIES - 1:
                # Gentler backoff for slow models to avoid overwhelming the server
                base_backoff = 3.0 if "nebulacoder" in model else 1.0
                sleep_time = base_backoff * (1.5 ** attempt)
                logger.info(f"Retry wait: {sleep_time:.1f}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                time.sleep(sleep_time)

        # Validate response
        if not response or not response.text:
            logger.error(f"Empty response from {model} after {self.MAX_RETRIES} attempts")
            raise RuntimeError(f"API returned empty response after {self.MAX_RETRIES} retries")

        try:
            if not response.text or not response.text.strip():
                logger.error(f"Empty response body from {model} (status={response.status_code})")
                raise RuntimeError(f"API returned empty body (status={response.status_code})")
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON response from {model}: {e}")
            logger.error(f"Response text (first 500 chars): {response.text[:500]}")
            raise RuntimeError(f"API returned invalid JSON from {model}: {e}")
        
        if self.verbose:
            logger.info("Response: {}".format(json.dumps(data, ensure_ascii=False, indent=4)))
    
        input_tokens_key = 'prompt_tokens' if is_gpt else 'input_tokens'
        output_tokens_key = 'completion_tokens' if is_gpt else 'output_tokens'
        output_reason_tokens = data.get('usage', {}).get('completion_tokens_details', {}).get('reasoning_tokens', 0)
        if self.verbose:
            logger.info("=" * 80)
            logger.info(f"LLM RESPONSE - Model: {model}")
            logger.info("Response: {}".format(json.dumps(data, ensure_ascii=False, indent=4)[:2000]))
            logger.info("Usage: {}".format(data.get('usage', {})))
            logger.info("=" * 80)
        if input_tokens_key in data.get('usage', {}) and output_tokens_key in data.get('usage', {}):
            input_tokens = data.get('usage', {})[input_tokens_key]
            output_tokens = data.get('usage', {})[output_tokens_key]
            if model == "gpt-4o":
                ip = 2.50
                op = 10.00
            elif model == "gpt-4o-mini":
                ip = 0.150
                op = 0.600 
            elif "claude" in model:
                ip = 3.0
                op = 15.0
            elif "r1" in model:
                ip = 0.55
                op = 2.19
            elif "gemini" in model:
                ip = 0.25  # Gemini Pro prices (per million tokens)
                op = 0.75
            elif "nebulacoder" in model:
                ip = 0.0
                op = 0.0
            elif "deepseek" in model:
                # DeepSeek-V4 pricing (approximate, per million tokens)
                ip = 0.27  # Input tokens
                op = 1.10  # Output tokens
            else:
                ip = 0.0
                op = 0.0
                
            price = (input_tokens / 1000000) * ip + (output_tokens / 1000000) * op
            
            # if self.verbose:
            logger.debug("{} input data {}, output_data {} LLM price: {}\n\n".format(model, input_tokens, output_tokens, price))
                # ))
        if use_official == "anthropic":
            result = data["content"][0]["text"]
            # make the format consistent
            data = [{"message": {"content": result}}]
            if not no_cache:
                llm_cache.save_cache(cache_name, call_args_dict, data)
            return data

        if 'choices' not in data:
            raise RuntimeError(f"No 'choices' in response: {data}. Possibly, the API key is invalid.")

        if not no_cache:
            llm_cache.save_cache(cache_name, call_args_dict, data['choices'])
        return data['choices']


if __name__ == "__main__":
    proxy = OpenAIApiProxy()
    proxy.call_embedding("text-embedding-3-small",
                         "I am")