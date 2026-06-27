from constants import (
    DEFAULT_GUEST_STATUS,
    DEFAULT_USER_RESET_PASSWORD,
    GUEST_SORT_OPTIONS,
    GUEST_STATUS_OPTIONS,
    PACKAGE_OPTIONS,
    PER_PAGE_OPTIONS,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    USER_SORT_OPTIONS,
)
from extensions import db
from flask import redirect, request, session, url_for
from models import BillingPayment, Guests, User
from services import account_service, attendance_service, auth_service, guest_service, staff_service
from sqlalchemy import String, func, or_


# Fungsi untuk menormalkan sorting tamu.
def normalize_guest_sort(sort_by):
    if sort_by in GUEST_SORT_OPTIONS:
        return sort_by
    return "latest"


# Fungsi untuk menormalkan sorting user.
def normalize_user_sort(sort_by):
    if sort_by in USER_SORT_OPTIONS:
        return sort_by
    return "name_asc"


# Fungsi untuk menormalkan jumlah per halaman.
def normalize_per_page(per_page):
    if per_page in PER_PAGE_OPTIONS:
        return per_page
    return 10


# Fungsi untuk mengambil tanggal minimal periode akhir.
def get_min_period_end_date():
    return account_service.get_min_period_end_date()


# Fungsi untuk membuat redirect user.
def build_users_redirect(message=None, error=None):
    query_args = {
        "search": request.form.get("search", ""),
        "page": request.form.get("page", 1),
        "per_page": request.form.get("per_page", 10),
        "sort_by": request.form.get("sort_by", "name_asc"),
    }
    if message:
        query_args["message"] = message
    if error:
        query_args["error"] = error
    return redirect(url_for("admin.users", **query_args))


# Fungsi untuk membuat redirect admin.
def build_admins_redirect(message=None, error=None):
    query_args = {}
    if message:
        query_args["message"] = message
    if error:
        query_args["error"] = error
    return redirect(url_for("admin.manage_admins", **query_args))


# Fungsi untuk membuat redirect tabel tamu.
def build_guest_table_redirect():
    query_args = {
        "search": request.form.get("search", ""),
        "page": request.form.get("page", 1),
        "per_page": request.form.get("per_page", 10),
        "sort_by": request.form.get("sort_by", "latest"),
    }

    if session.get("role") == ROLE_USER:
        return redirect(url_for("user.user_data", **query_args))

    owner_user_id = request.form.get("owner_user_id", "")
    if owner_user_id:
        query_args["owner_user_id"] = owner_user_id
    return redirect(url_for("admin.view_guests", **query_args))


# Fungsi untuk membuat redirect tabel tamu staff.
def build_staff_guest_table_redirect():
    query_args = {
        "search": request.form.get("search", ""),
        "page": request.form.get("page", 1),
        "per_page": request.form.get("per_page", 10),
        "sort_by": "attendance_desc",
    }
    return redirect(url_for("staff.staff_data", **query_args))


# Fungsi untuk mengambil tamu yang bisa diakses.
def get_accessible_guest(guest_id):
    current_user = auth_service.get_current_user()
    guest = db.session.get(Guests, guest_id)
    if not current_user or not guest:
        return None

    if current_user.role == ROLE_USER and guest.user_id != current_user.id:
        return None
    if current_user.role not in {ROLE_USER, ROLE_ADMIN, ROLE_SUPER_ADMIN}:
        return None
    return guest


# Fungsi untuk mengambil tamu staff yang bisa diakses.
def get_accessible_staff_guest(staff, guest_id):
    guest = db.session.get(Guests, guest_id)
    return get_accessible_staff_guest_from_object(staff, guest)


# Fungsi untuk mengambil tamu staff yang bisa diakses dari objek.
def get_accessible_staff_guest_from_object(staff, guest):
    if not staff or not guest:
        return None
    if guest.user_id != staff.owner_user_id:
        return None
    return guest


# Fungsi untuk membuat query tamu.
def build_guest_query(search="", owner_user_id=None, sort_by="latest"):
    query = Guests.query

    if owner_user_id is not None:
        query = query.filter(Guests.user_id == owner_user_id)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Guests.nama.ilike(search_pattern),
                Guests.no_hp.ilike(search_pattern),
                Guests.email.ilike(search_pattern),
                Guests.status.ilike(search_pattern),
            )
        )

    normalized_sort = normalize_guest_sort(sort_by)

    if normalized_sort == "name_asc":
        return query.order_by(func.lower(Guests.nama).asc(), Guests.id.desc())
    if normalized_sort == "name_desc":
        return query.order_by(func.lower(Guests.nama).desc(), Guests.id.desc())
    if normalized_sort == "attendance_desc":
        return query.order_by(Guests.kehadiran.is_(None).asc(), Guests.kehadiran.desc(), Guests.id.desc())
    return query.order_by(Guests.id.desc())


# Fungsi untuk membuat context paginasi tamu.
def build_guest_pagination_context(search, page, per_page, owner_user_id=None, sort_by="latest"):
    guest_service.clean_saved_guests_for_owner(owner_user_id)

    normalized_sort = normalize_guest_sort(sort_by)
    normalized_per_page = normalize_per_page(per_page)
    query = build_guest_query(
        search=search,
        owner_user_id=owner_user_id,
        sort_by=normalized_sort,
    )
    pagination = query.paginate(page=page, per_page=normalized_per_page, error_out=False)

    return {
        "guests": pagination.items,
        "pagination": pagination,
        "search": search,
        "per_page": normalized_per_page,
        "sort_by": normalized_sort,
        "total_guests": query.count(),
        "guest_status_options": GUEST_STATUS_OPTIONS,
        "default_guest_status": DEFAULT_GUEST_STATUS,
    }


