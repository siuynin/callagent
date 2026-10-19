import time

from conftest import silence, tone

from gateway.metrics import CallRecorder


def test_false_confirm_flagged_before_tool_success(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_output_transcript("Dạ em đã đặt ")
    rec.on_output_transcript("lịch cho anh lúc 3 giờ")
    assert len(rec.false_confirms) == 1
    assert rec.false_confirms[0]["tool"] == "create_appointment"


def test_confirm_after_tool_success_is_fine(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_tool_call("1", "create_appointment", {})
    rec.on_tool_result("1", "create_appointment", {"status": "ok"})
    rec.on_output_transcript("Em đã đặt xong lịch lái thử")
    assert rec.false_confirms == []


def test_failed_tool_does_not_unlock_confirmation(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_tool_result("1", "create_appointment", {"status": "slot_unavailable"})
    rec.on_output_transcript("em đã chốt lịch")
    assert len(rec.false_confirms) == 1


def test_handoff_claim_detected(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_output_transcript("Em đã kết nối anh với nhân viên")
    assert rec.false_confirms[0]["tool"] == "request_handoff"


def test_neutral_phrases_not_flagged(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_output_transcript("Anh muốn đặt lịch lúc mấy giờ ạ? Em sẽ kiểm tra rồi xác nhận lại.")
    assert rec.false_confirms == []


def test_latency_from_provider_eos(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_speech_ended()
    time.sleep(0.05)
    rec.on_agent_audio()
    rec.on_agent_audio()  # only the first chunk counts
    assert len(rec.latencies_ms) == 1 and 40 <= rec.latencies_ms[0] < 500


def test_latency_falls_back_to_local_vad(settings):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_caller_audio(tone(40))
    time.sleep(0.32)
    rec.on_caller_audio(silence(40))
    rec.on_agent_audio()
    assert rec.events[-1]["eos_source"] == "local"


def test_summary_and_report(settings, tmp_path):
    rec = CallRecorder(settings=settings, mode="test")
    rec.on_usage(100, 70, 30, {"prompt": {"AUDIO": 70}, "response": {"AUDIO": 30}})
    s = rec.summary()
    assert s["cost_estimate"] is None  # prices not configured -> never guess
    path = rec.write(tmp_path)
    assert path.exists()


def test_cost_estimate_when_prices_configured(settings):
    priced = settings.model_copy(
        update={
            "gemini_price_audio_in_per_mtok": 3.0,
            "gemini_price_audio_out_per_mtok": 12.0,
            "gemini_price_text_in_per_mtok": 0.5,
            "gemini_price_text_out_per_mtok": 2.0,
            "usd_to_vnd": 26000.0,
        }
    )
    rec = CallRecorder(settings=priced, mode="test", provider="gemini", model="gemini-3.8-live")
    rec.on_usage(3000, 2000, 1000, {"prompt": {"AUDIO": 2000}, "response": {"AUDIO": 1000}})
    cost = rec.summary()["cost_estimate"]
    assert cost["usd_total"] == round((2000 * 3 + 1000 * 12) / 1e6, 6)
    assert "vnd_per_minute" in cost


def test_empty_env_values_mean_unset(tmp_path):
    from gateway.config import Settings

    env = tmp_path / ".env"
    env.write_text(
        "PRICE_AUDIO_IN_PER_MTOK=\nUSD_TO_VND=\nAI_VOICE=\nAI_PROVIDER=mock   # comment\n", encoding="utf-8"
    )
    s = Settings(_env_file=env)
    assert s.gemini_price_audio_in_per_mtok is None and s.usd_to_vnd is None and s.ai_provider == "mock"
