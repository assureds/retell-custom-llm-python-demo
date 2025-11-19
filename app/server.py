import json
import os
import asyncio
import traceback
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from concurrent.futures import TimeoutError as ConnectionTimeoutError
from retell import Retell
from .custom_types import (
    ConfigResponse,
    ResponseRequiredRequest,
)
from .llm import LlmClient

# ========== FIX: Only load .env in development ==========
# In Heroku production, env vars are set directly in Config Vars
# We don't want load_dotenv(override=True) to overwrite them with empty .env values
if os.path.exists('.env'):
    print("DEBUG: Found .env file, loading environment variables...")
    load_dotenv(override=True)
else:
    print("DEBUG: No .env file found (expected in Heroku production)")

app = FastAPI()
retell = Retell(api_key=os.environ["RETELL_API_KEY"])

# Store dynamic variables per call
call_dynamic_variables = {}


@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        post_data = await request.json()
        print(f"DEBUG WEBHOOK: Received event: {post_data.get('event', 'unknown')}")
        print(f"DEBUG WEBHOOK: Full payload keys: {post_data.keys()}")
        
        # Skip signature verification for now - debugging
        print(f"DEBUG WEBHOOK: Accepting webhook without signature verification")
        
        event = post_data.get("event")
        call_data = post_data.get("call", {})  # Changed from 'data' to 'call'
        call_id = call_data.get("call_id", "unknown")
        
        if event == "call_started":
            print(f"DEBUG WEBHOOK: Call started - {call_id}")
        elif event == "call_ended":
            print(f"DEBUG WEBHOOK: Call ended - {call_id}")
        elif event == "call_analyzed":
            print(f"DEBUG WEBHOOK: Call analyzed - {call_id}")
        else:
            print(f"DEBUG WEBHOOK: Unknown event - {event}")
        
        return JSONResponse(status_code=200, content={"received": True})
    except Exception as err:
        print(f"ERROR in webhook: {err}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500, content={"message": "Internal Server Error"}
        )


@app.websocket("/llm-websocket/{call_id}")
async def websocket_handler(websocket: WebSocket, call_id: str):
    try:
        await websocket.accept()
        print(f"DEBUG WEBSOCKET: Connected - {call_id}")
        llm_client = LlmClient()

        config = ConfigResponse(
            response_type="config",
            config={
                "auto_reconnect": True,
                "call_details": True,
            },
        )
        await websocket.send_json(config.__dict__)
        print(f"DEBUG WEBSOCKET: Sent config - {call_id}")

        response_id = 0
        first_event = llm_client.draft_begin_message()
        await websocket.send_json(first_event.__dict__)
        print(f"DEBUG WEBSOCKET: Sent begin message - {call_id}")

        async def handle_message(request_json):
            nonlocal response_id

            interaction_type = request_json.get("interaction_type", "unknown")
            print(f"DEBUG WEBSOCKET: Received {interaction_type} - {call_id}")
            
            # ========== EXTRACT DYNAMIC VARIABLES FROM CALL_DETAILS ==========
            if interaction_type == "call_details":
                print(f"\n{'='*70}")
                print(f"🔍 CALL_DETAILS EVENT RECEIVED")
                print(f"{'='*70}")
                
                # Get the call object
                call_obj = request_json.get("call", {})
                
                # Extract dynamic_variables (converted from X- SIP headers by Retell)
                dynamic_variables = call_obj.get("retell_llm_dynamic_variables", {})
                
                # Store for this call
                if dynamic_variables:
                    call_dynamic_variables[call_id] = dynamic_variables
                    print(f"✅ Dynamic variables found: {len(dynamic_variables)} items")
                    for key, value in dynamic_variables.items():
                        print(f"  ✓ {key}: {value}")
                else:
                    print(f"⚠️  WARNING: No dynamic variables in call_details!")
                    call_dynamic_variables[call_id] = {}
                
                print(f"{'='*70}\n")
                return
            
            if interaction_type == "ping_pong":
                print(f"DEBUG WEBSOCKET: Responding to ping_pong")
                await websocket.send_json(
                    {
                        "response_type": "ping_pong",
                        "timestamp": request_json["timestamp"],
                    }
                )
                return
            
            if interaction_type == "update_only":
                print(f"DEBUG WEBSOCKET: Ignoring update_only")
                return
            
            if (
                interaction_type == "response_required"
                or interaction_type == "reminder_required"
            ):
                response_id = request_json["response_id"]
                
                # ========== GET STORED DYNAMIC VARIABLES FOR THIS CALL ==========
                stored_variables = call_dynamic_variables.get(call_id, {})
                print(f"\n📝 RESPONSE REQUIRED")
                print(f"Response ID: {response_id}")
                print(f"Using {len(stored_variables)} dynamic variables")
                if stored_variables:
                    for key in stored_variables.keys():
                        print(f"  ✓ {key}")
                # ================================================================
                
                request = ResponseRequiredRequest(
                    interaction_type=interaction_type,
                    response_id=response_id,
                    transcript=request_json["transcript"],
                    retell_llm_dynamic_variables=stored_variables,
                )
                print(
                    f"DEBUG WEBSOCKET: response_id={response_id}, interaction_type={interaction_type}"
                )
                print(f"DEBUG WEBSOCKET: retell_llm_dynamic_variables keys = {list(request.retell_llm_dynamic_variables.keys())}")

                async for event in llm_client.draft_response(request):
                    await websocket.send_json(event.__dict__)
                    if request.response_id < response_id:
                        break

        async for data in websocket.iter_json():
            asyncio.create_task(handle_message(data))

    except WebSocketDisconnect:
        print(f"DEBUG WEBSOCKET: Disconnected - {call_id}")
        # Clean up stored variables
        if call_id in call_dynamic_variables:
            del call_dynamic_variables[call_id]
    except ConnectionTimeoutError as e:
        print(f"DEBUG WEBSOCKET: Timeout error - {call_id}: {e}")
    except Exception as e:
        print(f"ERROR in LLM WebSocket: {e} for {call_id}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        await websocket.close(1011, "Server error")
    finally:
        print(f"DEBUG WEBSOCKET: Connection closed - {call_id}")
