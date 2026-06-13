"""
Webhook handler for Instagram events.
Receives real-time notifications from Meta when comments, messages, etc. occur.
"""
import hashlib
import hmac
import json
from flask import request, jsonify

from . import ig_bp
from .config import Config
from .models import User
from .automations import engine


@ig_bp.route('/webhook', methods=['GET'])
def webhook_verify():
    """
    Webhook verification handshake.
    Meta sends a GET request when you first configure the webhook URL
    in the App Dashboard. We must return the hub.challenge to verify.
    """
    # Log detailed diagnostics for the incoming GET request
    print(f"🔍 Incoming webhook GET request: URL={request.url}, Args={dict(request.args)}, User-Agent={request.headers.get('User-Agent')}")
    
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == Config.WEBHOOK_VERIFY_TOKEN:
        print(f"✅ Webhook verified successfully")
        return challenge, 200

    print(f"❌ Webhook verification failed: mode={mode}, token={token}")
    return 'Forbidden', 403


@ig_bp.route('/webhook', methods=['POST'])
def webhook_receive():
    """
    Receive incoming webhook events from Meta.
    All Instagram events (comments, messages, postbacks, etc.) come through here.
    """
    print("📥 Webhook POST request received")
    
    # Verify signature if app secret is configured
    if Config.META_APP_SECRET:
        signature = request.headers.get('X-Hub-Signature-256', '')
        print(f"🔑 Verifying signature header: {signature}")
        if not _verify_signature(request.data, signature):
            print("❌ Webhook signature verification failed")
            return 'Unauthorized', 401
        print("✅ Webhook signature verification passed")
    else:
        print("⚠️ META_APP_SECRET not configured. Signature verification skipped.")

    data = request.get_json()
    if not data:
        print("❌ Webhook payload is empty or not JSON")
        return 'Bad Request', 400

    print(f"📦 Webhook Payload: {json.dumps(data)}")

    # Only process Instagram events
    if data.get('object') != 'instagram':
        print(f"  ℹ️ Ignoring non-Instagram event: {data.get('object')}")
        return 'OK', 200

    # Process each entry
    for entry in data.get('entry', []):
        ig_account_id = entry.get('id')
        
        # Find the user in our database
        user = User.query.filter_by(ig_user_id=ig_account_id, is_active=True).first()
        if not user:
            # Print available users in DB for diagnostic purposes
            all_users = User.query.all()
            db_ids = [u.ig_user_id for u in all_users]
            print(f"  ⚠️ Received webhook for unknown/inactive IG account: {ig_account_id}. Registered IDs in DB: {db_ids}")
            continue

        print(f"📨 Webhook event matches registered user @{user.ig_username} (ID: {user.ig_user_id})")

        # Handle comment events (changes array)
        for change in entry.get('changes', []):
            field = change.get('field')
            value = change.get('value', {})

            if field == 'comments':
                print(f"  💬 New comment from @{value.get('from', {}).get('username', '?')}: \"{value.get('text', '')}\"")
                try:
                    engine.process_comment(value, user)
                except Exception as e:
                    print(f"  ❌ Error processing comment: {e}")

            elif field == 'live_comments':
                print(f"  🔴 Live comment from @{value.get('from', {}).get('username', '?')}")
                # Future: handle live comments

            else:
                print(f"  ℹ️ Unhandled change field: {field}")

        # Handle messaging events (messaging array)
        for messaging_event in entry.get('messaging', []):
            try:
                _handle_messaging_event(messaging_event, user)
            except Exception as e:
                print(f"  ❌ Error processing messaging event: {e}")

    # Always return 200 quickly — Meta expects a fast response
    return 'OK', 200


def _handle_messaging_event(event, user):
    """Dispatch a messaging event to the appropriate handler."""
    sender_id = event.get('sender', {}).get('id')

    if not sender_id:
        if 'read' in event:
            print("  👁️ Messages read receipt received")
        else:
            print(f"  ⚠️ Messaging event missing sender_id: {event}")
        return

    # Skip messages sent by ourselves
    if sender_id == user.ig_user_id:
        return

    if 'message' in event:

        # Incoming message (DM, story reply, etc.)
        message = event['message']
        text = message.get('text', '')
        print(f"  📩 DM from {sender_id}: \"{text[:50]}\"")

        # Check if this is a story reply or mention
        if message.get('referral'):
            referral = message['referral']
            print(f"    📎 Referral: {referral.get('type')} - {referral.get('source')}")

        # Check for quick reply click
        quick_reply = message.get('quick_reply', {})
        qr_payload = quick_reply.get('payload', '') if isinstance(quick_reply, dict) else ''
        
        if qr_payload and qr_payload.startswith('TRIGGER_AUTO_'):
            try:
                auto_id = int(qr_payload.split('_')[-1])
                engine.execute_automation_by_id(auto_id, user, sender_id)
            except Exception as e:
                print(f"  ❌ Error executing chained quick-reply automation {qr_payload}: {e}")
        else:
            engine.process_message(event, user)

    elif 'postback' in event:
        # Button click / quick reply postback
        postback = event['postback']
        payload = postback.get('payload', '')
        title = postback.get('title', '')
        print(f"  🔘 Postback from {sender_id}: \"{title}\" (payload: {payload})")
        
        if payload and payload.startswith('TRIGGER_AUTO_'):
            try:
                auto_id = int(payload.split('_')[-1])
                engine.execute_automation_by_id(auto_id, user, sender_id)
            except Exception as e:
                print(f"  ❌ Error executing chained postback automation {payload}: {e}")

    elif 'reaction' in event:
        # Message reaction
        reaction = event['reaction']
        print(f"  ❤️ Reaction from {sender_id}: {reaction.get('reaction')}")

    elif 'read' in event:
        # Message read receipt
        print(f"  👁️ Messages read by {sender_id}")

    else:
        print(f"  ℹ️ Unhandled messaging event type: {list(event.keys())}")


def _verify_signature(payload_body, signature_header):
    """
    Verify the X-Hub-Signature-256 header.
    Meta signs webhook payloads with HMAC-SHA256 using your app secret.
    """
    if not signature_header:
        return False

    if not signature_header.startswith('sha256='):
        return False

    expected_signature = signature_header[7:]  # Remove 'sha256=' prefix
    computed_signature = hmac.new(
        Config.META_APP_SECRET.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)
