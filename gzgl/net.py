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
    client = create_client(chain=chains[network], account=create_account(key(role)))
    _hex_chain_id_in_gas_estimates(client)
    return client


def _hex_chain_id_in_gas_estimates(client) -> None:
    """genlayer-py 0.19.1 puts `chainId` into eth_estimateGas as a plain int. Studio accepts
    that; Bradbury's node rejects every write and deploy with `cannot unmarshal non-string
    into Go struct field TransactionArgs.chainId of type *hexutil.Big`. Send it as hex.
    Remove once genlayer-py does (contracts/actions.py::_prepare_transaction)."""
    make_request = client.provider.make_request

    def patched(method, params, *args, **kwargs):
        if method == "eth_estimateGas" and params and isinstance(params[0], dict):
            chain_id = params[0].get("chainId")
            if isinstance(chain_id, int):
                params = [dict(params[0], chainId=hex(chain_id)), *params[1:]]
        return make_request(method, params, *args, **kwargs)

    client.provider.make_request = patched


# ------------------------------------------------------------ GenLayer writes (consensus v0.6)
#
# Since consensus v0.6 a write or deploy must carry a fees distribution, and the sender pays it
# from its balance: without one the consensus contract reverts with FeesDistributionMissing.
# genlayer-py 0.19 also replaced `status_name` with a `lifecycle` object. Every script goes
# through the helpers below so that this lives in one place.

STUDIO_TOP_UP = 10 * 10**18  # test GEN, minted free by sim_fundAccount on Studio networks
DECIDED = {"accepted": "ACCEPTED", "undetermined": "UNDETERMINED", "validators_timeout": "VALIDATORS_TIMEOUT",
           "leader_timeout": "LEADER_TIMEOUT"}


class GenLayerTxError(RuntimeError):
    """The transaction reached consensus but did not do what was asked."""


def gl_status(tx: dict) -> str:
    """Consensus status under the protocol's names (PENDING .. ACCEPTED, FINALIZED, CANCELED)."""
    if tx.get("status_name"):  # genlayer-py <= 0.18
        return str(tx["status_name"])
    lc = tx.get("lifecycle")
    if not isinstance(lc, dict):
        return "PENDING"
    state = lc.get("state")
    if state == "processing":
        phase = str(lc.get("phase") or "pending").upper()
        return "PENDING" if phase == "UNINITIALIZED" else phase
    if state == "decided":
        return DECIDED.get(str(lc.get("outcome")), "UNDETERMINED")
    return {"finalized": "FINALIZED", "canceled": "CANCELED"}.get(str(state), "PENDING")


def gl_rollback(tx: dict) -> str | None:
    """The contract's error code when the leader's execution rolled back, else None."""
    try:
        receipt = tx["consensus_data"]["leader_receipt"]
        res = (receipt[0] if isinstance(receipt, list) else receipt)["result"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(res, dict) or res.get("status") != "rollback":
        return None
    return str(res.get("payload") or "contract_error")


def _is_studio(client) -> bool:
    from genlayer_py.chains.utils import is_studio_chain

    return is_studio_chain(client.chain)


def _fees(client, estimate: dict) -> dict:
    fees = {"distribution": estimate["distribution"], "feeValue": int(estimate["feeValue"])}
    if estimate.get("messageAllocations"):
        fees["messageAllocations"] = estimate["messageAllocations"]
    if _is_studio(client):
        address = client.local_account.address
        if client.w3.eth.get_balance(address) < 2 * fees["feeValue"]:
            client.fund_account(address, STUDIO_TOP_UP)
    return fees  # on real testnets the account is funded from the faucet


def gl_write(client, address: str, function_name: str, args: list) -> str:
    """write_contract with fees attached. Returns the transaction hash as 0x hex."""
    call = {"address": address, "function_name": function_name, "args": args}
    estimate = None
    if _is_studio(client):
        try:  # Studio simulates this exact call and returns the budget to attach
            estimate = client.estimate_transaction_fees_for_write(**call)
        except Exception:  # noqa: BLE001 - e.g. the call would roll back; the write will say why
            estimate = None
    if estimate is None:
        estimate = client.estimate_transaction_fees({})
    return _hex(client.write_contract(**call, fees=_fees(client, estimate)))


def gl_deploy(client, code: str, args: list) -> str:
    """deploy_contract with fees attached. Returns the transaction hash as 0x hex."""
    return _hex(client.deploy_contract(code=code, args=args,
                                       fees=_fees(client, client.estimate_transaction_fees({}))))


def gl_wait(client, tx: str, finalized: bool = False, retries: int = 200, interval: int | None = None) -> dict:
    """Wait for a decision (or finalization) and return the full transaction.

    Raises GenLayerTxError unless validators accepted it and the contract did not roll back:
    genlayer-py 0.19 returns on any decision, including UNDETERMINED and timeouts."""
    kw = {} if interval is None else {"interval": interval}
    t = client.wait_for_transaction_receipt(transaction_hash=tx, wait_until="finalized" if finalized else "decided",
                                            retries=retries, full_transaction=True, **kw)
    status = gl_status(t)
    if status not in ("ACCEPTED", "FINALIZED"):
        raise GenLayerTxError(f"tx {tx} ended {status}")
    result = t.get("result_name")
    if status == "FINALIZED" and result is not None and str(result) not in ("AGREE", "MAJORITY_AGREE"):
        raise GenLayerTxError(f"tx {tx} finalized without agreement ({result})")
    rollback = gl_rollback(t)
    if rollback is not None:
        raise GenLayerTxError(f"tx {tx} rolled back: {rollback}")
    # GenLayer: success = ACCEPTED/FINALIZED *and* FINISHED_WITH_RETURN. A tx can reach
    # MAJORITY_AGREE and still have executed with an error (Bradbury, 2026-11-05).
    execution = t.get("tx_execution_result_name")
    if execution is not None and str(execution) != "FINISHED_WITH_RETURN":
        raise GenLayerTxError(f"tx {tx} executed {execution}")
    return t


def gl_contract_address(tx: dict) -> str:
    """The address a deploy transaction created."""
    for holder in (tx.get("tx_data_decoded"), tx.get("data"), tx):
        if isinstance(holder, dict) and holder.get("contract_address"):
            return str(holder["contract_address"])
    to = tx.get("to_address") or tx.get("recipient")
    if to:
        return str(to)
    raise GenLayerTxError("deploy transaction carries no contract address")


def _hex(tx) -> str:
    return tx if isinstance(tx, str) else "0x" + bytes(tx).hex()


def fuji():
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(FUJI_RPC))
    if w3.eth.chain_id != FUJI_CHAIN_ID:
        raise SystemExit(f"{FUJI_RPC} is chain {w3.eth.chain_id}, expected Fuji {FUJI_CHAIN_ID}")
    return w3
