"""Check required sandbox settings without printing tokens, phone numbers or secrets."""
from whatsapp_poc.server import Settings

try:
    Settings.from_env().validate()
except RuntimeError as exc:
    print(f"Configuration incomplete: {exc}")
    raise SystemExit(1)
else:
    print("Configuration looks complete. Keep .env private and run the webhook server.")
