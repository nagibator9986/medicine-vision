/**
 * MediPlatform — Main JavaScript
 */

document.addEventListener('DOMContentLoaded', function () {

    // ==========================================
    // Notifications
    // ==========================================

    const notificationBadge = document.getElementById('notificationCount');
    const notificationList = document.getElementById('notificationList');
    const markAllReadBtn = document.getElementById('markAllRead');

    /**
     * Fetch unread notification count and update the badge.
     */
    function fetchNotificationCount() {
        fetch('/api/notifications/count')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var count = data.count || 0;
                if (notificationBadge) {
                    notificationBadge.textContent = count;
                    if (count > 0) {
                        notificationBadge.classList.remove('d-none');
                    } else {
                        notificationBadge.classList.add('d-none');
                    }
                }
            })
            .catch(function () { /* silent */ });
    }

    // Initial fetch + poll every 30 seconds
    fetchNotificationCount();
    setInterval(fetchNotificationCount, 30000);

    /**
     * Load notifications into the dropdown when it's opened.
     */
    var notifDropdownEl = document.getElementById('notificationsDropdown');
    if (notifDropdownEl) {
        notifDropdownEl.addEventListener('show.bs.dropdown', function () {
            loadNotifications();
        });
    }

    function loadNotifications() {
        fetch('/api/notifications')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!notificationList) return;
                var items = data.notifications || [];
                if (items.length === 0) {
                    notificationList.innerHTML =
                        '<div class="text-center py-4 text-muted">' +
                            '<i class="fas fa-bell-slash fa-2x mb-2 d-block"></i>' +
                            '<span class="small">Нет новых уведомлений</span>' +
                        '</div>';
                    return;
                }
                var html = '';
                items.forEach(function (n) {
                    var iconClass = 'info';
                    var iconName = 'fa-info-circle';
                    if (n.type === 'appointment') { iconClass = 'appointment'; iconName = 'fa-calendar-check'; }
                    else if (n.type === 'message') { iconClass = 'message'; iconName = 'fa-comment'; }
                    else if (n.type === 'alert') { iconClass = 'alert'; iconName = 'fa-exclamation-triangle'; }

                    html +=
                        '<div class="notification-item' + (n.read ? '' : ' unread') + '" data-id="' + n.id + '">' +
                            '<div class="notif-icon ' + iconClass + '">' +
                                '<i class="fas ' + iconName + '"></i>' +
                            '</div>' +
                            '<div class="notif-text">' +
                                '<p>' + escapeHtml(n.message) + '</p>' +
                                '<div class="notif-time">' + formatDateRu(n.created_at) + '</div>' +
                            '</div>' +
                        '</div>';
                });
                notificationList.innerHTML = html;

                // Click handler to mark individual notification as read
                notificationList.querySelectorAll('.notification-item').forEach(function (item) {
                    item.addEventListener('click', function () {
                        var id = this.getAttribute('data-id');
                        markNotificationRead(id);
                        this.classList.remove('unread');
                    });
                });
            })
            .catch(function () { /* silent */ });
    }

    function markNotificationRead(id) {
        fetch('/api/notifications/' + id + '/read', { method: 'POST' })
            .then(function () { fetchNotificationCount(); })
            .catch(function () { /* silent */ });
    }

    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', function (e) {
            e.preventDefault();
            fetch('/api/notifications/read-all', { method: 'POST' })
                .then(function () {
                    fetchNotificationCount();
                    if (notificationList) {
                        notificationList.querySelectorAll('.notification-item.unread').forEach(function (el) {
                            el.classList.remove('unread');
                        });
                    }
                })
                .catch(function () { /* silent */ });
        });
    }

    // ==========================================
    // Bootstrap Tooltips & Popovers
    // ==========================================

    var tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (el) {
        new bootstrap.Tooltip(el);
    });

    var popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    popoverTriggerList.forEach(function (el) {
        new bootstrap.Popover(el);
    });

    // ==========================================
    // Auto-dismiss Flash Messages
    // ==========================================

    var flashAlerts = document.querySelectorAll('.flash-alert');
    flashAlerts.forEach(function (alert) {
        setTimeout(function () {
            alert.classList.add('fade-out');
            setTimeout(function () {
                var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
            }, 400);
        }, 5000);
    });

    // ==========================================
    // Smooth Scroll
    // ==========================================

    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (e) {
            var target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // ==========================================
    // Confirm Delete Dialog
    // ==========================================

    /**
     * Show a confirm-delete dialog. Returns a Promise that resolves to true/false.
     * Usage:
     *   confirmDelete('Вы уверены, что хотите удалить эту запись?').then(function(ok) { ... });
     */
    window.confirmDelete = function (message, title) {
        return new Promise(function (resolve) {
            var overlay = document.createElement('div');
            overlay.className = 'confirm-dialog-overlay';
            overlay.innerHTML =
                '<div class="confirm-dialog">' +
                    '<div class="confirm-icon"><i class="fas fa-trash-alt"></i></div>' +
                    '<h5 class="mb-2">' + escapeHtml(title || 'Удаление') + '</h5>' +
                    '<p class="text-muted mb-4">' + escapeHtml(message || 'Вы уверены? Это действие нельзя отменить.') + '</p>' +
                    '<div class="d-flex justify-content-center gap-3">' +
                        '<button class="btn btn-secondary px-4 btn-cancel">Отмена</button>' +
                        '<button class="btn btn-danger px-4 btn-confirm">Удалить</button>' +
                    '</div>' +
                '</div>';

            document.body.appendChild(overlay);

            overlay.querySelector('.btn-cancel').addEventListener('click', function () {
                overlay.remove();
                resolve(false);
            });

            overlay.querySelector('.btn-confirm').addEventListener('click', function () {
                overlay.remove();
                resolve(true);
            });

            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) {
                    overlay.remove();
                    resolve(false);
                }
            });
        });
    };

    // Wire up elements with data-confirm-delete attribute
    document.querySelectorAll('[data-confirm-delete]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            e.preventDefault();
            var msg = this.getAttribute('data-confirm-delete') || 'Вы уверены? Это действие нельзя отменить.';
            var href = this.getAttribute('href') || this.getAttribute('data-href');
            confirmDelete(msg).then(function (ok) {
                if (ok && href) {
                    window.location.href = href;
                }
            });
        });
    });

    // ==========================================
    // Format Dates to Russian Locale
    // ==========================================

    var MONTHS_RU_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    var MONTHS_RU = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

    /**
     * Format ISO date string to Russian locale.
     * E.g. "2026-03-22T14:30:00" => "22 марта 2026, 14:30"
     */
    window.formatDateRu = formatDateRu;

    function formatDateRu(dateStr) {
        if (!dateStr) return '';
        var d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        var day = d.getDate();
        var month = MONTHS_RU[d.getMonth()];
        var year = d.getFullYear();
        var hours = String(d.getHours()).padStart(2, '0');
        var mins = String(d.getMinutes()).padStart(2, '0');
        return day + ' ' + month + ' ' + year + ', ' + hours + ':' + mins;
    }

    /**
     * Format date short: "22 мар"
     */
    window.formatDateShortRu = function (dateStr) {
        if (!dateStr) return '';
        var d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.getDate() + ' ' + MONTHS_RU_SHORT[d.getMonth()];
    };

    // Auto-format elements with data-date attribute
    document.querySelectorAll('[data-date]').forEach(function (el) {
        var raw = el.getAttribute('data-date');
        el.textContent = formatDateRu(raw);
    });

    // ==========================================
    // Star Rating Widget
    // ==========================================

    document.querySelectorAll('.star-rating').forEach(function (widget) {
        var inputs = widget.querySelectorAll('input[type="radio"]');
        var labels = widget.querySelectorAll('label');

        labels.forEach(function (label) {
            label.addEventListener('click', function () {
                var value = this.getAttribute('for');
                var input = document.getElementById(value);
                if (input) {
                    input.checked = true;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });

            label.addEventListener('mouseenter', function () {
                var targetValue = parseInt(this.getAttribute('data-value') || '0', 10);
                labels.forEach(function (l) {
                    var lv = parseInt(l.getAttribute('data-value') || '0', 10);
                    if (lv <= targetValue) {
                        l.style.color = '#fbbf24';
                    } else {
                        l.style.color = '#d1d5db';
                    }
                });
            });
        });

        widget.addEventListener('mouseleave', function () {
            var checkedInput = widget.querySelector('input:checked');
            var checkedVal = checkedInput ? parseInt(checkedInput.value, 10) : 0;
            labels.forEach(function (l) {
                var lv = parseInt(l.getAttribute('data-value') || '0', 10);
                if (lv <= checkedVal) {
                    l.style.color = '#fbbf24';
                } else {
                    l.style.color = '#d1d5db';
                }
            });
        });
    });

    // ==========================================
    // Utility: Escape HTML
    // ==========================================

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

});
