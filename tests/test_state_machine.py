"""
Unit tests and regression test suite for Flow Chat Classifier,
UI Observer, and State Machine Decision Engine.
"""
import pytest
from automation.flow.chat_classifier import (
    is_duration_followup_question,
    classify_agent_message,
    AgentMessageType
)
from automation.flow.ui_observer import FlowUISnapshot
from automation.flow.state_machine import (
    FlowDecisionEngine,
    FlowDecisionAction,
    GenerationLifecycleState
)

def test_plain_8_seconds_is_not_duration_question():
    assert is_duration_followup_question("8 saniye") is False
    assert is_duration_followup_question("8 seconds") is False
    assert classify_agent_message("8 saniye") == AgentMessageType.GENERIC_INFO

def test_ready_messages_are_not_duration_questions():
    msg1 = "8 saniyelik videonuz başarıyla üretildi ve hazır durumda. Ekranınızdan oynatabilirsiniz."
    msg2 = "Videonuz hazır! Sol taraftaki panelde veya ana ekranda izleyebilirsiniz."
    msg3 = "Your video is ready. You can download it now."

    assert is_duration_followup_question(msg1) is False
    assert is_duration_followup_question(msg2) is False
    assert is_duration_followup_question(msg3) is False

    assert classify_agent_message(msg1) == AgentMessageType.MEDIA_READY_MESSAGE
    assert classify_agent_message(msg2) == AgentMessageType.MEDIA_READY_MESSAGE
    assert classify_agent_message(msg3) == AgentMessageType.MEDIA_READY_MESSAGE

def test_progress_messages_classified_correctly():
    msg1 = "Videonuz hâlâ hazırlanıyor. Kısa bir süre sonra tekrar kontrol edebilirsiniz."
    msg2 = "Üretim devam ediyor, birazdan hazır olacaktır."
    msg3 = "Video generation is in progress."

    assert is_duration_followup_question(msg1) is False
    assert classify_agent_message(msg1) == AgentMessageType.GENERATION_PROGRESS
    assert classify_agent_message(msg2) == AgentMessageType.GENERATION_PROGRESS
    assert classify_agent_message(msg3) == AgentMessageType.GENERATION_PROGRESS

def test_real_duration_questions_classified_correctly():
    tr_q = "Varsayılan video modelimiz olan Omni Flash 5 saniyeyi desteklememektedir. 4 saniye, 6 saniye, 8 saniye, 10 saniye. Hangi süreyi tercih edersiniz?"
    en_q = "Which duration do you prefer? 4 seconds, 6 seconds, 8 seconds, or 10 seconds."

    assert is_duration_followup_question(tr_q) is True
    assert is_duration_followup_question(en_q) is True
    assert classify_agent_message(tr_q) == AgentMessageType.DURATION_QUESTION
    assert classify_agent_message(en_q) == AgentMessageType.DURATION_QUESTION

def test_decision_engine_answers_duration_only_once():
    engine = FlowDecisionEngine()

    snapshot_question = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow/project/123",
        latest_new_agent_messages=["Hangi süreyi tercih edersiniz? 4 saniye, 6 saniye, 8 saniye."],
        latest_agent_message_type=AgentMessageType.DURATION_QUESTION,
        stop_button_visible=False,
        video_artifact_count=0
    )

    action1 = engine.decide_next_action(snapshot_question)
    assert action1 == FlowDecisionAction.ANSWER_DURATION_ONCE
    assert engine.duration_followup_answered is True

    # Next poll with same/repeating question must NOT answer again!
    action2 = engine.decide_next_action(snapshot_question)
    assert action2 == FlowDecisionAction.WAIT

def test_decision_engine_transitions_to_media_ready_on_video():
    engine = FlowDecisionEngine()

    snapshot_video = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow/project/123",
        latest_new_agent_messages=["8 saniyelik videonuz başarıyla üretildi."],
        latest_agent_message_type=AgentMessageType.MEDIA_READY_MESSAGE,
        stop_button_visible=False,
        video_artifact_count=1,
        new_video_artifact_detected=True,
        download_button_visible=True
    )

    action = engine.decide_next_action(snapshot_video)
    assert action == FlowDecisionAction.DOWNLOAD_MEDIA
    assert engine.state == GenerationLifecycleState.MEDIA_READY

def test_stop_button_forces_wait():
    engine = FlowDecisionEngine()

    snapshot_stop = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow/project/123",
        latest_new_agent_messages=[],
        latest_agent_message_type=AgentMessageType.UNKNOWN,
        stop_button_visible=True,
        video_artifact_count=0
    )

    action = engine.decide_next_action(snapshot_stop)
    assert action == FlowDecisionAction.WAIT
    assert engine.state == GenerationLifecycleState.MEDIA_GENERATING

def test_exact_bug_regression_sequence():
    """
    Simulate the exact user bug sequence:
    1. Duration question -> Answer once
    2. Repeated duration echoes -> WAIT
    3. Progress messages -> WAIT
    4. Ready message -> MEDIA_READY -> DOWNLOAD
    """
    engine = FlowDecisionEngine()
    actions_taken = []

    # Turn 1: Duration Question
    s1 = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow",
        latest_agent_message_type=AgentMessageType.DURATION_QUESTION,
        stop_button_visible=False
    )
    actions_taken.append(engine.decide_next_action(s1))

    # Turn 2: Echo of '8 saniye' in chat
    s2 = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow",
        latest_agent_message_type=AgentMessageType.GENERIC_INFO,
        stop_button_visible=True
    )
    actions_taken.append(engine.decide_next_action(s2))

    # Turn 3: "Videonuz hazırlanıyor"
    s3 = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow",
        latest_agent_message_type=AgentMessageType.GENERATION_PROGRESS,
        stop_button_visible=True
    )
    actions_taken.append(engine.decide_next_action(s3))

    # Turn 4: "Videonuz hazır!" + Video artifact
    s4 = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow",
        latest_agent_message_type=AgentMessageType.MEDIA_READY_MESSAGE,
        video_artifact_count=1,
        new_video_artifact_detected=True,
        download_button_visible=True
    )
    actions_taken.append(engine.decide_next_action(s4))

    assert actions_taken == [
        FlowDecisionAction.ANSWER_DURATION_ONCE,
        FlowDecisionAction.WAIT,
        FlowDecisionAction.WAIT,
        FlowDecisionAction.DOWNLOAD_MEDIA
    ]
    assert actions_taken.count(FlowDecisionAction.ANSWER_DURATION_ONCE) == 1
