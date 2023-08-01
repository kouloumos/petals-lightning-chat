from traceback import format_exc
import requests
import os

import hivemind
from flask import jsonify, request

import config
from app import app, models
from utils import safe_decode

API_KEY = os.getenv("API_KEY")
logger = hivemind.get_logger(__file__)

@app.get("/api/v1/split")
def request_split_payments():
    try:
        servers = ["...EZzF2U", "...u3icPG"]
        data = app.config.get("peer_data")
        print(data)
        total_amount = 10
        lightning_addresses = [{ server: data[server]} for server in servers]
        url = 'https://splitsats--kouloumos.repl.co/processData' 
        # url = 'http://localhost:3000/processData' 
        data = {
            'amount': total_amount,
            'servers': lightning_addresses
        }
        headers = {
            'x-api-key': API_KEY
        }
        response = requests.post(url, json=data, headers=headers)
        print(response)
        return response.json()
    except Exception:
        return jsonify(ok=False, traceback=format_exc())
    
@app.post("/api/v1/generate")
def http_api_generate():
    try:
        
        req_data = request.get_json()
        print(req_data)
        # request.get_data()
        model_name = get_typed_arg("model", str, config.DEFAULT_MODEL_NAME)
        inputs = req_data.get("inputs")
        do_sample = get_typed_arg("do_sample", int, 0)
        temperature = get_typed_arg("temperature", float, 1.0)
        top_k = get_typed_arg("top_k", int)
        top_p = get_typed_arg("top_p", float)
        max_length = get_typed_arg("max_length", int)
        max_new_tokens = get_typed_arg("max_new_tokens", int)
        session_id = req_data.get("session_id")
        logger.info(f"generate(), model={repr(model_name)}, inputs={repr(inputs)}")
        if session_id is not None:
            raise RuntimeError(
                "Reusing inference sessions was removed from HTTP API, please use WebSocket API instead"
            )

        model, tokenizer = models[model_name]

        if inputs is not None:
            inputs = tokenizer(inputs, return_tensors="pt")["input_ids"].to(config.DEVICE)
            n_input_tokens = inputs.shape[1]
        else:
            n_input_tokens = 0

        outputs = model.generate(
            inputs=inputs,
            do_sample=do_sample,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            max_length=max_length,
            max_new_tokens=max_new_tokens,
        )
        outputs = safe_decode(tokenizer, outputs[0, n_input_tokens:])
        logger.info(f"generate(), outputs={repr(outputs)}")

        return jsonify(ok=True, outputs=outputs)
    except Exception:
        return jsonify(ok=False, traceback=format_exc())


def get_typed_arg(name, expected_type, default=None):
    value = request.get_json().get(name)
    return expected_type(value) if value is not None else default
