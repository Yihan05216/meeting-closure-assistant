"""Editable meeting presets; roles do not imply speaker identities."""

MEETING_TEMPLATES = {
    "Product Launch Decision Meeting": {
        "meeting_type": "Product / Decision Meeting",
        "meeting_goal": "Decide whether to launch the product, confirm launch conditions and remaining task owners, and resolve any decision-making gaps before ending the meeting.",
        "agenda": "1. Review launch readiness.\n2. Confirm the launch date and conditions.\n3. Assign owners and deadlines for remaining tasks.\n4. Discuss pricing and follow-up needs.",
        "required_roles": "Product lead\nEngineering lead\nMarketing lead",
        "must_have_checks": "Establish current product readiness and remaining work.\nConfirm the launch decision, target date, and any conditions.\nAssign owners and deadlines for remaining launch tasks.\nAssign who decides whether to postpone if launch conditions fail.",
        "should_have_checks": "Agree how user feedback will be collected and reviewed.",
        "reference_checks": "Record longer-term pricing ideas or follow-up plans without requiring a final pricing decision today."
    },
    "Project Retrospective": {
        "meeting_type": "Project Retrospective",
        "meeting_goal": "Review the completed project, establish lessons from successes and difficulties, and agree practical improvements for the next project.",
        "agenda": "1. Review project outcomes against goals.\n2. Discuss what worked and what did not.\n3. Identify contributing factors and lessons.\n4. Agree improvement actions and follow-up.",
        "required_roles": "Project lead\nDelivery team representative\nStakeholder representative",
        "must_have_checks": "Establish the main project outcomes and gaps against goals.\nCapture lessons from both successes and difficulties.\nAgree improvement actions with owners and follow-up dates.",
        "should_have_checks": "Record differing perspectives or uncertainties about contributing factors.\nAgree how to assess whether the improvements helped.",
        "reference_checks": "Record ideas outside the next project's scope for future consideration."
    },
    "Client Progress Meeting": {
        "meeting_type": "Client Progress Meeting",
        "meeting_goal": "Align with the client on delivery progress, clarify feedback and dependencies, and agree the next milestone and responsibilities.",
        "agenda": "1. Review delivery progress and the current milestone.\n2. Hear client feedback and concerns.\n3. Discuss scope changes, blockers, and dependencies.\n4. Confirm next steps, owners, and dates.",
        "required_roles": "Client representative\nAccount lead\nDelivery lead",
        "must_have_checks": "Establish shared understanding of delivery progress.\nCapture the client's feedback or explicitly record that it is unavailable.\nAgree the next milestone and actions with owners and dates.\nClarify ownership and follow-up for dependencies affecting the next milestone.",
        "should_have_checks": "Clarify the impact of requested scope changes.\nAgree the next client check-in.",
        "reference_checks": "Record future opportunities outside the current delivery scope."
    }
}
