"""
Automation engine — matches incoming events against active rules and fires actions.
"""
from datetime import datetime
from .database import db, Automation, Contact, Conversation, MessageLog, User
from .messaging import messenger


class AutomationEngine:
    """Evaluate incoming events against automation rules and execute actions."""

    def process_comment(self, comment_data, user):
        """
        Process an incoming comment event.
        Check if it matches any active comment_keyword automations for this user.
        If so, send a private reply DM.
        
        comment_data: {
            "id": "<COMMENT_ID>",
            "from": {"id": "<IGSID>", "username": "commenter"},
            "text": "LINK please!",
            "media": {"id": "<MEDIA_ID>", "media_product_type": "REELS"}
        }
        """
        automations = Automation.query.filter_by(
            user_id=user.id,
            trigger_type='comment_keyword',
            is_active=True
        ).all()

        if not automations:
            print(f"  ℹ️ No active comment automations for @{user.ig_username}")
            return

        comment_text = (comment_data.get('text') or '').lower().strip()
        comment_id = comment_data.get('id')
        commenter_id = comment_data.get('from', {}).get('id')
        commenter_username = comment_data.get('from', {}).get('username', '')
        media_id = comment_data.get('media', {}).get('id')

        for automation in automations:
            if self._matches_comment_trigger(automation, comment_text, media_id):
                print(f"  🎯 Automation match: \"{automation.name}\" triggered by @{commenter_username}")

                # Update or create contact
                contact = self._get_or_create_contact(user.id, commenter_id, commenter_username)

                # Execute actions
                self._execute_actions(
                    automation=automation,
                    user=user,
                    contact=contact,
                    comment_id=comment_id,
                    context={'comment_text': comment_text, 'media_id': media_id}
                )

                # Increment trigger count
                automation.trigger_count = (automation.trigger_count or 0) + 1
                db.session.commit()

                # Only one automation per comment (first match wins)
                break

    def process_message(self, message_data, user):
        """
        Process an incoming DM.
        For MVP, mainly used to log messages and check dm_keyword automations.

        message_data: {
            "sender": {"id": "<IGSID>"},
            "recipient": {"id": "<IG_ID>"},
            "timestamp": 1234567890,
            "message": {"mid": "<MSG_ID>", "text": "Hello!"}
        }
        """
        sender_id = message_data.get('sender', {}).get('id')
        message = message_data.get('message', {})
        text = message.get('text', '')
        msg_id = message.get('mid', '')

        # Get or create contact
        contact = self._get_or_create_contact(user.id, sender_id)

        # Get or create conversation
        conversation = self._get_or_create_conversation(user.id, contact.id)

        # Log incoming message
        log = MessageLog(
            conversation_id=conversation.id,
            direction='incoming',
            message_type='text',
            content={"text": text},
            ig_message_id=msg_id
        )
        db.session.add(log)
        db.session.commit()

        # Check dm_keyword automations
        automations = Automation.query.filter_by(
            user_id=user.id,
            trigger_type='dm_keyword',
            is_active=True
        ).all()

        for automation in automations:
            keywords = automation.trigger_config.get('keywords', [])
            if self._text_matches_keywords(text, keywords):
                print(f"  🎯 DM Automation match: \"{automation.name}\" triggered by {sender_id}")
                self._execute_actions(
                    automation=automation,
                    user=user,
                    contact=contact,
                    context={'message_text': text, 'sender_id': sender_id}
                )
                automation.trigger_count = (automation.trigger_count or 0) + 1
                db.session.commit()
                break

    def execute_automation_by_id(self, automation_id, user, contact_igsid):
        """Execute a specific automation by ID (triggered by button click / quick reply)."""
        automation = Automation.query.filter_by(id=automation_id, user_id=user.id, is_active=True).first()
        if not automation:
            print(f"  ⚠️ Chained automation #{automation_id} not found or inactive")
            return
            
        contact = self._get_or_create_contact(user.id, contact_igsid)
        
        print(f"  🎯 Chained automation match: \"{automation.name}\" triggered for {contact_igsid}")
        self._execute_actions(
            automation=automation,
            user=user,
            contact=contact,
            context={'trigger_type': 'postback', 'automation_id': automation_id}
        )
        
        automation.trigger_count = (automation.trigger_count or 0) + 1
        db.session.commit()

    # ============ Internal helpers ============

    def _matches_comment_trigger(self, automation, comment_text, media_id):
        """Check if a comment matches an automation's trigger config."""
        config = automation.trigger_config or {}
        keywords = config.get('keywords', [])

        # Check media filter (if set, only match specific posts)
        target_media_id = config.get('media_id')
        if target_media_id and target_media_id != media_id:
            return False

        # Check keywords
        return self._text_matches_keywords(comment_text, keywords)

    def _text_matches_keywords(self, text, keywords):
        """Check if text contains any of the trigger keywords."""
        if not keywords:
            return False
        text_lower = text.lower().strip()
        for keyword in keywords:
            if keyword.lower().strip() in text_lower:
                return True
        return False

    def _execute_actions(self, automation, user, contact, comment_id=None, context=None):
        """Execute the action steps defined in an automation."""
        actions = automation.actions or []
        context = context or {}

        for i, action in enumerate(actions):
            action_type = action.get('type')
            print(f"    ▶ Executing action {i+1}/{len(actions)}: {action_type}")

            try:
                if action_type == 'send_private_reply' and comment_id:
                    text = self._render_text(action.get('text', ''), contact, context)
                    result = messenger.send_private_reply(
                        ig_id=user.ig_user_id,
                        comment_id=comment_id,
                        text=text,
                        access_token=user.access_token
                    )
                    self._log_outgoing(user, contact, 'private_reply', {"text": text},
                                       result.get('message_id'), automation.id)

                elif action_type == 'send_text':
                    text = self._render_text(action.get('text', ''), contact, context)
                    result = messenger.send_text(
                        ig_id=user.ig_user_id,
                        recipient_id=contact.igsid,
                        text=text,
                        access_token=user.access_token
                    )
                    self._log_outgoing(user, contact, 'text', {"text": text},
                                       result.get('message_id'), automation.id)

                elif action_type == 'send_button_template':
                    text = self._render_text(action.get('text', ''), contact, context)
                    buttons = action.get('buttons', [])
                    result = messenger.send_button_template(
                        ig_id=user.ig_user_id,
                        recipient_id=contact.igsid,
                        text=text,
                        buttons=buttons,
                        access_token=user.access_token
                    )
                    self._log_outgoing(user, contact, 'button_template',
                                       {"text": text, "buttons": buttons},
                                       result.get('message_id'), automation.id)

                elif action_type == 'send_quick_replies':
                    text = self._render_text(action.get('text', ''), contact, context)
                    replies = action.get('replies', [])
                    result = messenger.send_quick_replies(
                        ig_id=user.ig_user_id,
                        recipient_id=contact.igsid,
                        text=text,
                        replies=replies,
                        access_token=user.access_token
                    )
                    self._log_outgoing(user, contact, 'quick_reply',
                                       {"text": text, "replies": replies},
                                       result.get('message_id'), automation.id)

                elif action_type == 'send_image':
                    image_url = action.get('image_url', '')
                    result = messenger.send_image(
                        ig_id=user.ig_user_id,
                        recipient_id=contact.igsid,
                        image_url=image_url,
                        access_token=user.access_token
                    )
                    self._log_outgoing(user, contact, 'image', {"url": image_url},
                                       result.get('message_id'), automation.id)

                elif action_type == 'add_tag':
                    tag = action.get('tag', '')
                    if tag:
                        tags = contact.tags or []
                        if tag not in tags:
                            tags.append(tag)
                            contact.tags = tags
                            db.session.commit()
                            print(f"    🏷️ Added tag '{tag}' to @{contact.username}")

                else:
                    print(f"    ⚠️ Unknown action type: {action_type}")

            except Exception as e:
                print(f"    ❌ Action {action_type} failed: {e}")

    def _render_text(self, template, contact, context):
        """Replace placeholders in message templates."""
        text = template
        text = text.replace('{{username}}', contact.username or 'there')
        text = text.replace('{{first_name}}', (contact.username or 'there').split('.')[0])
        for key, value in context.items():
            text = text.replace(f'{{{{{key}}}}}', str(value))
        return text

    def _get_or_create_contact(self, user_id, igsid, username=None):
        """Find or create a contact."""
        contact = Contact.query.filter_by(user_id=user_id, igsid=igsid).first()
        if not contact:
            contact = Contact(
                user_id=user_id,
                igsid=igsid,
                username=username
            )
            db.session.add(contact)
            db.session.commit()
            print(f"    👤 New contact: @{username or igsid}")
        elif username and not contact.username:
            contact.username = username
            db.session.commit()

        contact.last_interaction = datetime.utcnow()
        db.session.commit()
        return contact

    def _get_or_create_conversation(self, user_id, contact_id):
        """Find or create a conversation."""
        from datetime import timedelta
        convo = Conversation.query.filter_by(
            user_id=user_id,
            contact_id=contact_id
        ).first()

        if not convo:
            convo = Conversation(
                user_id=user_id,
                contact_id=contact_id,
                last_message_at=datetime.utcnow(),
                window_expires_at=datetime.utcnow() + timedelta(hours=24),
                status='active'
            )
            db.session.add(convo)
        else:
            convo.last_message_at = datetime.utcnow()
            convo.window_expires_at = datetime.utcnow() + timedelta(hours=24)
            convo.status = 'active'

        db.session.commit()
        return convo

    def _log_outgoing(self, user, contact, msg_type, content, ig_msg_id, automation_id):
        """Log an outgoing message."""
        convo = self._get_or_create_conversation(user.id, contact.id)
        log = MessageLog(
            conversation_id=convo.id,
            direction='outgoing',
            message_type=msg_type,
            content=content,
            ig_message_id=ig_msg_id,
            automation_id=automation_id
        )
        db.session.add(log)
        db.session.commit()


# Singleton
engine = AutomationEngine()
