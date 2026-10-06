// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Interface the GenLayer bridge receiver calls on its target contract.
/// Copied from courtofinternet/pm-kit `interfaces/IGenLayerBridgeReceiver.sol`.
interface IGenLayerBridgeReceiver {
    function processBridgeMessage(uint32 _sourceChainId, address _sourceContract, bytes calldata _message) external;
}

/// @title InferenceEscrow
/// @notice Locks a buyer's funds for a cross-org agent job and moves them ONLY on a
/// GenLayer verdict produced by one specific VerifyJob Intelligent Contract.
///
/// Two delivery paths, each fixed at deploy (zero address = disabled):
///   - bridge:  GenLayer -> BridgeSender -> LayerZero -> BridgeReceiver -> processBridgeMessage
///   - relayer: an off-chain relayer reads the FINALIZED verdict on GenLayer and calls settle()
///
/// Security notes:
///   - The bridge path authenticates the ORIGINATING GenLayer contract (`_sourceContract`)
///     and chain id, not just the relay. GenLayer's reference BridgeSender lets any account
///     queue a message to any target (genlayer-foundation/internetcourt#11), so checking
///     `msg.sender == bridgeReceiver` alone would let anyone write verdicts.
///   - A verdict must echo the specHash and rubricHash the buyer committed at openJob, so a
///     case judged against a different spec or rubric cannot settle this job.
///   - Payouts are pull-based (withdraw), so a reverting recipient cannot block settlement.
///   - No token. Native currency only. No admin, no upgrade, no pause: config is immutable.
contract InferenceEscrow is IGenLayerBridgeReceiver {
    enum Status {
        None,
        Funded,
        Paid,
        Refunded
    }

    struct Job {
        address buyer;
        address seller;
        uint256 amount;
        uint64 deadline;
        Status status;
        uint8 score;
        bytes32 specHash;
        bytes32 rubricHash;
        bytes32 usageRoot;
        bytes32 verdictRef;
    }

    uint16 public constant MAX_FEE_BPS = 1_000; // 10%
    uint64 public constant MAX_DURATION = 365 days;

    address public immutable treasury;
    uint16 public immutable feeBps;
    uint64 public immutable minDuration;
    /// @notice Relayer signer allowed to call settle(); zero disables the relayer path.
    address public immutable relayer;
    /// @notice BridgeReceiver allowed to call processBridgeMessage(); zero disables the bridge path.
    address public immutable bridgeReceiver;
    /// @notice Source chain id the bridge stamps on GenLayer messages.
    uint32 public immutable genLayerChainId;
    /// @notice The VerifyJob Intelligent Contract whose verdicts this escrow honours.
    address public immutable verifyContract;

    mapping(bytes32 => Job) public jobs;
    mapping(address => uint256) public credits;

    event JobOpened(
        bytes32 indexed jobId,
        address indexed buyer,
        address indexed seller,
        uint256 amount,
        uint64 deadline,
        bytes32 specHash,
        bytes32 rubricHash
    );
    event JobSettled(
        bytes32 indexed jobId, bool passed, uint8 score, bytes32 usageRoot, bytes32 verdictRef, uint256 fee, bool viaBridge
    );
    event JobExpired(bytes32 indexed jobId);
    event Withdrawn(address indexed account, uint256 amount);

    error InvalidConfig();
    error InvalidJob();
    error JobExists();
    error NotFunded();
    error DeadlinePassed();
    error DeadlineNotReached();
    error Unauthorized();
    error UntrustedSource();
    error VerdictMismatch();
    error NothingToWithdraw();
    error TransferFailed();

    constructor(
        address _treasury,
        uint16 _feeBps,
        uint64 _minDuration,
        address _relayer,
        address _bridgeReceiver,
        uint32 _genLayerChainId,
        address _verifyContract
    ) {
        if (_treasury == address(0) || _feeBps > MAX_FEE_BPS) revert InvalidConfig();
        if (_relayer == address(0) && _bridgeReceiver == address(0)) revert InvalidConfig();
        if (_verifyContract == address(0)) revert InvalidConfig();
        treasury = _treasury;
        feeBps = _feeBps;
        minDuration = _minDuration;
        relayer = _relayer;
        bridgeReceiver = _bridgeReceiver;
        genLayerChainId = _genLayerChainId;
        verifyContract = _verifyContract;
    }

    /// @notice Lock msg.value for a job. The deadline must leave room for GenLayer
    /// finality plus appeals (minDuration), or a slow verdict would lose to expire().
    function openJob(bytes32 jobId, address seller, uint64 deadline, bytes32 specHash, bytes32 rubricHash)
        external
        payable
    {
        if (jobId == bytes32(0) || msg.value == 0) revert InvalidJob();
        if (seller == address(0) || seller == msg.sender) revert InvalidJob();
        if (deadline < block.timestamp + minDuration || deadline > block.timestamp + MAX_DURATION) {
            revert InvalidJob();
        }
        if (jobs[jobId].status != Status.None) revert JobExists();

        Job storage j = jobs[jobId];
        j.buyer = msg.sender;
        j.seller = seller;
        j.amount = msg.value;
        j.deadline = deadline;
        j.status = Status.Funded;
        j.specHash = specHash;
        j.rubricHash = rubricHash;

        emit JobOpened(jobId, msg.sender, seller, msg.value, deadline, specHash, rubricHash);
    }

    /// @notice Relayer path. `verdictRef` is the GenLayer transaction hash that produced the verdict.
    function settle(
        bytes32 jobId,
        bool passed,
        uint8 score,
        bytes32 usageRoot,
        bytes32 specHash,
        bytes32 rubricHash,
        bytes32 verdictRef
    ) external {
        if (relayer == address(0) || msg.sender != relayer) revert Unauthorized();
        _settle(jobId, passed, score, usageRoot, specHash, rubricHash, verdictRef, false);
    }

    /// @notice Bridge path. Message = abi.encode(bytes32 jobId, bool passed, uint8 score,
    /// bytes32 usageRoot, bytes32 specHash, bytes32 rubricHash).
    function processBridgeMessage(uint32 _sourceChainId, address _sourceContract, bytes calldata _message)
        external
        override
    {
        if (bridgeReceiver == address(0) || msg.sender != bridgeReceiver) revert Unauthorized();
        if (_sourceChainId != genLayerChainId || _sourceContract != verifyContract) revert UntrustedSource();

        (bytes32 jobId, bool passed, uint8 score, bytes32 usageRoot, bytes32 specHash, bytes32 rubricHash) =
            abi.decode(_message, (bytes32, bool, uint8, bytes32, bytes32, bytes32));
        // No GenLayer tx hash travels with a bridged message; fingerprint the message instead.
        bytes32 verdictRef = keccak256(abi.encode(_sourceChainId, _sourceContract, _message));
        _settle(jobId, passed, score, usageRoot, specHash, rubricHash, verdictRef, true);
    }

    /// @notice Refund the buyer once the deadline passes with no verdict. Callable by anyone.
    function expire(bytes32 jobId) external {
        Job storage j = jobs[jobId];
        if (j.status != Status.Funded) revert NotFunded();
        if (block.timestamp <= j.deadline) revert DeadlineNotReached();
        j.status = Status.Refunded;
        credits[j.buyer] += j.amount;
        emit JobExpired(jobId);
    }

    function withdraw() external {
        uint256 amount = credits[msg.sender];
        if (amount == 0) revert NothingToWithdraw();
        credits[msg.sender] = 0;
        emit Withdrawn(msg.sender, amount);
        (bool ok,) = msg.sender.call{value: amount}("");
        if (!ok) revert TransferFailed();
    }

    /// @notice Check one line of a job's sealed usage record against the root stored at settlement.
    /// Leaf = keccak256(0x00 || canonical_json_bytes); node = keccak256(0x01 || min(a,b) || max(a,b)).
    function verifyUsageLeaf(bytes32 jobId, bytes32 leafHash, bytes32[] calldata proof) external view returns (bool) {
        bytes32 root = jobs[jobId].usageRoot;
        if (root == bytes32(0)) return false;
        bytes32 h = leafHash;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 p = proof[i];
            h = h < p
                ? keccak256(abi.encodePacked(bytes1(0x01), h, p))
                : keccak256(abi.encodePacked(bytes1(0x01), p, h));
        }
        return h == root;
    }

    function _settle(
        bytes32 jobId,
        bool passed,
        uint8 score,
        bytes32 usageRoot,
        bytes32 specHash,
        bytes32 rubricHash,
        bytes32 verdictRef,
        bool viaBridge
    ) internal {
        Job storage j = jobs[jobId];
        if (j.status != Status.Funded) revert NotFunded();
        if (block.timestamp > j.deadline) revert DeadlinePassed();
        if (specHash != j.specHash || rubricHash != j.rubricHash) revert VerdictMismatch();

        j.score = score;
        j.usageRoot = usageRoot;
        j.verdictRef = verdictRef;

        uint256 fee = 0;
        if (passed) {
            fee = (j.amount * feeBps) / 10_000;
            j.status = Status.Paid;
            credits[j.seller] += j.amount - fee;
            if (fee > 0) credits[treasury] += fee;
        } else {
            j.status = Status.Refunded;
            credits[j.buyer] += j.amount;
        }
        emit JobSettled(jobId, passed, score, usageRoot, verdictRef, fee, viaBridge);
    }
}
