# code from https://replit.com/@Fedi/AI4ALL-Hackathon
import hashlib
import os
from pymacaroons import Macaroon, Verifier
import requests


MACAROON_SECRET_KEY = os.getenv("MACAROON_SECRET_KEY")

def generate_macaroon(payment_hash):
    # TODO: commit to the hash of the request
    m = Macaroon(location='cool-picture-service.example.com',
                 identifier='version=0',
                 key=MACAROON_SECRET_KEY)
    m.add_first_party_caveat(f'payment_hash={payment_hash}')
    return m.serialize()


def decode_macaroon(macaroon):
    m = Macaroon.deserialize(macaroon)
    invoice = None
    for c in m.caveats:
        if c.caveat_id.startswith('payment_hash='):
            invoice = c.caveat_id[len('payment_hash='):]
    return invoice


def validL402AuthHeader(auth_header):
    if "L402" in auth_header:
        parts = auth_header.split(" ")
        if len(parts) == 2 and ":" in parts[1]:
            macaroon, preimage = parts[1].split(":")
            macaroon = macaroon.replace("macaroon=", "")
            try:
                payment_hash_in_macaroon = decode_macaroon(macaroon)
                # print("payment_hash_in_macaroon:", payment_hash_in_macaroon)
                hashed_preimage = hashlib.sha256(
                    bytes.fromhex(preimage)).hexdigest()
                # print("hashed_preimage:", hashed_preimage)
                if hashed_preimage != payment_hash_in_macaroon:
                    print("Preimage doesn't match payment hash")
                    return False

                m = Macaroon.deserialize(macaroon)

                # Define the function that verifies the caveat
                def caveat_verifier(predicate):
                    return predicate == f'payment_hash={hashed_preimage}'

                # Define the verifier and satisfy the caveat verifier
                v = Verifier()
                v.satisfy_general(caveat_verifier)

                # Verification of the macaroon
                verified = v.verify(m, MACAROON_SECRET_KEY)

                if verified:
                    # print("Valid macaroon")
                    return True
                else:
                    print("Macaroon was tampered or all caveats were not met")
                    return False

            except Exception as e:
                print("Exception:", e)
                print("Failed to verify macaroon")
                return False

    return False

def getLnCallback(lnAddress, s = "s"):
    # split username@domain into username and domain
    username, domain = lnAddress.split('@')
    # construct the lnurl payment request
    res = f'http{s}://{domain}/.well-known/lnurlp/{username}'
    try:
        callback = requests.get(res).json()['callback']
        return callback
    except:
        return None
