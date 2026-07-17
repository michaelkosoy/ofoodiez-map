import logging
import os
import json
from datetime import datetime

import requests
from flask import jsonify, request, Response, current_app
from database.models import db, HappyHourPlace, PopupEvent, HitechEmail, User, Purchase
from whatsapp_bot.models import (
    WaConversation, WaCompany, WaAdvocate, WaUser,
    WaApplication, WaApplicationRecipient, WaCompanyRequest, WaContactMessage,
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
            "careers_url": c.careers_url or "",
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
        a = rec_agg.setdefault(r.application_id, {"emailed": 0, "approved": 0, "denied": 0})
        a["emailed"] += 1
        if r.approved_at:
            a["approved"] += 1
        if r.denied_at:
            a["denied"] += 1
    results = db.session.query(WaApplication, WaUser, WaCompany).join(
        WaUser, WaApplication.candidate_user_id == WaUser.id).join(
        WaCompany, WaApplication.company_id == WaCompany.id).order_by(
        WaApplication.created_at.desc()).all()
    out = []
    for app_row, usr, comp in results:
        ra = rec_agg.get(app_row.id, {"emailed": 0, "approved": 0, "denied": 0})
        job = app_row.job_posting_url or (("desc: " + app_row.job_description) if app_row.job_description else "")
        # Exact status derived from what actually happened (the stored field is
        # always "submitted"). Every row here IS a real CV submission.
        if ra["approved"]:
            status = "Approved"          # an advocate confirmed the referral
        elif ra["denied"]:
            status = "Disputed"          # advocate tapped "I didn't submit this"
        elif ra["emailed"]:
            status = "Emailed"           # forwarded to ≥1 advocate, awaiting reply
        else:
            status = "Not submitted"     # no advocate email — the CV did NOT reach an advocate
        out.append({
            "id": app_row.id,
            "user_id": app_row.candidate_user_id,
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
            "denied": ra["denied"],
            "status": status,
            "created": _fmt(app_row.created_at),
        })
    return jsonify(out)


def _recipient_advocate(rec):
    """Advocate details for one application recipient — who the CV was sent to."""
    adv = WaAdvocate.query.get(rec.advocate_id) if rec.advocate_id else None
    name = None
    if adv:
        if adv.user_id:
            au = WaUser.query.get(adv.user_id)
            if au:
                name = f"{au.first_name or ''} {au.last_name or ''}".strip() or None
        name = name or adv.advocate_name
    return {
        "name": name or "advocate",
        "email": rec.email or (adv.email if adv else "") or "",
        "title": (adv.role_title if adv else "") or "",
        "approved": bool(rec.approved_at),
        "status": rec.email_status or "sent",   # sent | pending | failed
    }


@admin_bp.route('/api/whatsapp/users/<int:id>/flow', methods=['GET'])
@login_required
def get_whatsapp_user_flow(id):
    """The full journey of one user, reconstructed from what we store: sign-up,
    company searches we couldn't serve (advocate not found), submitted applications
    (advocate found / emailed / approved), and their current live conversation."""
    u = WaUser.query.get_or_404(id)
    conv = WaConversation.query.filter_by(user_id=u.id).first()
    rec_by_app = {}
    for r in WaApplicationRecipient.query.all():
        rec_by_app.setdefault(r.application_id, []).append(r)

    events = []  # (sort_dt, dict)
    for req in WaCompanyRequest.query.filter_by(candidate_user_id=u.id).all():
        events.append((req.created_at, {
            "kind": "search", "when": _fmt(req.created_at),
            "company": req.company_name_raw,
            "detail": ("not in our list yet" if req.reason == "unknown_company"
                       else "no advocate there yet"),
            "status": req.status,   # open | handled
        }))
    for a in WaApplication.query.filter_by(candidate_user_id=u.id).all():
        comp = WaCompany.query.get(a.company_id)
        cname = comp.name if comp else "?"
        recs = rec_by_app.get(a.id, [])
        events.append((a.created_at, {
            "kind": "application", "when": _fmt(a.created_at),
            "company": cname, "role": a.role_query or "",
            "resume": a.resume_filename or "", "emailed": len(recs),
        }))
        # Each advocate the CV reached becomes its own phase: emailed → (approved).
        for r in recs:
            adv = _recipient_advocate(r)
            events.append((r.emailed_at or a.created_at, {
                "kind": "emailed", "when": _fmt(r.emailed_at or a.created_at),
                "company": cname, "advocate": adv, "status": r.email_status or "sent",
            }))
            if r.approved_at:
                events.append((r.approved_at, {
                    "kind": "approved", "when": _fmt(r.approved_at),
                    "company": cname, "advocate": adv,
                }))
    events.sort(key=lambda e: e[0] or datetime.min)

    state = None
    if conv and conv.flow:
        d = conv.data or {}
        state = {"flow": conv.flow, "step": conv.step, "company": d.get("company_name"),
                 "role": d.get("role_query"), "advocate": d.get("advocate_name"),
                 "when": _fmt(conv.updated_at)}
    return jsonify({
        "user": {"name": _name(u), "email": u.email or "", "phone": u.phone,
                 "joined": _fmt(u.created_at), "registered": bool(u.is_registered),
                 "blocked": bool(u.is_blocked)},
        "state": state,
        "events": [e[1] for e in events],
    })


def _req_key(req):
    """Group key for a backfill request: its normalized company name (falls back
    to a normalized raw name for any legacy row without one). Used to collapse the
    per-candidate request rows into one row per company."""
    return (req.normalized_name or (req.company_name_raw or "").strip().lower()) or "?"


@admin_bp.route('/api/whatsapp/requests', methods=['GET'])
@login_required
def get_whatsapp_requests():
    results = db.session.query(WaCompanyRequest, WaUser).join(
        WaUser, WaCompanyRequest.candidate_user_id == WaUser.id).order_by(
        WaCompanyRequest.created_at.desc()).all()
    # One row per company; each candidate who asked for it accumulates into a list.
    # Rows are indexed by the normalized company key so the by-company actions can
    # target the whole group (mark handled → notify everyone / delete all).
    groups = {}
    for req, usr in results:
        key = _req_key(req)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"id": key, "company": req.company_name_raw,
                               "created": _fmt(req.created_at),  # newest (query is desc)
                               "_seen": set(), "_names": [], "_open": 0}
        if req.status == "open":
            g["_open"] += 1
        if usr.id not in g["_seen"]:            # one entry per candidate, not per request
            g["_seen"].add(usr.id)
            g["_names"].append(f"{_name(usr)} ({usr.phone})" if usr.phone else _name(usr))
    out = [{
        "id": g["id"],
        "company": g["company"],
        "candidates": ", ".join(g["_names"]),
        "count": len(g["_names"]),
        "status": "open" if g["_open"] else "handled",  # open if any candidate is still open
        "created": g["created"],
    } for g in groups.values()]
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
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if name:
        norm = " ".join(name.lower().split())
        clash = WaCompany.query.filter(WaCompany.normalized_name == norm, WaCompany.id != c.id).first()
        if clash:
            return jsonify({"error": "another company already uses that name"}), 400
        c.name = name
        c.normalized_name = norm
    if "careers_url" in data:
        url = (data.get("careers_url") or "").strip()
        # rendered as an href on the public referrals page — allow http(s) only
        if url and not url.startswith(("http://", "https://")):
            return jsonify({"error": "careers URL must start with http:// or https://"}), 400
        c.careers_url = url or None
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name, "careers_url": c.careers_url or ""})


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


