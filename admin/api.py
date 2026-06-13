from flask import jsonify, request
from database.models import db, HappyHourPlace, PopupEvent
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
