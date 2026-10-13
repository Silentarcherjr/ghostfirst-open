"""Render only known synthetic placeholders; no real environment/credentials read."""
MOCK_CLIENT='MOCK_CLIENT'
MOCK_MERCHANT='DEMO_BAKERY_MERCHANT'


def render_mock_store(text):
    return text.replace('SANDBOX_CLIENT_ID',MOCK_CLIENT).replace('SANDBOX_MERCHANT_ID',MOCK_MERCHANT)
