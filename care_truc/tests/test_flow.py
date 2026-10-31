"""End-to-end algorithm fixtures through the sole runtime and JSON adapter."""
import asyncio

from care_truc.demo import run_adapter_demo


def test_labelled_adapter_flow(tmp_path):
    result = asyncio.run(run_adapter_demo(tmp_path))
    assert result['label'] == 'adapter demo: algorithm fixtures only'
    assert result['coin_receipt'] == 'succeeded'
    assert result['post_immutable'] is True
    assert result['evidence_resolved'] is True
    assert result['cancel_receipt'] == 'succeeded'
    assert result['handoff_receipt'] == 'succeeded'
    assert result['selector_source'] == 'template'
    assert result['guard_blocked'] is True
    assert result['customer_private'] is True