def _requests_for_key(key):
    """All backfill requests that belong to one company group (see _req_key). The
    requests table is a small ops queue, so filtering in Python keeps the grouping
    logic identical on read and write with no SQL edge cases."""
    key = (key or "").strip().lower()
    return key, [r for r in WaCompanyRequest.query.all() if _req_key(r) == key]


def _group_company(rows, key=None):
    """The WaCompany a request group maps to, if it exists yet (None while the
    company is still unknown)."""
    for r in rows:
        if r.resolved_company_id:
            c = WaCompany.query.get(r.resolved_company_id)
            if c:
                return c
    key = key or (_req_key(rows[0]) if rows else None)
    return WaCompany.query.filter_by(normalized_name=key).first() if key else None


@admin_bp.route('/api/whatsapp/requests/by-company', methods=['PUT'])
@login_required
def update_whatsapp_requests_by_company():
    """Mark every request for a company handled/open in one go. On 'handled', email
    EACH candidate (once) that their company is now available — but only once the
    company actually has an active advocate, so nobody is told 'available' too early."""
    body = request.json or {}
    status = body.get("status")
    if status not in ("open", "handled"):
        return jsonify({"error": "invalid status"}), 400
    key, rows = _requests_for_key(body.get("key"))
    if not rows:
        return jsonify({"error": "not found"}), 404
    if status == "handled":
        company = _group_company(rows, key)
        if not (company and WaAdvocate.query.filter_by(
                company_id=company.id, status="active").first()):
            # Nobody can refer them yet → don't mark handled or email; leave it open
            # so the backfill cron notifies everyone automatically once an advocate exists.
            return jsonify({"blocked": "no_advocate",
                            "company": company.name if company else rows[0].company_name_raw})
    newly = [r for r in rows if status == "handled" and r.status != "handled"]
    for r in rows:
        r.status = status
    db.session.commit()
    # Notify each unique candidate once. ponytail: one bot call per candidate —
    # fine for a handful; add a batch bot endpoint if a company backfills to many.
    emailed, seen = 0, set()
    for r in newly:
        if r.candidate_user_id in seen:
            continue
        seen.add(r.candidate_user_id)
        if _notify_via_bot(r.id) == "sent":
            emailed += 1
    return jsonify({"updated": len(rows), "candidates": len(seen), "emailed": emailed, "status": status})


