from datetime import datetime
from flask import jsonify, request, Response
from database.models import db, HappyHourPlace, PopupEvent
from whatsapp_bot.models import (
    WaConversation, WaCompany, WaAdvocate, WaUser,
    WaApplication, WaApplicationRecipient, WaCompanyRequest,
)
from . import admin_bp
from .auth import login_required

# --- Happy Hour Places API ---

@admin_bp.route('/api/places', methods=['GET'])
@login_required
def get_places():
    places = HappyHourPlace.query.all()
    return jsonify([p.to_dict() for p in places])

@admin_bp.route('/api/places', methods=['POST'])
@login_required
def create_place():
    data = request.json
    
    # Validation
    if not data.get('Name') or str(data.get('Name')).strip() == '':
        return jsonify({'error': 'English Name is required'}), 400
    if not data.get('Address') or str(data.get('Address')).strip() == '':
        return jsonify({'error': 'Address is required'}), 400
    if not data.get('Category') or str(data.get('Category')).strip() == '':
        return jsonify({'error': 'Category is required'}), 400

    try:
        place = HappyHourPlace(
            name=data.get('Name', ''),
            name_hebrew=data.get('NameHebrew', ''),
            address=data.get('Address', ''),
            city=data.get('City', ''),
            latitude=data.get('Latitude'),
            longitude=data.get('Longitude'),
            category=data.get('Category', ''),
            description=data.get('Description', ''),
            opening_hours=data.get('OpeningHours', ''),
            sunday=bool(data.get('Sunday', False)),
            monday=bool(data.get('Monday', False)),
            tuesday=bool(data.get('Tuesday', False)),
            wednesday=bool(data.get('Wednesday', False)),
            thursday=bool(data.get('Thursday', False)),
            friday=bool(data.get('Friday', False)),
            saturday=bool(data.get('Saturday', False)),
            reservation_link=data.get('ReservationLink', ''),
            instagram_url=data.get('InstagramURL', ''),
            image_url=data.get('ImageURL', ''),
            verified=bool(data.get('Verified', False)),
            kosher=data.get('Kosher') in [True, 'yes', 'true', 'True', 1],
            recommended=data.get('Recommended', '')
        )
        db.session.add(place)
        db.session.commit()
        from app import clear_data_cache
        clear_data_cache()
        return jsonify(place.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/api/places/<int:id>', methods=['PUT'])
@login_required
def update_place(id):
    place = HappyHourPlace.query.get_or_404(id)
    data = request.json
    try:
        if 'Name' in data: place.name = data['Name']
        if 'NameHebrew' in data: place.name_hebrew = data['NameHebrew']
        if 'Address' in data: place.address = data['Address']
        if 'City' in data: place.city = data['City']
        if 'Latitude' in data: place.latitude = data['Latitude'] if data['Latitude'] != "" else None
        if 'Longitude' in data: place.longitude = data['Longitude'] if data['Longitude'] != "" else None
        if 'Category' in data: place.category = data['Category']
        if 'Description' in data: place.description = data['Description']
        if 'OpeningHours' in data: place.opening_hours = data['OpeningHours']
        
        if 'Sunday' in data: place.sunday = bool(data['Sunday'])
        if 'Monday' in data: place.monday = bool(data['Monday'])
        if 'Tuesday' in data: place.tuesday = bool(data['Tuesday'])
        if 'Wednesday' in data: place.wednesday = bool(data['Wednesday'])
        if 'Thursday' in data: place.thursday = bool(data['Thursday'])
        if 'Friday' in data: place.friday = bool(data['Friday'])
        if 'Saturday' in data: place.saturday = bool(data['Saturday'])
        
        if 'ReservationLink' in data: place.reservation_link = data['ReservationLink']
        if 'InstagramURL' in data: place.instagram_url = data['InstagramURL']
        if 'ImageURL' in data: place.image_url = data['ImageURL']
        if 'Verified' in data: place.verified = bool(data['Verified'])
        if 'Kosher' in data: place.kosher = data['Kosher'] in [True, 'yes', 'true', 'True', 1]
        if 'Recommended' in data: place.recommended = data['Recommended']

        db.session.commit()
        from app import clear_data_cache
        clear_data_cache()
        return jsonify(place.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/api/places/<int:id>', methods=['DELETE'])
@login_required
def delete_place(id):
    place = HappyHourPlace.query.get_or_404(id)
    try:
        db.session.delete(place)
        db.session.commit()
        from app import clear_data_cache
        clear_data_cache()
        return '', 204
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

# --- Popup Events API ---

@admin_bp.route('/api/events', methods=['GET'])
@login_required
def get_events():
    events = PopupEvent.query.all()
    return jsonify([e.to_dict() for e in events])

@admin_bp.route('/api/events', methods=['POST'])
@login_required
def create_event():
    data = request.json
    
    # Validation
    if not data.get('title') or str(data.get('title')).strip() == '':
        return jsonify({'error': 'Title is required'}), 400
    if not data.get('date') or str(data.get('date')).strip() == '':
        return jsonify({'error': 'Date is required'}), 400
    if not data.get('location') or str(data.get('location')).strip() == '':
        return jsonify({'error': 'Location is required'}), 400

    try:
        event = PopupEvent(
            title=data.get('title', ''),
            date=data.get('date', ''),
            time=data.get('time', ''),
            location=data.get('location', ''),
            location_link=data.get('location_link', ''),
            description=data.get('description', ''),
            instagram_username=data.get('instagram_username', ''),
            instagram_link=data.get('instagram_link', ''),
            image=data.get('image', '')
        )
        db.session.add(event)
        db.session.commit()
        return jsonify(event.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/api/events/<int:id>', methods=['PUT'])
@login_required
def update_event(id):
    event = PopupEvent.query.get_or_404(id)
    data = request.json
    try:
        if 'title' in data: event.title = data['title']
        if 'date' in data: event.date = data['date']
        if 'time' in data: event.time = data['time']
        if 'location' in data: event.location = data['location']
        if 'location_link' in data: event.location_link = data['location_link']
        if 'description' in data: event.description = data['description']
        if 'instagram_username' in data: event.instagram_username = data['instagram_username']
        if 'instagram_link' in data: event.instagram_link = data['instagram_link']
        if 'image' in data: event.image = data['image']

        db.session.commit()
        return jsonify(event.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/api/events/<int:id>', methods=['DELETE'])
@login_required
def delete_event(id):
    event = PopupEvent.query.get_or_404(id)
    try:
        db.session.delete(event)
        db.session.commit()
        return '', 204
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

# --- WhatsApp Bot API ---

def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def _name(usr):
    return (f"{usr.first_name or ''} {usr.last_name or ''}".strip()
            or usr.profile_name or "Unknown")


def _resolve_company(name):
    """Find a company by normalized name, creating it if it doesn't exist."""
    norm = " ".join((name or "").strip().lower().split())
    if not norm:
        return None
    c = WaCompany.query.filter_by(normalized_name=norm).first()
    if not c:
        c = WaCompany(name=name.strip(), normalized_name=norm)
        db.session.add(c)
        db.session.commit()
    return c


def _set_phone(usr, phone):
    """Update a user's WhatsApp number with a uniqueness guard.
    Returns an error string, or None on success/no-op."""
    phone = (phone or "").strip()
    if not phone or phone == usr.phone:
        return None
    if WaUser.query.filter(WaUser.phone == phone, WaUser.id != usr.id).first():
        return "another user already has that WhatsApp number"
    usr.phone = phone
    return None


@admin_bp.route('/api/whatsapp/stats', methods=['GET'])
@login_required
def get_whatsapp_stats():
    start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return jsonify({
        "active_chats_today": WaConversation.query.filter(WaConversation.updated_at >= start_of_day).count(),
        "companies_count": WaCompany.query.count(),
        "advocates_count": WaAdvocate.query.filter_by(status="active").count(),
        "candidates_count": WaUser.query.filter(WaUser.first_name.isnot(None)).count(),
        "applications_count": WaApplication.query.count(),
        "open_requests_count": WaCompanyRequest.query.filter_by(status="open").count(),
    })


@admin_bp.route('/api/whatsapp/companies', methods=['GET'])
@login_required
def get_whatsapp_companies():
    agg = {}
    for adv in WaAdvocate.query.filter_by(status="active").all():
        a = agg.setdefault(adv.company_id, {"email": 0, "link": 0, "total": 0})
        a["total"] += 1
        if adv.email:
            a["email"] += 1
        if adv.referral_link:
            a["link"] += 1
    out = []
    for c in WaCompany.query.order_by(WaCompany.name).all():
        a = agg.get(c.id, {"email": 0, "link": 0, "total": 0})
        out.append({
            "id": c.id, "name": c.name,
            "total_advocates": a["total"],
            "email_advocates": a["email"],
            "link_advocates": a["link"],
            "serviceable": "Yes" if a["total"] > 0 else "No",
            "created": _fmt(c.created_at),
        })
    return jsonify(out)


@admin_bp.route('/api/whatsapp/advocates', methods=['GET'])
@login_required
def get_whatsapp_advocates():
    results = db.session.query(WaAdvocate, WaUser, WaCompany).join(
        WaUser, WaAdvocate.user_id == WaUser.id).join(
        WaCompany, WaAdvocate.company_id == WaCompany.id).all()
    advocates = []
    for adv, usr, comp in results:
        if adv.referral_link and adv.email:
            method = "email + link"
        elif adv.referral_link:
            method = "link"
        elif adv.email:
            method = "email"
        else:
            method = "—"
        advocates.append({
            "id": adv.id,
            "name": _name(usr),
            "first_name": usr.first_name or "",
            "last_name": usr.last_name or "",
            "company": comp.name,
            "number": usr.phone,
            "method": method,
            "email": adv.email or "",
            "referral_link": adv.referral_link or "",
            "title": adv.role_title or "",
            "status": adv.status,
            "created": _fmt(adv.created_at),
        })
    return jsonify(advocates)


@admin_bp.route('/api/whatsapp/candidates', methods=['GET'])
@login_required
def get_whatsapp_candidates():
    app_counts = {}
    for (uid,) in db.session.query(WaApplication.candidate_user_id).all():
        app_counts[uid] = app_counts.get(uid, 0) + 1
    advocate_uids = {uid for (uid,) in db.session.query(WaAdvocate.user_id).distinct().all()}
    out = []
    for u in WaUser.query.filter(WaUser.first_name.isnot(None)).order_by(WaUser.created_at.desc()).all():
        out.append({
            "id": u.id,
            "name": _name(u),
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "email": u.email or "",
            "number": u.phone,
            "applications": app_counts.get(u.id, 0),
            "is_advocate": "Yes" if u.id in advocate_uids else "No",
            "blocked": "Yes" if u.is_blocked else "No",
            "joined": _fmt(u.created_at),
        })
    return jsonify(out)


@admin_bp.route('/api/whatsapp/applications', methods=['GET'])
@login_required
def get_whatsapp_applications():
    rec_agg = {}
    for r in WaApplicationRecipient.query.all():
        a = rec_agg.setdefault(r.application_id, {"emailed": 0, "approved": 0})
        a["emailed"] += 1
        if r.approved_at:
            a["approved"] += 1
    results = db.session.query(WaApplication, WaUser, WaCompany).join(
        WaUser, WaApplication.candidate_user_id == WaUser.id).join(
        WaCompany, WaApplication.company_id == WaCompany.id).order_by(
        WaApplication.created_at.desc()).all()
    out = []
    for app_row, usr, comp in results:
        ra = rec_agg.get(app_row.id, {"emailed": 0, "approved": 0})
        job = app_row.job_posting_url or (("desc: " + app_row.job_description) if app_row.job_description else "")
        out.append({
            "id": app_row.id,
            "candidate": _name(usr),
            "number": usr.phone,
            "company": comp.name,
            "role": app_row.role_query or "",
            "job": job,
            "job_posting_url": app_row.job_posting_url or "",
            "job_description": app_row.job_description or "",
            "resume": app_row.resume_filename or "",
            "emailed": ra["emailed"],
            "approved": ra["approved"],
            "status": app_row.status,
            "created": _fmt(app_row.created_at),
        })
    return jsonify(out)


@admin_bp.route('/api/whatsapp/requests', methods=['GET'])
@login_required
def get_whatsapp_requests():
    results = db.session.query(WaCompanyRequest, WaUser).join(
        WaUser, WaCompanyRequest.candidate_user_id == WaUser.id).order_by(
        WaCompanyRequest.created_at.desc()).all()
    out = []
    for req, usr in results:
        out.append({
            "id": req.id,
            "company": req.company_name_raw,
            "reason": req.reason,
            "candidate": _name(usr),
            "number": usr.phone,
            "status": req.status,
            "created": _fmt(req.created_at),
        })
    return jsonify(out)


# --- WhatsApp Bot: edits + light actions ---

@admin_bp.route('/api/whatsapp/advocates/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_advocate(id):
    adv = WaAdvocate.query.get_or_404(id)
    data = request.json or {}
    if "status" in data:
        if data["status"] not in ("active", "inactive", "pending"):
            return jsonify({"error": "invalid status"}), 400
        adv.status = data["status"]
    if "email" in data:
        adv.email = (data["email"] or "").strip() or None
    if "referral_link" in data:
        adv.referral_link = (data["referral_link"] or "").strip() or None
    if "role_title" in data:
        adv.role_title = (data["role_title"] or "").strip() or None
    if data.get("company"):
        c = _resolve_company(data["company"])
        if c:
            adv.company_id = c.id
    # underlying user fields (name + WhatsApp number)
    usr = WaUser.query.get(adv.user_id)
    if usr is not None:
        if "first_name" in data:
            usr.first_name = (data["first_name"] or "").strip() or None
        if "last_name" in data:
            usr.last_name = (data["last_name"] or "").strip() or None
        if "phone" in data:
            err = _set_phone(usr, data["phone"])
            if err:
                return jsonify({"error": err}), 400
    db.session.commit()
    return jsonify({"id": adv.id, "status": adv.status})


@admin_bp.route('/api/whatsapp/companies/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_company(id):
    c = WaCompany.query.get_or_404(id)
    name = ((request.json or {}).get("name") or "").strip()
    if name:
        norm = " ".join(name.lower().split())
        clash = WaCompany.query.filter(WaCompany.normalized_name == norm, WaCompany.id != c.id).first()
        if clash:
            return jsonify({"error": "another company already uses that name"}), 400
        c.name = name
        c.normalized_name = norm
        db.session.commit()
    return jsonify({"id": c.id, "name": c.name})


@admin_bp.route('/api/whatsapp/requests/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_request(id):
    req = WaCompanyRequest.query.get_or_404(id)
    status = (request.json or {}).get("status")
    if status not in ("open", "handled"):
        return jsonify({"error": "invalid status"}), 400
    req.status = status
    db.session.commit()
    return jsonify({"id": req.id, "status": req.status})


@admin_bp.route('/api/whatsapp/users/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_user(id):
    usr = WaUser.query.get_or_404(id)
    data = request.json or {}
    if "is_blocked" in data:
        usr.is_blocked = bool(data["is_blocked"])
    if "email" in data:
        usr.email = (data["email"] or "").strip() or None
    if "first_name" in data:
        usr.first_name = (data["first_name"] or "").strip() or None
    if "last_name" in data:
        usr.last_name = (data["last_name"] or "").strip() or None
    if "phone" in data:
        err = _set_phone(usr, data["phone"])
        if err:
            return jsonify({"error": err}), 400
    db.session.commit()
    return jsonify({"id": usr.id, "is_blocked": usr.is_blocked, "email": usr.email})


@admin_bp.route('/api/whatsapp/applications/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_application(id):
    ap = WaApplication.query.get_or_404(id)
    data = request.json or {}
    if "role" in data:
        ap.role_query = (data["role"] or "").strip() or None
    if "job_posting_url" in data:
        ap.job_posting_url = (data["job_posting_url"] or "").strip() or None
    if "job_description" in data:
        ap.job_description = (data["job_description"] or "").strip() or None
    if data.get("status"):
        ap.status = data["status"].strip()
    db.session.commit()
    return jsonify({"id": ap.id, "status": ap.status})


@admin_bp.route('/api/whatsapp/applications/<int:id>/cv', methods=['GET'])
@login_required
def whatsapp_application_cv(id):
    from whatsapp_bot import storage
    app_row = WaApplication.query.get_or_404(id)
    path = app_row.resume_path or ""
    if not path:
        return "No CV on file for this application.", 404
    # Fetch the file server-side (with backend credentials) and stream it to the
    # already-logged-in admin, so the browser never hits a Twilio/Supabase auth prompt.
    if path.startswith("http"):
        content, ctype = storage.download_twilio_media(path)
    else:
        content, ctype = storage.download_object(path)
    if content is None:
        return ("Couldn't fetch the CV — the link may have expired, or Supabase "
                "Storage isn't configured on the bot service."), 502
    filename = app_row.resume_filename or "cv.pdf"
    return Response(content, mimetype=ctype or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})
