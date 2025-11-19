from anthropic import AsyncAnthropic
import os
from typing import List, Optional, Dict, Any
from .custom_types import (
    ResponseRequiredRequest,
    ResponseResponse,
    Utterance,
)

# ========== IMPROVED: Better begin message for panel status inquiry ==========
begin_sentence = "Hi there. I'm calling to check if you're accepting new providers on your panel. Could you help me with that?"

class LlmClient:
    def __init__(self):
        # ========== FIX: Get API key from environment with detailed debugging ==========
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        
        # Debug info
        print(f"\n{'='*70}")
        print(f"🔍 LLM CLIENT INITIALIZATION")
        print(f"{'='*70}")
        print(f"DEBUG: Checking ANTHROPIC_API_KEY environment variable")
        print(f"  Value exists: {bool(api_key)}")
        print(f"  Value length: {len(api_key) if api_key else 0}")
        if api_key:
            print(f"  First 30 chars: {api_key[:30]}...")
            print(f"  ✅ API Key found and accessible")
        else:
            print(f"  ❌ Value is NONE/EMPTY")
        print(f"{'='*70}\n")
        
        # Validate API key
        if not api_key or api_key.strip() == "":
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is empty or not set. "
                "Please add it to Heroku Config Vars (Settings → Reveal Config Vars) "
                "and restart the dyno."
            )
        
        print(f"✅ API Key initialized successfully")
        
        # Initialize AsyncAnthropic client
        try:
            self.client = AsyncAnthropic(api_key=api_key)
            print(f"✅ AsyncAnthropic client created successfully\n")
        except Exception as e:
            print(f"❌ ERROR creating AsyncAnthropic client: {str(e)}")
            print(f"This may indicate the API key is invalid or Anthropic API is unreachable")
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
        # Build metadata context from dynamic variables
        metadata_context = ""
        if request.retell_llm_dynamic_variables:
            print(f"✅ Dynamic variables received: {len(request.retell_llm_dynamic_variables)} items")
            
            metadata_context = "\n## PROVIDER & PLAN INFORMATION:\n"
            variables = request.retell_llm_dynamic_variables
            provider_name = variables.get('provider_name', 'Not provided')
            npi_number = variables.get('npi_number', 'Not provided')
            tax_id = variables.get('tax_id', 'Not provided')
            specialty = variables.get('specialty', 'Not provided')
            line_of_business = variables.get('line_of_business', 'Not provided')
            scenario_type = variables.get('scenario_type', 'Not provided')
            payer = variables.get('payer', 'Not provided')
            organization_name = variables.get('organization_name', 'Not provided')
            
            metadata_context += f"Provider/Organization Name: {provider_name}\n"
            metadata_context += f"NPI Number: {npi_number}\n"
            metadata_context += f"Tax ID: {tax_id}\n"
            metadata_context += f"Specialty: {specialty}\n"
            metadata_context += f"Line of Business: {line_of_business}\n"
            metadata_context += f"Insurance Plan: {payer}\n"
            metadata_context += f"\n## CRITICAL - WHICH IDENTIFIER TO USE:\n"
            if scenario_type == 'Existing State':
                metadata_context += f"✓ EXISTING STATE: Organization is already in-network in other states.\n"
                metadata_context += f"  ACTION: Provide the TAX ID when asked for verification.\n"
                metadata_context += f"  TAX ID: {tax_id}\n"
            else:
                metadata_context += f"✓ NEW STATE EXPANSION: Organization is entering this state for the first time.\n"
                metadata_context += f"  ACTION: Provide the NPI when asked for verification.\n"
                metadata_context += f"  NPI: {npi_number}\n"
        else:
            print("⚠️  No dynamic variables received from call_details")

        # ========== IMPROVED: Better system prompt for panel status verification ==========
        system_prompt = f'''## OBJECTIVE
You are calling a health insurance company's credentialing department to determine if they are ACCEPTING NEW PROVIDERS on their panel. Your goal is to gather information about panel status for a specific provider and insurance plan.

{metadata_context}

## YOUR MISSION
Get a clear answer: Is the {payer if variables.get('payer') else 'insurance'} panel OPEN or CLOSED for {provider_name if variables.get('provider_name') else 'this provider'}?

## CONVERSATION FLOW
1. **Introduce yourself professionally** - Brief, friendly, and direct
2. **Provide provider information** - Share the appropriate identifier (NPI or Tax ID based on scenario)
3. **Confirm all details** - Specialty, state, line of business, and other relevant info
4. **Get the panel status** - Ask directly: "Is the panel currently accepting new providers?"
5. **Clarify if needed** - Ask about specific LOBs or service areas if unclear
6. **Get confirmation** - Request a reference number for this inquiry
7. **End professionally** - Thank them and close the call

## COMMUNICATION STYLE
- **Be Professional but Friendly**: Sound like a real credentialing coordinator, not a robot
- **Be Clear and Concise**: Get to the point quickly. Sentences should be short (under 10 words)
- **Be Efficient**: Insurance staff are busy - respect their time
- **Be Prepared**: Know your provider details cold and have answers ready
- **Listen Actively**: Pay attention to what they say and respond directly to it
- **Verify Details**: Confirm everything you hear to avoid misunderstandings

## HANDLING COMMON RESPONSES
- If they ask "Which provider?" → State the provider name and specialty clearly
- If they ask "What's your provider number?" → Give either NPI or Tax ID (based on scenario type)
- If they ask "Which state?" → Provide the relevant state/states
- If panel is CLOSED → Ask about timing: "When might the panel reopen?" or "Is there a waitlist?"
- If panel is OPEN → Ask about next steps: "What's the credentialing process?" or "How long does it take?"
- If they transfer you → Thank them and repeat your request to the new person

## KEY INFORMATION TO COLLECT
✓ Confirmed panel status (OPEN/CLOSED/WAITLIST)
✓ Effective date of status (when it opened/closed)
✓ Any limitations (specific specialties, geographic areas)
✓ Reference number for this inquiry
✓ Contact info or next steps if applicable

## TONE & PERSONALITY
- Confident and professional
- Respectful of their expertise
- Patient if they need to look things up
- Friendly but business-focused
- Clear in your objectives

## IMPORTANT REMINDERS
- Do NOT be pushy or demanding
- Do NOT argue about policies
- Do NOT sound uncertain about provider information
- Do NOT accept vague answers - push for clarity on OPEN vs CLOSED
- Do accept that sometimes they need to transfer you or call you back'''

        transcript_messages = self.convert_transcript_to_anthropic_messages(
            request.transcript
        )

        if request.interaction_type == "reminder_required":
            transcript_messages.append(
                {
                    "role": "user",
                    "content": "(The user hasn't responded in a while. Generate a polite follow-up prompt to get their attention.)",
                }
            )

        return system_prompt, transcript_messages

    async def draft_response(self, request: ResponseRequiredRequest):
        try:
            system_prompt, messages = self.prepare_prompt(request)
            
            print(f"\n📞 CALLING CLAUDE API")
            print(f"Model: claude-opus-4-1")
            print(f"Max tokens: 150")
            print(f"System prompt length: {len(system_prompt)} chars")
            print(f"Messages: {len(messages)} turns")
            
            # ========== UPDATED: Using claude-opus-4-1 instead of 20241022 ==========
            stream = await self.client.messages.create(
                model="claude-opus-4-1",
                max_tokens=150,
                system=system_prompt,
                messages=messages,
                stream=True,
            )
            
            print(f"✅ Claude API stream started successfully\n")
            
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

            # Send final response signaling completion
            response = ResponseResponse(
                response_id=request.response_id,
                content="",
                content_complete=True,
                end_call=False,
            )
            yield response
            
        except Exception as e:
            print(f"\n❌ ERROR in draft_response: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            
            # Send error fallback response
            response = ResponseResponse(
                response_id=request.response_id,
                content="I apologize, I'm experiencing a technical issue. Could you please repeat that?",
                content_complete=True,
                end_call=False,
            )
            yield response