@admin_bp.route('/api/whatsapp/requests/by-company', methods=['DELETE'])
@login_required
def delete_whatsapp_requests_by_company():
    """Delete every request for one company group."""
    key, rows = _requests_for_key(request.args.get("key"))
    for r in rows:
        db.session.delete(r)
    db.session.commit()
    return '', 204


# --- WhatsApp Bot: Contact-Us messages ---

@admin_bp.route('/api/whatsapp/contacts', methods=['GET'])
@login_required
def get_whatsapp_contacts():
    rows = WaContactMessage.query.order_by(WaContactMessage.created_at.desc()).all()
    return jsonify([{
        "id": m.id,
        "name": m.name or "—",
        "phone": m.phone or "",
        "email": m.email or "",
        "message": m.message or "",
        "status": "handled" if m.handled_at else "open",
        "created": _fmt(m.created_at),
    } for m in rows])


@admin_bp.route('/api/whatsapp/contacts/<int:id>', methods=['PUT'])
@login_required
def update_whatsapp_contact(id):
    m = WaContactMessage.query.get_or_404(id)
    status = (request.json or {}).get("status")
    if status not in ("open", "handled"):
        return jsonify({"error": "invalid status"}), 400
    m.handled_at = datetime.utcnow() if status == "handled" else None
    db.session.commit()
    return jsonify({"id": m.id, "status": status})


@admin_bp.route('/api/whatsapp/contacts/<int:id>', methods=['DELETE'])
@login_required
def delete_whatsapp_contact(id):
    m = WaContactMessage.query.get_or_404(id)
    db.session.delete(m)
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


