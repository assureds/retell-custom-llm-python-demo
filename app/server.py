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
from .redis_utils import redis_store

if os.path.exists('.env'):
    print("DEBUG: Found .env file, loading environment variables...")
    load_dotenv(override=True)
else:
    print("DEBUG: No .env file found (expected in Heroku production)")

app = FastAPI()
retell = Retell(api_key=os.environ["RETELL_API_KEY"])

call_phone_numbers = {}


@app.post("/redis-store")
async def redis_store_metadata(request: Request):
    """Store provider metadata in Redis before making the call"""
    try:
        data = await request.json()
        print(f"\n{'='*70}")
        print(f"🔴 REDIS STORE ENDPOINT CALLED")
        print(f"{'='*70}")
        
        phone_number = data.get("phone_number")
        if not phone_number:
            return JSONResponse(
                status_code=400,
                content={"error": "phone_number is required"}
            )
        
        metadata = {
            "provider_name": data.get("provider_name", ""),
            "npi_number": data.get("npi_number", ""),
            "tax_id": data.get("tax_id", ""),
            "specialty": data.get("specialty", ""),
            "scenario_type": data.get("scenario_type", ""),
            "line_of_business": data.get("line_of_business", ""),
            "payer": data.get("payer", ""),
            "organization_name": data.get("organization_name", ""),
        }
        
        print(f"Phone number: {phone_number}")
        print(f"Storing {len(metadata)} metadata fields:")
        for key, value in metadata.items():
            if value:
                print(f"  ✓ {key}: {value}")
        
        success = redis_store.store_metadata(phone_number, metadata)
        
        if success:
            print(f"{'='*70}\n")
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": f"Metadata stored for {phone_number}",
                    "fields_stored": len([v for v in metadata.values() if v])
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to store metadata"}
            )
    
    except Exception as err:
        print(f"❌ ERROR in redis_store_metadata: {err}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"error": str(err)}
        )


@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        post_data = await request.json()
        print(f"DEBUG WEBHOOK: Received event: {post_data.get('event', 'unknown')}")
        
        event = post_data.get("event")
        call_data = post_data.get("call", {})
        call_id = call_data.get("call_id", "unknown")
        
        if event == "call_started":
            print(f"DEBUG WEBHOOK: Call started - {call_id}")
        elif event == "call_ended":
            print(f"DEBUG WEBHOOK: Call ended - {call_id}")
            if call_id in call_phone_numbers:
                phone_info = call_phone_numbers[call_id]
                to_number = phone_info.get("to") if isinstance(phone_info, dict) else phone_info
                if to_number:
                    redis_store.delete_metadata(to_number)
                del call_phone_numbers[call_id]
        elif event == "call_analyzed":
            print(f"DEBUG WEBHOOK: Call analyzed - {call_id}")
        
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
            
            if interaction_type == "call_details":
                print(f"\n{'='*70}")
                print(f"🔍 CALL_DETAILS EVENT RECEIVED")
                print(f"{'='*70}")
                
                call_obj = request_json.get("call", {})
                from_number = call_obj.get("from_number", None)
                to_number = call_obj.get("to_number", None)
                
                print(f"From Number (Agent 1): {from_number}")
                print(f"To Number (Your Phone): {to_number}")
                
                if from_number:
                    call_phone_numbers[call_id] = {"from": from_number, "to": to_number}
                
                dynamic_variables = {}
                if to_number:
                    print(f"\n🔴 REDIS LOOKUP: Attempting to retrieve metadata by phone number")
                    redis_metadata = redis_store.retrieve_metadata(to_number)
                    if redis_metadata:
                        dynamic_variables = redis_metadata
                        print(f"✅ Successfully retrieved {len(dynamic_variables)} fields from Redis")
                    else:
                        print(f"⚠️  No metadata found in Redis for {to_number}")
                
                if dynamic_variables:
                    for key, value in dynamic_variables.items():
                        if key and value:
                            print(f"  ✓ {key}: {value}")
                else:
                    print(f"⚠️  No dynamic variables available for this call")
                
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
                
                stored_variables = {}
                
                if call_id in call_phone_numbers:
                    phone_info = call_phone_numbers[call_id]
                    to_number = phone_info.get("to") if isinstance(phone_info, dict) else phone_info
                    if to_number:
                        stored_variables = redis_store.retrieve_metadata(to_number) or {}
                
                if not stored_variables and "retell_llm_dynamic_variables" in request_json:
                    stored_variables = request_json.get("retell_llm_dynamic_variables", {})
                
                print(f"\n📝 RESPONSE REQUIRED")
                print(f"Response ID: {response_id}")
                print(f"Using {len(stored_variables)} dynamic variables")
                if stored_variables:
                    for key in stored_variables.keys():
                        if key and stored_variables[key]:
                            print(f"  ✓ {key}")
                
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
    except ConnectionTimeoutError as e:
        print(f"DEBUG WEBSOCKET: Timeout error - {call_id}: {e}")
    except Exception as e:
        print(f"ERROR in LLM WebSocket: {e} for {call_id}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        await websocket.close(1011, "Server error")
    finally:
        print(f"DEBUG WEBSOCKET: Connection closed - {call_id}")
