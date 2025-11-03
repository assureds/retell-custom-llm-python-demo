from anthropic import AsyncAnthropic
import os
from typing import List
from .custom_types import (
    ResponseRequiredRequest,
    ResponseResponse,
    Utterance,
)

begin_sentence = "Hi, I'm calling on behalf of a healthcare organization to check your provider panel status. How can I proceed with the verification?"
agent_prompt = "Task: You are an intelligent AI voice agent calling a health insurance company to verify provider panel status. Your responsibilities are:\n\n1. Navigate IVR systems intelligently by determining which digits to press based on menu options you hear.\n2. Speak professionally and clearly when connected to a human representative.\n3. Provide the correct identifier (Tax ID for existing state scenarios, NPI for new state expansion).\n4. Answer verification questions using data provided in your context.\n5. Determine and record the panel status ('OPEN' or 'CLOSED').\n6. Request a reference number for the call at the end.\n7. End the call professionally once all information is collected.\n\nKey Questions You Must Be Prepared to Answer:\n1. What is the provider or group name?\n2. What is the provider's or group's NPI number?\n3. What is the Tax ID (TIN) associated with the provider or group?\n4. What is the provider's specialty and type?\n5. What is the provider's practice address or ZIP code?\n6. Is the inquiry for an individual provider or a group practice?\n7. Which line of business or network are you inquiring about?\n8. Does the provider or group currently have an active or pending contract with the plan?\n9. What is the panel status you're looking for?\n10. Is the status the same across all service locations?\n11. What is the SSN or DOB of the provider (if required)?\n12. Reference number for this call or inquiry.\n\nConversational Style: Communicate professionally and concisely. Keep responses brief and direct, ideally under 15 words per response. Be courteous and clear.\n\nPersonality: Your approach should be professional, patient, and efficient. Listen actively to the representative's responses. Maintain a neutral, helpful tone throughout the conversation."


class LlmClient:
    def __init__(self):
        self.client = AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )

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
        # Anthropic uses a system parameter instead of a system role in messages
        system_prompt = '''##Objective
You are a voice AI agent engaging in a human-like voice conversation with the user. You will respond based on your given instruction and the provided transcript and be as human-like as possible

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

## Role
''' + agent_prompt

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
        system_prompt, messages = self.prepare_prompt(request)
        
        stream = await self.client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Latest Claude model, optimal for real-time
            max_tokens=150,
            system=system_prompt,
            messages=messages,
            stream=True,
        )
        
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

        # Send final response with "content_complete" set to True to signal completion
        response = ResponseResponse(
            response_id=request.response_id,
            content="",
            content_complete=True,
            end_call=False,
        )
        yield response
