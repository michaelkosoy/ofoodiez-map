from flask import render_template, redirect, url_for
from . import admin_bp
from .auth import login_required

@admin_bp.route('/')
@login_required
def dashboard():
    # Redirect to places by default
    return redirect(url_for('admin.places'))

@admin_bp.route('/places')
@login_required
def places():
    return render_template('admin/places.html')

@admin_bp.route('/events')
@login_required
def events():
    return render_template('admin/events.html')

@admin_bp.route('/whatsapp')
@login_required
def whatsapp():
    return render_template('admin/whatsapp.html')

@admin_bp.route('/hitech')
@login_required
def hitech_emails():
    return render_template('admin/hitech.html')

@admin_bp.route('/hitech/content')
@login_required
def hitech_content():
    return render_template('admin/hitech_content.html')

@admin_bp.route('/members')
@login_required
def members():
    return render_template('admin/members.html')

@admin_bp.route('/blog')
@login_required
def blog():
    return render_template('admin/blog.html')
