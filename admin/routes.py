from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, request, flash
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

@admin_bp.route('/portfolio/content')
@login_required
def portfolio_content():
    return render_template('admin/portfolio_content.html')

@admin_bp.route('/members')
@login_required
def members():
    return render_template('admin/members.html')

@admin_bp.route('/blog')
@login_required
def blog():
    return render_template('admin/blog.html')

@admin_bp.route('/hitech/suppliers')
@login_required
def hitech_suppliers():
    return render_template('admin/hitech_suppliers.html')


# ---- Portfolio access codes (client codes for the private /portfolio page) ----

@admin_bp.route('/portfolio/access')
@login_required
def portfolio_access():
    from database.models import PortfolioAccess
    codes = PortfolioAccess.query.order_by(PortfolioAccess.created_at.desc()).all()
    return render_template('admin/portfolio_access.html', codes=codes, now=datetime.utcnow())

@admin_bp.route('/portfolio/access/create', methods=['POST'])
@login_required
def portfolio_access_create():
    from database.models import db, PortfolioAccess
    company = request.form.get('company', '').strip()
    code = request.form.get('code', '').strip() or company.lower().replace(' ', '')
    show_launch = bool(request.form.get('show_launch'))
    show_boost = bool(request.form.get('show_boost'))
    launch_price = request.form.get('launch_price', '').strip() or None
    launch_price_note = request.form.get('launch_price_note', '').strip() or None
    boost_price = request.form.get('boost_price', '').strip() or None
    if not company:
        flash('Company name is required', 'error')
    elif not show_launch and not show_boost:
        flash('Pick at least one package to show', 'error')
    elif PortfolioAccess.query.filter(db.func.lower(PortfolioAccess.code) == code.lower()).first():
        flash(f'Code "{code}" already exists — pick another', 'error')
    else:
        db.session.add(PortfolioAccess(company=company, code=code,
                                       expires_at=datetime.utcnow() + timedelta(days=7),
                                       show_launch=show_launch, show_boost=show_boost,
                                       launch_price=launch_price,
                                       launch_price_note=launch_price_note,
                                       boost_price=boost_price))
        db.session.commit()
        flash(f'Access for {company} created — code "{code}", valid 7 days', 'success')
    return redirect(url_for('admin.portfolio_access'))

@admin_bp.route('/portfolio/access/<int:code_id>/renew', methods=['POST'])
@login_required
def portfolio_access_renew(code_id):
    from database.models import db, PortfolioAccess
    row = db.session.get(PortfolioAccess, code_id)
    if row:
        row.expires_at = datetime.utcnow() + timedelta(days=7)
        db.session.commit()
        flash(f'{row.company} renewed — 7 days from now', 'success')
    return redirect(url_for('admin.portfolio_access'))

@admin_bp.route('/portfolio/access/<int:code_id>/delete', methods=['POST'])
@login_required
def portfolio_access_delete(code_id):
    from database.models import db, PortfolioAccess
    row = db.session.get(PortfolioAccess, code_id)
    if row:
        db.session.delete(row)
        db.session.commit()
        flash(f'Access for {row.company} revoked', 'success')
    return redirect(url_for('admin.portfolio_access'))
