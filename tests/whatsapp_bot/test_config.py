from whatsapp_bot.config import WaConfig


def test_twilio_rest_config_reads_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_MESSAGING_SERVICE_SID", "MG_test")
    monkeypatch.setenv("WA_CT_WELCOME", "HX_welcome")
    monkeypatch.setenv("WA_CT_BACK_TO_MENU", "HX_back")
    assert WaConfig.TWILIO_ACCOUNT_SID == "AC_test"
    assert WaConfig.TWILIO_MESSAGING_SERVICE_SID == "MG_test"
    assert WaConfig.WA_CT_WELCOME == "HX_welcome"
    assert WaConfig.WA_CT_BACK_TO_MENU == "HX_back"
