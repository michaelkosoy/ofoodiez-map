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

def test_media_automation_e2e():
    print("🚀 Starting Instagram Automation Phase 5 Media Verification...")
    
    # Configure test environment
    app.config['TESTING'] = True
    client = app.test_client()

    with app.app_context():
        # Setup clean test records
        print("🧹 Cleaning existing test records...")
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

    # Set up session for client requests
    with client.session_transaction() as sess:
        sess['ig_user_id'] = user_id

    # 2. Test fetching media endpoint (GET /ig/api/media)
    print("\n📷 Testing GET /ig/api/media (mock items since we are using test_token)...")
    resp = client.get('/ig/api/media')
    assert resp.status_code == 200, f"Failed to get media: {resp.data}"
    media_items = json.loads(resp.data.decode('utf-8'))
    assert len(media_items) > 0, "No mock media returned"
    print(f"   ✅ Retrieved {len(media_items)} mock media items successfully.")

    # 3. Create a Specific-Post Automation via the API
    print("\n⚡ Creating a post-specific comment automation via API...")
    payload_specific = {
        "name": "Falafel Post Automation",
        "trigger_type": "comment_keyword",
        "trigger_config": {
            "keywords": ["crispy", "falafel"],
            "media_id": "mock_media_1"
        },
        "actions": [
            {
                "type": "send_private_reply",
                "text": "Here is the recipe for the crispy falafel: https://ofoodiez.com/falafel"
            }
        ],
        "is_active": True
    }
    resp = client.post('/ig/api/automations', 
                        data=json.dumps(payload_specific), 
                        content_type='application/json')
    assert resp.status_code == 201, f"Failed to create automation: {resp.data}"
    specific_data = json.loads(resp.data.decode('utf-8'))
    specific_id = specific_data['automation']['id']
    print(f"   ✅ Created post-specific automation ID: {specific_id}")

    # 4. Create an All-Posts Automation via the API
    print("\n⚡ Creating an all-posts comment automation via API...")
    payload_all = {
        "name": "General Yummy Automation",
        "trigger_type": "comment_keyword",
        "trigger_config": {
            "keywords": ["yummy"],
            "media_id": None
        },
        "actions": [
            {
                "type": "send_private_reply",
                "text": "Glad you like our food! Check out our website: https://ofoodiez.com"
            }
        ],
        "is_active": True
    }
    resp = client.post('/ig/api/automations', 
                        data=json.dumps(payload_all), 
                        content_type='application/json')
    assert resp.status_code == 201, f"Failed to create general automation: {resp.data}"
    all_data = json.loads(resp.data.decode('utf-8'))
    all_id = all_data['automation']['id']
    print(f"   ✅ Created general automation ID: {all_id}")

    # 5. Test editing an automation via API
    print("\n⚡ Testing update/edit automation API...")
    edit_payload = {
        "name": "Crispy Falafel Recipe Automation",
        "trigger_config": {
            "keywords": ["crispy", "falafel", "recipe"],
            "media_id": "mock_media_1"
        }
    }
    resp = client.put(f'/ig/api/automations/{specific_id}', 
                       data=json.dumps(edit_payload), 
                       content_type='application/json')
    assert resp.status_code == 200, f"Failed to edit automation: {resp.data}"
    
    with app.app_context():
        updated_auto = Automation.query.get(specific_id)
        assert updated_auto.name == "Crispy Falafel Recipe Automation", "Name update failed"
        assert "recipe" in updated_auto.trigger_config.get("keywords", []), "Keywords update failed"
        assert updated_auto.trigger_config.get("media_id") == "mock_media_1", "media_id update failed"
        print("   ✅ Successfully verified edited attributes in database.")

    # Helper for webhook request payload and signature
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

    # 6. Simulate webhook: keyword MATCH, but media_id does NOT MATCH
    print("\n📨 Webhook Simulation A: Keyword Matches, but media_id does NOT match (Different post)...")
    comment_payload_a = {
        "object": "instagram",
        "entry": [
            {
                "id": "test_ig_user",
                "time": int(datetime.utcnow().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_id_101",
                            "text": "Give me the recipe for this crispy falafel!",
                            "from": {
                                "id": "test_igsid_301",
                                "username": "customer_a"
                            },
                            "media": {
                                "id": "mock_media_2",  # Different post
                                "media_product_type": "REELS"
                            }
                        }
                    }
                ]
            }
        ]
    }
    resp = send_webhook_post(comment_payload_a)
    assert resp.status_code == 200
    
    with app.app_context():
        # Check if contact is created (in webhooks.py, contact is created inside the matching loop, so customer_a should NOT exist in DB since no automation matched)
        contact_a = Contact.query.filter_by(igsid="test_igsid_301").first()
        assert contact_a is None, "Contact should not be created because specific-post automation did not match"
        print("   ✅ Webhook A correctly did NOT trigger automation (Post ID mismatched).")

    # 7. Simulate webhook: keyword MATCH and media_id MATCH
    print("\n📨 Webhook Simulation B: Keyword Matches and media_id Matches (Specific post)...")
    comment_payload_b = {
        "object": "instagram",
        "entry": [
            {
                "id": "test_ig_user",
                "time": int(datetime.utcnow().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_id_102",
                            "text": "I want that crispy falafel recipe!",
                            "from": {
                                "id": "test_igsid_302",
                                "username": "customer_b"
                            },
                            "media": {
                                "id": "mock_media_1",  # Correct post
                                "media_product_type": "REELS"
                            }
                        }
                    }
                ]
            }
        ]
    }
    resp = send_webhook_post(comment_payload_b)
    assert resp.status_code == 200
    
    with app.app_context():
        contact_b = Contact.query.filter_by(igsid="test_igsid_302").first()
        assert contact_b is not None, "Contact customer_b should be created"
        convo_b = Conversation.query.filter_by(contact_id=contact_b.id).first()
        assert convo_b is not None
        logs = MessageLog.query.filter_by(conversation_id=convo_b.id).all()
        assert len(logs) == 1
        assert "recipe for the crispy falafel" in logs[0].content["text"]
        print("   ✅ Webhook B successfully triggered specific-post automation.")

    # 8. Simulate webhook: general keyword MATCH (All-posts automation)
    print("\n📨 Webhook Simulation C: General Keyword Matches (Targeting All posts)...")
    comment_payload_c = {
        "object": "instagram",
        "entry": [
            {
                "id": "test_ig_user",
                "time": int(datetime.utcnow().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_id_103",
                            "text": "This looks so yummy!",
                            "from": {
                                "id": "test_igsid_303",
                                "username": "customer_c"
                            },
                            "media": {
                                "id": "mock_media_3",  # Any post
                                "media_product_type": "REELS"
                            }
                        }
                    }
                ]
            }
        ]
    }
    resp = send_webhook_post(comment_payload_c)
    assert resp.status_code == 200
    
    with app.app_context():
        contact_c = Contact.query.filter_by(igsid="test_igsid_303").first()
        assert contact_c is not None, "Contact customer_c should be created"
        convo_c = Conversation.query.filter_by(contact_id=contact_c.id).first()
        assert convo_c is not None
        logs = MessageLog.query.filter_by(conversation_id=convo_c.id).all()
        assert len(logs) == 1
        assert "Glad you like our food" in logs[0].content["text"]
        print("   ✅ Webhook C successfully triggered general-post automation on a different post.")

    print("\n🎉 ALL PHASE 5 MEDIA DISCOVERY & POST-SPECIFIC AUTOMATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_media_automation_e2e()
