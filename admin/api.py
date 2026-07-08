import logging
import os
import json
from datetime import datetime

import requests
from flask import jsonify, request, Response
from database.models import db, HappyHourPlace, PopupEvent, HitechEmail, User
from whatsapp_bot.models import (
    WaConversation, WaCompany, WaAdvocate, WaUser,
    WaApplication, WaApplicationRecipient, WaCompanyRequest,
)
from . import admin_bp
from .auth import login_required

logger = logging.getLogger("admin")

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
    # Left join on WaUser: curated advocates have no bot user (user_id is NULL).
    results = db.session.query(WaAdvocate, WaUser, WaCompany).outerjoin(
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
            "name": _name(usr) if usr else (adv.advocate_name or "—"),
            "first_name": (usr.first_name if usr else "") or "",
            "last_name": (usr.last_name if usr else "") or "",
            "advocate_name": adv.advocate_name or "",
            "company": comp.name,
            "number": usr.phone if usr else "",
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
    if "advocate_name" in data:
        adv.advocate_name = (data["advocate_name"] or "").strip() or None
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


@admin_bp.route('/api/whatsapp/companies/<int:id>/advocates', methods=['GET'])
@login_required
def get_company_advocates(id):
    WaCompany.query.get_or_404(id)
    results = db.session.query(WaAdvocate, WaUser).join(
        WaUser, WaAdvocate.user_id == WaUser.id
    ).filter(WaAdvocate.company_id == id).order_by(WaAdvocate.created_at.desc()).all()
    out = []
    for adv, usr in results:
        out.append({
            "id": adv.id,
            "name": _name(usr),
            "first_name": usr.first_name or "",
            "last_name": usr.last_name or "",
            "phone": usr.phone or "",
            "email": adv.email or "",
            "referral_link": adv.referral_link or "",
            "role_title": adv.role_title or "",
            "status": adv.status,
            "created": _fmt(adv.created_at),
        })
    return jsonify(out)


@admin_bp.route('/api/whatsapp/companies/<int:id>/advocates', methods=['POST'])
@login_required
def add_company_advocate(id):
    company = WaCompany.query.get_or_404(id)
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Phone number is required"}), 400

    # Find or create WaUser by phone
    usr = WaUser.query.filter_by(phone=phone).first()
    if usr is None:
        usr = WaUser(
            phone=phone,
            first_name=(data.get("first_name") or "").strip() or None,
            last_name=(data.get("last_name") or "").strip() or None,
        )
        db.session.add(usr)
        db.session.flush()
    else:
        if data.get("first_name"):
            usr.first_name = data["first_name"].strip()
        if data.get("last_name"):
            usr.last_name = data["last_name"].strip()

    email = (data.get("email") or "").strip() or None
    existing = WaAdvocate.query.filter_by(user_id=usr.id, company_id=company.id, email=email).first()
    if existing:
        return jsonify({"error": "This advocate already exists for this company"}), 409

    adv = WaAdvocate(
        user_id=usr.id,
        company_id=company.id,
        email=email,
        referral_link=(data.get("referral_link") or "").strip() or None,
        role_title=(data.get("role_title") or "").strip() or None,
        status=data.get("status", "active"),
    )
    db.session.add(adv)
    db.session.commit()
    return jsonify({
        "id": adv.id,
        "name": _name(usr),
        "first_name": usr.first_name or "",
        "last_name": usr.last_name or "",
        "phone": usr.phone,
        "email": adv.email or "",
        "referral_link": adv.referral_link or "",
        "role_title": adv.role_title or "",
        "status": adv.status,
        "created": _fmt(adv.created_at),
    }), 201


@admin_bp.route('/api/whatsapp/advocates/<int:id>', methods=['DELETE'])
@login_required
def delete_whatsapp_advocate(id):
    adv = WaAdvocate.query.get_or_404(id)
    db.session.delete(adv)
    db.session.commit()
    return '', 204


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


@admin_bp.route('/api/whatsapp/companies', methods=['POST'])
@login_required
def create_whatsapp_company():
    name = ((request.json or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Company name is required"}), 400
    norm = " ".join(name.lower().split())
    existing = WaCompany.query.filter_by(normalized_name=norm).first()
    if existing:
        return jsonify({"error": "That company already exists", "id": existing.id}), 409
    c = WaCompany(name=name, normalized_name=norm)
    db.session.add(c)
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name}), 201


@admin_bp.route('/api/whatsapp/advocates', methods=['POST'])
@login_required
def create_whatsapp_advocate():
    """Create an advocate directly (no need to open a company first). Company is
    given by name (resolved/created). Phone is optional: with it we link/create a
    WhatsApp user; without it the advocate is curated (name stored on the row)."""
    data = request.json or {}
    company_name = (data.get("company") or "").strip()
    if not company_name:
        return jsonify({"error": "Company is required"}), 400
    company = _resolve_company(company_name)
    first = (data.get("first_name") or "").strip() or None
    last = (data.get("last_name") or "").strip() or None
    email = (data.get("email") or "").strip() or None
    phone = (data.get("phone") or "").strip()
    status = (data.get("status") or "active").strip()
    if status not in ("active", "inactive", "pending"):
        status = "active"

    usr = None
    if phone:
        usr = WaUser.query.filter_by(phone=phone).first()
        if usr is None:
            usr = WaUser(phone=phone, first_name=first, last_name=last)
            db.session.add(usr)
            db.session.flush()
        else:
            if first:
                usr.first_name = first
            if last:
                usr.last_name = last
        if WaAdvocate.query.filter_by(user_id=usr.id, company_id=company.id, email=email).first():
            return jsonify({"error": "This advocate already exists for this company"}), 409

    adv = WaAdvocate(
        user_id=(usr.id if usr else None),
        company_id=company.id,
        advocate_name=(None if usr else (" ".join(x for x in (first, last) if x) or None)),
        email=email,
        referral_link=(data.get("referral_link") or "").strip() or None,
        role_title=(data.get("role_title") or "").strip() or None,
        status=status,
    )
    db.session.add(adv)
    db.session.commit()
    return jsonify({"id": adv.id}), 201


@admin_bp.route('/api/whatsapp/candidates', methods=['POST'])
@login_required
def create_whatsapp_candidate():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    first = (data.get("first_name") or "").strip()
    if not phone:
        return jsonify({"error": "WhatsApp number is required"}), 400
    if not first:
        return jsonify({"error": "First name is required"}), 400
    if WaUser.query.filter_by(phone=phone).first():
        return jsonify({"error": "A user with that number already exists"}), 409
    u = WaUser(
        phone=phone, first_name=first,
        last_name=(data.get("last_name") or "").strip() or None,
        email=(data.get("email") or "").strip() or None,
    )
    db.session.add(u)
    db.session.commit()
    return jsonify({"id": u.id}), 201


@admin_bp.route('/api/whatsapp/companies/<int:id>', methods=['DELETE'])
@login_required
def delete_whatsapp_company(id):
    c = WaCompany.query.get_or_404(id)
    _delete_company_cascade(c)
    db.session.commit()
    return '', 204


@admin_bp.route('/api/whatsapp/companies/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_whatsapp_companies():
    ids = (request.json or {}).get("ids") or []
    ids = [int(i) for i in ids if str(i).lstrip("-").isdigit()]
    if not ids:
        return jsonify({"error": "No company ids provided"}), 400
    companies = WaCompany.query.filter(WaCompany.id.in_(ids)).all()
    for c in companies:
        _delete_company_cascade(c)
    db.session.commit()
    return jsonify({"deleted": len(companies)})


def _delete_company_cascade(company):
    """Delete a company plus everything that references it — advocates and
    applications (with their recipients) — and detach it from backfill requests,
    so there are no FK violations."""
    app_ids = [a.id for a in WaApplication.query.filter_by(company_id=company.id).all()]
    if app_ids:
        WaApplicationRecipient.query.filter(
            WaApplicationRecipient.application_id.in_(app_ids)).delete(synchronize_session=False)
        WaApplication.query.filter_by(company_id=company.id).delete(synchronize_session=False)
    WaAdvocate.query.filter_by(company_id=company.id).delete(synchronize_session=False)
    WaCompanyRequest.query.filter_by(resolved_company_id=company.id).update(
        {WaCompanyRequest.resolved_company_id: None}, synchronize_session=False)
    db.session.delete(company)


@admin_bp.route('/api/whatsapp/candidates/<int:id>', methods=['DELETE'])
@login_required
def delete_whatsapp_candidate(id):
    u = WaUser.query.get_or_404(id)
    _delete_user_cascade(u)
    db.session.commit()
    return '', 204


def _delete_user_cascade(user):
    """Delete a user (candidate/advocate) and everything that references them —
    applications (+recipients), advocate rows, backfill requests, conversation."""
    app_ids = [a.id for a in WaApplication.query.filter_by(candidate_user_id=user.id).all()]
    if app_ids:
        WaApplicationRecipient.query.filter(
            WaApplicationRecipient.application_id.in_(app_ids)).delete(synchronize_session=False)
        WaApplication.query.filter_by(candidate_user_id=user.id).delete(synchronize_session=False)
    WaAdvocate.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    WaCompanyRequest.query.filter_by(candidate_user_id=user.id).delete(synchronize_session=False)
    WaConversation.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.delete(user)


@admin_bp.route('/api/whatsapp/applications/<int:id>', methods=['DELETE'])
@login_required
def delete_whatsapp_application(id):
    a = WaApplication.query.get_or_404(id)
    WaApplicationRecipient.query.filter_by(application_id=a.id).delete(synchronize_session=False)
    db.session.delete(a)
    db.session.commit()
    return '', 204


@admin_bp.route('/api/whatsapp/requests/<int:id>', methods=['DELETE'])
@login_required
def delete_whatsapp_request(id):
    r = WaCompanyRequest.query.get_or_404(id)
    db.session.delete(r)
    db.session.commit()
    return '', 204


# --- HiTech Content Manager API ---

@admin_bp.route('/api/hitech/content', methods=['GET'])
@login_required
def get_hitech_content():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'hitech_content.json')
    try:
        with open(path, encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/api/hitech/content', methods=['PUT'])
@login_required
def update_hitech_content():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'hitech_content.json')
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _notify_via_bot(request_id):
    """Ask the BOT service (which has the SendGrid env vars; this main app does
    not) to email the candidate that their requested company is now available.
    Best-effort → returns True iff the bot reports the email was sent. The shared
    key (WA_CRON_SECRET / ADMIN_SECRET) must match on both services."""
    base = os.environ.get("WA_BOT_BASE_URL", "https://ofoodiez-map-1.onrender.com").rstrip("/")
    secret = os.environ.get("WA_CRON_SECRET") or os.environ.get("ADMIN_SECRET", "ofoodiez2025")
    try:
        resp = requests.post(f"{base}/wa/requests/{request_id}/notify",
                             params={"key": secret}, timeout=15)
        return bool(resp.ok and resp.json().get("emailed"))
    except Exception:
        logger.exception("admin: notify-via-bot failed for request %s", request_id)
        return False


@admin_bp.route('/api/whatsapp/requests/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_request(id):
    req = WaCompanyRequest.query.get_or_404(id)
    status = (request.json or {}).get("status")
    if status not in ("open", "handled"):
        return jsonify({"error": "invalid status"}), 400
    newly_handled = status == "handled" and req.status != "handled"
    req.status = status
    db.session.commit()
    # On "Mark handled", let the candidate know their company is now available.
    emailed = _notify_via_bot(req.id) if newly_handled else False
    return jsonify({"id": req.id, "status": req.status, "emailed": emailed})


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


# --- HiTech / Tech Community API ---

@admin_bp.route('/api/hitech-emails', methods=['POST'])
@login_required
def create_hitech_email():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    if not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Invalid email.'}), 400
    if HitechEmail.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already exists.'}), 409
    entry = HitechEmail(
        email=email,
        linkedin_url=(data.get('linkedin_url') or '').strip() or None,
        job_title=(data.get('job_title') or '').strip() or None,
        company=(data.get('company') or '').strip() or None,
        gender=(data.get('gender') or '').strip() or None,
        list_name=(data.get('list_name') or '').strip() or None,
        verified=bool(data.get('verified', False)),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({
        'id': entry.id, 'email': entry.email,
        'linkedin_url': entry.linkedin_url or '', 'job_title': entry.job_title or '',
        'company': entry.company or '', 'gender': entry.gender or '',
        'verified': bool(entry.verified), 'list_name': entry.list_name or '',
        'joined': entry.created_at.strftime('%Y-%m-%d %H:%M') if entry.created_at else ''
    }), 201

@admin_bp.route('/api/hitech-emails', methods=['GET'])
@login_required
def get_hitech_emails():
    emails = HitechEmail.query.order_by(HitechEmail.created_at.desc()).all()
    return jsonify([{
        'id': e.id,
        'email': e.email,
        'linkedin_url': e.linkedin_url or '',
        'job_title': e.job_title or '',
        'company': e.company or '',
        'verified': bool(e.verified),
        'gender': e.gender or '',
        'list_name': e.list_name or '',
        'joined': e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else ''
    } for e in emails])

@admin_bp.route('/api/hitech-emails/<int:id>', methods=['PATCH'])
@login_required
def update_hitech_email(id):
    """Update editable fields (currently: list_name, job_title) on a tech community member."""
    entry = HitechEmail.query.get_or_404(id)
    data = request.json or {}
    if 'list_name' in data:
        entry.list_name = (data['list_name'] or '').strip() or None
    if 'job_title' in data:
        entry.job_title = (data['job_title'] or '').strip() or None
    if 'linkedin_url' in data:
        entry.linkedin_url = (data['linkedin_url'] or '').strip() or None
    if 'company' in data:
        entry.company = (data['company'] or '').strip() or None
    if 'verified' in data:
        entry.verified = bool(data['verified'])
    if 'gender' in data:
        entry.gender = (data['gender'] or '').strip() or None
    db.session.commit()
    return jsonify({'id': entry.id, 'list_name': entry.list_name or '', 'job_title': entry.job_title or '', 'company': entry.company or '', 'linkedin_url': entry.linkedin_url or ''})

@admin_bp.route('/api/hitech-emails/<int:id>/reject', methods=['POST'])
@login_required
def reject_hitech_email(id):
    entry = HitechEmail.query.get_or_404(id)
    from whatsapp_bot.emailer import send_hitech_rejection_email
    sent = send_hitech_rejection_email(entry.email)
    if sent:
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Email not sent — check SendGrid config.'}), 500

@admin_bp.route('/api/hitech-emails/<int:id>', methods=['DELETE'])
@login_required
def delete_hitech_email(id):
    entry = HitechEmail.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/api/hitech-emails/send-email', methods=['POST'])
@login_required
def send_hitech_bulk_email():
    data = request.json or {}
    subject = (data.get('subject') or '').strip()
    body_text = (data.get('body') or '').strip()
    button_url = (data.get('button_url') or '').strip()
    button_text = (data.get('button_text') or '').strip() or 'Register Now'
    target = data.get('target', 'all')
    list_name = (data.get('list_name') or '').strip()
    specific_email = (data.get('specific_email') or '').strip()

    if not subject or not body_text:
        return jsonify({'success': False, 'message': 'Subject and Body are required.'}), 400

    # Query recipients
    if target == 'all':
        recipients = HitechEmail.query.all()
    elif target == 'verified':
        recipients = HitechEmail.query.filter_by(verified=True).all()
    elif target == 'unverified':
        recipients = HitechEmail.query.filter_by(verified=False).all()
    elif target == 'list':
        if not list_name:
            return jsonify({'success': False, 'message': 'List tag is required.'}), 400
        recipients = HitechEmail.query.filter_by(list_name=list_name).all()
    elif target == 'specific':
        if not specific_email or '@' not in specific_email:
            return jsonify({'success': False, 'message': 'Valid test email address is required.'}), 400
        # Create a dummy container for the loop
        class DummyRecipient:
            def __init__(self, email):
                self.email = email
        recipients = [DummyRecipient(specific_email)]
    else:
        return jsonify({'success': False, 'message': 'Invalid target audience.'}), 400

    if not recipients:
        return jsonify({'success': True, 'sent_count': 0, 'message': 'No recipients found for this target.'})

    # Prepare beautiful HTML email template wrapping the body text
    button_html = ""
    if button_url:
        button_html = (
            f'<div style="margin: 28px 0; text-align: center;">'
            f'  <a href="{button_url}" target="_blank" style="'
            f'    background-color: #720815; color: #ffffff;'
            f'    text-decoration: none; padding: 12px 24px;'
            f'    border-radius: 8px; font-weight: bold; font-family: sans-serif;'
            f'    display: inline-block;'
            f'  ">{button_text}</a>'
            f'</div>'
        )

    formatted_body = body_text.replace('\n', '<br>')
    
    html_template = (
        f'<div style="'
        f'  font-family: sans-serif; font-size: 16px; color: #333333;'
        f'  line-height: 1.6; max-width: 600px; margin: 0 auto;'
        f'  direction: rtl; text-align: right; padding: 20px;'
        f'  background-color: #fdfaf4; border-radius: 12px;'
        f'  border: 1px solid #e9ecef;'
        f'">'
        f'  <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 2px solid #720815;">'
        f'    <span style="font-size: 20px; font-weight: bold; color: #720815;">Ofoodiez Tech Community</span>'
        f'  </div>'
        f'  <div style="font-size: 15px; color: #222;">'
        f'    {formatted_body}'
        f'  </div>'
        f'  {button_html}'
        f'  <div style="margin-top: 36px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 12px; color: #777; text-align: center;">'
        f'    זהו דיוור שנשלח לחברי קהילת Ofoodiez Tech. <br>'
        f'    Ofoodiez © 2026'
        f'  </div>'
        f'</div>'
    )

    plain_button_text = f"\n\n{button_text}: {button_url}" if button_url else ""
    text_content = f"{body_text}{plain_button_text}\n\nOfoodiez Tech Community"

    from whatsapp_bot.emailer import send_custom_community_email
    from flask import current_app
    import threading

    app_instance = current_app._get_current_object()
    recipient_emails = [r.email for r in recipients]

    def bg_send():
        with app_instance.app_context():
            print(f"📧 Starting background bulk email dispatch to {len(recipient_emails)} recipients...")
            sent_count = 0
            for email in recipient_emails:
                try:
                    success = send_custom_community_email(
                        to_email=email,
                        subject=subject,
                        body_html=html_template,
                        body_text=text_content
                    )
                    if success:
                        sent_count += 1
                except Exception as e:
                    print(f"❌ Error sending email to {email}: {e}")
            print(f"📧 Background bulk email dispatch complete. Successfully sent: {sent_count}/{len(recipient_emails)}")

    threading.Thread(target=bg_send, daemon=True).start()

    return jsonify({'success': True, 'message': f'Bulk sending started in the background for {len(recipient_emails)} recipients.'})



# --- Site Members API ---

def _user_method(u):
    if u.google_id and u.password_hash:
        return "Email + Google"
    if u.google_id:
        return "Google"
    return "Email"

def _user_dict(u):
    return {
        'id': u.id,
        'email': u.email,
        'name': u.name or '',
        'method': _user_method(u),
        'is_paid': bool(u.is_paid),                                   # raw manual flag (editable)
        'paid_until': u.paid_until.strftime('%Y-%m-%d') if u.paid_until else '',
        'payplus_sub_uid': u.payplus_sub_uid or '',
        'created_at': u.created_at.strftime('%Y-%m-%d') if u.created_at else '',
    }

@admin_bp.route('/api/users', methods=['GET'])
@login_required
def get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([_user_dict(u) for u in users])

@admin_bp.route('/api/users/<int:id>', methods=['PUT'])
@login_required
def update_user(id):
    user = User.query.get_or_404(id)
    data = request.json or {}
    if 'name' in data:
        user.name = (data.get('name') or '').strip() or None
    if 'is_paid' in data:
        user.is_paid = bool(data.get('is_paid'))
    if 'paid_until' in data:
        raw = (data.get('paid_until') or '').strip()
        if not raw:
            user.paid_until = None
        else:
            try:
                user.paid_until = datetime.strptime(raw, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Paid until must be YYYY-MM-DD (or blank)'}), 400
    db.session.commit()
    return jsonify(_user_dict(user))


# --- Blog Content API ---

def _blog_path(slug):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'app', 'data', f'blog_{slug}.json')

@admin_bp.route('/api/blog/<slug>', methods=['GET'])
@login_required
def get_blog(slug):
    path = _blog_path(slug)
    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404
    with open(path, encoding='utf-8') as f:
        return jsonify(json.load(f))

@admin_bp.route('/api/blog/<slug>', methods=['PUT'])
@login_required
def save_blog(slug):
    path = _blog_path(slug)
    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True})
