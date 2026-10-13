import json
from pathlib import Path
import tomllib
import pytest
from ghost_checkout.web import UI
from ghost_checkout.wisp_lite import ROOT, sdk_metadata


def test_public_store_assets_match_authorized_demo_source_when_present():
    original=Path(__file__).resolve().parents[3]/'deploy/demo-pages/shop'
    if not original.exists(): pytest.skip('Standalone public export has no private checkout.')
    for path in ROOT.iterdir(): assert path.read_bytes()==(original/path.name).read_bytes()


def test_env_license_and_devcontainer_are_judge_ready():
    project=Path(__file__).resolve().parents[1]
    assert 'Apache License' in (project/'LICENSE').read_text()
    env=(project/'.env.example').read_text()
    for key in ('PAYPAL_CLIENT_SECRET','LLM_API_KEY'): assert key+'=\n' in env
    container=json.loads((project/'.devcontainer/devcontainer.json').read_text())
    assert container['forwardPorts']==[8876]
    assert container['portsAttributes']['8876']['visibility']=='private'
    config=tomllib.loads((project/'pyproject.toml').read_text())
    assert config['project']['requires-python']=='>=3.12'
    assert 'paypal-server-sdk==2.0.0' in config['project']['dependencies']


def test_public_observer_identifiers_do_not_come_from_page_text_or_v6_queries():
    assert sdk_metadata('https://www.paypal.com/sdk/js?client-id=MOCK&merchant-id=A,B')['merchant_ids']==['A','B']
    assert sdk_metadata('https://www.paypal.com.evil.test/sdk/js?merchant-id=X') is None
    assert sdk_metadata('https://www.paypal.com/web-sdk/v6/core?merchant-id=X') is None
    assert sdk_metadata('https://www.paypal.com/sdk/js?merchant-id=pay%20X')['merchant_ids']==[]


def test_rendered_mock_fixture_identity_matches_recorded_contract():
    from ghost_checkout.store_fixtures import render_mock_store
    from ghost_checkout.demo_data import records,BASE
    html=render_mock_store(ROOT.joinpath('corner-bakery.html').read_text())
    merchant=records()[BASE+'corner-bakery.html']['payment_provider']['merchant_ids'][0]
    assert 'merchant-id='+merchant in html
    flash=records()[BASE+'flash-sale.html']
    assert flash['verdict']['state']=='no_obvious_danger'
    assert flash['verdict']['rules']==['NSB-0']
    assert flash['payment_provider']['claimed_merchant_id']!=flash['payment_provider']['merchant_ids'][0]
