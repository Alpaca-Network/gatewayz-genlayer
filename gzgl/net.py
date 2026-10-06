"""Network + key loading shared by the scripts. Keys come from the env file named by
GZGL_ENV (default ~/.gatewayz-genlayer-testnet.env) — never from the repo."""

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(os.environ.get("GZGL_ENV", Path.home() / ".gatewayz-genlayer-testnet.env"))
load_dotenv(ENV_FILE)

FUJI_RPC = os.environ.get("FUJI_RPC", "https://api.avax-test.network/ext/bc/C/rpc")
FUJI_CHAIN_ID = 43113
DEPLOYMENTS = Path(os.environ.get("GZGL_DEPLOYMENTS", Path(__file__).resolve().parents[1] / "deployments"))


def key(role: str) -> str:
    k = os.environ.get(f"{role}_PRIVATE_KEY")
    if not k:
        raise SystemExit(f"{role}_PRIVATE_KEY missing — expected in {ENV_FILE}")
    return k


def genlayer_client(network: str, role: str = "OPERATOR"):
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import localnet, studionet, testnet_bradbury

    chains = {"localnet": localnet, "studionet": studionet, "bradbury": testnet_bradbury}
    if network not in chains:
        raise SystemExit(f"unknown GenLayer network {network}; pick one of {sorted(chains)}")
    return create_client(chain=chains[network], account=create_account(key(role)))


def fuji():
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(FUJI_RPC))
    if w3.eth.chain_id != FUJI_CHAIN_ID:
        raise SystemExit(f"{FUJI_RPC} is chain {w3.eth.chain_id}, expected Fuji {FUJI_CHAIN_ID}")
    return w3
