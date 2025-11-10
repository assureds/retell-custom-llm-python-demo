if (
    request_json["interaction_type"] == "response_required"
    or request_json["interaction_type"] == "reminder_required"
):
    response_id = request_json["response_id"]
    request = ResponseRequiredRequest(
        interaction_type=request_json["interaction_type"],
        response_id=response_id,
        transcript=request_json["transcript"],
        retell_llm_dynamic_variables=request_json.get("retell_llm_dynamic_variables"),  # ADD THIS LINE
    )
    print(
        f"""Received interaction_type={request_json['interaction_type']}, response_id={response_id}, last_transcript={request_json['transcript'][-1]['content']}"""
    )

    async for event in llm_client.draft_response(request):
        await websocket.send_json(event.__dict__)
        if request.response_id < response_id:
            break  # new response needed, abandon this one
