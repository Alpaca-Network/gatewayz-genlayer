// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {InferenceEscrow} from "../src/InferenceEscrow.sol";

contract Reenterer {
    InferenceEscrow public escrow;
    uint256 public hits;

    constructor(InferenceEscrow e) {
        escrow = e;
    }

    function pull() external {
        escrow.withdraw();
    }

    receive() external payable {
        hits++;
        if (hits < 3) {
            try escrow.withdraw() {} catch {}
        }
    }
}

contract Rejecter {
    receive() external payable {
        revert("no");
    }
}

contract InferenceEscrowTest is Test {
    InferenceEscrow escrow;

    address treasury = makeAddr("treasury");
    address relayer = makeAddr("relayer");
    address bridge = makeAddr("bridgeReceiver");
    address verifyIC = makeAddr("verifyJobIC");
    address buyer = makeAddr("buyer");
    address seller = makeAddr("seller");
    address stranger = makeAddr("stranger");

    uint32 constant GL_CHAIN = 61998;
    uint16 constant FEE_BPS = 250; // 2.5%
    uint64 constant MIN_DURATION = 6 hours;

    bytes32 constant JOB = keccak256("job-1");
    bytes32 constant SPEC = keccak256("spec");
    bytes32 constant RUBRIC = keccak256("rubric");
    bytes32 constant ROOT = keccak256("root");
    bytes32 constant GL_TX = keccak256("genlayer-tx");

    function setUp() public {
        escrow = new InferenceEscrow(treasury, FEE_BPS, MIN_DURATION, relayer, bridge, GL_CHAIN, verifyIC);
        vm.deal(buyer, 100 ether);
    }

    function _open(uint256 amount) internal returns (uint64 deadline) {
        deadline = uint64(block.timestamp + 48 hours);
        vm.prank(buyer);
        escrow.openJob{value: amount}(JOB, seller, deadline, SPEC, RUBRIC);
    }

    function _status(bytes32 id) internal view returns (InferenceEscrow.Status s) {
        (,,,, s,,,,,) = escrow.jobs(id);
    }

    function _msg(bool passed, bytes32 spec, bytes32 rubric) internal pure returns (bytes memory) {
        return abi.encode(JOB, passed, uint8(88), ROOT, spec, rubric);
    }

    // ---------- constructor ----------

    function test_constructor_rejects_bad_config() public {
        vm.expectRevert(InferenceEscrow.InvalidConfig.selector);
        new InferenceEscrow(address(0), FEE_BPS, MIN_DURATION, relayer, bridge, GL_CHAIN, verifyIC);
        vm.expectRevert(InferenceEscrow.InvalidConfig.selector);
        new InferenceEscrow(treasury, 1_001, MIN_DURATION, relayer, bridge, GL_CHAIN, verifyIC);
        vm.expectRevert(InferenceEscrow.InvalidConfig.selector);
        new InferenceEscrow(treasury, FEE_BPS, MIN_DURATION, address(0), address(0), GL_CHAIN, verifyIC);
        vm.expectRevert(InferenceEscrow.InvalidConfig.selector);
        new InferenceEscrow(treasury, FEE_BPS, MIN_DURATION, relayer, bridge, GL_CHAIN, address(0));
    }

    // ---------- openJob ----------

    function test_open_locks_funds() public {
        _open(1 ether);
        assertEq(address(escrow).balance, 1 ether);
        assertEq(uint8(_status(JOB)), uint8(InferenceEscrow.Status.Funded));
    }

    function test_open_rejects_duplicate_and_bad_inputs() public {
        _open(1 ether);
        uint64 dl = uint64(block.timestamp + 48 hours);
        vm.startPrank(buyer);
        vm.expectRevert(InferenceEscrow.JobExists.selector);
        escrow.openJob{value: 1 ether}(JOB, seller, dl, SPEC, RUBRIC);
        vm.expectRevert(InferenceEscrow.InvalidJob.selector);
        escrow.openJob{value: 0}(keccak256("j2"), seller, dl, SPEC, RUBRIC);
        vm.expectRevert(InferenceEscrow.InvalidJob.selector);
        escrow.openJob{value: 1 ether}(keccak256("j3"), buyer, dl, SPEC, RUBRIC);
        vm.expectRevert(InferenceEscrow.InvalidJob.selector);
        escrow.openJob{value: 1 ether}(keccak256("j4"), address(0), dl, SPEC, RUBRIC);
        vm.expectRevert(InferenceEscrow.InvalidJob.selector);
        escrow.openJob{value: 1 ether}(bytes32(0), seller, dl, SPEC, RUBRIC);
        vm.stopPrank();
    }

    function test_open_rejects_deadline_shorter_than_appeal_window() public {
        vm.prank(buyer);
        vm.expectRevert(InferenceEscrow.InvalidJob.selector);
        escrow.openJob{value: 1 ether}(JOB, seller, uint64(block.timestamp + MIN_DURATION - 1), SPEC, RUBRIC);
    }

    // ---------- relayer path ----------

    function test_relayer_pass_pays_seller_minus_fee() public {
        _open(1 ether);
        vm.prank(relayer);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        assertEq(escrow.credits(seller), 0.975 ether);
        assertEq(escrow.credits(treasury), 0.025 ether);
        assertEq(escrow.credits(buyer), 0);
        assertEq(uint8(_status(JOB)), uint8(InferenceEscrow.Status.Paid));
        (,,,,,,,, bytes32 root, bytes32 ref) = escrow.jobs(JOB);
        assertEq(root, ROOT);
        assertEq(ref, GL_TX);
    }

    function test_relayer_fail_refunds_buyer_in_full() public {
        _open(1 ether);
        vm.prank(relayer);
        escrow.settle(JOB, false, 20, ROOT, SPEC, RUBRIC, GL_TX);
        assertEq(escrow.credits(buyer), 1 ether);
        assertEq(escrow.credits(seller), 0);
        assertEq(escrow.credits(treasury), 0);
        assertEq(uint8(_status(JOB)), uint8(InferenceEscrow.Status.Refunded));
    }

    function test_only_relayer_can_settle() public {
        _open(1 ether);
        vm.prank(stranger);
        vm.expectRevert(InferenceEscrow.Unauthorized.selector);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        vm.prank(seller);
        vm.expectRevert(InferenceEscrow.Unauthorized.selector);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
    }

    function test_cannot_settle_twice() public {
        _open(1 ether);
        vm.startPrank(relayer);
        escrow.settle(JOB, false, 20, ROOT, SPEC, RUBRIC, GL_TX);
        vm.expectRevert(InferenceEscrow.NotFunded.selector);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        vm.stopPrank();
    }

    function test_verdict_for_other_spec_or_rubric_is_rejected() public {
        _open(1 ether);
        vm.startPrank(relayer);
        vm.expectRevert(InferenceEscrow.VerdictMismatch.selector);
        escrow.settle(JOB, true, 91, ROOT, keccak256("other spec"), RUBRIC, GL_TX);
        vm.expectRevert(InferenceEscrow.VerdictMismatch.selector);
        escrow.settle(JOB, true, 91, ROOT, SPEC, keccak256("lenient rubric"), GL_TX);
        vm.stopPrank();
    }

    function test_settle_unknown_job_reverts() public {
        vm.prank(relayer);
        vm.expectRevert(InferenceEscrow.NotFunded.selector);
        escrow.settle(keccak256("nope"), true, 91, ROOT, SPEC, RUBRIC, GL_TX);
    }

    // ---------- bridge path ----------

    function test_bridge_pass_settles() public {
        _open(1 ether);
        vm.prank(bridge);
        escrow.processBridgeMessage(GL_CHAIN, verifyIC, _msg(true, SPEC, RUBRIC));
        assertEq(escrow.credits(seller), 0.975 ether);
        (,,,,,,,,, bytes32 ref) = escrow.jobs(JOB);
        assertTrue(ref != bytes32(0));
    }

    /// The internetcourt#11 attack: a real BridgeReceiver relays a message that some OTHER
    /// GenLayer account queued. It must not settle.
    function test_bridge_rejects_message_from_untrusted_genlayer_sender() public {
        _open(1 ether);
        vm.prank(bridge);
        vm.expectRevert(InferenceEscrow.UntrustedSource.selector);
        escrow.processBridgeMessage(GL_CHAIN, stranger, _msg(true, SPEC, RUBRIC));
        assertEq(uint8(_status(JOB)), uint8(InferenceEscrow.Status.Funded));
    }

    function test_bridge_rejects_wrong_source_chain() public {
        _open(1 ether);
        vm.prank(bridge);
        vm.expectRevert(InferenceEscrow.UntrustedSource.selector);
        escrow.processBridgeMessage(GL_CHAIN + 1, verifyIC, _msg(true, SPEC, RUBRIC));
    }

    function test_bridge_rejects_direct_caller() public {
        _open(1 ether);
        vm.prank(stranger);
        vm.expectRevert(InferenceEscrow.Unauthorized.selector);
        escrow.processBridgeMessage(GL_CHAIN, verifyIC, _msg(true, SPEC, RUBRIC));
    }

    function test_disabled_paths_reject() public {
        InferenceEscrow bridgeOnly =
            new InferenceEscrow(treasury, FEE_BPS, MIN_DURATION, address(0), bridge, GL_CHAIN, verifyIC);
        vm.prank(address(0));
        vm.expectRevert(InferenceEscrow.Unauthorized.selector);
        bridgeOnly.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);

        InferenceEscrow relayerOnly =
            new InferenceEscrow(treasury, FEE_BPS, MIN_DURATION, relayer, address(0), GL_CHAIN, verifyIC);
        vm.prank(address(0));
        vm.expectRevert(InferenceEscrow.Unauthorized.selector);
        relayerOnly.processBridgeMessage(GL_CHAIN, verifyIC, _msg(true, SPEC, RUBRIC));
    }

    // ---------- deadline / expire ----------

    function test_expire_refunds_after_deadline_only() public {
        uint64 dl = _open(1 ether);
        vm.expectRevert(InferenceEscrow.DeadlineNotReached.selector);
        escrow.expire(JOB);
        vm.warp(dl + 1);
        vm.prank(stranger);
        escrow.expire(JOB);
        assertEq(escrow.credits(buyer), 1 ether);
    }

    function test_late_verdict_loses_to_deadline() public {
        uint64 dl = _open(1 ether);
        vm.warp(dl + 1);
        vm.prank(relayer);
        vm.expectRevert(InferenceEscrow.DeadlinePassed.selector);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
    }

    function test_cannot_expire_settled_job() public {
        uint64 dl = _open(1 ether);
        vm.prank(relayer);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        vm.warp(dl + 1);
        vm.expectRevert(InferenceEscrow.NotFunded.selector);
        escrow.expire(JOB);
    }

    // ---------- withdraw ----------

    function test_withdraw_pays_and_zeroes() public {
        _open(1 ether);
        vm.prank(relayer);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        uint256 before = seller.balance;
        vm.prank(seller);
        escrow.withdraw();
        assertEq(seller.balance - before, 0.975 ether);
        assertEq(escrow.credits(seller), 0);
        vm.prank(seller);
        vm.expectRevert(InferenceEscrow.NothingToWithdraw.selector);
        escrow.withdraw();
    }

    function test_withdraw_reentrancy_cannot_double_pay() public {
        Reenterer r = new Reenterer(escrow);
        uint64 dl = uint64(block.timestamp + 48 hours);
        vm.prank(buyer);
        escrow.openJob{value: 1 ether}(JOB, address(r), dl, SPEC, RUBRIC);
        vm.prank(relayer);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        r.pull();
        assertEq(address(r).balance, 0.975 ether);
        assertEq(address(escrow).balance, 0.025 ether); // only the treasury's fee remains
    }

    function test_reverting_recipient_does_not_block_settlement() public {
        Rejecter rej = new Rejecter();
        uint64 dl = uint64(block.timestamp + 48 hours);
        vm.prank(buyer);
        escrow.openJob{value: 1 ether}(JOB, address(rej), dl, SPEC, RUBRIC);
        vm.prank(relayer);
        escrow.settle(JOB, true, 91, ROOT, SPEC, RUBRIC, GL_TX);
        assertEq(escrow.credits(address(rej)), 0.975 ether);
    }

    // ---------- usage proofs ----------

    function _leaf(bytes memory data) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(bytes1(0x00), data));
    }

    function _node(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a < b
            ? keccak256(abi.encodePacked(bytes1(0x01), a, b))
            : keccak256(abi.encodePacked(bytes1(0x01), b, a));
    }

    function test_verify_usage_leaf_against_settled_root() public {
        bytes32 l0 = _leaf("a");
        bytes32 l1 = _leaf("b");
        bytes32 l2 = _leaf("c");
        bytes32 root = _node(_node(l0, l1), l2); // odd leaf promoted

        _open(1 ether);
        vm.prank(relayer);
        escrow.settle(JOB, true, 91, root, SPEC, RUBRIC, GL_TX);

        bytes32[] memory p = new bytes32[](2);
        p[0] = l1;
        p[1] = l2;
        assertTrue(escrow.verifyUsageLeaf(JOB, l0, p));
        bytes32[] memory p2 = new bytes32[](1);
        p2[0] = _node(l0, l1);
        assertTrue(escrow.verifyUsageLeaf(JOB, l2, p2));
        assertFalse(escrow.verifyUsageLeaf(JOB, _leaf("forged"), p));
    }

    // ---------- fuzz ----------

    function testFuzz_settlement_conserves_value(uint96 amount, bool passed) public {
        vm.assume(amount > 0);
        vm.deal(buyer, amount);
        uint64 dl = uint64(block.timestamp + 48 hours);
        vm.prank(buyer);
        escrow.openJob{value: amount}(JOB, seller, dl, SPEC, RUBRIC);
        vm.prank(relayer);
        escrow.settle(JOB, passed, 50, ROOT, SPEC, RUBRIC, GL_TX);
        assertEq(escrow.credits(buyer) + escrow.credits(seller) + escrow.credits(treasury), amount);
        assertEq(address(escrow).balance, amount);
    }
}
