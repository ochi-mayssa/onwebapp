/* ==========================================================================
   Branding Wizard — Interactive JavaScript
   ========================================================================== */
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('wizardForm');
    const step = form ? parseInt(form.dataset.step, 10) : 1;

    function csrfToken() {
        const el = document.querySelector('[name=csrfmiddlewaretoken]');
        return el ? el.value : '';
    }

    /* ── Option chips (brand values, current branding) ─────────────── */
    document.querySelectorAll('.option-chip').forEach(function (chip) {
        chip.addEventListener('click', function (e) {
            if (e.target.tagName === 'INPUT') return;
            const cb = chip.querySelector('input[type="checkbox"]');
            if (!cb) return;
            cb.checked = !cb.checked;
            chip.classList.toggle('selected', cb.checked);
        });
        const cb = chip.querySelector('input[type="checkbox"]');
        if (cb) {
            cb.addEventListener('change', function () {
                chip.classList.toggle('selected', cb.checked);
            });
        }
    });

    /* ── Color picker (step 2) ──────────────────────────────────────── */
    var MAX_COLORS = 5;
    var selectedColorsEl = document.getElementById('selectedColors');
    var colorInputsEl = document.getElementById('colorInputs');
    var customPicker = document.getElementById('customColorPicker');
    var customPreview = document.getElementById('customColorPreview');
    var addCustomBtn = document.getElementById('addCustomColor');

    function getSelectedColors() {
        return Array.from(colorInputsEl.querySelectorAll('input[name="preferred_colors"]'))
            .map(function (inp) { return inp.value; });
    }

    function addColor(hex) {
        hex = hex.toLowerCase();
        if (getSelectedColors().indexOf(hex) !== -1) return;
        if (getSelectedColors().length >= MAX_COLORS) return;

        var inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'preferred_colors';
        inp.value = hex;
        colorInputsEl.appendChild(inp);

        renderSelectedColors();
        scheduleAutosave();
    }

    function removeColor(hex) {
        hex = hex.toLowerCase();
        var inp = colorInputsEl.querySelector('input[name="preferred_colors"][value="' + hex + '"]');
        if (inp) inp.remove();
        renderSelectedColors();
        scheduleAutosave();
    }

    function renderSelectedColors() {
        if (!selectedColorsEl) return;
        var colors = getSelectedColors();
        selectedColorsEl.innerHTML = '';
        colors.forEach(function (hex) {
            var chip = document.createElement('span');
            chip.className = 'selected-color-chip';
            chip.dataset.color = hex;
            chip.innerHTML =
                '<span class="selected-color-fill" style="background:' + hex + '"></span>' +
                '<span class="selected-color-hex">' + hex + '</span>' +
                '<button type="button" class="selected-color-remove" aria-label="Remove color"><i class="fa-solid fa-xmark"></i></button>';
            chip.querySelector('.selected-color-remove').addEventListener('click', function () {
                removeColor(hex);
            });
            selectedColorsEl.appendChild(chip);
        });
    }

    if (customPicker) {
        customPicker.addEventListener('input', function () {
            if (customPreview) customPreview.style.background = customPicker.value;
        });
    }
    if (addCustomBtn) {
        addCustomBtn.addEventListener('click', function () {
            if (customPicker) addColor(customPicker.value);
        });
    }

    if (selectedColorsEl) {
        selectedColorsEl.addEventListener('click', function (e) {
            var removeBtn = e.target.closest('.selected-color-remove');
            if (!removeBtn) return;
            var chip = removeBtn.closest('.selected-color-chip');
            if (chip) removeColor(chip.dataset.color);
        });
    }

    renderSelectedColors();

    /* ── Collection cards (step 4) ─────────────────────────────────── */
    document.querySelectorAll('.collection-card').forEach(function (card) {
        card.addEventListener('click', function (e) {
            if (e.target.closest('.btn-preview-collection') || e.target.closest('.collection-choose')) return;
            var radio = card.querySelector('input[type="radio"][name="collection"]');
            if (radio) {
                radio.checked = true;
                selectCollection(card);
            }
        });
    });

    var chooseBtns = document.querySelectorAll('.collection-choose');
    chooseBtns.forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var card = btn.closest('.collection-card');
            var radio = card.querySelector('input[type="radio"][name="collection"]');
            if (radio) {
                radio.checked = true;
                selectCollection(card);
            }
        });
    });

    function selectCollection(card) {
        document.querySelectorAll('.collection-card').forEach(function (c) {
            c.classList.remove('is-selected');
            var badge = c.querySelector('.collection-selected-badge');
            if (badge) badge.remove();
        });
        card.classList.add('is-selected');
        if (!card.querySelector('.collection-selected-badge')) {
            var cover = card.querySelector('.collection-cover');
            if (cover) {
                var badge = document.createElement('span');
                badge.className = 'collection-selected-badge';
                badge.innerHTML = '<i class="fa-solid fa-check"></i>';
                cover.appendChild(badge);
            }
        }
        // Update summary
        var summary = document.getElementById('collectionSummary');
        if (summary) {
            summary.classList.remove('d-none');
            document.getElementById('summaryName').textContent = card.dataset.name || '—';
            document.getElementById('summaryIndustry').textContent = card.dataset.industry || '';
            document.getElementById('summaryThumb').src = card.dataset.image || '';
            document.getElementById('summaryThumb').alt = card.dataset.name || '';
        }
    }

    // Restore selection on load
    var checkedRadio = document.querySelector('input[type="radio"][name="collection"]:checked');
    if (checkedRadio) {
        var card = checkedRadio.closest('.collection-card');
        if (card) selectCollection(card);
    }

    /* ── Filter chips (step 4) ─────────────────────────────────────── */
    var filterChips = document.querySelectorAll('#libraryFilter .filter-chip');
    var groups = document.querySelectorAll('#libraryGroups .library-group');

    filterChips.forEach(function (chip) {
        chip.addEventListener('click', function () {
            filterChips.forEach(function (c) { c.classList.remove('is-active'); });
            chip.classList.add('is-active');
            var filter = chip.dataset.filter;
            groups.forEach(function (g) {
                g.style.display = (filter === 'all' || g.dataset.category === filter) ? '' : 'none';
            });
        });
    });

    /* ── Collection preview modal ──────────────────────────────────── */
    var previewBtns = document.querySelectorAll('.btn-preview-collection');
    previewBtns.forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var card = btn.closest('.collection-card');
            if (!card) return;
            var modal = document.getElementById('collectionPreviewModal');
            var body = document.getElementById('collectionPreviewBody');
            if (!modal || !body) return;

            var img = card.dataset.image;
            var name = card.dataset.name || '';
            var industry = card.dataset.industry || '';
            var desc = card.dataset.description || '';
            var color = card.dataset.color || '#6366f1';
            var tags = [];
            try { tags = JSON.parse(card.dataset.tags || '[]'); } catch (e) {}
            var examples = [];
            try { examples = JSON.parse(card.dataset.examples || '[]'); } catch (e) {}

            body.innerHTML =
                '<div style="background:linear-gradient(135deg,' + color + '22,' + color + '44);min-height:200px;display:flex;align-items:center;justify-content:center;">' +
                    (img ? '<img src="' + img + '" alt="' + name + '" style="width:100%;max-height:320px;object-fit:cover;">' :
                     '<span style="font-size:3rem;font-weight:800;color:' + color + ';">' + name.slice(0, 2).toUpperCase() + '</span>') +
                '</div>' +
                '<div class="p-4">' +
                    '<h4 class="fw-800 mb-1">' + name + '</h4>' +
                    '<p class="text-muted mb-2">' + industry + '</p>' +
                    '<p class="mb-3">' + desc + '</p>' +
                    (tags.length ? '<div class="d-flex flex-wrap gap-2 mb-3">' + tags.map(function (t) {
                        return '<span class="badge bg-light text-dark border">' + t + '</span>';
                    }).join('') + '</div>' : '') +
                    (examples.length ? '<h6 class="fw-700 mb-2">What\'s Included</h6><ul class="mb-0">' + examples.map(function (ex) {
                        return '<li><i class="fa-solid fa-check text-success me-1"></i>' + ex + '</li>';
                    }).join('') + '</ul>' : '') +
                '</div>';

            var bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        });
    });

    /* ── Dropzone file upload (step 3) ─────────────────────────────── */
    var dropzone = document.getElementById('dropzone');
    var fileInput = document.getElementById('fileInput');
    var uploadList = document.getElementById('uploadList');

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', function () { fileInput.click(); });
        dropzone.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
        });

        dropzone.addEventListener('dragover', function (e) { e.preventDefault(); dropzone.classList.add('is-dragover'); });
        dropzone.addEventListener('dragleave', function () { dropzone.classList.remove('is-dragover'); });
        dropzone.addEventListener('drop', function (e) {
            e.preventDefault();
            dropzone.classList.remove('is-dragover');
            if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener('change', function () {
            if (fileInput.files.length) uploadFiles(fileInput.files);
            fileInput.value = '';
        });
    }

    function uploadFiles(files) {
        Array.from(files).forEach(function (file) {
            var fd = new FormData();
            fd.append('file', file);
            var item = createUploadItem(file.name, file.size, 'Uploading…');
            fetch('/branding/wizard/upload/', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken() },
                body: fd,
            })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
            .then(function (res) {
                if (res.ok && res.data.ok) {
                    updateUploadItem(item, res.data);
                } else {
                    failUploadItem(item, res.data.error || res.data.details || 'Upload failed');
                }
            })
            .catch(function () { failUploadItem(item, 'Network error'); });
        });
    }

    function createUploadItem(name, size, status) {
        var div = document.createElement('div');
        div.className = 'upload-item is-uploading';
        div.innerHTML =
            '<div class="upload-thumb upload-thumb-file"><i class="fa-solid fa-spinner fa-spin"></i></div>' +
            '<div class="upload-meta"><span class="upload-name">' + escapeHtml(name) + '</span>' +
            '<span class="upload-sub">' + formatSize(size) + ' · ' + status + '</span></div>' +
            '<span class="upload-type-badge">…</span>' +
            '<button type="button" class="upload-remove" aria-label="Cancel"><i class="fa-solid fa-xmark"></i></button>';
        if (uploadList) uploadList.prepend(div);
        return div;
    }

    function updateUploadItem(item, data) {
        if (!item) return;
        item.classList.remove('is-uploading');
        item.dataset.assetId = data.id;
        var thumb = item.querySelector('.upload-thumb');
        if (data.is_image && data.url) {
            thumb.className = 'upload-thumb';
            thumb.innerHTML = '<img src="' + data.url + '" alt="' + escapeHtml(data.name) + '">';
        } else {
            thumb.innerHTML = '<i class="fa-solid fa-file"></i>';
        }
        item.querySelector('.upload-sub').textContent = data.type + ' · ' + data.size;
        item.querySelector('.upload-type-badge').textContent = data.type;
        var rmBtn = item.querySelector('.upload-remove');
        rmBtn.dataset.assetId = data.id;
        rmBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
        rmBtn.addEventListener('click', function () { removeAsset(item, data.id); });
    }

    function failUploadItem(item, msg) {
        if (!item) return;
        item.classList.remove('is-uploading');
        item.classList.add('is-error');
        item.querySelector('.upload-sub').textContent = msg;
        item.querySelector('.upload-thumb').innerHTML = '<i class="fa-solid fa-triangle-exclamation text-danger"></i>';
        var rmBtn = item.querySelector('.upload-remove');
        rmBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        rmBtn.addEventListener('click', function () { item.remove(); });
    }

    function removeAsset(item, assetId) {
        if (!assetId) { item.remove(); return; }
        fetch('/branding/upload/' + assetId + '/delete/', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken() },
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.ok) item.remove();
        })
        .catch(function () { item.remove(); });
    }

    // Bind existing delete buttons
    document.querySelectorAll('.upload-remove[data-asset-id]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var item = btn.closest('.upload-item');
            removeAsset(item, btn.dataset.assetId);
        });
    });

    function formatSize(bytes) {
        if (!bytes) return '0 B';
        var units = ['B', 'KB', 'MB', 'GB'];
        var i = 0;
        while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
        return bytes.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
    }

    function escapeHtml(str) {
        var d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    /* ── Autosave (debounced on input change) ──────────────────────── */
    var autosaveTimer = null;
    var autosaveStatus = document.getElementById('autosaveStatus');
    var autosaveLabel = autosaveStatus ? autosaveStatus.querySelector('span:last-child') : null;

    function scheduleAutosave() {
        clearTimeout(autosaveTimer);
        if (autosaveLabel) autosaveLabel.textContent = 'Unsaved changes…';
        if (autosaveStatus) autosaveStatus.classList.add('is-saving');
        autosaveTimer = setTimeout(doAutosave, 1500);
    }

    function doAutosave() {
        if (!form) return;
        var data = collectStepData(step);
        fetch('/branding/wizard/autosave/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ step: step, data: data }),
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.status === 'saved') {
                if (autosaveLabel) autosaveLabel.textContent = 'Saved';
                if (autosaveStatus) { autosaveStatus.classList.remove('is-saving'); autosaveStatus.classList.add('is-saved'); }
                setTimeout(function () {
                    if (autosaveStatus) autosaveStatus.classList.remove('is-saved');
                }, 2000);
            }
        })
        .catch(function () {
            if (autosaveLabel) autosaveLabel.textContent = 'Save failed';
            if (autosaveStatus) autosaveStatus.classList.remove('is-saving');
        });
    }

    function collectStepData(s) {
        var data = {};
        var names = ['company_name', 'industry', 'website', 'country', 'business_description',
                     'company_description', 'target_audience', 'additional_notes'];
        names.forEach(function (n) {
            var el = document.getElementById('id_' + n);
            if (el) data[n] = el.value;
        });
        // Consent
        ['consent_data_processing', 'consent_analytics', 'consent_marketing', 'consent_third_party'].forEach(function (n) {
            var el = document.querySelector('[name="' + n + '"]');
            if (el) data[n] = el.checked ? 'on' : '';
        });
        // Multi-select checkboxes (brand_values, current_branding only)
        ['brand_values', 'current_branding'].forEach(function (n) {
            var checked = document.querySelectorAll('[name="' + n + '"]:checked');
            data[n] = Array.from(checked).map(function (c) { return c.value; });
        });
        // Preferred colors from hidden inputs
        data.preferred_colors = Array.from(
            document.querySelectorAll('#colorInputs input[name="preferred_colors"]')
        ).map(function (inp) { return inp.value; });
        // Collection
        var col = document.querySelector('[name="collection"]:checked');
        if (col) data.collection_id = col.value;
        return data;
    }

    if (form) {
        form.addEventListener('input', scheduleAutosave);
        form.addEventListener('change', scheduleAutosave);
    }
});
