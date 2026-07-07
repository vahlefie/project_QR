from datetime import date, datetime
from io import BytesIO
import re

import pandas as pd
from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.security import generate_password_hash


# Fungsi untuk membuat Blueprint admin dan super-admin.
def create_admin_blueprint(deps):
    admin_bp = Blueprint("admin", __name__)
    account_number_pattern = re.compile(r"^[0-9]{10,16}$")

    # Fungsi untuk redirect kembali ke halaman setting WhatsApp.
    def build_whatsapp_settings_redirect(message=None, error=None, template_id=None):
        query_args = {}
        if message:
            query_args["message"] = message
        if error:
            query_args["error"] = error
        if template_id:
            query_args["template_id"] = template_id
        return redirect(url_for("admin.whatsapp_settings", **query_args))

    # Fungsi untuk redirect kembali ke halaman payment admin.
    def build_payment_redirect(message=None, error=None, owner_user_id=None):
        query_args = {}
        if message:
            query_args["message"] = message
        if error:
            query_args["error"] = error
        if owner_user_id:
            query_args["owner_user_id"] = owner_user_id
        return redirect(url_for("admin.admin_payment", **query_args))

    # Fungsi untuk membaca waktu payment format HH:MM.
    def parse_payment_time(value):
        try:
            return datetime.strptime(value, "%H:%M").time()
        except (TypeError, ValueError):
            return None

    # Fungsi untuk mengambil daftar client pada halaman payment.
    def get_payment_clients():
        return deps.User.query.filter_by(role=deps.ROLE_USER).order_by(deps.User.nama.asc()).all()

    # Fungsi untuk membangun context histori payment client.
    def build_payment_history_context():
        selected_owner_user_id = deps.parse_int(request.args.get("owner_user_id"))
        clients = get_payment_clients()
        query = deps.BillingPayment.query.join(deps.User)

        if selected_owner_user_id:
            query = query.filter(deps.BillingPayment.user_id == selected_owner_user_id)

        payments = query.order_by(deps.BillingPayment.payment_date.desc(), deps.BillingPayment.id.desc()).all()
        return {
            "user": deps.get_current_user_display_name(),
            "clients": clients,
            "payments": payments,
            "selected_owner_user_id": selected_owner_user_id,
            "total_cash_in": sum(payment.amount or 0 for payment in payments),
        }

    # Fungsi untuk memvalidasi password akun aktif sebelum aksi sensitif.
    def validate_current_account_password():
        current_user = deps.get_current_user()
        password = request.form.get("account_block_password", "").strip()
        if not password:
            return current_user, "Password wajib diisi."
        if not current_user or not deps.password_matches(current_user.password, password):
            return current_user, "Password tidak sesuai."
        return current_user, None

    # Fungsi untuk menampilkan daftar user dengan filter dan pagination.
    @admin_bp.route("/users")
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk menampilkan daftar user/client.
    def users():
        all_users = deps.User.query.filter_by(role=deps.ROLE_USER).all()
        deps.sync_users_activation_status(all_users)

        search = request.args.get("search", "")
        page = deps.parse_int(request.args.get("page"), 1)
        per_page = deps.parse_int(request.args.get("per_page"), 10)
        sort_by = request.args.get("sort_by", "name_asc")
        context = deps.build_user_list_context(search, page, per_page, sort_by)
        return render_template("users.html", **context)

    # Fungsi untuk menampilkan transaksi pembayaran client.
    @admin_bp.route("/admin/payment")
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk menampilkan form input payment client.
    def admin_payment():
        selected_owner_user_id = deps.parse_int(request.args.get("owner_user_id"))
        return render_template(
            "admin_payment.html",
            user=deps.get_current_user_display_name(),
            clients=get_payment_clients(),
            selected_owner_user_id=selected_owner_user_id,
            bank_options=deps.INDONESIA_BANK_OPTIONS,
            package_options=deps.PACKAGE_OPTIONS,
            payment_type_options=("Lunas", "Sebagian", "DP"),
            min_period_end_date=deps.get_min_period_end_date().isoformat(),
            today=date.today().isoformat(),
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )

    # Fungsi untuk menampilkan histori pembayaran client.
    @admin_bp.route("/admin/payment-history")
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk melihat histori payment semua client.
    def admin_payment_history():
        return render_template("admin_payment_history.html", **build_payment_history_context())

    # Fungsi untuk mencatat pembayaran client secara manual.
    @admin_bp.route("/admin/payment/input", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk input payment manual dan pencatatan kas masuk.
    def input_payment():
        owner_user_id = deps.parse_int(request.form.get("owner_user_id"))
        account = deps.User.query.filter_by(id=owner_user_id, role=deps.ROLE_USER).first() if owner_user_id else None
        if not account:
            return build_payment_redirect(error="Client wajib dipilih.")

        amount_text = deps.get_form_text("amount").replace(".", "").replace(",", "")
        amount = deps.parse_int(amount_text)
        if amount is None or amount <= 0:
            return build_payment_redirect(error="Nominal pembayaran harus lebih dari 0.", owner_user_id=owner_user_id)

        payment_date = deps.parse_iso_date(request.form.get("payment_date", "").strip()) or date.today()
        payment_time = parse_payment_time(request.form.get("payment_time", "").strip())
        if not payment_time:
            return build_payment_redirect(error="Waktu Payment wajib diisi format HH:MM.", owner_user_id=owner_user_id)

        package_name = request.form.get("package_name", "").strip().lower()
        if package_name not in deps.PACKAGE_OPTIONS:
            return build_payment_redirect(error="Paket wajib dipilih.", owner_user_id=owner_user_id)

        payment_type = request.form.get("payment_type", "").strip()
        if payment_type not in {"Lunas", "Sebagian", "DP"}:
            return build_payment_redirect(error="Jenis Bayar tidak valid.", owner_user_id=owner_user_id)

        period_start = deps.parse_iso_date(request.form.get("period_start", "").strip())
        period_end = deps.parse_iso_date(request.form.get("period_end", "").strip())
        event_name = deps.get_form_text("event_name")
        if not period_start:
            return build_payment_redirect(error="Periode Mulai wajib diisi.", owner_user_id=owner_user_id)

        if not period_end or period_end <= date.today():
            return build_payment_redirect(
                error="Periode Akhir harus lebih dari hari ini.",
                owner_user_id=owner_user_id,
            )

        if period_start and period_end < period_start:
            return build_payment_redirect(
                error="Periode Akhir tidak boleh lebih awal dari Periode Mulai.",
                owner_user_id=owner_user_id,
            )

        if not event_name:
            return build_payment_redirect(error="Event wajib diisi.", owner_user_id=owner_user_id)

        payment_method = deps.get_form_text("payment_method") or "Transfer"
        if payment_method not in {"Transfer", "Cash", "QRIS", "Virtual Account"}:
            return build_payment_redirect(error="Metode payment tidak valid.", owner_user_id=owner_user_id)

        origin_bank = deps.get_form_text("origin_bank")
        account_number = deps.get_form_text("account_number")
        if payment_method == "Transfer":
            if not origin_bank or origin_bank == "N/A" or not account_number or account_number == "N/A":
                return build_payment_redirect(
                    error="Bank Asal dan Nomor Rekening wajib diisi untuk metode Transfer.",
                    owner_user_id=owner_user_id,
                )
            if origin_bank not in deps.INDONESIA_BANK_OPTIONS:
                return build_payment_redirect(error="Bank Asal tidak valid.", owner_user_id=owner_user_id)
            if not account_number_pattern.fullmatch(account_number):
                return build_payment_redirect(
                    error="Nomor Rekening harus 10 - 16 digit angka.",
                    owner_user_id=owner_user_id,
                )
        else:
            origin_bank = "N/A"
            account_number = "N/A"

        previous_payment = deps.get_latest_verified_payment(account)
        if previous_payment and previous_payment.period_end and previous_payment.period_end < date.today():
            deps.archive_previous_event_for_reactivation(account, previous_payment)

        payment = deps.BillingPayment()
        payment.user_id = account.id
        payment.payment_date = payment_date
        payment.payment_time = payment_time
        payment.amount = amount
        payment.payment_method = payment_method
        payment.origin_bank = origin_bank
        payment.account_number = account_number
        payment.payment_type = payment_type
        payment.package_name = package_name
        payment.period_start = period_start
        payment.period_end = period_end
        payment.event_name = event_name
        payment.status = "verified"
        payment.notes = deps.get_form_text("notes") or None

        current_user = deps.get_current_user()
        payment.created_by = current_user.username if current_user else None

        deps.db.session.add(payment)
        account.paket = package_name
        if period_end:
            account.periode_akhir = period_end
            deps.db.session.flush()
            deps.sync_user_activation_status(account)

        deps.db.session.commit()
        deps.log_activity_event(
            "INPUT_CLIENT_PAYMENT",
            details={
                "payment_id": payment.id,
                "target_user_id": account.id,
                "target_username": account.username,
                "amount": amount,
                "payment_date": payment.payment_date.isoformat(),
                "payment_time": payment.payment_time.strftime("%H:%M"),
                "payment_method": payment.payment_method,
                "payment_type": payment.payment_type,
                "event_name": payment.event_name,
            },
        )
        return build_payment_redirect(message="Payment client berhasil dicatat.", owner_user_id=owner_user_id)

    # Fungsi untuk menangani form tambah user baru.
    @admin_bp.route("/admin/users/new", methods=["GET", "POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk menambahkan user/client baru.
    def add_user():
        form_data = request.form if request.method == "POST" else {}

        if request.method == "POST":
            password = deps.get_form_text("password")
            nama = deps.get_form_text("nama")
            raw_no_hp_text = deps.get_form_text("no_hp")
            no_hp_text = deps.normalize_phone_number(raw_no_hp_text)
            no_hp = int(no_hp_text) if no_hp_text else None
            email = deps.get_form_text("email").lower()
            perusahaan = deps.get_form_text("perusahaan")
            alamat = deps.get_form_text("alamat")
            kota = deps.get_form_text("kota")
            provinsi = deps.get_form_text("provinsi")

            if raw_no_hp_text and not raw_no_hp_text.isdigit():
                error = "No HP harus berupa angka."
                return render_template(
                    "add_user.html",
                    user=deps.get_current_user_display_name(),
                    error=error,
                    form_data=form_data,
                )

            error = deps.validate_new_user_form(password, nama, no_hp_text, no_hp, email)
            if error:
                return render_template(
                    "add_user.html",
                    user=deps.get_current_user_display_name(),
                    error=error,
                    form_data=form_data,
                )

            try:
                username = deps.generate_client_username(nama, no_hp_text)
            except ValueError as exc:
                return render_template(
                    "add_user.html",
                    user=deps.get_current_user_display_name(),
                    error=str(exc),
                    form_data=form_data,
                )

            account = deps.User()
            account.username = username
            account.password = generate_password_hash(password)
            account.nama = nama
            account.no_hp = no_hp
            account.email = email
            account.perusahaan = perusahaan or None
            account.alamat = alamat or None
            account.kota = kota or None
            account.provinsi = provinsi or None
            account.tgl_daftar = date.today()
            account.role = deps.ROLE_USER
            deps.db.session.add(account)
            deps.db.session.commit()
            deps.log_activity_event(
                "CREATE_USER_ACCOUNT",
                details={
                    "target_user_id": account.id,
                    "target_username": account.username,
                    "target_email": account.email,
                },
            )
            return redirect("/users")

        return render_template(
            "add_user.html",
            user=deps.get_current_user_display_name(),
            error=None,
            form_data=form_data,
        )

    # Fungsi untuk menampilkan halaman pengelolaan akun admin.
    @admin_bp.route("/super-admin/admins")
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk menampilkan daftar admin.
    def manage_admins():
        return render_template(
            "manage_admins.html",
            admins=deps.get_manageable_admins(),
            user=deps.get_current_user_display_name(),
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )

    # Fungsi untuk menampilkan halaman setting WhatsApp super admin.
    @admin_bp.route("/super-admin/settings/whatsapp")
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk mengelola konfigurasi WhatsApp.
    def whatsapp_settings():
        selected_template_id = deps.parse_int(request.args.get("template_id"))
        context = deps.build_whatsapp_settings_context(
            selected_template_id=selected_template_id,
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
        return render_template("whatsapp_settings.html", **context)

    # Fungsi untuk menyimpan mode pengiriman WhatsApp.
    @admin_bp.route("/super-admin/settings/whatsapp/mode", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk memperbarui mode pengiriman WhatsApp.
    def update_whatsapp_mode():
        try:
            setting = deps.update_whatsapp_send_mode(request.form.get("send_mode", ""))
        except ValueError as exc:
            return build_whatsapp_settings_redirect(error=str(exc))

        deps.log_activity_event(
            "UPDATE_WHATSAPP_MODE",
            details={"send_mode": setting.send_mode},
        )
        return build_whatsapp_settings_redirect(message="Mode pengiriman WhatsApp berhasil disimpan.")

    # Fungsi untuk menyimpan nomor WhatsApp pengirim.
    @admin_bp.route("/super-admin/settings/whatsapp/phone", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk memperbarui nomor WhatsApp.
    def update_whatsapp_phone():
        try:
            setting = deps.update_whatsapp_phone(request.form.get("whatsapp_phone", ""))
        except ValueError as exc:
            return build_whatsapp_settings_redirect(error=str(exc))

        deps.log_activity_event(
            "UPDATE_WHATSAPP_PHONE",
            details={"phone_number": setting.phone_number},
        )
        return build_whatsapp_settings_redirect(message="Nomor WhatsApp berhasil disimpan.")

    # Fungsi untuk menyimpan token API WhatsApp.
    @admin_bp.route("/super-admin/settings/whatsapp/api-token", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk memperbarui API token WhatsApp.
    def update_whatsapp_api_token():
        try:
            deps.update_whatsapp_api_token(request.form.get("api_token", ""))
        except ValueError as exc:
            return build_whatsapp_settings_redirect(error=str(exc))

        deps.log_activity_event(
            "UPDATE_WHATSAPP_API_TOKEN",
            details={"api_token_updated": True},
        )
        return build_whatsapp_settings_redirect(message="API WhatsApp berhasil disimpan.")

    # Fungsi untuk menyimpan Phone Number ID WhatsApp API.
    @admin_bp.route("/super-admin/settings/whatsapp/api-phone-number-id", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk memperbarui Phone Number ID WhatsApp API.
    def update_whatsapp_api_phone_number_id():
        try:
            setting = deps.update_whatsapp_api_phone_number_id(request.form.get("api_phone_number_id", ""))
        except ValueError as exc:
            return build_whatsapp_settings_redirect(error=str(exc))

        deps.log_activity_event(
            "UPDATE_WHATSAPP_API_PHONE_NUMBER_ID",
            details={"api_phone_number_id": setting.api_phone_number_id},
        )
        return build_whatsapp_settings_redirect(message="Phone Number ID WhatsApp berhasil disimpan.")

    # Fungsi untuk menyimpan template pesan WhatsApp.
    @admin_bp.route("/super-admin/settings/whatsapp/template", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk menyimpan template pesan WhatsApp.
    def save_whatsapp_message_template():
        template_id = deps.parse_int(request.form.get("template_id"))
        try:
            template = deps.save_whatsapp_template(
                template_id,
                request.form.get("template_name", ""),
                request.form.get("template_body", ""),
            )
        except ValueError as exc:
            return build_whatsapp_settings_redirect(error=str(exc), template_id=template_id)

        deps.log_activity_event(
            "SAVE_WHATSAPP_TEMPLATE",
            details={"template_id": template.id, "template_name": template.name},
        )
        return build_whatsapp_settings_redirect(
            message="Template pesan WhatsApp berhasil disimpan.",
            template_id=template.id,
        )

    # Fungsi untuk menangani form tambah admin baru.
    @admin_bp.route("/super-admin/admins/new", methods=["GET", "POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk menambahkan akun admin baru.
    def add_admin():
        form_data = request.form if request.method == "POST" else {}

        if request.method == "POST":
            username = deps.get_form_text("username")
            password = deps.get_form_text("password")
            raw_no_hp_text = deps.get_form_text("no_hp")
            no_hp_text = deps.normalize_phone_number(raw_no_hp_text)
            no_hp = int(no_hp_text) if no_hp_text else None
            email = deps.get_form_text("email").lower()

            if raw_no_hp_text and not raw_no_hp_text.isdigit():
                error = "No HP harus berupa angka."
                return render_template(
                    "add_admin.html",
                    user=deps.get_current_user_display_name(),
                    error=error,
                    form_data=form_data,
                )

            error = deps.validate_admin_form(username, password, no_hp_text, no_hp, email)
            if error:
                return render_template(
                    "add_admin.html",
                    user=deps.get_current_user_display_name(),
                    error=error,
                    form_data=form_data,
                )

            account = deps.User()
            account.username = username
            account.password = generate_password_hash(password)
            account.no_hp = no_hp
            account.email = email
            account.role = deps.ROLE_ADMIN
            account.tgl_daftar = date.today()
            deps.db.session.add(account)
            deps.db.session.commit()
            deps.log_activity_event(
                "CREATE_ADMIN_ACCOUNT",
                details={
                    "target_user_id": account.id,
                    "target_username": account.username,
                    "target_email": account.email,
                },
            )
            return redirect(url_for("admin.manage_admins", message="Admin baru berhasil ditambahkan."))

        return render_template(
            "add_admin.html",
            user=deps.get_current_user_display_name(),
            error=None,
            form_data=form_data,
        )

    # Fungsi untuk mereset password admin dan menandai wajib ganti password.
    @admin_bp.route("/super-admin/admins/<int:admin_id>/reset", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk mengatur ulang password admin.
    def reset_admin_password(admin_id):
        account = deps.User.query.filter_by(id=admin_id, role=deps.ROLE_ADMIN).first()
        if not account:
            return deps.build_admins_redirect(error="Admin tidak ditemukan.")

        username = account.username
        deps.set_account_password(account, deps.DEFAULT_ADMIN_PASSWORD)
        account.must_reset_password = True
        deps.db.session.commit()
        deps.log_activity_event(
            "RESET_ADMIN_PASSWORD",
            details={
                "target_user_id": account.id,
                "target_username": username,
            },
        )
        return deps.build_admins_redirect(
            message=f"Password {username} berhasil direset ke {deps.DEFAULT_ADMIN_PASSWORD}."
        )

    # Fungsi untuk memblokir akses login admin.
    @admin_bp.route("/super-admin/admins/<int:admin_id>/block", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk memblokir login admin.
    def block_admin_account(admin_id):
        account = deps.User.query.filter_by(id=admin_id, role=deps.ROLE_ADMIN).first()
        if not account:
            return deps.build_admins_redirect(error="Admin tidak ditemukan.")

        current_user, error = validate_current_account_password()
        if error:
            return deps.build_admins_redirect(error=error)

        if account.is_blocked:
            return deps.build_admins_redirect(message=f"Admin {account.username} sudah diblokir.")

        deps.block_account_login(account)
        deps.db.session.commit()
        deps.log_activity_event(
            "BLOCK_ADMIN_ACCOUNT",
            details={
                "target_user_id": account.id,
                "target_username": account.username,
                "blocked_by": current_user.username if current_user else None,
            },
        )
        return deps.build_admins_redirect(message=f"Admin {account.username} berhasil diblokir.")

    # Fungsi untuk membuka blokir akses login admin.
    @admin_bp.route("/super-admin/admins/<int:admin_id>/unblock", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk membuka blokir login admin.
    def unblock_admin_account(admin_id):
        account = deps.User.query.filter_by(id=admin_id, role=deps.ROLE_ADMIN).first()
        if not account:
            return deps.build_admins_redirect(error="Admin tidak ditemukan.")

        current_user, error = validate_current_account_password()
        if error:
            return deps.build_admins_redirect(error=error)

        if not account.is_blocked:
            return deps.build_admins_redirect(message=f"Admin {account.username} sudah aktif.")

        deps.unblock_account_login(account)
        deps.db.session.commit()
        deps.log_activity_event(
            "UNBLOCK_ADMIN_ACCOUNT",
            details={
                "target_user_id": account.id,
                "target_username": account.username,
                "unblocked_by": current_user.username if current_user else None,
            },
        )
        return deps.build_admins_redirect(message=f"Admin {account.username} berhasil dibuka blokirnya.")

    # Fungsi untuk menghapus akun admin setelah password super admin valid.
    @admin_bp.route("/super-admin/admins/<int:admin_id>/delete", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk menghapus akun admin.
    def delete_admin(admin_id):
        account = deps.User.query.filter_by(id=admin_id, role=deps.ROLE_ADMIN).first()
        if not account:
            return deps.build_admins_redirect(error="Admin tidak ditemukan.")

        super_admin_password = request.form.get("super_admin_password", "").strip()
        current_user = deps.get_current_user()
        if not current_user or not deps.password_matches(current_user.password, super_admin_password):
            deps.log_auth_event(
                "AUTH_FAILED",
                "Gagal hapus admin: password Super Admin salah",
                account=current_user,
                level="WARN",
            )
            return deps.build_admins_redirect(error="Password Super Admin salah.")

        username = account.username
        target_user_id = account.id
        deps.db.session.delete(account)
        deps.db.session.commit()
        deps.log_activity_event(
            "DELETE_ADMIN_ACCOUNT",
            details={
                "target_user_id": target_user_id,
                "target_username": username,
            },
        )
        return deps.build_admins_redirect(message=f"Admin {username} berhasil dihapus.")

    # Fungsi untuk memperbarui detail profile user.
    @admin_bp.route("/admin/users/<int:user_id>/period", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk memperbarui profile client dari modal detail.
    def update_user_period(user_id):
        account = deps.User.query.filter_by(id=user_id, role=deps.ROLE_USER).first()
        if not account:
            return deps.build_users_redirect(error="Client tidak ditemukan")

        nama = deps.get_form_text("nama")
        raw_no_hp_text = deps.get_form_text("no_hp")
        no_hp_text = deps.normalize_phone_number(raw_no_hp_text)
        no_hp = int(no_hp_text) if no_hp_text else None
        email = deps.get_form_text("email").lower()
        perusahaan = deps.get_form_text("perusahaan")
        alamat = deps.get_form_text("alamat")
        kota = deps.get_form_text("kota")
        provinsi = deps.get_form_text("provinsi")

        if not nama or not any(character.isalpha() for character in nama):
            return deps.build_users_redirect(error="Nama wajib diisi.")

        if not all(character.isalpha() or character == " " for character in nama):
            return deps.build_users_redirect(error="Nama hanya boleh berisi huruf.")

        if raw_no_hp_text and not raw_no_hp_text.isdigit():
            return deps.build_users_redirect(error="No HP harus berupa angka.")

        if no_hp is None:
            return deps.build_users_redirect(error="No HP minimal 8 digit dan hanya boleh diawali 62, 08, atau 8.")

        if not email or "@" not in email or "." not in email:
            return deps.build_users_redirect(error="Format email tidak sesuai.")

        if len(nama) > 30:
            return deps.build_users_redirect(error="Nama maksimal 30 karakter.")

        if len(email) > 30:
            return deps.build_users_redirect(error="Email maksimal 30 karakter.")

        if len(perusahaan) > 50:
            return deps.build_users_redirect(error="Perusahaan maksimal 50 karakter.")

        if len(alamat) > 100:
            return deps.build_users_redirect(error="Alamat maksimal 100 karakter.")

        if len(kota) > 60:
            return deps.build_users_redirect(error="Kota maksimal 60 karakter.")

        if len(provinsi) > 50:
            return deps.build_users_redirect(error="Provinsi maksimal 50 karakter.")

        if deps.User.query.filter(deps.User.id != account.id, deps.User.no_hp == no_hp).first():
            return deps.build_users_redirect(error="No HP sudah terdaftar.")

        if deps.User.query.filter(deps.User.id != account.id, deps.User.email == email).first():
            return deps.build_users_redirect(error="Email sudah terdaftar.")

        old_profile = {
            "nama": account.nama,
            "no_hp": account.no_hp,
            "email": account.email,
            "perusahaan": account.perusahaan,
            "alamat": account.alamat,
            "kota": account.kota,
            "provinsi": account.provinsi,
        }
        account.nama = nama
        account.no_hp = no_hp
        account.email = email
        account.perusahaan = perusahaan or None
        account.alamat = alamat or None
        account.kota = kota or None
        account.provinsi = provinsi or None
        deps.sync_user_activation_status(account)
        deps.db.session.commit()
        deps.log_activity_event(
            "UPDATE_CLIENT_DETAIL",
            details={
                "target_user_id": account.id,
                "target_username": account.username,
                "old_profile": old_profile,
                "new_profile": {
                    "nama": account.nama,
                    "no_hp": account.no_hp,
                    "email": account.email,
                    "perusahaan": account.perusahaan,
                    "alamat": account.alamat,
                    "kota": account.kota,
                    "provinsi": account.provinsi,
                },
                "aktivasi": account.aktivasi,
            },
        )

        return deps.build_users_redirect(message="Detail client berhasil diperbarui.")

    # Fungsi untuk membuat atau memperbarui URL publik verifikasi kehadiran client.
    @admin_bp.route("/admin/users/<int:user_id>/attendance-url/generate", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk membuat ulang URL kehadiran user.
    def generate_user_attendance_url(user_id):
        account = deps.User.query.filter_by(id=user_id, role=deps.ROLE_USER).first()
        if not account:
            return jsonify({"status": "not_found", "message": "Client tidak ditemukan."}), 404
        return (
            jsonify(
                {
                    "status": "moved",
                    "message": "URL publik sekarang dibuat per staff melalui menu Staff client.",
                }
            ),
            410,
        )

    # Fungsi untuk mereset password user dan menandai wajib ganti password.
    @admin_bp.route("/admin/users/<int:user_id>/reset", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk mengatur ulang password user.
    def reset_user_password(user_id):
        account = deps.User.query.filter_by(id=user_id, role=deps.ROLE_USER).first()
        if not account:
            return deps.build_users_redirect(error="Client tidak ditemukan")

        display_name = account.nama or account.username
        deps.set_account_password(account, deps.DEFAULT_USER_RESET_PASSWORD)
        account.must_reset_password = True
        deps.db.session.commit()
        deps.log_activity_event(
            "RESET_USER_PASSWORD",
            details={
                "target_user_id": account.id,
                "target_username": account.username,
            },
        )
        return deps.build_users_redirect(
            message=f"Password {display_name} berhasil direset ke {deps.DEFAULT_USER_RESET_PASSWORD}."
        )

    # Fungsi untuk memblokir akses login client.
    @admin_bp.route("/admin/users/<int:user_id>/block", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk memblokir login client.
    def block_user_account(user_id):
        account = deps.User.query.filter_by(id=user_id, role=deps.ROLE_USER).first()
        if not account:
            return deps.build_users_redirect(error="Client tidak ditemukan")

        current_user, error = validate_current_account_password()
        if error:
            return deps.build_users_redirect(error=error)

        display_name = account.nama or account.username
        if account.is_blocked:
            return deps.build_users_redirect(message=f"Client {display_name} sudah diblokir.")

        deps.block_account_login(account)
        deps.db.session.commit()
        deps.log_activity_event(
            "BLOCK_CLIENT_ACCOUNT",
            details={
                "target_user_id": account.id,
                "target_username": account.username,
                "blocked_by": current_user.username if current_user else None,
            },
        )
        return deps.build_users_redirect(message=f"Client {display_name} berhasil diblokir.")

    # Fungsi untuk membuka blokir akses login client.
    @admin_bp.route("/admin/users/<int:user_id>/unblock", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk membuka blokir login client.
    def unblock_user_account(user_id):
        account = deps.User.query.filter_by(id=user_id, role=deps.ROLE_USER).first()
        if not account:
            return deps.build_users_redirect(error="Client tidak ditemukan")

        current_user, error = validate_current_account_password()
        if error:
            return deps.build_users_redirect(error=error)

        display_name = account.nama or account.username
        if not account.is_blocked:
            return deps.build_users_redirect(message=f"Client {display_name} sudah aktif.")

        deps.unblock_account_login(account)
        deps.db.session.commit()
        deps.log_activity_event(
            "UNBLOCK_CLIENT_ACCOUNT",
            details={
                "target_user_id": account.id,
                "target_username": account.username,
                "unblocked_by": current_user.username if current_user else None,
            },
        )
        return deps.build_users_redirect(message=f"Client {display_name} berhasil dibuka blokirnya.")

    # Fungsi untuk menangani upload Excel tamu oleh admin untuk user tertentu.
    @admin_bp.route("/admin/upload-guests", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk mengunggah data tamu dari sisi admin.
    def upload_guests():
        owner_user = deps.get_selected_owner_user(request.form)
        if not owner_user:
            context = deps.build_admin_guest_context(
                search="",
                page=1,
                per_page=10,
                selected_owner_user_id=None,
                sort_by="latest",
            )
            context["upload_warning"] = "Pilih client pemilik data tamu terlebih dahulu"
            return render_template("admin_guests.html", **context), 400

        try:
            file = deps.get_uploaded_file()
            preview = deps.build_guest_upload_preview(file, owner_user)
            saved_upload_path = deps.save_uploaded_guest_file(file, owner_user)
            deps.clear_pending_guest_upload()

            if preview["stats"]["duplicate_count"] == 0:
                deps.save_guest_rows(
                    owner_user=owner_user,
                    rows=preview["rows"],
                    duplicate_indexes=[],
                    include_duplicates=True,
                )
                context = deps.build_admin_guest_context(
                    search="",
                    page=1,
                    per_page=10,
                    selected_owner_user_id=owner_user.id,
                    sort_by="latest",
                )
                context["upload_result"] = preview
                deps.log_activity_event(
                    "UPLOAD_GUESTS_ADMIN",
                    details={
                        "owner_user_id": owner_user.id,
                        "owner_username": owner_user.username,
                        "stats": preview.get("stats", {}),
                        "duplicate_action": "none",
                        "upload_file_path": str(saved_upload_path),
                    },
                )
                return render_template("admin_guests.html", **context)

            pending_upload = deps.save_pending_guest_upload(owner_user, preview)
            deps.log_activity_event(
                "UPLOAD_GUESTS_ADMIN_PENDING",
                details={
                    "owner_user_id": owner_user.id,
                    "owner_username": owner_user.username,
                    "stats": preview.get("stats", {}),
                    "upload_file_path": str(saved_upload_path),
                },
            )
        except deps.UploadValidationError as exc:
            context = deps.build_admin_guest_context(
                search="",
                page=1,
                per_page=10,
                selected_owner_user_id=owner_user.id,
                sort_by="latest",
            )
            error = str(exc)
            if error == "Format data excel tidak sesuai":
                context["upload_warning"] = error
            else:
                context["upload_error"] = error
            return render_template("admin_guests.html", **context), 400

        context = deps.build_admin_guest_context(
            search="",
            page=1,
            per_page=10,
            selected_owner_user_id=owner_user.id,
            sort_by="latest",
        )
        context["pending_upload"] = pending_upload
        return render_template("admin_guests.html", **context)

    # Fungsi untuk menyimpan hasil upload tamu admin setelah konfirmasi duplicate.
    @admin_bp.route("/admin/upload-guests-confirm", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk mengonfirmasi hasil preview upload Excel dari sisi admin.
    def upload_guests_confirm():
        pending_upload = deps.load_pending_guest_upload()
        owner_user_id = deps.parse_int(pending_upload.get("owner_user_id") if pending_upload else None)
        owner_user = deps.User.query.filter_by(id=owner_user_id, role=deps.ROLE_USER).first()

        if not pending_upload or not owner_user:
            deps.clear_pending_guest_upload()
            context = deps.build_admin_guest_context(
                search="",
                page=1,
                per_page=10,
                selected_owner_user_id=owner_user_id,
                sort_by="latest",
            )
            context["upload_error"] = "Data upload sudah tidak tersedia. Silakan upload ulang."
            return render_template("admin_guests.html", **context)

        should_update_duplicates = request.form.get("include_duplicates") == "yes"
        if should_update_duplicates:
            saved_count = deps.replace_guest_rows(owner_user, pending_upload["rows"])
            message = f"{saved_count} data tamu berhasil diperbarui/disimpan."
        else:
            saved_count = deps.save_guest_rows(
                owner_user=owner_user,
                rows=pending_upload["rows"],
                duplicate_indexes=pending_upload.get("duplicate_indexes", []),
                include_duplicates=False,
            )
            message = f"{saved_count} data tamu berhasil disimpan."

        deps.clear_pending_guest_upload()
        deps.log_activity_event(
            "CONFIRM_GUEST_UPLOAD_ADMIN",
            details={
                "owner_user_id": owner_user.id,
                "owner_username": owner_user.username,
                "saved_count": saved_count,
                "include_duplicates": should_update_duplicates,
            },
        )
        return redirect(url_for("admin.view_guests", owner_user_id=owner_user.id, message=message))

    # Fungsi untuk menampilkan data tamu semua user bagi admin.
    @admin_bp.route("/admin/guests")
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk menampilkan data tamu dari sisi admin.
    def view_guests():
        search = request.args.get("search", "")
        page = deps.parse_int(request.args.get("page"), 1)
        per_page = deps.parse_int(request.args.get("per_page"), 10)
        sort_by = request.args.get("sort_by", "latest")
        selected_owner_user_id = deps.parse_int(request.args.get("owner_user_id"))

        context = deps.build_admin_guest_context(
            search=search,
            page=page,
            per_page=per_page,
            selected_owner_user_id=selected_owner_user_id,
            sort_by=sort_by,
        )
        context["message"] = request.args.get("message", "")
        return render_template("admin_guests.html", **context)

    # Fungsi untuk mengunduh data tamu admin dalam format Excel.
    @admin_bp.route("/admin/guests/download")
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk mengunduh data tamu ke Excel.
    def download_guests():
        search = request.args.get("search", "")
        sort_by = request.args.get("sort_by", "latest")
        selected_owner_user_id = deps.parse_int(request.args.get("owner_user_id"))
        owner_user = (
            deps.User.query.filter_by(id=selected_owner_user_id, role=deps.ROLE_USER).first()
            if selected_owner_user_id
            else None
        )
        if owner_user and not deps.is_owner_in_active_billing_period(owner_user):
            archive = deps.ensure_final_guest_backup(owner_user) or deps.get_latest_final_archive(owner_user)
            if not archive:
                return "Data backup final belum tersedia.", 404
            output = deps.build_final_archive_excel(owner_user, archive=archive)
            deps.log_activity_event(
                "DOWNLOAD_GUESTS_ADMIN_FINAL",
                details={
                    "owner_user_id": owner_user.id,
                    "archive_id": archive.id,
                    "csv_path": archive.csv_path,
                },
            )
            return send_file(
                output,
                as_attachment=True,
                download_name=deps.build_final_guest_export_filename(owner_user, archive=archive),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        query = deps.build_guest_query(
            search=search,
            owner_user_id=selected_owner_user_id,
            sort_by=sort_by,
        )

        rows = []
        for index, guest in enumerate(query.all(), start=1):
            rows.append(
                {
                    "no": index,
                    "nama": guest.nama,
                    "no_hp": guest.no_hp or "N/A",
                    "email": guest.email or "N/A",
                    "status": guest.status or deps.DEFAULT_GUEST_STATUS,
                    "kehadiran": deps.format_attendance_time(guest.kehadiran) or "N/A",
                    "verifikasi": guest.verified_by_staff_name or "N/A",
                }
            )
        deps.log_activity_event(
            "DOWNLOAD_GUESTS",
            details={
                "owner_user_id": selected_owner_user_id,
                "row_count": len(rows),
                "search": search,
                "sort_by": sort_by,
            },
        )

        output = BytesIO()
        columns = ["no", "nama", "no_hp", "email", "status", "kehadiran", "verifikasi"]
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(rows, columns=columns).to_excel(writer, index=False, sheet_name="Data Tamu")
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=deps.build_active_guest_export_filename(owner_user),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Fungsi untuk menghapus seluruh data tamu milik user yang dipilih admin.
    @admin_bp.route("/admin/delete-guests", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk menghapus semua data tamu milik user terpilih.
    def delete_guests():
        owner_user_id = deps.parse_int(request.form.get("owner_user_id"))

        if owner_user_id is None:
            return "Pilih client terlebih dahulu sebelum menghapus data tamu ❌"

        deleted_count = deps.Guests.query.filter_by(user_id=owner_user_id).delete()

        deps.db.session.commit()
        deps.log_activity_event(
            "DELETE_GUESTS_BULK",
            details={
                "owner_user_id": owner_user_id,
                "deleted_count": deleted_count,
            },
        )
        return redirect(f"/admin/guests?owner_user_id={owner_user_id}")

    return admin_bp