@admin_bp.route('/api/portfolio/content', methods=['GET'])
@login_required
def get_portfolio_content():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'portfolio_content.json')
    try:
        with open(path, encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/api/portfolio/content', methods=['PUT'])
@login_required
def update_portfolio_content():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'portfolio_content.json')
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
    Best-effort → returns the bot's result string so the admin UI can show WHY a
    candidate wasn't emailed: 'sent' | 'no_email' | 'no_advocate' | 'failed' |
    'unreachable'. The shared key (WA_CRON_SECRET / ADMIN_SECRET) must match on
    both services — a mismatch shows up as 'unreachable'."""
    base = os.environ.get("WA_BOT_BASE_URL", "https://ofoodiez-map-1.onrender.com").rstrip("/")
    secret = os.environ.get("WA_CRON_SECRET") or os.environ.get("ADMIN_SECRET", "ofoodiez2025")
    try:
        resp = requests.post(f"{base}/wa/requests/{request_id}/notify",
                             params={"key": secret}, timeout=15)
        if resp.ok:
            return (resp.json() or {}).get("result") or "failed"
        return "unreachable"
    except Exception:
        logger.exception("admin: notify-via-bot failed for request %s", request_id)
        return "unreachable"


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
    notify_result = _notify_via_bot(req.id) if newly_handled else None
    return jsonify({"id": req.id, "status": req.status,
                    "emailed": notify_result == "sent", "notify_result": notify_result})


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

@admin_bp.route('/api/email-images', methods=['GET'])
@login_required
def get_email_images():
    folder = os.path.join(current_app.static_folder, 'img', 'emails')
    if not os.path.exists(folder):
        return jsonify([])
    try:
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and not f.startswith('.')]
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/hitech-emails/send-email', methods=['POST'])
@login_required
def send_hitech_bulk_email():
    data = request.json or {}
    subject = (data.get('subject') or '').strip()
    body_text = (data.get('body') or '').strip()
    button_url = (data.get('button_url') or '').strip()
    button_text = (data.get('button_text') or '').strip() or 'Register Now'
    image_url = (data.get('image_url') or '').strip()
    
    # If image URL starts with relative /static path or static path, make it absolute
    if image_url:
        if image_url.startswith('/') or image_url.startswith('static/'):
            url_path = image_url if image_url.startswith('/') else '/' + image_url
            image_url = request.url_root.rstrip('/') + url_path
            
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

    image_html = ""
    if image_url:
        image_html = (
            f'<div style="margin-bottom: 24px; text-align: center;">'
            f'  <img src="{image_url}" alt="Ofoodiez Tech Event" style="max-width: 100%; border-radius: 8px; height: auto; display: block; margin: 0 auto;" />'
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
        f'    {image_html}'
        f'    {formatted_body}'
        f'  </div>'
        f'  {button_html}'
        f'  <div style="margin-top: 36px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 12px; color: #777; text-align: center;">'
        f'    זהו דיוור שנשלח לחברי קהילת Ofoodiez Tech. <br>'
        f'    <a href="UNSUBSCRIBE_LINK" style="color: #777; text-decoration: underline;">הסרה מהרשימה</a> | '
        f'    Ofoodiez © 2026'
        f'  </div>'
        f'</div>'
    )

    plain_image_text = f"\n\n[Image: {image_url}]" if image_url else ""
    plain_button_text = f"\n\n{button_text}: {button_url}" if button_url else ""
    text_content = f"{body_text}{plain_image_text}{plain_button_text}\n\nOfoodiez Tech Community"

    from whatsapp_bot.emailer import send_custom_community_email
    from flask import current_app
    import threading

    app_instance = current_app._get_current_object()

    # Campaign identity = the subject. Recipients already marked with it are skipped,
    # so re-triggering the same campaign RESUMES (after a restart or a SendGrid
    # daily-quota cutoff) instead of double-sending. New subject = new campaign.
    pending = [(getattr(r, 'id', None), r.email) for r in recipients
               if getattr(r, 'last_campaign', None) != subject]
    skipped = len(recipients) - len(pending)

    if not pending:
        return jsonify({'success': True,
                        'message': f'Nothing to send — all {skipped} recipients already '
                                   f'received this campaign (same subject = resume; '
                                   f'change the subject for a new campaign).'})

    _BULK_EMAIL_STATUS.clear()
    _BULK_EMAIL_STATUS.update({'campaign': subject, 'total': len(pending),
                               'sent': 0, 'failed': 0, 'done': False, 'aborted': ''})

    def bg_send():
        with app_instance.app_context():
            logger.info(f"📧 Bulk email '{subject}': dispatching to {len(pending)} recipients "
                        f"({skipped} already had it)...")
            failed_emails = []
            consecutive_failures = 0
            for row_id, email in pending:
                try:
                    unsub_link = f"https://ofoodiez.com/hitech/unsubscribe?email={email}"
                    personal_html = html_template.replace("UNSUBSCRIBE_LINK", unsub_link)
                    personal_text = f"{text_content}\n\nלהסרה מהרשימה: {unsub_link}"
                    success = send_custom_community_email(
                        to_email=email,
                        subject=subject,
                        body_html=personal_html,
                        body_text=personal_text
                    )
                except Exception as e:
                    success, e_reason = False, str(e)
                else:
                    e_reason = "SendGrid returned False"
                if success:
                    consecutive_failures = 0
                    _BULK_EMAIL_STATUS['sent'] += 1
                    if row_id is not None:   # persist immediately -> restart-safe resume
                        row = HitechEmail.query.get(row_id)
                        if row:
                            row.last_campaign = subject
                            row.last_sent_at = datetime.utcnow()
                            db.session.commit()
                else:
                    failed_emails.append((email, e_reason))
                    _BULK_EMAIL_STATUS['failed'] += 1
                    consecutive_failures += 1
                    if consecutive_failures >= 8:
                        # Almost certainly the SendGrid daily quota (100/day on free) —
                        # stop burning the list; re-trigger with the same subject after
                        # the quota resets and it resumes from here.
                        _BULK_EMAIL_STATUS['aborted'] = ('stopped after 8 consecutive failures '
                                                         '(SendGrid quota?) — re-send the same '
                                                         'subject later to resume')
                        logger.error(f"📧 Bulk email '{subject}': aborting — 8 consecutive "
                                     f"failures (SendGrid daily quota?).")
                        break

            _BULK_EMAIL_STATUS['done'] = True
            sent_count = _BULK_EMAIL_STATUS['sent']
            logger.info(f"📧 Bulk email '{subject}' finished: sent {sent_count}"
                        f"/{len(pending)}, failed {len(failed_emails)}.")

            # Summary email to ops (kept from the parallel-send revision).
            from whatsapp_bot.config import WaConfig
            admin_email = WaConfig.WA_OPS_EMAIL or "info@ofoodiez.com"
            recipient_emails = [e for _, e in pending]
            if failed_emails:
                failed_details = "\n".join([f" - {email}: {reason}" for email, reason in failed_emails])
                logger.error(f"❌ Failed to send to {len(failed_emails)} recipients:\n{failed_details}")
                
                status_subject = f"Bulk Email Status: FAILED ({len(failed_emails)} failures)"
                status_body_text = (
                    f"Bulk email sending completed with failures.\n\n"
                    f"Subject: {subject}\n"
                    f"Total recipients attempted: {len(recipient_emails)}\n"
                    f"Successfully sent: {sent_count}\n"
                    f"Failed count: {len(failed_emails)}\n\n"
                    f"Failed recipients:\n{failed_details}"
                )
                status_body_html = (
                    f"<div style='font-family: sans-serif; font-size: 15px; color: #222; direction: ltr; text-align: left;'>"
                    f"<h3>Bulk Email Sending completed with failures</h3>"
                    f"<p><b>Subject:</b> {subject}</p>"
                    f"<p><b>Total Attempted:</b> {len(recipient_emails)}</p>"
                    f"<p><b>Successfully Sent:</b> {sent_count}</p>"
                    f"<p><b>Failed Count:</b> {len(failed_emails)}</p>"
                    f"<h4>Failed Recipients:</h4>"
                    f"<pre style='background: #f8f9fa; padding: 12px; border: 1px solid #ddd; border-radius: 4px;'>"
                    f"{failed_details}"
                    f"</pre>"
                    f"</div>"
                )
            else:
                status_subject = "Bulk Email Status: SUCCESS"
                status_body_text = (
                    f"Bulk email sending completed successfully.\n\n"
                    f"Subject: {subject}\n"
                    f"Total recipients attempted: {len(recipient_emails)}\n"
                    f"Successfully sent: {sent_count}\n"
                    f"Failed count: 0\n"
                )
                status_body_html = (
                    f"<div style='font-family: sans-serif; font-size: 15px; color: #222; direction: ltr; text-align: left;'>"
                    f"<h3>Bulk Email Sending Completed Successfully</h3>"
                    f"<p><b>Subject:</b> {subject}</p>"
                    f"<p><b>Total Attempted:</b> {len(recipient_emails)}</p>"
                    f"<p><b>Successfully Sent:</b> {sent_count}</p>"
                    f"<p><b>Failed Count:</b> 0</p>"
                    f"</div>"
                )
            
            try:
                send_custom_community_email(
                    to_email=admin_email,
                    subject=status_subject,
                    body_html=status_body_html,
                    body_text=status_body_text
                )
            except Exception as mail_err:
                logger.error(f"❌ Failed to send status notification email to admin: {mail_err}")

    threading.Thread(target=bg_send, daemon=True).start()

    return jsonify({'success': True,
                    'message': f'Sending to {len(pending)} recipients in the background'
                               + (f' ({skipped} already received this campaign — skipped).'
                                  if skipped else '.')})


# Progress of the (single) in-flight bulk email campaign. In-memory: one Render
# worker, and a restart both kills the thread and clears this — the DB markers
# (last_campaign) are the durable record.
_BULK_EMAIL_STATUS = {}


@admin_bp.route('/api/hitech-emails/send-status')
@login_required
def hitech_send_status():
    return jsonify(_BULK_EMAIL_STATUS)



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
        # ponytail: per-user query; fine at this member count
        'items': ', '.join(sorted(p.item for p in Purchase.query.filter_by(user_id=u.id))),
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
    if 'items' in data:
        # Comma-separated Grow item slugs; replaces the user's purchases.
        # ponytail: re-created rows lose the original paid_at — acceptable for admin overrides.
        want = {s.strip() for s in str(data.get('items') or '').split(',') if s.strip()}
        Purchase.query.filter_by(user_id=user.id).delete()
        for slug in want:
            db.session.add(Purchase(user_id=user.id, item=slug))
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
    from listing_submissions import atomic_write_json
    path = _blog_path(slug)
    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    atomic_write_json(path, data)
    return jsonify({'ok': True})


@admin_bp.route('/api/<slug>/listing-status', methods=['POST'])
@login_required
def update_listing_status(slug):
    """Approve/reject a submitted business listing (a places/suppliers-style
    entry carrying a submission_id — hand-curated rows have none and aren't
    addressable here; submission_id is distinct from the admin table's cosmetic
    display "id" column, which is reassigned/stripped on every render).
    Generic across any page configured in listing_submissions.py. Unlike the
    generic save_blog PUT, this fires a best-effort notification email to the
    submitter, so it's kept separate from plain field edits."""
    from listing_submissions import get_config, blog_json_path, atomic_write_json

    config = get_config(slug)
    if not config:
        return jsonify({'error': 'Unknown listing page'}), 404

    data = request.json or {}
    kind = data.get('kind')
    submission_id = data.get('submission_id')
    new_status = data.get('status')
    if kind not in config['kinds'] or not submission_id or new_status not in ('approved', 'rejected'):
        return jsonify({'error': 'kind, submission_id and a valid status are required'}), 400

    path = blog_json_path(slug)
    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404
    with open(path, encoding='utf-8') as f:
        blog_data = json.load(f)

    array_key = config['kinds'][kind]['array_key']
    entries = blog_data.get(array_key, [])
    entry = next((e for e in entries if e.get('submission_id') == submission_id), None)
    if not entry:
        return jsonify({'error': 'Submission not found'}), 404

    entry['status'] = new_status
    entry['reviewed_at'] = datetime.utcnow().isoformat()

    atomic_write_json(path, blog_data)

    contact_email = (entry.get('contact_email') or '').strip()
    if contact_email:
        try:
            from whatsapp_bot.emailer import send_custom_community_email
            listing_title = config['listing_title_he']
            listing_url = config['listing_url']
            if new_status == 'approved':
                subject = f"העסק שלך אושר ב{listing_title}! 🎉"
                html = (
                    "<div style='font-family: sans-serif; font-size: 15px; color: #222; direction: rtl; text-align: right;'>"
                    f"<p>שלום {entry.get('contact_name') or ''},</p>"
                    f"<p>העסק <b>{entry.get('name')}</b> אושר ומופיע כעת ב{listing_title} של Ofoodiez!</p>"
                    f"<p><a href='{listing_url}'>לצפייה</a></p>"
                    "<p>תודה, Ofoodiez</p></div>"
                )
                text = f"Hi {entry.get('contact_name') or ''},\n\n{entry.get('name')} has been approved and is now live: {listing_url}\n\nThanks,\nOfoodiez"
            else:
                subject = f"עדכון לגבי ההגשה שלך ל{listing_title}"
                html = (
                    "<div style='font-family: sans-serif; font-size: 15px; color: #222; direction: rtl; text-align: right;'>"
                    f"<p>שלום {entry.get('contact_name') or ''},</p>"
                    f"<p>תודה שהגשת את <b>{entry.get('name')}</b> ל{listing_title} של Ofoodiez. הפעם לא נוכל לפרסם את ההגשה.</p>"
                    "<p>תודה, Ofoodiez</p></div>"
                )
                text = f"Hi {entry.get('contact_name') or ''},\n\nThanks for submitting {entry.get('name')}. We're not able to publish it this time.\n\nThanks,\nOfoodiez"
            send_custom_community_email(to_email=contact_email, subject=subject, body_html=html, body_text=text)
        except Exception as e:
            logger.warning("%s listing status email failed: %s", slug, e)

    return jsonify({'ok': True, 'entry': entry})
