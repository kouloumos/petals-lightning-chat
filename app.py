import hivemind
from flask import Flask
from flask_cors import CORS
from flask_sock import Sock
from transformers import AutoTokenizer

from petals import AutoDistributedModelForCausalLM

import config
from state_updater import StateUpdaterThread

logger = hivemind.get_logger(__file__)

logger.info("Connecting to DHT")
dht = hivemind.DHT(initial_peers=config.INITIAL_PEERS, client_mode=False, num_workers=32, start=True)

models = {}
for model_info in config.MODELS:
    logger.info(f"Loading tokenizer for {model_info.repo}")
    tokenizer = AutoTokenizer.from_pretrained(model_info.repo, add_bos_token=False, use_fast=False)

    logger.info(f"Loading model {model_info.repo} with adapter {model_info.adapter} and dtype {config.TORCH_DTYPE}")
    # We set use_fast=False since LlamaTokenizerFast takes a long time to init
    model = AutoDistributedModelForCausalLM.from_pretrained(
        model_info.repo,
        active_adapter=model_info.adapter,
        torch_dtype=config.TORCH_DTYPE,
        initial_peers=config.INITIAL_PEERS,
        max_retries=3,
    )
    model = model.to(config.DEVICE)

    model_name = model_info.adapter if model_info.adapter is not None else model_info.repo
    models[model_name] = model, tokenizer

logger.info("Starting Flask app")
app = Flask(__name__)
CORS(app)
app.config['SOCK_SERVER_OPTIONS'] = {'ping_interval': 25}
sock = Sock(app)

logger.info("Starting updater")
updater = StateUpdaterThread(dht, app, daemon=True)
updater.start()
updater.ready.wait()

@app.route("/")
def main_page():
    return updater.last_state


import http_api
import websocket_api
