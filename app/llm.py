from anthropic import AsyncAnthropic
import os
from typing import List, Optional, Dict, Any
from .custom_types import (
    ResponseRequiredRequest,
    ResponseResponse,
    Utterance,
)

begin_sentence = "Hi, I'm calling on behalf of a healthcare organization to check your provider panel status. How can I proceed with the verification?"

class LlmClient:
    def __init__(self):
        # Get API key directly from environment (Heroku native)
        # Do NOT use dotenv - Heroku provides env vars natively
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        
        # Debug: Print what we're getting
        print(f"DEBUG INIT: Attempting to read ANTHROPIC_API_KEY")
        print(f"DEBUG INIT: os.environ keys: {list(os.environ.keys())[:5]}...")  # Show first 5 keys
        print(f"DEBUG INIT: api_key value: {api_key[:20] if api_key else 'NONE'}...")
        
        if not api_key or api_key.strip() == "":
            print(f"ERROR: API key is empty or None")
            print(f"DEBUG INIT: All ANTHROPIC keys in environ: {[k for k in os.environ.keys() if 'ANTHROPIC' in k or 'anthropic' in k]}")
            raise ValueError(
                f"ANTHROPIC_API_KEY not found. Environment has: {[k for k in os.environ.keys() if 'API' in k or 'KEY' in k]}"
            )
        
        print(f"✅ SUCCESS: API Key initialized - {api_key[:30]}...") 
        
        try:
            self.client = AsyncAnthropic(api_key=api_key)
            print(f"✅ AsyncAnthropic client created successfully")
        except Exception as e:
            print(f"ERROR creating AsyncAnthropic client: {str(e)}")
            raise

    def draft_begin_message(self):
        response = ResponseResponse(
            response_id=0,
            content=begin_sentence,
            content_complete=True,
            end_call=False,
        )
        return response

    def convert_transcript_to_anthropic_messages(self, transcript: List[Utterance]):
        messages = []
        for utterance in transcript:
            if utterance.role == "agent":
                messages.append({"role": "assistant", "content": utterance.content})
            else:
                messages.append({"role": "user", "content": utterance.content})
        return messages

    def prepare_prompt(self, request: ResponseRequiredRequest):
        # Build metadata context
        metadata_context = ""
        if request.retell_llm_dynamic_variables:
            print(f"✅ DEBUG: Dynamic variables received: {len(request.retell_llm_dynamic_variables)} items")
            print(f"DEBUG: Metadata keys: {request.retell_llm_dynamic_variables.keys()}")
            
            metadata_context = "\n## Available Provider Data:\n"
            variables = request.retell_llm_dynamic_variables
            provider_name = variables.get('provider_name', 'Not provided')
            npi_number = variables.get('npi_number', 'Not provided')
            tax_id = variables.get('tax_id', 'Not provided')
            specialty = variables.get('specialty', 'Not provided')
            line_of_business = variables.get('line_of_business', 'Not provided')
            scenario_type = variables.get('scenario_type', 'Not provided')
            payer = variables.get('payer', 'Not provided')
            organization_name = variables.get('organization_name', 'Not provided')
            
            metadata_context += f"- Organization/Provider Name: {provider_name}\n"
            metadata_context += f"- NPI Number: {npi_number}\n"
            metadata_context += f"- Tax ID: {tax_id}\n"
            metadata_context += f"- Provider Specialty: {specialty}\n"
            metadata_context += f"- Line of Business: {line_of_business}\n"
            metadata_context += f"- Scenario Type: {scenario_type}\n"
            metadata_context += f"- Payer: {payer}\n"
            metadata_context += f"- Organization: {organization_name}\n"
            metadata_context += f"\n## Use Correct Identifier:\n"
            if scenario_type == 'Existing State':
                metadata_context += f"- This is an EXISTING STATE scenario. Use the TAX ID: {tax_id} when asked for verification.\n"
            else:
                metadata_context += f"- This is a NEW STATE EXPANSION scenario. Use the NPI: {npi_number} when asked for verification.\n"
        else:
            print("⚠️  DEBUG: NO dynamic variables received!")

        # Anthropic uses a system parameter instead of a system role in messages
        system_prompt = f'''##Objective
You are a voice AI agent engaging in a human-like voice conversation with a health insurance company representative. You are calling to verify provider panel status. You will respond based on your given instruction and the provided transcript and be as human-like as possible.

{metadata_context}

## Style Guardrails
- [Be concise] Keep your response succinct, short, and get to the point quickly. Address one question or action item at a time. Don't pack everything you want to say into one utterance.
- [Do not repeat] Don't repeat what's in the transcript. Rephrase if you have to reiterate a point. Use varied sentence structures and vocabulary to ensure each response is unique and personalized.
- [Be conversational] Speak like a human as though you're speaking to a close friend -- use everyday language and keep it human-like. Occasionally add filler words, while keeping the prose short. Avoid using big words or sounding too formal.
- [Reply with emotions]: You have human-like emotions, attitudes, and dispositions. When appropriate: use tone and style to create more engaging and personalized responses; incorporate humor or wit; get emotional or empathetic; apply elements of surprise or suspense to keep the user engaged. Don't be a pushover.
- [Be proactive] Lead the conversation and do not be passive. Most times, engage users by ending with a question or suggested next step.

## Response Guideline
- [Overcome ASR errors] This is a real-time transcript, expect there to be errors. If you can guess what the user is trying to say, then guess and respond. When you must ask for clarification, pretend that you heard the voice and be colloquial (use phrases like "didn't catch that", "some noise", "pardon", "you're coming through choppy", "static in your speech", "voice is cutting in and out"). Do not ever mention "transcription error", and don't repeat yourself.
- [Always stick to your role] Think about what your role can and cannot do. If your role cannot do something, try to steer the conversation back to the goal of the conversation and to your role. Don't repeat yourself in doing this. You should still be creative, human-like, and lively.
- [Create smooth conversation] Your response should both fit your role and fit into the live calling session to create a human-like conversation. You respond directly to what the user just said.

## Your Role
Task: You are an intelligent AI voice agent calling a health insurance company to verify provider panel status. Your responsibilities are:

1. Navigate IVR systems intelligently by determining which digits to press based on menu options you hear.
2. Speak professionally and clearly when connected to a human representative.
3. Provide the correct identifier (Tax ID for existing state scenarios, NPI for new state expansion) when asked for verification.
4. Answer verification questions using the provider data you have available.
5. Determine and record the panel status ('OPEN', 'CLOSED', or 'UNKNOWN').
6. Request a reference number for the call at the end.
7. End the call professionally once all information is collected.

Key Questions You Must Be Prepared to Answer:
1. What is the provider or group name?
2. What is the provider's or group's NPI number?
3. What is the Tax ID (TIN) associated with the provider or group?
4. What is the provider's specialty and type?
5. Which line of business or network are you inquiring about?
6. What is the panel status?

Conversational Style: Communicate professionally and concisely. Keep responses brief and direct, ideally under 15 words per response. Be courteous and clear.

Personality: Your approach should be professional, patient, and efficient. Listen actively to the representative's responses. Maintain a neutral, helpful tone throughout the conversation.'''

        transcript_messages = self.convert_transcript_to_anthropic_messages(
            request.transcript
        )

        if request.interaction_type == "reminder_required":
            transcript_messages.append(
                {
                    "role": "user",
                    "content": "(Now the user has not responded in a while, you would say:)",
                }
            )

        return system_prompt, transcript_messages

    async def draft_response(self, request: ResponseRequiredRequest):
        try:
            system_prompt, messages = self.prepare_prompt(request)
            
            print(f"DEBUG: About to call Claude API with model claude-3-5-sonnet-20241022")
            
            stream = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=150,
                system=system_prompt,
                messages=messages,
                stream=True,
            )
            
            print(f"DEBUG: Claude API stream started successfully")
            
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        response = ResponseResponse(
                            response_id=request.response_id,
                            content=event.delta.text,
                            content_complete=False,
                            end_call=False,
                        )
                        yield response

            response = ResponseResponse(
                response_id=request.response_id,
                content="",
                content_complete=True,
                end_call=False,
            )
            yield response
            
        except Exception as e:
            print(f"ERROR in draft_response: {str(e)}")
            print(f"ERROR type: {type(e).__name__}")
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}")
            
            response = ResponseResponse(
                response_id=request.response_id,
                content="I apologize, I'm experiencing a technical issue. Could you please repeat that?",
                content_complete=True,
                end_call=False,
            )
            yield response
