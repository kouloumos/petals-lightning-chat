import json
import requests
import os
from traceback import format_exc

import flask_sock
import hivemind
import torch
import bolt11

import config
from app import app, sock, models
from utils import safe_decode
from auth import validL402AuthHeader, generate_macaroon, getLnCallback

logger = hivemind.get_logger(__file__)

API_KEY = os.getenv("API_KEY")
# the main address in which  the swarm is getting paid
# and from which the sats are distributed in the next step
lnAddress =  os.getenv("SWARM_LN_ADDRESS") 
lnCallback = getLnCallback(lnAddress, "")

# price based on together.ai prices ($0.015 per 1k tokens used)
price_for_1k_tokens = 50 # sats per 1k tokens

def request_split_payments(total_amount, servers):
    try:
        print(f"Payment of {total_amount} sats split between {servers}")
        data = app.config.get("peer_data")
        lightning_addresses = [{ server: data[server]} for server in servers]
        url = 'https://splitsats--kouloumos.repl.co/processData'
        data = {
            'amount': total_amount,
            'servers': lightning_addresses
        }
        headers = {
            'x-api-key': API_KEY
        }
        response = requests.post(url, json=data, headers=headers)
        print(response.json())
        if (response.json().status == "success"):
            return True
        else:
            return False
    except Exception:
        return False

@sock.route("/api/v2/generate")
def ws_api_generate(ws):
    try:
        request = json.loads(ws.receive(timeout=config.STEP_TIMEOUT))
        assert request["type"] == "open_inference_session"
        model_name = request.get("model")
        if model_name is None:
            model_name = config.DEFAULT_MODEL_NAME
        logger.info(f"ws.generate.open(), model={repr(model_name)}, max_length={repr(request['max_length'])}")

        model, tokenizer = models[model_name]

        with model.inference_session(max_length=request["max_length"]) as session:
            ws.send(json.dumps({"ok": True}))

            while True:
                request = json.loads(ws.receive(timeout=config.STEP_TIMEOUT))
                assert request["type"] == "generate"

                inputs = request.get("inputs")
                logger.info(f"Received inputs={repr(inputs)}")
                if inputs is not None:
                    inputs = tokenizer(inputs, return_tensors="pt")["input_ids"].to(config.DEVICE)
                    n_input_tokens = inputs.shape[1]
                else:
                    n_input_tokens = 0
                # check for payment
                auth_header = request.get("authorization")
                if auth_header and validL402AuthHeader(auth_header):
                    logger.info(f"Valid payment included")
                    logger.info(f"ws.generate.step()")
                    stop_sequence = request.get("stop_sequence")
                    extra_stop_sequences = request.get("extra_stop_sequences")
                    if extra_stop_sequences is not None:
                        cont_token = tokenizer(stop_sequence, return_tensors="pt")["input_ids"].to(config.DEVICE)
                        assert cont_token.shape == (1, 1), \
                            "extra_stop_sequences require stop_sequence length to be exactly 1 token"

                    all_outputs = ''
                    delta_q = []
                    stop = False
                    while not stop:
                        peer_ids = [f"...{str(peer.span.peer_id)[-6:]}" for peer in session._server_sessions]
                        outputs = model.generate(
                            inputs=inputs,
                            do_sample=request.get("do_sample", False),
                            temperature=request.get("temperature", 1.0),
                            top_k=request.get("top_k"),
                            top_p=request.get("top_p"),
                            max_length=request.get("max_length"),
                            max_new_tokens=request.get("max_new_tokens"),
                            session=session,
                        )
                        delta = outputs[0, n_input_tokens:].tolist()
                        outputs = safe_decode(tokenizer, torch.Tensor(delta_q + delta))
                        inputs = None  # Inputs are passed only for the 1st token of the bot's response
                        n_input_tokens = 0 
                        combined = all_outputs + outputs
                        stop = stop_sequence is None or combined.endswith(stop_sequence)
                        if extra_stop_sequences is not None:
                            for seq in extra_stop_sequences:
                                if combined.endswith(seq):
                                    stop = True
                                    session.last_token_id = cont_token
                        if not stop and outputs[-10:].find(u'\ufffd') > -1:
                            # If there's a replacement character, keep getting more tokens
                            # until we can decode properly
                            delta_q = delta_q + delta
                            logger.info(f"ws.generate.append_retry(), all_outputs={repr(combined)}")
                        else:
                            all_outputs = combined
                            delta_q = []
                            # logger.info(f"ws.generate.step(), all_outputs={repr(all_outputs)}, stop={stop}")
                            ws.send(json.dumps({"ok": True, "outputs": outputs, "stop": stop, "peers": peer_ids}))
                    # split payment
                    request_split_payments(amount_sats, peer_ids)
                else:
                    amount_sats = 8
                    logger.info(f"Payment for {amount_sats} sats required, responding with request")
                    # get invoice
                    # print(f"Getting invoice for {amount_sats} sats...")
                    invoice = requests.get(f'{lnCallback}?amount={amount_sats * 1000}&comment=petals chat service').json()["pr"]
                    payment_hash = bolt11.decode(invoice).tags["p"]
                    macaroon = generate_macaroon(payment_hash)
                    # print(f"Generated macaroon: {macaroon}")
                    # print("Responding with 402 Payment Required.")
                    ws.send(json.dumps({"ok": False, "invoice": invoice, "macaroon": macaroon, "status_code": 402}))
    except flask_sock.ConnectionClosed:
        pass
    except Exception:
        logger.warning("ws.generate failed:", exc_info=True)
        ws.send(json.dumps({"ok": False, "traceback": format_exc()}))
    finally:
        logger.info(f"ws.generate.close()")