# Fungsi untuk membuat context tamu user.
def build_user_guest_context(current_user, search, page, per_page, sort_by):
    is_client_active = account_service.calculate_account_activation_status(current_user)
    context = build_guest_pagination_context(
        search=search,
        page=page,
        per_page=per_page,
        owner_user_id=current_user.id,
        sort_by=sort_by,
    )
    context["user"] = account_service.get_user_display_name(current_user)
    context["layout_template"] = "user_layout.html"
    context["is_client_active"] = is_client_active
    context["allow_guest_upload"] = is_client_active
    context["allow_guest_mutations"] = is_client_active
    context["allow_guest_export"] = True
    context["show_guest_table"] = is_client_active
    context["data_endpoint"] = "user.user_data"
    context["add_guest_endpoint"] = "user.add_user_guest"
    context["status_endpoint"] = "guests.update_guest_status"
    context["delete_endpoint"] = "guests.delete_guest_row"
    return context


# Fungsi untuk membuat context tamu staff.
def build_staff_guest_context(staff, search, page, per_page, sort_by):
    owner_user = staff_service.get_staff_owner(staff)
    if not owner_user:
        raise RuntimeError("Owner staff tidak valid.")
    context = build_guest_pagination_context(
        search=search,
        page=page,
        per_page=per_page,
        owner_user_id=owner_user.id,
        sort_by="attendance_desc",
    )
    context["user"] = staff_service.get_staff_display_name(staff)
    context["staff"] = staff
    context["owner_user"] = owner_user
    context["layout_template"] = "staff_layout.html"
    context["allow_guest_upload"] = False
    context["show_guest_qr_column"] = False
    context["data_endpoint"] = "staff.staff_data"
    context["add_guest_endpoint"] = "staff.add_staff_guest"
    context["status_endpoint"] = "staff.update_staff_guest_status"
    context["delete_endpoint"] = "staff.delete_staff_guest_row"
    return context


# Fungsi untuk membuat context tamu admin.
def build_admin_guest_context(search, page, per_page, selected_owner_user_id=None, sort_by="latest"):
    context = build_guest_pagination_context(
        search=search,
        page=page,
        per_page=per_page,
        owner_user_id=selected_owner_user_id,
        sort_by=sort_by,
    )
    context["user"] = account_service.get_current_user_display_name()
    context["users"] = account_service.get_manageable_users()
    context["selected_owner_user_id"] = selected_owner_user_id or ""
    return context


# Fungsi untuk membuat query user.
def build_user_query(search="", sort_by="name_asc"):
    query = User.query.filter_by(role=ROLE_USER)
    search = search.strip()

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.nama.ilike(search_pattern),
                User.username.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.no_hp.cast(String).ilike(search_pattern),
            )
        )

    normalized_sort = normalize_user_sort(sort_by)
    if normalized_sort == "name_desc":
        return query.order_by(func.lower(User.nama).desc(), User.username.desc())
    return query.order_by(func.lower(User.nama).asc(), User.username.asc())


# Fungsi untuk membuat context daftar user.
def build_user_list_context(search, page, per_page, sort_by):
    normalized_sort = normalize_user_sort(sort_by)
    normalized_per_page = normalize_per_page(per_page)
    query = build_user_query(search=search, sort_by=normalized_sort)
    pagination = query.paginate(page=page, per_page=normalized_per_page, error_out=False)
    attendance_url_states = {
        account.id: {
            "generated_at_text": attendance_service.format_attendance_token_generated_at(
                account.attendance_token_generated_at
            ),
        }
        for account in pagination.items
    }
    latest_payment_period_starts = {}
    latest_payment_period_ends = {}
    latest_payment_event_names = {}
    latest_payment_package_names = {}
    for account in pagination.items:
        latest_payment = (
            BillingPayment.query.filter_by(user_id=account.id)
            .order_by(BillingPayment.payment_date.desc(), BillingPayment.id.desc())
            .first()
        )
        latest_payment_period_starts[account.id] = latest_payment.period_start if latest_payment else None
        latest_payment_period_ends[account.id] = latest_payment.period_end if latest_payment else None
        latest_payment_package_names[account.id] = latest_payment.package_name if latest_payment else None
        if latest_payment and getattr(latest_payment, "event_name", None):
            latest_payment_event_names[account.id] = latest_payment.event_name
        else:
            latest_payment_event_names[account.id] = None

    return {
        "users": pagination.items,
        "pagination": pagination,
        "search": search,
        "sort_by": normalized_sort,
        "per_page": normalized_per_page,
        "total_users": query.count(),
        "user": account_service.get_current_user_display_name(),
        "package_options": PACKAGE_OPTIONS,
        "min_period_end_date": get_min_period_end_date().isoformat(),
        "message": request.args.get("message", ""),
        "error": request.args.get("error", ""),
        "default_user_reset_password": DEFAULT_USER_RESET_PASSWORD,
        "attendance_url_states": attendance_url_states,
        "latest_payment_period_starts": latest_payment_period_starts,
        "latest_payment_period_ends": latest_payment_period_ends,
        "latest_payment_event_names": latest_payment_event_names,
        "latest_payment_package_names": latest_payment_package_names,
    }
