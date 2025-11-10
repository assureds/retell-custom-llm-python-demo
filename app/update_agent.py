import requests
import json

# Your configuration
RETELL_API_KEY = "key_8a60a38093605066adac4b7664bb"  # Use your full key
AGENT_ID = "agent_e6b00f28c6a3c54a505246c799"
WEBSOCKET_URL = "wss://retell-panel-status-api-20c4237e2cfa.herokuapp.com/llm-websocket"

# Retell API endpoint - corrected
url = f"https://api.retellai.com/v2/agents/{AGENT_ID}"

# Headers
headers = {
    "Authorization": f"Bearer {RETELL_API_KEY}",
    "Content-Type": "application/json"
}

# Payload to update agent with custom LLM
payload = {
    "llm_websocket_url": WEBSOCKET_URL
}

print(f"Updating agent {AGENT_ID}...")
print(f"Setting WebSocket URL to: {WEBSOCKET_URL}")

# Make the request
response = requests.patch(url, headers=headers, json=payload)

print(f"\nResponse Status: {response.status_code}")
print(f"Response Body: {response.text}")

if response.status_code in [200, 201]:
    print("\n✅ SUCCESS! Agent updated with custom LLM WebSocket URL")
else:
    print(f"\n❌ ERROR: {response.text}")
```

---
