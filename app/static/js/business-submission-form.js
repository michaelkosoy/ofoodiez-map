/**
 * Generic "add your business" submission modal — used by any blog listing page
 * that lets the public submit a business for moderation (see
 * listing_submissions.py for the backend side). Reads its config from
 * window.BUSINESS_SUBMISSION_CONFIG, which the including page renders as:
 *
 *   window.BUSINESS_SUBMISSION_CONFIG = {
 *     slug: 'bachelorette',
 *     modalSubtitle: '...',
 *     kinds: { venue: { label: '...', categories: [...] }, supplier: {...} }
 *   };
 *
 * Nothing in this file is bachelorette-specific — a future page (e.g. a HiTech
 * suppliers directory) only needs to render its own config object and include
 * this same script + components/business_submission_modal.html.
 */
(function () {
    var config = window.BUSINESS_SUBMISSION_CONFIG || { slug: '', kinds: {} };
    var selectedKind = null;

    function buildKindToggle() {
        var container = document.getElementById('biz-kind-toggle');
        if (!container) return;
        container.innerHTML = '';
        Object.keys(config.kinds).forEach(function (kindKey) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'biz-kind-btn';
            btn.dataset.kind = kindKey;
            btn.textContent = config.kinds[kindKey].label_he;
            btn.addEventListener('click', function () { selectKind(kindKey); });
            container.appendChild(btn);
        });
    }

    function selectKind(kindKey) {
        selectedKind = kindKey;
        document.getElementById('biz-kind').value = kindKey;

        document.querySelectorAll('.biz-kind-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.kind === kindKey);
        });

        var categorySelect = document.getElementById('biz-category');
        var categories = (config.kinds[kindKey] && config.kinds[kindKey].categories) || [];
        categorySelect.disabled = false;
        categorySelect.innerHTML = '<option value="" disabled selected>בחרו קטגוריה</option>' +
            categories.map(function (c) { return '<option value="' + c + '">' + c + '</option>'; }).join('');
    }

    window.openBusinessModal = function () {
        var modal = document.getElementById('business-modal');
        selectedKind = null;
        document.getElementById('biz-kind').value = '';
        document.querySelectorAll('.biz-kind-btn').forEach(function (btn) { btn.classList.remove('active'); });
        var categorySelect = document.getElementById('biz-category');
        categorySelect.innerHTML = '<option value="" disabled selected>בחרו קטגוריה</option>';
        categorySelect.disabled = true;

        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    };

    window.closeBusinessModal = function () {
        document.getElementById('business-modal').classList.remove('show');
        document.body.style.overflow = '';
        document.getElementById('business-form').reset();
        document.querySelectorAll('.biz-kind-btn').forEach(function (btn) { btn.classList.remove('active'); });
        document.getElementById('biz-category').disabled = true;
    };

    window.closeBusinessModalOnOutside = function (event) {
        if (event.target.id === 'business-modal') window.closeBusinessModal();
    };

    window.submitBusinessForm = function (event) {
        event.preventDefault();
        var form = event.target;
        var submitBtn = form.querySelector('.biz-form-submit-btn');
        var originalText = submitBtn.innerHTML;

        if (!selectedKind) {
            showBusinessFormToast('❌ בחרו קודם מה אתם מוסיפים', true);
            return;
        }

        var contactEmail = document.getElementById('biz-contact-email').value.trim();
        var contactPhone = document.getElementById('biz-contact-phone').value.trim();
        if (!contactEmail && !contactPhone) {
            showBusinessFormToast('❌ נא למלא אימייל או טלפון ליצירת קשר', true);
            return;
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> שולח...';

        var payload = {
            kind: selectedKind,
            website: document.getElementById('biz-website').value, // honeypot
            name: document.getElementById('biz-name').value.trim(),
            category: document.getElementById('biz-category').value,
            description: document.getElementById('biz-description').value.trim(),
            location: document.getElementById('biz-location').value.trim(),
            price: document.getElementById('biz-price').value.trim(),
            discount: document.getElementById('biz-discount').value.trim(),
            link: document.getElementById('biz-link').value.trim(),
            instagram: document.getElementById('biz-instagram').value.trim(),
            whatsapp: document.getElementById('biz-whatsapp').value.trim(),
            contact_name: document.getElementById('biz-contact-name').value.trim(),
            contact_email: contactEmail,
            contact_phone: contactPhone
        };

        fetch('/api/' + config.slug + '/submit-business', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (response) { return response.json(); })
            .then(function (result) {
                if (result.success) {
                    window.closeBusinessModal();
                    showBusinessFormToast('✅ תודה רבה! הבקשה נשלחה ותיבדק בקרוב.');
                } else {
                    showBusinessFormToast('❌ ' + (result.message || 'שגיאה בשליחה, נסו שוב.'), true);
                }
            })
            .catch(function () {
                showBusinessFormToast('❌ שגיאה בשליחה, נסו שוב מאוחר יותר.', true);
            })
            .finally(function () {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            });
    };

    function showBusinessFormToast(message, isError) {
        var existing = document.querySelector('.biz-toast');
        if (existing) existing.remove();

        var toast = document.createElement('div');
        toast.className = 'biz-toast' + (isError ? ' biz-toast-error' : '');
        toast.textContent = message;
        document.body.appendChild(toast);

        requestAnimationFrame(function () { toast.classList.add('show'); });
        setTimeout(function () {
            toast.classList.remove('show');
            setTimeout(function () { toast.remove(); }, 300);
        }, 3500);
    }

    document.addEventListener('DOMContentLoaded', buildKindToggle);
})();
