import os
import sys
import json
import hmac
import hashlib
from datetime import datetime, timedelta

# Ensure the root of the project is in the path
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from app import app
from instagram_automation.database import db, User, Automation, Contact, Conversation, MessageLog
from instagram_automation.config import Config

def test_ig_automation_e2e():
    print("🚀 Starting Instagram Automation Phase 4 Verification...")
    
    # Configure test environment
    app.config['TESTING'] = True
    client = app.test_client()

    with app.app_context():
        # Setup clean test records
        print("🧹 Cleaning existing test records...")
        # Clean up database
        MessageLog.query.delete()
        Conversation.query.delete()
        Contact.query.delete()
        Automation.query.delete()
        User.query.delete()
        db.session.commit()

        # 1. Create a Test User
        print("👤 Creating test user...")
        test_user = User(
            ig_user_id='test_ig_user',
            ig_username='tester_account',
            access_token='test_token_123',
            token_expires_at=datetime.utcnow() + timedelta(days=60),
            is_active=True
        )
        db.session.add(test_user)
        db.session.commit()
        user_id = test_user.id
        print(f"   Created user ID: {user_id}")

        # 2. Create Automation B (Chained Flow target)
        print("⚡ Creating Automation B (flow target)...")
        auto_b = Automation(
            user_id=user_id,
            name="Flow B: Confirm Chain",
            trigger_type="dm_keyword",
            trigger_config={"keywords": ["CONFIRM_B"]},
            actions=[
                {"type": "send_text", "text": "Success! Flow B chained successfully for {{username}}!"},
                {"type": "add_tag", "tag": "CHAINED_SUCCESS"}
            ],
            is_active=True
        )
        db.session.add(auto_b)
        db.session.commit()
        auto_b_id = auto_b.id
        print(f"   Created Automation B ID: {auto_b_id}")

        # 3. Create Automation A (Initial Comment Trigger)
        print("⚡ Creating Automation A (initial trigger with buttons)...")
        auto_a = Automation(
            user_id=user_id,
            name="Flow A: Initial Comment",
            trigger_type="comment_keyword",
            trigger_config={"keywords": ["START"]},
            actions=[
                {
                    "type": "send_button_template", 
                    "text": "Hey {{username}}! Click the button below to trigger flow B.", 
                    "buttons": [
                        {
                            "type": "postback",
                            "title": "Trigger B",
                            "payload": f"TRIGGER_AUTO_{auto_b_id}"
                        },
                        {
                            "type": "web_url",
                            "title": "Open oFoodiez",
                            "url": "https://ofoodiez.com"
                        }
                    ]
                }
            ],
            is_active=True
        )
        db.session.add(auto_a)
        db.session.commit()
        auto_a_id = auto_a.id
        print(f"   Created Automation A ID: {auto_a_id}")

    # Helpers for webhook request payload and signature
    def send_webhook_post(payload):
        body_bytes = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if Config.META_APP_SECRET:
            sig = hmac.new(
                Config.META_APP_SECRET.encode('utf-8'),
                body_bytes,
                hashlib.sha256
            ).hexdigest()
            headers['X-Hub-Signature-256'] = f'sha256={sig}'
        return client.post('/ig/webhook', data=body_bytes, headers=headers)

    # 4. Simulate a Comment Event (fires Automation A)
    print("\n📨 Simulating comment webhook ('START' keyword)...")
    comment_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "test_ig_user",
                "time": int(datetime.utcnow().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_id_111",
                            "text": "Start the demo",
                            "from": {
                                "id": "test_igsid_999",
                                "username": "jane_doe"
                            },
                            "media": {
                                "id": "media_id_222",
                                "media_product_type": "REELS"
                            }
                        }
                    }
                ]
            }
        ]
    }
    
    resp = send_webhook_post(comment_payload)
    assert resp.status_code == 200, f"Webhook comment simulation failed: {resp.data}"
    print("✅ Comment webhook handled with HTTP 200")

    # Verify database side effects of Automation A
    with app.app_context():
        contact = Contact.query.filter_by(igsid="test_igsid_999").first()
        assert contact is not None, "Contact jane_doe was not created"
        assert contact.username == "jane_doe", "Contact username mismatch"
        print("✅ Contact 'jane_doe' successfully created in DB")

        convo = Conversation.query.filter_by(contact_id=contact.id).first()
        assert convo is not None, "Conversation was not created"
        assert convo.is_window_open() is True, "24h messaging window should be open"
        print("✅ Conversation thread initialized with active 24h window")

        # Check logged messages
        logs = MessageLog.query.filter_by(conversation_id=convo.id).all()
        assert len(logs) == 1, f"Expected 1 logged message, got {len(logs)}"
        assert logs[0].message_type == "button_template", f"Expected button_template type, got {logs[0].message_type}"
        assert logs[0].content["buttons"][0]["payload"] == f"TRIGGER_AUTO_{auto_b_id}", "Button payload mismatch"
        print("✅ MessageLog correctly recorded the outgoing button template message")
        convo_id = convo.id
        contact_id = contact.id

    # 5. Simulate Postback Click (fires Automation B via Chaining)
    print("\n🔘 Simulating button click postback webhook...")
    postback_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "test_ig_user",
                "time": int(datetime.utcnow().timestamp()),
                "messaging": [
                    {
                        "sender": {"id": "test_igsid_999"},
                        "recipient": {"id": "test_ig_user"},
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "postback": {
                            "title": "Trigger B",
                            "payload": f"TRIGGER_AUTO_{auto_b_id}"
                        }
                    }
                ]
            }
        ]
    }

    resp = send_webhook_post(postback_payload)
    assert resp.status_code == 200, f"Webhook postback simulation failed: {resp.data}"
    print("✅ Postback webhook handled with HTTP 200")

    # Verify side effects of Automation B
    with app.app_context():
        contact = Contact.query.get(contact_id)
        assert "CHAINED_SUCCESS" in contact.tags, "Tag CHAINED_SUCCESS was not added to contact"
        print("✅ Contact tag 'CHAINED_SUCCESS' successfully added")

        logs = MessageLog.query.filter_by(conversation_id=convo_id).all()
        # Should now have 2 messages: the button template (outgoing) and the text message (outgoing)
        assert len(logs) == 2, f"Expected 2 logged messages, got {len(logs)}"
        assert logs[1].message_type == "text", f"Expected text message type, got {logs[1].message_type}"
        assert "Success! Flow B chained successfully" in logs[1].content["text"], f"Message content mismatch: {logs[1].content}"
        print("✅ Flow B successfully chained and logged target text response")

    # 6. Test Live Chat APIs
    print("\n📥 Testing Live Chat Dashboard APIs...")

    # Log in test client to bypass _require_login
    # We can inject user_id into session
    with client.session_transaction() as sess:
        sess['ig_user_id'] = user_id

    # A. GET /ig/api/inbox
    print("   Testing GET /ig/api/inbox...")
    resp = client.get('/ig/api/inbox')
    assert resp.status_code == 200, f"GET /ig/api/inbox failed: {resp.data}"
    inbox_data = json.loads(resp.data.decode('utf-8'))
    assert len(inbox_data) == 1, f"Expected 1 conversation, got {len(inbox_data)}"
    assert inbox_data[0]['id'] == convo_id, "Inbox conversation ID mismatch"
    assert inbox_data[0]['is_window_open'] is True, "Window status mismatch in API"
    assert "CHAINED_SUCCESS" in inbox_data[0]['contact']['tags'], "Contact tags missing in API"
    print("   ✅ GET /ig/api/inbox returns correct structure and tags")

    # B. GET /ig/api/inbox/<convo_id>/messages
    print(f"   Testing GET /ig/api/inbox/{convo_id}/messages...")
    resp = client.get(f'/ig/api/inbox/{convo_id}/messages')
    assert resp.status_code == 200, f"GET messages failed: {resp.data}"
    messages_data = json.loads(resp.data.decode('utf-8'))
    assert len(messages_data) == 2, f"Expected 2 messages, got {len(messages_data)}"
    assert messages_data[0]['message_type'] == 'button_template'
    assert messages_data[1]['message_type'] == 'text'
    print("   ✅ GET messages timeline returns complete history")

    # C. POST /ig/api/inbox/<convo_id>/send (Manual chat reply)
    print(f"   Testing POST /ig/api/inbox/{convo_id}/send...")
    # Note: we use 'test_token_123' which allows fallback mock message ID
    resp = client.post(f'/ig/api/inbox/{convo_id}/send', 
                       data=json.dumps({"text": "Hi from live support! 👋"}), 
                       content_type='application/json')
    assert resp.status_code == 200, f"Send message failed: {resp.data}"
    send_data = json.loads(resp.data.decode('utf-8'))
    assert send_data['success'] is True, "Expected success: True"
    assert send_data['message']['content']['text'] == "Hi from live support! 👋"
    print("   ✅ POST send message successfully logged manual reply (bypassing Meta API via mock token)")

    # D. POST /ig/api/contacts/<contact_id>/update (Update profile details & tags)
    print(f"   Testing POST /ig/api/contacts/{contact_id}/update...")
    update_payload = {
        "email": "jane@example.com",
        "phone": "+15550199",
        "tags": ["CHAINED_SUCCESS", "VIP_CUSTOMER"]
    }
    resp = client.post(f'/ig/api/contacts/{contact_id}/update',
                       data=json.dumps(update_payload),
                       content_type='application/json')
    assert resp.status_code == 200, f"Update contact failed: {resp.data}"
    update_data = json.loads(resp.data.decode('utf-8'))
    assert update_data['success'] is True
    assert update_data['contact']['email'] == "jane@example.com"
    assert update_data['contact']['phone'] == "+15550199"
    assert "VIP_CUSTOMER" in update_data['contact']['tags']
    print("   ✅ POST update contact successfully saved email, phone, and tags")

    # Verify updates in database
    with app.app_context():
        contact = Contact.query.get(contact_id)
        assert contact.email == "jane@example.com"
        assert contact.phone == "+15550199"
        assert "VIP_CUSTOMER" in contact.tags
        print("✅ Contact updates persistent in Database")

    print("\n🎉 ALL E2E VERIFICATION TESTS PASSED SUCCESSFULLY! Phase 4 features are fully operational.")

if __name__ == "__main__":
    test_ig_automation_e2e()
